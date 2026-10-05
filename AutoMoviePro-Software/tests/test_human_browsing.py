import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.human_browsing_engine import HumanBrowsingEngine

class TestHumanBrowsing(unittest.TestCase):
    def setUp(self):
        self.engine = HumanBrowsingEngine(start_hour=8, end_hour=24, max_daily_subs=3)

    def test_allowed_hours(self):
        # 10 AM should be allowed
        self.assertTrue(self.engine.is_within_allowed_hours(hour=10))
        # 11 PM (23:00) should be allowed
        self.assertTrue(self.engine.is_within_allowed_hours(hour=23))
        # 2 AM should NOT be allowed
        self.assertFalse(self.engine.is_within_allowed_hours(hour=2))
        # 7 AM should NOT be allowed
        self.assertFalse(self.engine.is_within_allowed_hours(hour=7))

    def test_daily_sub_limit_enforcement(self):
        test_date = "2026-09-21"
        # Reset counter for test
        self.engine.increment_counter("subs", date_str=test_date)
        self.engine.increment_counter("subs", date_str=test_date)
        self.engine.increment_counter("subs", date_str=test_date)

        # Since max_daily_subs is 3, can_subscribe_today should return False
        self.assertFalse(self.engine.can_subscribe_today(date_str=test_date))

    def test_session_execution(self):
        session = self.engine.simulate_watch_session(
            niche="Islamic Stories",
            forced_channel_type="type_a",
            mock_fast_mode=True
        )
        self.assertEqual(session["channel_type"], "type_a")
        self.assertEqual(session["status"], "completed")
        self.assertIn("Islamic Stories", session["topic"])

        # Check recent sessions retrieval
        recent = self.engine.get_recent_sessions(limit=5)
        self.assertIsInstance(recent, list)
        self.assertGreater(len(recent), 0)


if __name__ == "__main__":
    unittest.main()
