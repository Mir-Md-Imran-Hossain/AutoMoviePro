import os
import sys
import io
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.captcha_handler import CaptchaHandler


def _make_test_puzzle_image() -> bytes:
    img = Image.new("RGB", (300, 150), color=(220, 220, 220))
    draw = ImageDraw.Draw(img)
    draw.rectangle([130, 30, 160, 120], fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCaptchaHandler(unittest.TestCase):
    def setUp(self):
        self.handler = CaptchaHandler(confidence_threshold=0.80, allow_simulation=False)

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

    def test_local_ai_solve_with_real_image(self):
        """Verifies real vision AI solves puzzle slider with authentic image bytes."""
        puzzle_bytes = _make_test_puzzle_image()
        res_puzzle = self.handler.solve_with_local_ai("puzzle_slider", image_bytes=puzzle_bytes)
        self.assertTrue(res_puzzle["solved"])
        self.assertIn("slide_x_offset", res_puzzle)
        self.assertGreaterEqual(res_puzzle["confidence"], 0.80)
        self.assertEqual(res_puzzle["method"], "vision_pil_edge_detection")

    def test_local_ai_solve_without_context_refuses_fake_pass(self):
        """Verifies that without challenge images or Turnstile tokens, fake passes are refused."""
        res_cf = self.handler.solve_with_local_ai("cloudflare")
        self.assertFalse(res_cf["solved"])
        self.assertEqual(res_cf["error"], "BROWSER_DOM_INTERACTION_REQUIRED")

        res_no_img = self.handler.solve_with_local_ai("puzzle_slider")
        self.assertFalse(res_no_img["solved"])
        self.assertEqual(res_no_img["error"], "VISION_ANALYSIS_FAILED")

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

        # Mobile user resolves it authentically
        resolved = self.handler.resolve_from_mobile(captcha_id, {"touch_x": 150, "touch_y": 200})
        self.assertTrue(resolved)

        updated_status = self.handler.get_challenge_status(captcha_id)
        self.assertEqual(updated_status["status"], "solved_remotely")
        self.assertEqual(updated_status["solution"]["touch_x"], 150)


if __name__ == "__main__":
    unittest.main()
