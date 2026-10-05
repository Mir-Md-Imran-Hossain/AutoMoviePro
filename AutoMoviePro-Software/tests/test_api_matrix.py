"""Comprehensive unit & integration tests for Step 3: API Hub & Failover Matrix.
Standard library unittest implementation (zero external dependency).

Tests:
- Key persistence & secure masking
- Grok Primary/Fallback & Google Agent failover chain
- Video generation failover chain (Veo -> Agnes -> Pexels)
- Image generation failover chain (Google -> Agnes -> Pollinations -> Pexels)
- Language-specific Google TTS keys mapping
- Full readiness validation report
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.api_matrix.api_hub import ApiHub


class TestApiMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.hub = ApiHub(data_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_update_and_mask_api_keys(self):
        """Validates saving API credentials and ensuring secure masked display."""
        summary = self.hub.update_keys(
            grok_primary_key="xai-primary-secret-key-12345",
            grok_fallback_key="xai-fallback-secret-key-67890",
            google_media_key="AIzaSyGoogleMediaProKey",
            google_tts_keys={
                "bn": ["AIzaSyBnTtsKey001"],
                "en": ["AIzaSyEnTtsKey002"],
            },
            agnes_key="agnes-video-key-abc",
            pexels_key="pexels-stock-key-xyz",
            pollinations_key="pollinations-key-999",
        )

        self.assertTrue(summary["grok"]["primary_configured"])
        self.assertEqual(summary["grok"]["primary_masked"], "xai-...2345")
        self.assertTrue(summary["grok"]["fallback_configured"])
        self.assertTrue(summary["google"]["media_key_configured"])
        self.assertTrue(summary["google"]["tts_by_language"]["bn"]["configured"])
        self.assertTrue(summary["google"]["tts_by_language"]["en"]["configured"])
        self.assertFalse(summary["google"]["tts_by_language"]["hi"]["configured"])
        self.assertTrue(summary["agnes"]["configured"])
        self.assertTrue(summary["pexels"]["configured"])
        self.assertTrue(summary["pollinations"]["configured"])

    def test_agent_failover_chain(self):
        """Verifies Grok Primary -> Grok Fallback -> Google AI Studio -> OpenRouter chain."""
        self.hub.update_keys(
            grok_primary_key="key-grok-1",
            grok_fallback_key="key-grok-2",
            google_media_key="key-google-media",
            openrouter_key="key-openrouter",
        )

        chain = self.hub.resolve_agent_llm_chain()
        providers = [p for p, _ in chain]
        self.assertEqual(providers, [
            "grok_primary",
            "grok_fallback",
            "google_agent_fallback",
            "openrouter_fallback",
        ])

    def test_video_generation_failover_chain(self):
        """Verifies Google Veo -> Agnes Video -> Pexels Stock Video chain."""
        self.hub.update_keys(
            google_media_key="key-veo-pro",
            agnes_key="key-agnes-vid",
            pexels_key="key-pexels-vid",
        )

        chain = self.hub.resolve_video_generation_chain()
        providers = [p for p, _ in chain]
        self.assertEqual(providers, [
            "google_veo",
            "agnes_video",
            "pexels_stock_video",
        ])

    def test_image_generation_failover_chain(self):
        """Verifies Google Image -> Agnes Image -> Pollinations -> Pexels chain."""
        self.hub.update_keys(
            google_media_key="key-google-img",
            agnes_key="key-agnes-img",
            pollinations_key="key-pol-img",
            pexels_key="key-pexels-img",
        )

        chain = self.hub.resolve_image_generation_chain()
        providers = [p for p, _ in chain]
        self.assertEqual(providers, [
            "google_image",
            "agnes_image",
            "pollinations_image",
            "pexels_stock_image",
        ])

    def test_language_specific_tts_keys(self):
        """Tests language-keyed Google TTS routing and fallback to general Google key."""
        self.hub.update_keys(
            google_media_key="general-google-key",
            google_tts_keys={
                "bn": ["bn-tts-dedicated-key"],
            }
        )

        # Bangla has dedicated key
        bn_keys = self.hub.resolve_tts_keys_for_language("bn")
        self.assertEqual(bn_keys, ["bn-tts-dedicated-key"])

        # English has no dedicated key, falls back to general google media key
        en_keys = self.hub.resolve_tts_keys_for_language("en")
        self.assertEqual(en_keys, ["general-google-key"])

    def test_readiness_validation(self):
        """Checks validation report highlighting missing required keys."""
        # Empty config should report missing Grok & Video keys
        rep1 = self.hub.validate_readiness_for_languages(["en", "bn"])
        self.assertFalse(rep1["ready"])
        self.assertGreaterEqual(len(rep1["errors"]), 2)

        # Fully configured
        self.hub.update_keys(
            grok_primary_key="grok-p",
            grok_fallback_key="grok-f",
            google_media_key="goog-media",
            google_tts_keys={
                "en": ["goog-en"],
                "bn": ["goog-bn"],
            },
            agnes_key="agnes-k",
        )
        rep2 = self.hub.validate_readiness_for_languages(["en", "bn"])
        self.assertTrue(rep2["ready"])
        self.assertEqual(len(rep2["errors"]), 0)

    def test_grok_primary_to_fallback_failover_execution(self):
        """Simulates Grok Primary quota exhaustion (429) automatically failing over to Grok Fallback."""
        self.hub.update_keys(
            grok_primary_key="grok-primary-test-key",
            grok_fallback_key="grok-fallback-test-key",
            google_media_key="google-agent-pro-key",
        )

        call_log = []

        def mock_llm_caller(provider: str, key: str):
            call_log.append((provider, key))
            if provider == "grok_primary":
                raise Exception("HTTP 429: Rate limit or quota exceeded for grok_primary")
            return f"Success response generated by {provider}"

        res = self.hub.execute_agent_llm(
            prompt="Write a video script about ancient architecture",
            caller_override=mock_llm_caller,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "grok_fallback")
        self.assertIn("Success response generated by grok_fallback", res["data"])
        self.assertEqual(len(res["failover_history"]), 1)
        self.assertEqual(res["failover_history"][0]["provider"], "grok_primary")
        self.assertIn("429", res["failover_history"][0]["error"])

    def test_language_specific_tts_chain_and_pro_fallback(self):
        """Simulates language-specific TTS keys exhausting quota and failing over to Google Pro Media key."""
        self.hub.update_keys(
            google_media_key="google-pro-media-key-shared",
            google_tts_keys={
                "bn": ["bn-tts-key-001", "bn-tts-key-002"],
            }
        )

        chain = self.hub.resolve_tts_chain_for_language("bn")
        providers = [p for p, _ in chain]
        self.assertEqual(providers, [
            "google_tts_bn_1",
            "google_tts_bn_2",
            "google_tts_media_fallback",
        ])

        # Simulate key 1 & 2 quota failure -> Media fallback succeeds
        call_log = []

        def mock_tts_caller(provider: str, key: str):
            call_log.append((provider, key))
            if provider in ("google_tts_bn_1", "google_tts_bn_2"):
                raise Exception(f"HTTP 429: {provider} ResourceExhausted quota exceeded")
            return {"audio_content_base64": "mock_mp3_data", "provider": provider}

        res = self.hub.execute_tts(
            lang_code="bn",
            text="স্বাগতম আমাদের অটো মুভি প্রো তে",
            caller_override=mock_tts_caller,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "google_tts_media_fallback")
        self.assertEqual(len(res["failover_history"]), 2)
        self.assertEqual(res["failover_history"][0]["provider"], "google_tts_bn_1")
        self.assertEqual(res["failover_history"][1]["provider"], "google_tts_bn_2")

    def test_video_generation_failover_veo_to_agnes_to_pexels(self):
        """Simulates Google Veo and Agnes failing, seamlessly falling back to Pexels Stock Video."""
        self.hub.update_keys(
            google_media_key="google-veo-key",
            agnes_key="agnes-video-key",
            pexels_key="pexels-stock-key",
        )

        call_log = []

        def mock_video_caller(provider: str, key: str):
            call_log.append(provider)
            if provider == "google_veo":
                raise Exception("Google Veo 429: Daily generation quota limit reached")
            if provider == "agnes_video":
                raise Exception("Agnes 503: Service temporarily unavailable")
            return {"video_url": "https://pexels.com/video/12345.mp4", "provider": provider}

        res = self.hub.execute_video(
            prompt="Futuristic city skyline at night",
            duration_sec=4.0,
            caller_override=mock_video_caller,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "pexels_stock_video")
        self.assertEqual(call_log, ["google_veo", "agnes_video", "pexels_stock_video"])
        self.assertEqual(len(res["failover_history"]), 2)

    def test_image_generation_failover_to_pollinations(self):
        """Simulates Google Image and Agnes Image quota failures falling back to Pollinations."""
        self.hub.update_keys(
            google_media_key="google-pro-key",
            agnes_key="agnes-key",
            pollinations_key="pollinations-key",
        )

        def mock_img_caller(provider: str, key: str):
            if provider in ("google_image", "agnes_image"):
                raise Exception(f"{provider} quota error: 429 too many requests")
            return {"image_url": "https://image.pollinations.ai/prompt/test", "provider": provider}

        res = self.hub.execute_image(
            prompt="Cyberpunk samurai in neon rain",
            aspect_ratio="16:9",
            caller_override=mock_img_caller,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["provider"], "pollinations_image")
        self.assertEqual(len(res["failover_history"]), 2)

    def test_graceful_non_crashing_failure_when_all_exhausted(self):
        """Validates that when every key in a chain is exhausted, customer work does not crash."""
        self.hub.update_keys(
            grok_primary_key="grok-key-1",
        )

        def all_fail_caller(provider: str, key: str):
            raise Exception("Fatal quota exhaustion across entire organization")

        res = self.hub.execute_agent_llm(
            prompt="Hello world",
            caller_override=all_fail_caller,
        )

        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "all_providers_exhausted")
        self.assertIn("failed or exhausted quota", res["message"])
        self.assertIsNone(res["provider"])


if __name__ == "__main__":
    unittest.main()

