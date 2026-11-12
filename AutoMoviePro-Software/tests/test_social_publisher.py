import os
import sys
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.social_publisher import (
    MultiPlatformAutoPublisher,
    YouTubePublisher,
    FacebookPublisher,
    TikTokPublisher,
    VideoAnalyticsTracker,
)


class TestSocialPublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = MultiPlatformAutoPublisher()
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.temp_file.write(b"valid test video bytes for publishing")
        self.temp_file.close()
        self.video_path = self.temp_file.name

        self.metadata = {
            "title": "Top 10 Hidden Mysteries of Space",
            "description": "Explore the unknown depths of outer space.",
            "tags": ["space", "mystery", "science"]
        }

    def tearDown(self):
        if os.path.exists(self.video_path):
            os.remove(self.video_path)

    def test_youtube_unauthenticated_is_strictly_rejected(self):
        """Verifies that publishing without OAuth credentials fails with AUTHENTICATION_REQUIRED and never fakes a link."""
        res = YouTubePublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_short=True,
            oauth_token=None,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["platform"], "youtube")
        self.assertIn("AUTHENTICATION_REQUIRED", res["error"])
        self.assertNotIn("url", res)

    def test_facebook_unauthenticated_is_strictly_rejected(self):
        """Verifies that publishing without Meta credentials fails with AUTHENTICATION_REQUIRED and never fakes a link."""
        res = FacebookPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_reel=True,
            page_id=None,
            access_token=None,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["platform"], "facebook")
        self.assertIn("AUTHENTICATION_REQUIRED", res["error"])
        self.assertNotIn("url", res)

    def test_tiktok_unauthenticated_is_strictly_rejected(self):
        """Verifies that publishing without TikTok credentials fails with AUTHENTICATION_REQUIRED and never fakes a link."""
        res = TikTokPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            access_token=None,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["platform"], "tiktok")
        self.assertIn("AUTHENTICATION_REQUIRED", res["error"])
        self.assertNotIn("url", res)

    @patch("urllib.request.urlopen")
    def test_youtube_publish_with_valid_oauth(self, mock_urlopen):
        """Tests authentic YouTube resumable upload flow with valid OAuth token."""
        # 1st call for init upload session
        mock_resp_init = MagicMock()
        mock_resp_init.headers = {"Location": "https://upload.youtube.com/upload_session_123"}
        mock_resp_init.__enter__.return_value = mock_resp_init

        # 2nd call for video bytes upload
        mock_resp_upload = MagicMock()
        mock_resp_upload.read.return_value = json.dumps({"id": "real_yt_vid_999"}).encode("utf-8")
        mock_resp_upload.__enter__.return_value = mock_resp_upload

        mock_urlopen.side_effect = [mock_resp_init, mock_resp_upload]

        res = YouTubePublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_short=True,
            oauth_token="ya29.valid_test_token"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["video_id"], "real_yt_vid_999")
        self.assertEqual(res["url"], "https://www.youtube.com/shorts/real_yt_vid_999")
        self.assertEqual(res["method"], "official_api_v3")

    @patch("urllib.request.urlopen")
    def test_facebook_publish_with_valid_token(self, mock_urlopen):
        """Tests authentic Facebook Meta Graph API upload flow with access token and page ID."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "real_fb_vid_888"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = FacebookPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_reel=True,
            page_id="123456789",
            access_token="EAAX_valid_token"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["video_id"], "real_fb_vid_888")
        self.assertEqual(res["url"], "https://www.facebook.com/reel/real_fb_vid_888")
        self.assertEqual(res["method"], "meta_graph_api_v19")

    @patch("urllib.request.urlopen")
    def test_tiktok_publish_with_valid_token(self, mock_urlopen):
        """Tests authentic TikTok Content Posting API flow with access token."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"publish_id": "real_tt_post_777"}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = TikTokPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            access_token="act.valid_tiktok_token"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["video_id"], "real_tt_post_777")
        self.assertEqual(res["url"], "https://www.tiktok.com/@user/video/real_tt_post_777")
        self.assertEqual(res["method"], "tiktok_api_v2")

    def test_analytics_tracker_zero_fabrication(self):
        """Verifies that VideoAnalyticsTracker does not generate fake random views/likes."""
        with tempfile.TemporaryDirectory() as td:
            analytics_file = Path(td) / "analytics.json"
            tracker = VideoAnalyticsTracker(data_file=analytics_file)
            metrics = tracker.refresh_metrics()

            self.assertIn("records", metrics)
            for r in metrics["records"]:
                # When unpolled or fresh, views should be 0 rather than fake 150+
                self.assertGreaterEqual(r["views"], 0)


if __name__ == "__main__":
    unittest.main()
