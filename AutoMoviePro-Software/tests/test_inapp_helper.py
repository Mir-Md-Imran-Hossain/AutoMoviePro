import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.agent.inapp_helper import InAppHelperAgent

class TestInAppHelper(unittest.TestCase):
    def setUp(self):
        self.helper = InAppHelperAgent()

    def test_tooltip_info(self):
        tip_bn = self.helper.get_tooltip_info("api_fallback", language="bn")
        self.assertIn("ব্যাকআপ", tip_bn["title"])
        self.assertIn("কোটা", tip_bn["description"])

        tip_en = self.helper.get_tooltip_info("intel_qsv", language="en")
        self.assertIn("Intel", tip_en["title"])

    def test_natural_language_queries(self):
        res_upload = self.helper.handle_user_query("আমার আপলোড করা ভিডিও দেখাও", language="bn")
        self.assertEqual(res_upload["intent"], "view_upload_history")
        self.assertEqual(res_upload["action"], "open_screen")

        res_pending = self.helper.handle_user_query("কেন দেরি হচ্ছে?", language="bn")
        self.assertEqual(res_pending["intent"], "explain_status")

        res_api = self.helper.handle_user_query("How to get my API key?", language="en")
        self.assertEqual(res_api["intent"], "api_help")
        self.assertEqual(res_api["target_screen"], "api_hub")

    def test_database_history_and_pending_queries(self):
        from app import db as store
        store.init_db()
        with store.db() as conn:
            conn.execute(
                """
                INSERT INTO jobs (title, video_type, platform, upload_status, error, created_at, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("টেস্ট ইসলামিক রহস্য পর্ব ১", "short", "YouTube", "done", None, "2026-08-05 14:00:00", "2026-08-05 14:05:00")
            )

        res_date = self.helper.handle_user_query("2026-08-05 তারিখে কি কি ভিডিও আপলোড হয়েছে?", language="bn")
        self.assertEqual(res_date["intent"], "view_upload_history")
        self.assertIn("টেস্ট ইসলামিক রহস্য পর্ব ১", res_date["reply"])
        self.assertGreaterEqual(res_date["records_count"], 1)

        res_status = self.helper.handle_user_query("ভিডিও কেন আটকে আছে?", language="bn")
        self.assertEqual(res_status["intent"], "explain_status")


if __name__ == "__main__":
    unittest.main()
