import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from user_app_service import UserAppService

class TestUserApp(unittest.TestCase):
    def setUp(self):
        self.service = UserAppService()

    def test_status_telemetry_disconnected(self):
        """When PC is disconnected, no fake youtube URL or fake connected state is returned."""
        status = self.service.get_software_status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["system_state"], "disconnected")
        self.assertIsNone(status.get("last_published_url"))

    def test_remote_captcha_resolution_disconnected(self):
        """When PC is disconnected, submit_remote_solution must NOT return fake ok=True."""
        res = self.service.submit_remote_solution("c_test_123", {"offset_x": 142})
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "PC_CONNECTION_FAILED")

    def test_online_slider_puzzle_and_upload_resume(self):
        """Tests live slider puzzle reception, mobile resolution, and real-time upload resumption."""
        mock_status = {
            "ok": True,
            "connected": True,
            "system_state": "active",
            "videos_generated_today": 3,
            "videos_published_today": 2,
            "last_published_url": "https://www.youtube.com/shorts/real_vid_123"
        }
        mock_captcha = {
            "has_captcha": True,
            "captcha_id": "cap_slider_999",
            "type": "puzzle_slider",
            "prompt": "পাজল স্লাইডারটি টেনে মিলিয়ে ক্যাপচাটি সমাধান করুন।"
        }
        mock_solve_res = {
            "ok": True,
            "captcha_id": "cap_slider_999",
            "upload_resumed": True,
            "message": "মোবাইল থেকে ক্যাপচা সমাধান সফল! পিসিতে আপলোড চালু হয়েছে।"
        }
        mock_resume_res = {
            "ok": True,
            "upload_resumed": True,
            "message": "পিসিতে সোশ্যাল মিডিয়া ভিডিও আপলোড রিয়েল-টাইমে চালু হয়েছে।"
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            # 1. Test status
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_status).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            status = self.service.get_software_status()
            self.assertTrue(status["connected"])
            self.assertEqual(status["last_published_url"], "https://www.youtube.com/shorts/real_vid_123")

            # 2. Test live slider puzzle detection
            mock_resp.read.return_value = json.dumps(mock_captcha).encode("utf-8")
            cap = self.service.fetch_pending_captcha()
            self.assertTrue(cap["has_captcha"])
            self.assertEqual(cap["type"], "puzzle_slider")

            # 3. Test drag solving & real-time upload resume
            mock_resp.read.side_effect = [
                json.dumps(mock_solve_res).encode("utf-8"),
                json.dumps(mock_resume_res).encode("utf-8")
            ]
            solve_res = self.service.submit_remote_solution("cap_slider_999", {"x": 180, "y": 120})
            self.assertTrue(solve_res["ok"])
            self.assertIn("মোবাইল থেকে ক্যাপচা সমাধান সফল", solve_res["message"])


if __name__ == "__main__":
    unittest.main()
