#!/usr/bin/env python3
"""AMP-003 TASK-003 — Idempotency concurrency stress (100 rounds × 20 workers)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.executor import IdempotentExecutor

WORKERS = 20
ROUNDS = 100


def _persist_json(work: Path, output: dict) -> str:
    p = work / "result.json"
    p.write_text(json.dumps(output), encoding="utf-8")
    return str(p)


class T003ConcurrencyStress(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_round(self, work: Path) -> int:
        inv = {"n": 0}
        lock = threading.Lock()
        ex = IdempotentExecutor(work)

        def worker():
            def _exec():
                with lock:
                    inv["n"] += 1
                return {"ok": True}

            ex.execute(
                job_id="t003",
                stage="factpack",
                entity_id="e1",
                inputs={"topic": "concurrent-stress"},
                execute_fn=_exec,
                validate_fn=lambda o: (True, "ok"),
                persist_fn=lambda o: _persist_json(work, o),
            )

        threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        return inv["n"]

    def test_100_rounds_20_workers_single_execution(self):
        duplicate_rounds = 0
        max_in_round = 0
        for i in range(ROUNDS):
            work = self.tmp / f"round-{i}"
            work.mkdir()
            n = self._run_round(work)
            max_in_round = max(max_in_round, n)
            if n != 1:
                duplicate_rounds += 1
        self.assertEqual(duplicate_rounds, 0, f"duplicates={duplicate_rounds} max={max_in_round}")
        self.assertEqual(max_in_round, 1)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(T003ConcurrencyStress)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"\nAMP-003 TASK-003 CONCURRENCY: {result.testsRun - failed} / {result.testsRun}")
    print(f"ROUNDS={ROUNDS} WORKERS={WORKERS} TOTAL_ATTEMPTS={ROUNDS * WORKERS}")
    if failed:
        raise SystemExit(1)
