#!/usr/bin/env python3
"""AMP-001 TASK-003 — Long/Short reserve isolation."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.intelligence.contracts import ContentFormat, TopicLifecycleStatus
from pipeline.intelligence.reserve_queue import load_reserve, save_reserve, update_reserve


class Task003IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cid = 96003

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_long_refresh_does_not_change_short(self):
        long_entries = [{"title": "Long Only", "canonical_topic": "long-only", "status": TopicLifecycleStatus.RESERVED.value, "rank": 1, "eligible": True, "score": {"total_score": 0.9, "hard_blocked": False}}]
        short_entries = [{"title": "Short Only", "canonical_topic": "short-only", "status": TopicLifecycleStatus.RESERVED.value, "rank": 1, "eligible": True, "score": {"total_score": 0.9, "hard_blocked": False}}]
        save_reserve(self.tmp, ContentFormat.LONG, long_entries, channel_id=self.cid)
        save_reserve(self.tmp, ContentFormat.SHORT, short_entries, channel_id=self.cid)

        new_long = [{"title": "Long Updated", "canonical_topic": "long-updated", "format": "LONG", "channel_id": self.cid, "eligible": True, "score": {"total_score": 0.95, "hard_blocked": False}}]
        update_reserve(self.tmp, ContentFormat.LONG, [{"candidate": new_long[0], "eligible": True, "score": new_long[0]["score"]}], channel_id=self.cid)

        short_after = load_reserve(self.tmp, ContentFormat.SHORT, channel_id=self.cid)
        long_after = load_reserve(self.tmp, ContentFormat.LONG, channel_id=self.cid)
        self.assertEqual(short_after[0]["canonical_topic"], "short-only")
        self.assertEqual(long_after[0]["canonical_topic"], "long-updated")


if __name__ == "__main__":
    unittest.main()
