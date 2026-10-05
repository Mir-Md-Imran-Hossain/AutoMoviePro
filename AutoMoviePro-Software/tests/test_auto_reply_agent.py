import os
import sys
import unittest
import time
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.auto_reply_agent import AutoReplyAgent, REPLIED_CACHE_FILE, REPLY_LOGS_FILE

class TestAutoReplyAgent(unittest.TestCase):
    def setUp(self):
        self.agent = AutoReplyAgent()

    def test_salam_detection(self):
        reply_bn = self.agent.generate_reply_text("Assalamu Alaikum brother, great video!", language="bn")
        self.assertIn("ওয়ালাইকুম আসসালাম", reply_bn)

        reply_en = self.agent.generate_reply_text("Salam! Nice content", language="en")
        self.assertIn("Walaikum Assalam", reply_en)

    def test_appreciation_and_questions(self):
        reply_nice = self.agent.generate_reply_text("খুব সুন্দর ভিডিও!", language="bn")
        self.assertIn("অনেক অনেক ধন্যবাদ", reply_nice)

        reply_q = self.agent.generate_reply_text("পরের পর্ব কবে আসবে?", language="bn")
        self.assertIn("চমৎকার প্রশ্ন করেছেন", reply_q)

    def test_process_comments_and_anti_duplicate(self):
        unique_id = f"test_cmt_{int(time.time()*1000)}"
        comments = [
            {"id": unique_id, "author": "User1", "text": "Very informative!"}
        ]

        # First run should reply
        res1 = self.agent.process_incoming_comments(
            platform="youtube",
            comments=comments,
            min_delay_sec=0.01,
            max_delay_sec=0.02
        )
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["comment_id"], unique_id)

        # Second run should skip since it is already replied
        res2 = self.agent.process_incoming_comments(
            platform="youtube",
            comments=comments,
            min_delay_sec=0.01,
            max_delay_sec=0.02
        )
        self.assertEqual(len(res2), 0)

    def test_logs_retrieval(self):
        logs = self.agent.get_logs(limit=10)
        self.assertIsInstance(logs, list)


if __name__ == "__main__":
    unittest.main()
