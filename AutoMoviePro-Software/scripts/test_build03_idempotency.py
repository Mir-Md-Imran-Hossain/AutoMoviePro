#!/usr/bin/env python3
"""BUILD-03 idempotency, checkpoint, resume, duplicate prevention tests (offline)."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.factpack_bridge import idempotent_build_fact_pack
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.idempotency.normalize import canonical_json, normalize_fingerprint_payload
from pipeline.idempotency.resume_resolver import ResumeResolver
from pipeline.idempotency.retry_policy import RetryClass, classify_error, retry_decision
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore
from pipeline.idempotency.unknown_result import reconcile_unknown


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_stable(self):
        a = compute_fingerprint(job_id="j1", stage="factpack", entity_id="e1", inputs={"topic": "X"})
        b = compute_fingerprint(job_id="j1", stage="factpack", entity_id="e1", inputs={"topic": "X"})
        self.assertEqual(a, b)

    def test_fingerprint_differs_on_input(self):
        a = compute_fingerprint(job_id="j1", stage="factpack", entity_id="e1", inputs={"topic": "A"})
        b = compute_fingerprint(job_id="j1", stage="factpack", entity_id="e1", inputs={"topic": "B"})
        self.assertNotEqual(a, b)

    def test_retry_same_fingerprint(self):
        base = {"job_id": "j", "stage": "s", "entity_id": "e", "inputs": {"x": 1}}
        fp1 = compute_fingerprint(**{k: v for k, v in base.items() if k != "inputs"}, inputs=base["inputs"])
        payload = dict(base)
        payload["attempt"] = 2
        normalized = normalize_fingerprint_payload(payload)
        self.assertNotIn("attempt", normalized)
        fp2 = compute_fingerprint(job_id="j", stage="s", entity_id="e", inputs={"x": 1})
        self.assertEqual(fp1, fp2)

    def test_normalization_key_order(self):
        p1 = canonical_json({"b": 2, "a": 1})
        p2 = canonical_json({"a": 1, "b": 2})
        self.assertEqual(p1, p2)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_claim_and_reuse(self):
        store = IdempotencyStore(self.tmp)
        rec = IdempotencyRecord(
            fingerprint="fp1",
            job_id="j",
            stage="factpack",
            entity_id="e",
        )
        claimed, _ = store.atomic_claim(rec)
        self.assertTrue(claimed)
        claimed2, existing = store.atomic_claim(rec)
        self.assertFalse(claimed2)
        self.assertIsNotNone(existing)
        existing.request_state = IdempotencyState.SUCCEEDED
        existing.result_reference = str(self.tmp / "out.json")
        (self.tmp / "out.json").write_text('{"ok": true}', encoding="utf-8")
        store.put(existing)
        claimed3, ex3 = store.atomic_claim(rec)
        self.assertFalse(claimed3)
        self.assertEqual(ex3.request_state, IdempotencyState.SUCCEEDED)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_execute_and_reuse(self):
        ex = IdempotentExecutor(self.tmp)
        counter = {"n": 0}

        def run():
            counter["n"] += 1
            return {"value": 42}

        def persist(o):
            p = self.tmp / "result.json"
            p.write_text(json.dumps(o), encoding="utf-8")
            return str(p)

        r1 = ex.execute(
            job_id="j1",
            stage="factpack",
            entity_id="e1",
            inputs={"topic": "Test"},
            execute_fn=run,
            validate_fn=lambda o: (True, "ok"),
            persist_fn=persist,
        )
        self.assertEqual(r1.action, "execute")
        self.assertEqual(counter["n"], 1)

        def run2():
            counter["n"] += 1
            return {"value": 99}

        r2 = ex.execute(
            job_id="j1",
            stage="factpack",
            entity_id="e1",
            inputs={"topic": "Test"},
            execute_fn=run2,
        )
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(counter["n"], 1)

    def test_duplicate_prevented_concurrent(self):
        ex = IdempotentExecutor(self.tmp, stale_sec=9999)
        started = threading.Event()
        proceed = threading.Event()
        counter = {"n": 0}

        def slow_run():
            counter["n"] += 1
            started.set()
            proceed.wait(timeout=5)
            return {"done": True}

        results = []

        def worker():
            r = ex.execute(
                job_id="j1",
                stage="factpack",
                entity_id="e1",
                inputs={"topic": "Concurrent"},
                execute_fn=slow_run,
                validate_fn=lambda o: (True, "ok"),
            )
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        started.wait(timeout=2)
        t2.start()
        time.sleep(0.2)
        proceed.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(counter["n"], 1)
        self.assertIn("duplicate_prevented", results)


class RetryTests(unittest.TestCase):
    def test_non_retryable(self):
        d = retry_decision(exc=ValueError("invalid configuration"), attempt=1, max_attempts=3)
        self.assertFalse(d.should_retry)
        self.assertEqual(d.retry_class, RetryClass.NON_RETRYABLE)

    def test_bounded_retry(self):
        d = retry_decision(exc=RuntimeError("503 temporary"), attempt=3, max_attempts=3)
        self.assertFalse(d.should_retry)

    def test_unknown_timeout(self):
        self.assertEqual(classify_error(TimeoutError("response lost")), RetryClass.UNKNOWN)


class CheckpointResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resume_skips_completed(self):
        ex = IdempotentExecutor(self.tmp)
        stages = ["topic", "research", "factpack", "script"]
        for stage in ["topic", "research", "factpack"]:
            out_path = self.tmp / f"{stage}.json"

            def persist(o, p=out_path):
                p.write_text(json.dumps(o), encoding="utf-8")
                return str(p)

            ex.execute(
                job_id="job-x",
                stage=stage,
                entity_id="e",
                inputs={"s": stage},
                execute_fn=lambda s=stage: {"stage": s},
                validate_fn=lambda o: (True, "ok"),
                persist_fn=persist,
            )

        resolver = ResumeResolver(self.tmp, stage_order=stages)
        plan = resolver.resolve("job-x")
        self.assertEqual(plan.resume_from, "script")
        self.assertEqual(plan.completed_stages, ["topic", "research", "factpack"])


class FactPackPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_double_run_zero_duplicate_generation(self):
        r1 = idempotent_build_fact_pack(self.tmp, job_id="j", topic="Chernobyl", notes="Reactor four.")
        r2 = idempotent_build_fact_pack(self.tmp, job_id="j", topic="Chernobyl", notes="Reactor four.")
        self.assertEqual(r1["execution_count"], 1)
        self.assertEqual(r2["execution_count"], 0)
        self.assertEqual(r2["action"], "reuse")
        self.assertIn("claims", r2["fact_pack"])


class UnknownResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reconcile_from_local_artifact(self):
        store = IdempotencyStore(self.tmp)
        art = self.tmp / "video.mp4"
        art.write_bytes(b"x" * 2000)
        rec = IdempotencyRecord(
            fingerprint="fp",
            job_id="j",
            stage="visual",
            entity_id="s1",
            request_state=IdempotencyState.UNKNOWN,
        )
        store.put(rec)
        result = reconcile_unknown(store, rec, local_artifact_path=str(art))
        self.assertTrue(result.resolved)
        self.assertEqual(result.new_state, IdempotencyState.SUCCEEDED)


class CrashResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_crash_after_result_reuses(self):
        ex = IdempotentExecutor(self.tmp)
        out_file = self.tmp / "factpack" / "e.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps({"claims": [{"id": "1", "claim": "x"}]}), encoding="utf-8")
        fp = compute_fingerprint(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "T"})
        store = ex.store
        rec = IdempotencyRecord(
            fingerprint=fp,
            job_id="j",
            stage="factpack",
            entity_id="e",
            request_state=IdempotencyState.SUCCEEDED,
            result_reference=str(out_file),
            result_hash=hash_text(str(out_file)),
        )
        store.put(rec)
        cp_store = CheckpointStore(self.tmp / "checkpoints")
        from domain.enums import JobState
        from domain.execution import Checkpoint

        cp_store.save_checkpoint(
            Checkpoint(
                job_id="j",
                stage="factpack",
                state=JobState.VERIFYING,
                input_hash=fp,
                output_hash=rec.result_hash,
                metadata={"result_reference": str(out_file)},
            )
        )
        counter = {"n": 0}

        def run():
            counter["n"] += 1
            return {}

        r = ex.execute(job_id="j", stage="factpack", entity_id="e", inputs={"topic": "T"}, execute_fn=run)
        self.assertEqual(r.action, "reuse")
        self.assertEqual(counter["n"], 0)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for case in (
        FingerprintTests,
        StoreTests,
        ExecutorTests,
        RetryTests,
        CheckpointResumeTests,
        FactPackPilotTests,
        UnknownResultTests,
        CrashResumeTests,
    ):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
