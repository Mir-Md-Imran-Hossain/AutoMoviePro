import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from app.config import OUTPUT_DIR
from app.main import app


class VideoLibraryAndStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Create a test mp4 file for testing
        cls.test_short = OUTPUT_DIR / "test_short_video_9_16.mp4"
        cls.test_long = OUTPUT_DIR / "test_long_documentary_video.mp4"
        cls.test_short.write_bytes(b"dummy mp4 content for testing")
        cls.test_long.write_bytes(b"dummy long mp4 content for testing")

    @classmethod
    def tearDownClass(cls):
        if cls.test_short.exists():
            cls.test_short.unlink()
        if cls.test_long.exists():
            cls.test_long.unlink()

    def test_videos_library_returns_all_videos(self):
        """GET /api/videos/library returns video list, count, and size."""
        res = self.client.get("/api/videos/library")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertGreaterEqual(data.get("count", 0), 2)
        filenames = [v["filename"] for v in data.get("videos", [])]
        self.assertIn("test_short_video_9_16.mp4", filenames)
        self.assertIn("test_long_documentary_video.mp4", filenames)

    def test_videos_library_filter_short(self):
        """GET /api/videos/library?folder=short filters for shorts only."""
        res = self.client.get("/api/videos/library?folder=short")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        for v in data.get("videos", []):
            self.assertTrue(v.get("is_short"))

    def test_videos_library_filter_long(self):
        """GET /api/videos/library?folder=long filters for long videos only."""
        res = self.client.get("/api/videos/library?folder=long")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        for v in data.get("videos", []):
            self.assertFalse(v.get("is_short"))

    def test_open_folder_endpoint(self):
        """POST /api/open-folder safely invokes platform open."""
        with patch("platform.system", return_value="Windows"), patch("os.startfile") as mock_startfile:
            res = self.client.post("/api/open-folder", json={})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("ok"))
            mock_startfile.assert_called_once()

    def test_output_static_mount_serves_files(self):
        """Static mount /output/... serves media files."""
        res = self.client.get("/output/test_short_video_9_16.mp4")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"dummy mp4 content for testing")


if __name__ == "__main__":
    unittest.main()
