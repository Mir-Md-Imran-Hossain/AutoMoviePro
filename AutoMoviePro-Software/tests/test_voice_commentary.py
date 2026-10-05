import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.voice.voice_commentary import FuturisticVoiceEngine

class TestVoiceCommentary(unittest.TestCase):
    def setUp(self):
        self.engine = FuturisticVoiceEngine()
        self.engine.set_mute_state(False)
        self.engine.set_volume(0.9)

    def test_startup_briefing_bn(self):
        briefing = self.engine.get_startup_briefing(
            user_name="Mr. Rahim",
            active_channels_count=2,
            scheduled_today=3,
            language="bn"
        )
        self.assertTrue(briefing["speech_active"])
        self.assertIn("Mr. Rahim", briefing["text"])
        self.assertIn("সিস্টেম প্রস্তুত", briefing["text"])
        self.assertEqual(briefing["volume"], 0.9)

    def test_mute_behavior(self):
        self.engine.set_mute_state(True)
        briefing = self.engine.get_startup_briefing()
        self.assertFalse(briefing["speech_active"])
        self.assertEqual(briefing["reason"], "muted")

    def test_onboarding_and_pipeline_commentary(self):
        self.engine.set_mute_state(False)
        guide = self.engine.get_onboarding_guide("api_setup", language="bn")
        self.assertTrue(guide["speech_active"])
        self.assertIn("Grok", guide["text"])

        comm = self.engine.get_pipeline_commentary("published", language="bn")
        self.assertTrue(comm["speech_active"])
        self.assertIn("ইউটিউব", comm["text"])

    def test_all_15_requirements_cues_and_audio_files(self):
        cues_to_test = [
            "topic_research", "topic_found", "title_script", "script_ready",
            "localize_start", "localize_bn_progress", "localize_bn_done",
            "localize_hi_progress", "localize_hi_done", "audio_gen_start",
            "agnes_generating", "agnes_fallback_google", "scene1_done",
            "pollinations_image", "upload_starting"
        ]
        for c in cues_to_test:
            res = self.engine.get_pipeline_commentary(c, language="bn")
            self.assertTrue(res["speech_active"], f"Cue {c} should be active")
            self.assertIsNotNone(res["text"], f"Cue {c} should have text")
            self.assertIsNotNone(res["audio_file"], f"Cue {c} should have audio file")
            self.assertTrue(os.path.exists(res["audio_file"]), f"Audio file for {c} must exist on disk")


if __name__ == "__main__":
    unittest.main()
