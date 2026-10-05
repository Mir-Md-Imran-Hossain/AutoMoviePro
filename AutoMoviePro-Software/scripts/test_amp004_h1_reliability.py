"""AMP004-H1 — Production reliability & concurrency hardening tests.

Mock/local only. Paid APIs = 0.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pipeline.generation_cache import GenerationCache
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import compute_fingerprint
from pipeline.idempotency.fs_lock import normalize_lock_key, thread_lock_for
from pipeline.idempotency.mock_visual_provider import MockVisualProvider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyStore
from pipeline.idempotency.visual_runtime import execute_visual_request
from pipeline.intelligence.contracts import ContentFormat
from pipeline.intelligence.reserve_queue import consume_top, save_reserve
from scripts.test_build04a_visual_runtime import _spec


def _worker_claim(work: str, fp_inputs: dict, counter_file: str) -> str:
    """OS-process worker: attempt idempotent execute once."""
    work_p = Path(work)
    ex = IdempotentExecutor(work_p)

    def _exec():
        # count provider entries via atomic file append
        with open(counter_file, "a", encoding="utf-8") as fh:
            fh.write("1\n")
        time.sleep(0.05)
        out = work_p / "result.json"
        out.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return {"ok": True}

    r = ex.execute(
        job_id="h1job",
        stage="factpack",
        entity_id="e1",
        inputs=fp_inputs,
        execute_fn=_exec,
        validate_fn=lambda o: (True, "ok"),
        persist_fn=lambda o: str(work_p / "result.json"),
    )
    return r.action


def _worker_reserve(work: str, channel_id: int, out_file: str) -> None:
    top, _ = consume_top(Path(work), ContentFormat.SHORT, channel_id=channel_id, language="en")
    if top:
        with open(out_file, "a", encoding="utf-8") as fh:
            fh.write(str(top.get("canonical_topic") or top.get("title") or "") + "\n")


class H1ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_h1_"))

    def test_01_normalize_strips_extended_path(self):
        p = self.tmp / "idempotency" / "IDEMPOTENCY.json"
        a = normalize_lock_key(p)
        b = normalize_lock_key(Path("\\\\?\\" + str(p.resolve()).lstrip("\\\\?\\")))
        # both should collapse to same identity
        self.assertEqual(a, b)
        self.assertFalse(a.startswith("\\\\?\\"))

    def test_02_thread_lock_same_for_extended_prefix(self):
        p = self.tmp / "x.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
        k1 = thread_lock_for(p)
        extended = Path("\\\\?\\" + str(p.resolve()))
        k2 = thread_lock_for(extended)
        self.assertIs(k1, k2)

    def test_03_def011_stress_50_rounds(self):
        fails = 0
        for i in range(50):
            work = self.tmp / f"r{i}"
            work.mkdir()
            spec = _spec()
            out = work / "conc.mp4"
            pl = threading.Lock()
            calls = {"n": 0}
            results: list[str] = []

            def gen():
                if not pl.acquire(blocking=False):
                    raise AssertionError("duplicate provider invocation")
                calls["n"] += 1
                time.sleep(0.03)
                return MockVisualProvider().generate(out_path=out)

            def worker():
                r = execute_visual_request(work, spec, out, provider_fn=gen)
                results.append(r.action)

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join(timeout=15)
            t2.join(timeout=15)
            if calls["n"] != 1 or any(a not in ("execute", "reuse", "duplicate_prevented") for a in results):
                fails += 1
        self.assertEqual(fails, 0, f"DEF-011 still reproduces fails={fails}/50")

    def test_04_thread_failure_then_retry_bounded(self):
        work = self.tmp / "failround"
        work.mkdir()
        inv = {"n": 0}
        ex = IdempotentExecutor(work)

        def fail_once():
            inv["n"] += 1
            if inv["n"] == 1:
                raise ConnectionError("transient")
            p = work / "ok.json"
            p.write_text("{}", encoding="utf-8")
            return {"ok": True}

        r1 = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "t"},
            execute_fn=fail_once,
            validate_fn=lambda o: (True, "ok"),
            persist_fn=lambda o: str(work / "ok.json"),
        )
        self.assertEqual(r1.action, "failed")
        self.assertEqual(inv["n"], 1)

        r2 = ex.execute(
            job_id="j",
            stage="factpack",
            entity_id="e",
            inputs={"topic": "t"},
            execute_fn=fail_once,
            validate_fn=lambda o: (True, "ok"),
            persist_fn=lambda o: str(work / "ok.json"),
        )
        self.assertEqual(r2.action, "execute")
        self.assertEqual(inv["n"], 2)

    def test_05_process_single_claim(self):
        work = self.tmp / "proc"
        work.mkdir()
        counter = str(work / "counter.txt")
        Path(counter).write_text("", encoding="utf-8")
        inputs = {"topic": "proc-h1"}
        ctx = mp.get_context("spawn")
        procs = [
            ctx.Process(target=_worker_claim, args=(str(work), inputs, counter)) for _ in range(4)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            self.assertEqual(p.exitcode, 0)
        lines = Path(counter).read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1, f"provider entries={lines}")

    def test_06_process_reserve_one_consume(self):
        work = self.tmp / "res"
        work.mkdir()
        entries = [
            {
                "canonical_topic": "Only Topic",
                "title": "Only Topic",
                "topic_id": "t1",
                "status": "RESERVED",
                "score": 1.0,
                "rank": 1,
            },
            {
                "canonical_topic": "Second",
                "title": "Second",
                "topic_id": "t2",
                "status": "RESERVED",
                "score": 0.5,
                "rank": 2,
            },
        ]
        save_reserve(work, ContentFormat.SHORT, entries, channel_id=0, language="en")
        out = str(work / "consumed.txt")
        Path(out).write_text("", encoding="utf-8")
        ctx = mp.get_context("spawn")
        procs = [
            ctx.Process(target=_worker_reserve, args=(str(work), 0, out)) for _ in range(4)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
        topics = [ln for ln in Path(out).read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(topics.count("Only Topic"), 1)

    def test_07_checkpoint_concurrent_no_lost_update(self):
        cps = CheckpointStore(self.tmp / "cps")
        errors: list[str] = []

        def writer(i: int):
            try:
                cp = cps.create_checkpoint(
                    job_id="j1",
                    stage=f"stage-{i % 3}",
                    input_hash=f"in{i}",
                    output_hash=f"out{i}",
                    result_reference=f"ref{i}",
                )
                cps.save_checkpoint(cp)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        data = json.loads((self.tmp / "cps" / "CHECKPOINTS.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data.get("checkpoints") or []), 20)

    def test_08_generation_cache_concurrent(self):
        cache = GenerationCache(self.tmp / "gc")
        key = "k1"
        art = self.tmp / "gc" / "a.mp4"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_bytes(b"\x00" * 2000)

        def w():
            cache.request_create(key, artifact=art)
            cache.commit(key, art)

        threads = [threading.Thread(target=w) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        raw = json.loads((self.tmp / "gc" / "GENERATION_CACHE.json").read_text(encoding="utf-8"))
        self.assertIn(key, raw.get("entries") or {})
        self.assertEqual((raw["entries"][key]).get("status"), "ready")

    def test_09_build04a_test06_100_loops(self):
        suite_fails = 0
        for _ in range(100):
            case = __import__("scripts.test_build04a_visual_runtime", fromlist=["Build04AVisualTests"]).Build04AVisualTests(
                "test_06_concurrent_duplicate"
            )
            case.setUp()
            try:
                case.test_06_concurrent_duplicate()
            except Exception:
                suite_fails += 1
            finally:
                # best-effort cleanup handled by OS temp
                pass
        self.assertEqual(suite_fails, 0, f"test_06 failed {suite_fails}/100")


if __name__ == "__main__":
    unittest.main()
