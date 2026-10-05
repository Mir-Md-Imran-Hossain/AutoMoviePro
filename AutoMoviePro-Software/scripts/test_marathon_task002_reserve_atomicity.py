#!/usr/bin/env python3
"""AMP-001 TASK-002 — Multi-worker reserve consume atomicity acceptance tests."""
from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.contracts import ContentFormat, TopicLifecycleStatus
from pipeline.intelligence.reserve_queue import consume_top, load_reserve, save_reserve

WORKERS = 20
ROUNDS = 100
TOPICS_PER_ROUND = 15


class Task002ReserveAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_reserve(self, work: Path, count: int) -> None:
        entries = [
            {
                "title": f"Topic {i}",
                "canonical_topic": f"topic-{i}",
                "status": TopicLifecycleStatus.RESERVED.value,
                "rank": i + 1,
            }
            for i in range(count)
        ]
        save_reserve(work, ContentFormat.LONG, entries, channel_id=0)

    def _run_consume_round(self, work: Path) -> tuple[int, int]:
        """Return (duplicate_consumptions, total_consumed)."""
        self._seed_reserve(work, TOPICS_PER_ROUND)
        consumed: list[str] = []
        lock = threading.Lock()

        def worker():
            top, _ = consume_top(work, ContentFormat.LONG, channel_id=0)
            if top is not None:
                key = str(top.get("canonical_topic") or top.get("title") or "")
                with lock:
                    consumed.append(key)

        threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        unique = set(consumed)
        duplicate_count = len(consumed) - len(unique)
        return duplicate_count, len(consumed)

    def test_concurrent_consume_no_duplicates_100_rounds(self):
        """20 workers × 100 rounds — same reserve item never consumed twice."""
        total_duplicates = 0
        for i in range(ROUNDS):
            work = self.tmp / f"round-{i}"
            work.mkdir()
            dup, got = self._run_consume_round(work)
            total_duplicates += dup
            self.assertEqual(dup, 0, f"round {i}: duplicate consumption detected (got={got})")
            self.assertEqual(got, TOPICS_PER_ROUND, f"round {i}: expected {TOPICS_PER_ROUND} unique consumes")
            remaining = load_reserve(work, ContentFormat.LONG, channel_id=0)
            self.assertEqual(len(remaining), 0, f"round {i}: reserve should be empty after consume")

        self.assertEqual(total_duplicates, 0)

    def test_concurrent_writers_no_corruption(self):
        """Concurrent save_reserve must not corrupt JSON."""
        work = self.tmp / "writers"
        work.mkdir()
        errors: list[str] = []
        lock = threading.Lock()

        def writer(i: int):
            try:
                entries = [
                    {
                        "title": f"W{i}-{j}",
                        "canonical_topic": f"w{i}-{j}",
                        "status": TopicLifecycleStatus.RESERVED.value,
                        "rank": j + 1,
                    }
                    for j in range(5)
                ]
                save_reserve(work, ContentFormat.LONG, entries, channel_id=0)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(errors, [])
        loaded = load_reserve(work, ContentFormat.LONG, channel_id=0)
        self.assertIsInstance(loaded, list)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Task002ReserveAtomicityTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\nAMP-001 TASK-002 TESTS: {result.testsRun - len(result.failures) - len(result.errors)} / {result.testsRun}")
    if not result.wasSuccessful():
        raise SystemExit(1)
