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


if __name__ == "__main__":
    unittest.main()
