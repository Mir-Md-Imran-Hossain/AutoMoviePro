import os
import sys
import unittest
import tempfile
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.social_publisher import (
    MultiPlatformAutoPublisher,
    YouTubePublisher,
    FacebookPublisher,
    TikTokPublisher
)

class TestSocialPublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = MultiPlatformAutoPublisher()
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.temp_file.write(b"dummy video data")
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

    def test_youtube_short_publish(self):
        res = YouTubePublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_short=True
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["platform"], "youtube")
        self.assertIn("youtube.com/shorts/", res["url"])
        self.assertFalse(res["made_for_kids"])

    def test_youtube_long_publish(self):
        res = YouTubePublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_short=False
        )
        self.assertTrue(res["ok"])
        self.assertIn("youtu.be/", res["url"])

    def test_facebook_reel_publish(self):
        res = FacebookPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata,
            is_reel=True
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["platform"], "facebook")
        self.assertIn("facebook.com/reel/", res["url"])

    def test_tiktok_publish(self):
        res = TikTokPublisher.publish(
            video_path=self.video_path,
            metadata=self.metadata
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["platform"], "tiktok")
        self.assertIn("tiktok.com/@user/video/", res["url"])

    def test_multi_platform_orchestration_and_history(self):
        result = self.publisher.publish_video(
            video_path=self.video_path,
            metadata=self.metadata,
            platforms=["youtube", "facebook", "tiktok"],
            is_short=True
        )
        self.assertTrue(result["ok"])
        self.assertIn("youtube", result["published_urls"])
        self.assertIn("facebook", result["published_urls"])
        self.assertIn("tiktok", result["published_urls"])

        history = self.publisher.get_publication_history(limit=5)
        self.assertIsInstance(history, list)
        self.assertGreater(len(history), 0)


if __name__ == "__main__":
    unittest.main()
