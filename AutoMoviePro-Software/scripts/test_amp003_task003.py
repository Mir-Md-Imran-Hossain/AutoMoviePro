#!/usr/bin/env python3
"""AMP-003 TASK-003 — Global Idempotency + Checkpoint + Recovery."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import BUILD03_FINGERPRINT_VERSION, compute_fingerprint, hash_text
from pipeline.idempotency.identity import AttemptIdentity, ExecutionIdentity, JobIdentity, StageIdentity
from pipeline.idempotency.normalize import canonical_json, normalize_fingerprint_payload
from pipeline.idempotency.retry_policy import RetryClass, retry_decision
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore
from pipeline.idempotency.unknown_result import reconcile_unknown


def _persist_json(tmp: Path, output: dict) -> str:
    p = tmp / "result.json"
    p.write_text(json.dumps(output), encoding="utf-8")
    return str(p)


class T003IdentityTests(unittest.TestCase):
    def test_01_identity_hierarchy_distinct(self):
        job = JobIdentity(job_id="job-1")
        stage = StageIdentity(job_id="job-1", stage="factpack", entity_id="e1")
        fp = compute_fingerprint(job_id="job-1", stage="factpack", entity_id="e1", inputs={"x": 1})
        attempt = AttemptIdentity(job_id="job-1", stage="factpack", fingerprint=fp, attempt_number=2)
        execution = ExecutionIdentity.from_parts("job-1", "factpack", "e1", fp)
        self.assertEqual(job.job_id, stage.job_id)
        self.assertEqual(attempt.fingerprint, execution.fingerprint)
        self.assertIn("job-1", execution.execution_key)

    def test_02_retry_same_fingerprint_not_new_generation(self):
        fp1 = compute_fingerprint(job_id="j", stage="s", entity_id="e", inputs={"a": 1})
        fp2 = compute_fingerprint(job_id="j", stage="s", entity_id="e", inputs={"a": 1})
        self.assertEqual(fp1, fp2)
        normalized = normalize_fingerprint_payload({"attempt": 3, "job_id": "j"})
        self.assertNotIn("attempt", normalized)


class T003FingerprintTests(unittest.TestCase):
    def test_03_fingerprint_deterministic(self):
        a = compute_fingerprint(job_id="j", stage="visual", entity_id="s0", inputs={"prompt": "test"})
        b = compute_fingerprint(job_id="j", stage="visual", entity_id="s0", inputs={"prompt": "test"})
        self.assertEqual(a, b)

    def test_04_fingerprint_excludes_volatile(self):
        payload = {"job_id": "j", "timestamp": 123, "attempt": 2, "inputs": {"k": "v"}}
        norm = normalize_fingerprint_payload(payload)
        self.assertNotIn("timestamp", norm)
        self.assertNotIn("attempt", norm)

    def test_05_fingerprint_version_present(self):
        fp = compute_fingerprint(job_id="j", stage="s", entity_id="e", inputs={})
        self.assertEqual(len(fp), 64)
        blob = canonical_json({"fingerprint_version": BUILD03_FINGERPRINT_VERSION})
        self.assertIn("build03", blob)


class T003AtomicClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_06_claimed_false_never_executes(self):
        ex = IdempotentExecutor(self.tmp, stale_sec=9999)
        started = threading.Event()
        proceed = threading.Event()
        counter = {"n": 0}

        def slow_run():
            counter["n"] += 1
            started.set()
            proceed.wait(timeout=5)
            return {"ok": True}

        def worker(results: list):
            r = ex.execute(
                job_id="j",
                stage="factpack",
                entity_id="e",
                inputs={"topic": "claim-test"},
                execute_fn=slow_run,
                validate_fn=lambda o: (True, "ok"),
            )
            results.append(r.action)

        results: list[str] = []
        t1 = threading.Thread(target=worker, args=(results,))
        t2 = threading.Thread(target=worker, args=(results,))
        t1.start()
        started.wait(timeout=2)
        t2.start()
        time.sleep(0.15)
        proceed.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(counter["n"], 1)
        self.assertIn("duplicate_prevented", results)

    def test_07_atomic_claim_single_owner(self):
        store = IdempotencyStore(self.tmp)
        rec = IdempotencyRecord(fingerprint="fp", job_id="j", stage="s", entity_id="e")
        c1, _ = store.atomic_claim(rec, worker_id="w1")
        c2, prior = store.atomic_claim(rec, worker_id="w2")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(prior.request_state, IdempotencyState.IN_PROGRESS)


class T003WaitReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_08_wait_then_reuse(self):
        ex = IdempotentExecutor(self.tmp, stale_sec=9999)
        gate = threading.Event()
        done = threading.Event()
        counter = {"n": 0}

        def slow_run():
            counter["n"] += 1
            gate.set()
            time.sleep(0.3)
            return {"v": 1}

        actions: list[str] = []

        def worker():
            r = ex.execute(
                job_id="j",
                stage="factpack",
                entity_id="e",
                inputs={"topic": "wait-reuse"},
                execute_fn=slow_run,
                validate_fn=lambda o: (True, "ok"),
                persist_fn=lambda o: _persist_json(self.tmp, o),
            )
            actions.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        gate.wait(timeout=2)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(counter["n"], 1)
        self.assertIn("reuse", actions)


class T003StaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_09_stale_in_progress_reclaimed(self):
        idem_dir = self.tmp / "idempotency"
        store = IdempotencyStore(idem_dir, stale_sec=0.01)
        fp = compute_fingerprint(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "stale"})
        stale = IdempotencyRecord(
            fingerprint=fp,
            job_id="j",
            stage="factpack",
            entity_id="e",
            request_state=IdempotencyState.IN_PROGRESS,
            updated_at=time.time() - 60,
        )
        stale.updated_at = time.time() - 60
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(
            json.dumps({"records": {fp: stale.to_dict()}, "metrics": {}}),
            encoding="utf-8",
        )
        store._reload()
        inv = {"n": 0}
        ex = IdempotentExecutor(self.tmp, stale_sec=0.01)
        r = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "stale"},
            execute_fn=lambda: inv.__setitem__("n", inv["n"] + 1) or {"ok": True},
            validate_fn=lambda o: (True, "ok"),
            persist_fn=lambda o: _persist_json(self.tmp, o),
        )
        self.assertEqual(r.action, "execute")
        self.assertEqual(inv["n"], 1)
        metrics = ex.store.metrics()
        self.assertGreaterEqual(int(metrics.get("stale_reclaim_count") or 0), 1)


class T003UnknownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_10_unknown_reconcile_from_artifact(self):
        store = IdempotencyStore(self.tmp)
        art = self.tmp / "out.mp4"
        art.write_bytes(b"x" * 3000)
        h = hash_text("placeholder")
        rec = IdempotencyRecord(
            fingerprint="fp",
            job_id="j",
            stage="visual",
            entity_id="s1",
            request_state=IdempotencyState.UNKNOWN,
            result_reference=str(art),
        )
        store.put(rec)
        result = reconcile_unknown(store, rec, local_artifact_path=str(art))
        self.assertTrue(result.resolved)
        self.assertEqual(result.new_state, IdempotencyState.SUCCEEDED)

    def test_11_unknown_no_blind_execute(self):
        ex = IdempotentExecutor(self.tmp)
        fp = compute_fingerprint(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "unk"})
        store = ex.store
        store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id="j",
                stage="factpack",
                entity_id="e",
                request_state=IdempotencyState.UNKNOWN,
            )
        )
        inv = {"n": 0}
        r = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "unk"},
            execute_fn=lambda: inv.__setitem__("n", inv["n"] + 1),
        )
        self.assertEqual(r.action, "unknown")
        self.assertEqual(inv["n"], 0)


class T003CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_12_checkpoint_after_success(self):
        ex = IdempotentExecutor(self.tmp)
        ex.execute(
            job_id="job-cp",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "cp"},
            execute_fn=lambda: {"ok": True},
            validate_fn=lambda o: (True, "ok"),
            persist_fn=lambda o: _persist_json(self.tmp, o),
        )
        cps = ex.checkpoint_store.latest_for_job("job-cp")
        self.assertGreaterEqual(len(cps), 1)
        self.assertEqual(cps[-1]["stage"], "factpack")

    def test_13_corrupt_checkpoint_recovery(self):
        cp_dir = self.tmp / "checkpoints"
        cp_dir.mkdir()
        (cp_dir / "CHECKPOINTS.json").write_text("{bad", encoding="utf-8")
        store = CheckpointStore(cp_dir)
        data = store._load()
        self.assertEqual(data.get("checkpoints"), [])
        self.assertTrue((cp_dir / "CHECKPOINTS.corrupt").is_file() or (cp_dir / "CHECKPOINTS.json.corrupt").is_file())


class T003RetryTests(unittest.TestCase):
    def test_14_retry_budget_terminal(self):
        d = retry_decision(exc=RuntimeError("503 temporary"), attempt=3, max_attempts=3)
        self.assertFalse(d.should_retry)

    def test_15_non_retryable(self):
        d = retry_decision(exc=ValueError("invalid configuration"), attempt=1, max_attempts=3)
        self.assertEqual(d.retry_class, RetryClass.NON_RETRYABLE)

    def test_16_unknown_timeout(self):
        d = retry_decision(exc=TimeoutError("response lost"), attempt=1, max_attempts=3)
        self.assertEqual(d.retry_class, RetryClass.UNKNOWN)


class T003CacheValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_17_corrupt_cache_rejected(self):
        ex = IdempotentExecutor(self.tmp)
        fp = compute_fingerprint(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "badcache"})
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        ex.store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id="j",
                stage="factpack",
                entity_id="e",
                request_state=IdempotencyState.SUCCEEDED,
                result_reference=str(bad),
            )
        )
        inv = {"n": 0}
        r = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "badcache"},
            execute_fn=lambda: inv.__setitem__("n", inv["n"] + 1) or {"fresh": True},
            validate_fn=lambda o: (True, "ok"),
            persist_fn=lambda o: _persist_json(self.tmp, o),
        )
        self.assertEqual(r.action, "execute")
        self.assertEqual(inv["n"], 1)


class T003BypassTests(unittest.TestCase):
    def test_18_video_pipeline_uses_idempotent_bridges(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_plan_niche_production", src)
        self.assertIn("idempotent_synthesize_narration", src)
        self.assertIn("idempotent_compose_final_video", src)

    def test_19_legacy_fallback_documented(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("legacy plan_niche_production", src)


class T003CrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_20_crash_after_persist_reuses(self):
        ex = IdempotentExecutor(self.tmp)
        out = self.tmp / "fact.json"
        out.write_text(json.dumps({"claims": []}), encoding="utf-8")
        fp = compute_fingerprint(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "T"})
        ex.store.put(
            IdempotencyRecord(
                fingerprint=fp,
                job_id="j",
                stage="factpack",
                entity_id="e",
                request_state=IdempotencyState.SUCCEEDED,
                result_reference=str(out),
                result_hash=hash_text(str(out)),
            )
        )
        inv = {"n": 0}
        r = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "T"},
            execute_fn=lambda: inv.__setitem__("n", inv["n"] + 1),
        )
        self.assertEqual(r.action, "reuse")
        self.assertEqual(inv["n"], 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\nAMP-003 TASK-003 TESTS: {passed} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
