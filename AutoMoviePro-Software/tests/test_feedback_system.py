import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.feedback.feedback_system import FeedbackSystem

class TestFeedbackSystem(unittest.TestCase):
    def setUp(self):
        self.system = FeedbackSystem()

    def test_urgent_bug_ticket(self):
        res = self.system.submit_ticket(
            user_id="usr_001",
            category="urgent_bug",
            title="Video render fails on scene 4",
            description="Intel QSV error when encoding scene 4"
        )
        self.assertTrue(res["ok"])
        token = res["token"]
        self.assertTrue(token.startswith("TK-"))
        self.assertEqual(res["sla_hours"], 72)

        ticket = self.system.get_ticket_status(token)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["category"], "urgent_bug")
        self.assertEqual(ticket["status"], "open")

    def test_review_eligibility(self):
        # 2 hours (7200s) should not be eligible
        self.assertFalse(self.system.check_review_eligibility(7200))
        # 3.5 hours (12600s) should be eligible
        self.assertTrue(self.system.check_review_eligibility(12600))

    def test_submit_review_showcase(self):
        # 5 star review
        res_5 = self.system.submit_review(
            user_id="usr_002",
            user_name="Mr. Kamal",
            rating=5,
            review_text="অসাধারণ সফটওয়্যার! প্রতিদিন ৪টি ভিডিও তৈরি হচ্ছে।"
        )
        self.assertTrue(res_5["ok"])
        self.assertTrue(res_5["showcase_eligible"])

        # 3 star review
        res_3 = self.system.submit_review(
            user_id="usr_003",
            user_name="Mr. John",
            rating=3,
            review_text="Good but needs more templates"
        )
        self.assertTrue(res_3["ok"])
        self.assertFalse(res_3["showcase_eligible"])


if __name__ == "__main__":
    unittest.main()
