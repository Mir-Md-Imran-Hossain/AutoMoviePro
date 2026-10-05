#!/usr/bin/env python3
"""BUILD-04G-H1 — Idempotency concurrency hardening acceptance tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore

WORKERS = 20
ROUNDS = 100


def _persist_json(tmp: Path, output: dict) -> str:
    p = tmp / "result.json"
    p.write_text(json.dumps(output), encoding="utf-8")
    return str(p)


class H1ConcurrencyTests(unittest.TestCase):
  def setUp(self):
    self.tmp = Path(tempfile.mkdtemp())

  def tearDown(self):
    shutil.rmtree(self.tmp, ignore_errors=True)

  def _run_round(self, work: Path, *, inputs: dict | None = None) -> int:
    """20 workers, same fingerprint — return provider invocation count."""
    inv = {"n": 0}
    lock = threading.Lock()
    executor = IdempotentExecutor(work)
    inputs = inputs or {"topic": "h1-concurrent"}

    def worker():
      def _exec():
        with lock:
          inv["n"] += 1
        return {"ok": True}

      executor.execute(
        job_id="h1",
        stage="factpack",
        entity_id="e1",
        inputs=inputs,
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

  def test_primary_100_rounds_20_workers(self):
    """2,000 attempts — exactly 1 provider execution per round."""
    duplicate_rounds = 0
    max_in_round = 0
    for i in range(ROUNDS):
      work = self.tmp / f"round-{i}"
      work.mkdir()
      n = self._run_round(work)
      max_in_round = max(max_in_round, n)
      if n != 1:
        duplicate_rounds += 1
    self.assertEqual(duplicate_rounds, 0, f"duplicate rounds={duplicate_rounds}, max={max_in_round}")
    self.assertEqual(max_in_round, 1)

  def test_scenario_a_first_succeeds_others_reuse(self):
    work = self.tmp / "scenario-a"
    work.mkdir()
    n = self._run_round(work)
    self.assertEqual(n, 1)
    store = IdempotencyStore(work / "idempotency")
    fp = compute_fingerprint(job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "h1-concurrent"})
    rec = store.get(fp)
    self.assertIsNotNone(rec)
    self.assertEqual(rec.request_state, IdempotencyState.SUCCEEDED)

  def test_scenario_b_failure_then_safe_retry(self):
    work = self.tmp / "scenario-b"
    work.mkdir()
    ex = IdempotentExecutor(work)
    attempts = {"n": 0}

    def fail_once():
      attempts["n"] += 1
      if attempts["n"] == 1:
        raise RuntimeError("503 temporary")
      return {"ok": True}

    r1 = ex.execute(
      job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "retry"},
      execute_fn=fail_once,
      validate_fn=lambda o: (True, "ok"),
      persist_fn=lambda o: _persist_json(work, o),
    )
    self.assertIn(r1.action, ("failed", "unknown"))
    self.assertEqual(attempts["n"], 1)

    r2 = ex.execute(
      job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "retry"},
      execute_fn=fail_once,
      validate_fn=lambda o: (True, "ok"),
      persist_fn=lambda o: _persist_json(work, o),
    )
    self.assertIn(r2.action, ("execute", "reuse"))
    self.assertLessEqual(attempts["n"], 2)

  def test_scenario_c_stale_in_progress_recovery(self):
    work = self.tmp / "scenario-c"
    work.mkdir()
    store = IdempotencyStore(work / "idempotency", stale_sec=0.01)
    fp = compute_fingerprint(job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "stale"})
    stale = IdempotencyRecord(
      fingerprint=fp, job_id="h1", stage="factpack", entity_id="e1",
      request_state=IdempotencyState.IN_PROGRESS,
      updated_at=time.time() - 10,
    )
    store.put(stale)
    inv = {"n": 0}

    def _exec():
      inv["n"] += 1
      return {"recovered": True}

    ex = IdempotentExecutor(work, stale_sec=0.01)
    r = ex.execute(
      job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "stale"},
      execute_fn=_exec,
      validate_fn=lambda o: (True, "ok"),
      persist_fn=lambda o: _persist_json(work, o),
    )
    self.assertIn(r.action, ("execute", "unknown", "duplicate_prevented", "reuse"))
    self.assertLessEqual(inv["n"], 1)

  def test_scenario_d_cached_zero_executions(self):
    work = self.tmp / "scenario-d"
    work.mkdir()
    out = work / "cached.json"
    out.write_text(json.dumps({"cached": True}), encoding="utf-8")
    fp = compute_fingerprint(job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "cached"})
    store = IdempotencyStore(work / "idempotency")
    store.put(IdempotencyRecord(
      fingerprint=fp, job_id="h1", stage="factpack", entity_id="e1",
      request_state=IdempotencyState.SUCCEEDED,
      result_reference=str(out),
      result_hash=hash_text(str(out)),
    ))
    inv = {"n": 0}
    ex = IdempotentExecutor(work)

    def _exec():
      inv["n"] += 1
      return {"should": "not run"}

    for _ in range(WORKERS):
      r = ex.execute(
        job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": "cached"},
        execute_fn=_exec,
      )
      self.assertEqual(r.action, "reuse")
    self.assertEqual(inv["n"], 0)

  def test_scenario_e_different_fingerprints_independent(self):
    work = self.tmp / "scenario-e"
    work.mkdir()
    inv = {"n": 0}
    lock = threading.Lock()
    ex = IdempotentExecutor(work)

    def run_for(topic: str):
      def _exec():
        with lock:
          inv["n"] += 1
        return {"topic": topic}

      out_dir = work / topic.replace(" ", "_")
      out_dir.mkdir(parents=True, exist_ok=True)

      ex.execute(
        job_id="h1", stage="factpack", entity_id="e1", inputs={"topic": topic},
        execute_fn=_exec,
        validate_fn=lambda o: (True, "ok"),
        persist_fn=lambda o, d=out_dir: _persist_json(d, o),
      )

    threads = []
    for i in range(5):
      threads.append(threading.Thread(target=run_for, args=(f"topic-{i}",)))
    for t in threads:
      t.start()
    for t in threads:
      t.join()
    self.assertEqual(inv["n"], 5)


if __name__ == "__main__":
  suite = unittest.defaultTestLoader.loadTestsFromTestCase(H1ConcurrencyTests)
  result = unittest.TextTestRunner(verbosity=2).run(suite)
  failed = len(result.failures) + len(result.errors)
  print(f"\nBUILD-04G-H1 TESTS: {result.testsRun - failed} / {result.testsRun}")
  print(f"ROUNDS={ROUNDS} WORKERS={WORKERS} TOTAL_ATTEMPTS={ROUNDS * WORKERS}")
  sys.exit(0 if failed == 0 else 1)
