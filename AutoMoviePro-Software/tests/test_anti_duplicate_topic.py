"""Comprehensive unit & integration tests for Step 4: Anti-Duplicate Topic Research & Dual Storage.
Standard library unittest implementation (zero external dependency).

Tests:
- Segregated short vs. long topic repositories
- Exact duplicate detection and rejection
- Similarity / token overlap duplicate detection
- Historical duplicate tracking
- Quality scoring by local agent
- Status updates (approved -> used)
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.anti_duplicate_topic import AntiDuplicateTopicEngine


class TestAntiDuplicateTopic(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = AntiDuplicateTopicEngine(storage_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_segregated_storage_short_and_long(self):
        """Validates that shorts and longs are strictly saved in separate databases."""
        res_short = self.engine.add_topic(
            title="5 Shocking AI Tools You Must Know",
            niche="Technology & AI Innovations",
            video_format="short",
            seo_keywords=["ai tools", "technology", "chatgpt"],
        )
        self.assertTrue(res_short["ok"])

        res_long = self.engine.add_topic(
            title="The Complete History of Artificial Intelligence Documented",
            niche="Technology & AI Innovations",
            video_format="long",
            seo_keywords=["ai history", "alan turing", "deep learning"],
        )
        self.assertTrue(res_long["ok"])

        shorts = self.engine.list_topics("short")
        longs = self.engine.list_topics("long")
        all_topics = self.engine.list_topics()

        self.assertEqual(len(shorts), 1)
        self.assertEqual(shorts[0]["title"], "5 Shocking AI Tools You Must Know")
        self.assertEqual(len(longs), 1)
        self.assertEqual(longs[0]["title"], "The Complete History of Artificial Intelligence Documented")
        self.assertEqual(len(all_topics), 2)

    def test_exact_duplicate_rejection(self):
        """Prevents adding the exact same topic title twice."""
        res1 = self.engine.add_topic(
            title="Lessons from Surah Al-Kahf for Modern Times",
            niche="Islamic History & Moral Stories",
            video_format="short",
        )
        self.assertTrue(res1["ok"])

        # Attempt duplicate
        res2 = self.engine.add_topic(
            title="Lessons from Surah Al-Kahf for Modern Times",
            niche="Islamic History & Moral Stories",
            video_format="short",
        )
        self.assertFalse(res2["ok"])
        self.assertEqual(res2["error"], "duplicate_topic")

    def test_similarity_duplicate_rejection(self):
        """Detects and rejects re-worded duplicate topics using Jaccard token overlap."""
        res1 = self.engine.add_topic(
            title="Engineering Secrets of the Bronze Age Collapse",
            niche="World History & Geopolitics",
            video_format="long",
        )
        self.assertTrue(res1["ok"])

        # Very similar title re-phrased
        res2 = self.engine.add_topic(
            title="The Secrets of Engineering in Bronze Age Collapse Revealed",
            niche="World History & Geopolitics",
            video_format="long",
        )
        self.assertFalse(res2["ok"])
        self.assertEqual(res2["error"], "duplicate_topic")
        self.assertIn("similarity", res2["reason"].lower())

    def test_topic_quality_score_and_status(self):
        """Verifies local agent quality evaluation and usage status transitions."""
        res = self.engine.add_topic(
            title="Why 90% of Startups Fail in Year One",
            niche="Business, Finance & Entrepreneurship",
            video_format="short",
            seo_keywords=["startups", "finance", "business tips"],
        )
        self.assertTrue(res["ok"])
        topic = res["topic"]
        self.assertGreaterEqual(topic["quality_score"], 80.0)
        self.assertEqual(topic["status"], "approved")

        # Mark used
        marked = self.engine.mark_topic_used(topic["id"])
        self.assertTrue(marked)

        shorts = self.engine.list_topics("short")
        self.assertEqual(shorts[0]["status"], "used")


if __name__ == "__main__":
    unittest.main()
