import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.captcha_handler import CaptchaHandler

class TestCaptchaHandler(unittest.TestCase):
    def setUp(self):
        self.handler = CaptchaHandler(confidence_threshold=0.80, allow_simulation=True)

    def test_captcha_detection(self):
        self.assertEqual(
            self.handler.detect_captcha(html_snippet="<div>g-recaptcha-response</div>"),
            "recaptcha"
        )
        self.assertEqual(
            self.handler.detect_captcha(html_snippet="Checking if you are human... cf-turnstile"),
            "cloudflare"
        )
        self.assertEqual(
            self.handler.detect_captcha(html_snippet="Please drag the puzzle slider"),
            "puzzle_slider"
        )
        self.assertIsNone(self.handler.detect_captcha(html_snippet="Normal page content"))

    def test_local_ai_solve(self):
        res = self.handler.solve_with_local_ai("cloudflare")
        self.assertTrue(res["solved"])
        self.assertGreaterEqual(res["confidence"], 0.80)

        res_puzzle = self.handler.solve_with_local_ai("puzzle_slider")
        self.assertTrue(res_puzzle["solved"])
        self.assertIn("slide_x_offset", res_puzzle)

    def test_mobile_app_fallback_and_remote_resolve(self):
        captcha_id = "test_cap_12345"
        dispatch = self.handler.dispatch_to_mobile_app(
            captcha_id=captcha_id,
            captcha_type="puzzle_slider",
            screenshot_b64="data:image/png;base64,sample_screen"
        )
        self.assertTrue(dispatch["ok"])
        self.assertEqual(dispatch["captcha_id"], captcha_id)

        # Status should be pending
        status = self.handler.get_challenge_status(captcha_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "pending_user_input")

        # Simulate mobile user resolving it
        resolved = self.handler.resolve_from_mobile(captcha_id, {"touch_x": 150, "touch_y": 200})
        self.assertTrue(resolved)

        updated_status = self.handler.get_challenge_status(captcha_id)
        self.assertEqual(updated_status["status"], "solved_remotely")
        self.assertEqual(updated_status["solution"]["touch_x"], 150)


if __name__ == "__main__":
    unittest.main()
