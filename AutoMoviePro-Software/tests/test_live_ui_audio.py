import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.main import app

class TestLiveUIAndAudioEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_homepage_html_includes_new_features(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        # Verify Live Scrolling Ticker
        self.assertIn("liveTickerBar", html)
        self.assertIn("liveTickerText", html)
        # Verify Jarvis AI Voice Console
        self.assertIn("jarvisConsole", html)
        self.assertIn("jarvisSoundToggle", html)
        self.assertIn("playJarvisAudioCue", html)
        # Verify Legal Modal
        self.assertIn("legalTermsModal", html)
        # Verify Interactive info
        self.assertIn("fieldInfoModal", html)

    def test_audio_cue_asset_serving(self):
        # Check that welcome_bn.wav is physically served with audio/wav mime type
        res = self.client.get("/assets/audio/voice_cues/welcome_bn.wav")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(len(res.content), 5000)
        # Check that startup_chime.wav is served
        res_chime = self.client.get("/assets/audio/voice_cues/startup_chime.wav")
        self.assertEqual(res_chime.status_code, 200)
        self.assertGreater(len(res_chime.content), 5000)

    def test_live_announcements_api(self):
        res = self.client.get("/api/announcements/list?language=bn")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertGreater(len(data.get("announcements", [])), 0)

    def test_granular_voice_commentary_stages(self):
        # Test key milestone stages across the whole pipeline
        stages_to_test = [
            "welcome",
            "startup_ready",
            "topic_research_start",
            "topic_research_progress",
            "topic_research_done",
            "script_start",
            "script_progress",
            "script_done",
            "localization_start",
            "localization_done",
            "audio_start",
            "audio_done",
            "short_video_start",
            "short_video_done",
            "long_video_start",
            "long_video_done",
            "facebook_upload_start",
            "facebook_upload_done",
            "youtube_upload_start",
            "youtube_upload_done",
            "cycle_complete_idle"
        ]

        for stage in stages_to_test:
            res = self.client.get(f"/api/voice/commentary?stage={stage}&language=bn")
            self.assertEqual(res.status_code, 200, f"Failed for stage: {stage}")
            data = res.json()
            self.assertIn("audio_file", data, f"Missing audio_file for stage: {stage}")
            self.assertTrue(data["audio_file"].startswith("/assets/audio/voice_cues/"), f"Invalid audio URL for {stage}: {data['audio_file']}")
            self.assertIn("text", data)
            self.assertTrue(len(data["text"]) > 0)
            
            # Verify the audio asset is actually served by FastAPI
            asset_res = self.client.get(data["audio_file"])
            self.assertEqual(asset_res.status_code, 200, f"Asset not found for {stage}: {data['audio_file']}")
            self.assertGreater(len(asset_res.content), 20000, f"Audio file is too small for {stage}")

    def test_dynamic_language_localization(self):
        # 1. Test Bengali target language
        res_bn = self.client.get("/api/voice/commentary?stage=localization_start&target_language=bn&language=bn")
        self.assertEqual(res_bn.status_code, 200)
        data_bn = res_bn.json()
        self.assertIn("বাংলা", data_bn["text"])
        self.assertNotIn("৫০টি", data_bn["text"])

        # 2. Test English target language
        res_en = self.client.get("/api/voice/commentary?stage=localization_start&target_language=en&language=bn")
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.json()
        self.assertIn("ইংরেজি", data_en["text"])
        self.assertNotIn("৫০টি", data_en["text"])

        # 3. Test Spanish target language
        res_es = self.client.get("/api/voice/commentary?stage=localization_start&target_language=es&language=bn")
        self.assertEqual(res_es.status_code, 200)
        data_es = res_es.json()
        self.assertIn("স্প্যানিশ", data_es["text"])
        self.assertNotIn("৫০টি", data_es["text"])

    def test_sector_controls_and_preferences(self):
        # 1. Update sectors: turn off live pipeline commentary
        up_res = self.client.post("/api/voice/settings", json={
            "sectors": {"live_pipeline_commentary": False}
        })
        self.assertEqual(up_res.status_code, 200)
        self.assertFalse(up_res.json()["settings"]["sectors"]["live_pipeline_commentary"])

        # Verify commentary is suppressed
        comm_res = self.client.get("/api/voice/commentary?stage=topic_research_start&language=bn")
        self.assertEqual(comm_res.status_code, 200)
        self.assertFalse(comm_res.json()["speech_active"])

        # 2. Turn on live commentary and turn on milestone_only
        self.client.post("/api/voice/settings", json={
            "sectors": {
                "live_pipeline_commentary": True,
                "milestone_only_notifications": True
            }
        })

        # Non-milestone should be suppressed
        res_prog = self.client.get("/api/voice/commentary?stage=topic_research_progress&language=bn")
        self.assertFalse(res_prog.json()["speech_active"])

        # Milestone should be active
        res_mile = self.client.get("/api/voice/commentary?stage=short_video_done&language=bn")
        self.assertTrue(res_mile.json()["speech_active"])

        # Reset to default
        self.client.post("/api/voice/settings", json={
            "is_muted": False,
            "volume": 0.85,
            "sectors": {
                "live_pipeline_commentary": True,
                "interactive_field_guidance": True,
                "system_advisory_alerts": True,
                "milestone_only_notifications": False
            }
        })

    def test_preflight_advisory_api(self):
        res = self.client.get("/api/voice/preflight-advisory?language=bn")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertIn(data["status"], ["ok", "warning", "blocked"])
        self.assertIn("text", data)
        self.assertTrue(len(data["text"]) > 0)
        self.assertIn("title", data)

    def test_field_guidance_api(self):
        # Bengali guidance
        res_bn = self.client.get("/api/voice/field-guidance?field_key=channel_name&language=bn")
        self.assertEqual(res_bn.status_code, 200)
        data_bn = res_bn.json()
        self.assertTrue(data_bn["ok"])
        self.assertIn("এখানে আপনার চ্যানেলের নাম দিন", data_bn["text"])

        # English guidance
        res_en = self.client.get("/api/voice/field-guidance?field_key=channel_name&language=en")
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.json()
        self.assertTrue(data_en["ok"])
        self.assertIn("Enter your channel name", data_en["text"])


if __name__ == "__main__":
    unittest.main()

