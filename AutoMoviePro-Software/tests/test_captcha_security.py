import os
import sys
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from fastapi.testclient import TestClient
from pipeline.captcha_handler import CaptchaHandler
from app.mobile_bridge import MobileBridge
from app.main import app


def _generate_test_puzzle_image() -> bytes:
    """Generates a test image with a high-contrast dark slot for slider gap testing."""
    img = Image.new("RGB", (300, 150), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    # Draw a distinct dark vertical notch representing the puzzle slot
    draw.rectangle([120, 30, 150, 120], fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCaptchaSecurity(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.bridge = MobileBridge.get_instance()
        self.bridge.clear_captcha_challenge()

    def tearDown(self):
        self.bridge.clear_captcha_challenge()
        if "AMP_ALLOW_CAPTCHA_SIMULATION" in os.environ:
            del os.environ["AMP_ALLOW_CAPTCHA_SIMULATION"]
        if "AMP_FORCE_CAPTCHA_PROD" in os.environ:
            del os.environ["AMP_FORCE_CAPTCHA_PROD"]

    def test_production_simulation_endpoint_strictly_forbidden(self):
        """In production, /api/mobile/captcha/simulate must return HTTP 403 Forbidden."""
        os.environ["AMP_FORCE_CAPTCHA_PROD"] = "1"
        os.environ["AMP_ALLOW_CAPTCHA_SIMULATION"] = "0"

        with patch("app.config.is_production_runtime", return_value=True):
            resp = self.client.post("/api/mobile/captcha/simulate", json={
                "type": "recaptcha",
                "captcha_id": "test_fake_inject"
            })
            self.assertEqual(resp.status_code, 403)
            data = resp.json()
            self.assertFalse(data["ok"])
            self.assertEqual(data["error"], "SIMULATION_DISABLED_IN_PRODUCTION")

    def test_dev_mode_allows_simulation_endpoint(self):
        """In dev/test mode with simulation enabled, /api/mobile/captcha/simulate succeeds."""
        os.environ["AMP_ALLOW_CAPTCHA_SIMULATION"] = "1"

        with patch("app.config.is_production_runtime", return_value=False):
            resp = self.client.post("/api/mobile/captcha/simulate", json={
                "type": "puzzle_slider",
                "captcha_id": "sim_cap_001"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertTrue(data.get("simulated"))

    def test_production_local_ai_refuses_mock_token(self):
        """In production, CaptchaHandler NEVER emits mock_token_pass for reCAPTCHA."""
        handler = CaptchaHandler(allow_simulation=False)
        with patch("pipeline.captcha_handler._is_production", return_value=True):
            res = handler.solve_with_local_ai("recaptcha")
            self.assertFalse(res["solved"])
            self.assertEqual(res["confidence"], 0.0)
            self.assertEqual(res.get("error"), "MOCK_TOKEN_FORBIDDEN_IN_PRODUCTION")
            self.assertNotIn("mock_token_pass", str(res))

    def test_production_local_ai_cloudfare_and_puzzle_require_context(self):
        """In production, Cloudflare and image-less puzzle sliders cannot be trivially faked."""
        handler = CaptchaHandler(allow_simulation=False)
        with patch("pipeline.captcha_handler._is_production", return_value=True):
            cf_res = handler.solve_with_local_ai("cloudflare")
            self.assertFalse(cf_res["solved"])
            self.assertEqual(cf_res.get("error"), "BROWSER_DOM_INTERACTION_REQUIRED")

            puzzle_no_img = handler.solve_with_local_ai("puzzle_slider")
            self.assertFalse(puzzle_no_img["solved"])
            self.assertEqual(puzzle_no_img.get("error"), "VISION_ANALYSIS_FAILED")

    def test_puzzle_slider_solves_with_real_image_analysis(self):
        """Puzzle slider with real image bytes uses PIL edge analysis to find slot."""
        handler = CaptchaHandler(allow_simulation=False)
        test_img = _generate_test_puzzle_image()
        res = handler.solve_with_local_ai("puzzle_slider", image_bytes=test_img)
        self.assertTrue(res["solved"])
        self.assertGreater(res["slide_x_offset"], 50)
        self.assertEqual(res.get("method"), "vision_pil_edge_detection")

    def test_pipeline_fail_secure_escalates_to_mobile_tier(self):
        """When local AI cannot cryptographically solve reCAPTCHA, pipeline dispatches to mobile."""
        handler = CaptchaHandler(allow_simulation=False)
        with patch("pipeline.captcha_handler._is_production", return_value=True):
            result = handler.handle_pipeline_captcha("<div>g-recaptcha-response</div>")
            self.assertTrue(result["needed"])
            self.assertFalse(result["ok"])  # Not cleared yet
            self.assertEqual(result["tier"], "mobile_app_fallback")
            self.assertIn("captcha_id", result)

    def test_token_validation_rejects_mock_tokens_in_production(self):
        """validate_token unconditionally rejects mock tokens and short dummy values in production."""
        handler = CaptchaHandler(allow_simulation=False)
        with patch("pipeline.captcha_handler._is_production", return_value=True):
            self.assertFalse(handler.validate_token("mock_token_pass"))
            self.assertFalse(handler.validate_token("MOCK_TOKEN_PASS"))
            self.assertFalse(handler.validate_token("mock_bypass_123"))
            self.assertFalse(handler.validate_token("simulated"))
            self.assertFalse(handler.validate_token("short_token"))
            self.assertFalse(handler.validate_token(""))

            # Valid high-entropy real token passes
            valid_token = "03AFcWeA6x_RealGoogleRecaptchaTokenLongStringWithPlentyOfEntropy1234567890"
            self.assertTrue(handler.validate_token(valid_token))

    def test_mobile_bridge_prevents_unauthorized_resolution_bypass(self):
        """MobileBridge rejects remote resolution if no challenge is active or ID mismatches."""
        # 1. No active challenge
        res = self.bridge.resolve_captcha_remotely("any_id", {"touch_x": 100})
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "NO_ACTIVE_CHALLENGE")

        # 2. Set active challenge
        self.bridge.set_captcha_challenge({"captcha_id": "real_cap_999"})

        # 3. ID mismatch attempt
        res_mismatch = self.bridge.resolve_captcha_remotely("wrong_id", {"touch_x": 100})
        self.assertFalse(res_mismatch["ok"])
        self.assertEqual(res_mismatch["error"], "CHALLENGE_MISMATCH")

        # 4. Mock token bypass attempt in production
        with patch("app.config.is_production_runtime", return_value=True):
            res_mock = self.bridge.resolve_captcha_remotely("real_cap_999", {"token": "mock_token_pass"})
            self.assertFalse(res_mock["ok"])
            self.assertEqual(res_mock["error"], "MOCK_TOKEN_REJECTED")

        # 5. Legitimate coordinates resolution succeeds
        res_valid = self.bridge.resolve_captcha_remotely("real_cap_999", {"touch_x": 145, "touch_y": 80})
        self.assertTrue(res_valid["ok"])
        self.assertEqual(res_valid["captcha_id"], "real_cap_999")

    def test_api_solve_endpoint_returns_400_on_bypass_attempt(self):
        """FastAPI endpoint /api/mobile/captcha/solve returns HTTP 400 when solve is rejected."""
        self.bridge.set_captcha_challenge({"captcha_id": "challenge_456"})
        resp = self.client.post("/api/mobile/captcha/solve", json={
            "captcha_id": "wrong_challenge",
            "coordinates": {"touch_x": 10}
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "CHALLENGE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
