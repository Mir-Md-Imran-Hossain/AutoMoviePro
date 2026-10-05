"""T003 — Topic scoring unit tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.channel_dna import from_channel_row
from pipeline.topic_scoring import rank_topics, score_topic, select_best_topic


class TopicScoringTests(unittest.TestCase):
    def setUp(self):
        self.dna = from_channel_row({"id": 1, "niche": "Ancient Civilizations"})

    def test_gadget_fails_hard(self):
        r = score_topic("iPhone 15 Pro review", self.dna, trend_score=0.99, trend_evidence="LIVE")
        self.assertFalse(r["passed"])

    def test_evergreen_can_pass_without_live_trend(self):
        r = score_topic(
            "Lost Library of Alexandria",
            self.dna,
            trend_score=0.2,
            trend_evidence="UNVERIFIED",
            evergreen_verified=True,
            freshness=0.8,
        )
        self.assertTrue(r["passed"], r)
        self.assertGreaterEqual(r["total"], 0.45)

    def test_unverified_low_trend_fails(self):
        r = score_topic(
            "Some Vague Thing",
            self.dna,
            trend_score=0.1,
            trend_evidence="UNVERIFIED",
            evergreen_verified=False,
            freshness=0.5,
        )
        self.assertFalse(r["passed"])

    def test_duplicate_penalty(self):
        ok = score_topic(
            "Göbekli Tepe pillars",
            self.dna,
            evergreen_verified=True,
            freshness=0.9,
            is_duplicate=False,
        )
        dup = score_topic(
            "Göbekli Tepe pillars",
            self.dna,
            evergreen_verified=True,
            freshness=0.9,
            is_duplicate=True,
        )
        self.assertTrue(ok["passed"])
        self.assertFalse(dup["passed"])
        self.assertLess(dup["total"], ok["total"])

    def test_rank_and_select(self):
        cands = [
            {"topic": "iPhone 16", "trend_score": 0.99, "trend_evidence": "LIVE"},
            {
                "topic": "Terracotta Army warriors",
                "trend_score": 0.3,
                "evergreen_verified": True,
                "freshness": 0.85,
            },
            {
                "topic": "Lost Library of Alexandria",
                "trend_score": 0.4,
                "evergreen_verified": True,
                "freshness": 0.9,
            },
        ]
        ranked = rank_topics(cands, self.dna)
        self.assertTrue(all(r["topic"] != "iPhone 16" or not r["passed"] for r in ranked))
        best = select_best_topic(cands, dna=self.dna)
        self.assertTrue(best["passed"])
        self.assertNotIn("iphone", best["topic"].lower())


if __name__ == "__main__":
    unittest.main()
