"""Tests for Google Pro Veo video generation and Imagen image generation."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.google_media import (
    generate_imagen_image,
    generate_veo_video,
    is_google_pro_available,
    normalize_aspect_ratio,
)
from pipeline.purpose_caps import CAPABILITIES, google_allowed_for_purpose, image_provider_chain


class TestGoogleProMedia(unittest.TestCase):
    def test_normalize_aspect_ratio(self):
        self.assertEqual(normalize_aspect_ratio("16:9"), "16:9")
        self.assertEqual(normalize_aspect_ratio("landscape"), "16:9")
        self.assertEqual(normalize_aspect_ratio("9:16"), "9:16")
        self.assertEqual(normalize_aspect_ratio("portrait"), "9:16")
        self.assertEqual(normalize_aspect_ratio("short"), "9:16")
        self.assertEqual(normalize_aspect_ratio("1:1"), "1:1")
        self.assertEqual(normalize_aspect_ratio("", width=1080, height=1920), "9:16")
        self.assertEqual(normalize_aspect_ratio("", width=1920, height=1080), "16:9")

    def test_is_google_pro_available(self):
        self.assertTrue(is_google_pro_available(["AIzaSyFakeKey123"]))
        self.assertFalse(is_google_pro_available([]))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyEnvKey"}):
            self.assertTrue(is_google_pro_available(None))

    def test_purpose_caps_google_media_enabled(self):
        self.assertTrue(CAPABILITIES["google"]["image"])
        self.assertTrue(CAPABILITIES["google"]["video"])
        self.assertTrue(google_allowed_for_purpose("image"))
        self.assertTrue(google_allowed_for_purpose("video"))
        self.assertTrue(google_allowed_for_purpose("translate"))
        chain = image_provider_chain()
        self.assertIn("google", chain)

    def test_generate_veo_video_no_key(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "test.mp4"
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                res = generate_veo_video("test prompt", out, "")
                self.assertIsNone(res)

    @patch("google.genai.Client")
    def test_generate_veo_video_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_op = MagicMock()
        mock_op.done = True
        mock_video_obj = MagicMock()
        mock_vid_item = MagicMock()
        mock_vid_item.video = mock_video_obj
        mock_op.response.generated_videos = [mock_vid_item]

        mock_client.models.generate_videos.return_value = mock_op

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "veo_test.mp4"
            # Define side effect for download to write mock bytes
            def fake_download(file, destination):
                Path(destination).write_bytes(b"RIFF" + b"\x00" * 6000)

            mock_client.files.download.side_effect = fake_download

            res = generate_veo_video(
                "Futuristic city cinematic shot",
                out,
                "fake-key",
                aspect_ratio="9:16",
                duration_seconds=5,
            )
            self.assertIsNotNone(res)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 5000)

    @patch("google.genai.Client")
    def test_generate_imagen_image_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_img_item = MagicMock()
        mock_img_item.image.image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 4000
        mock_resp.generated_images = [mock_img_item]

        mock_client.models.generate_images.return_value = mock_resp

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "imagen_test.jpg"
            res = generate_imagen_image(
                "Sleek smartphone on clean desk",
                out,
                "fake-key",
                aspect_ratio="16:9",
            )
            self.assertIsNotNone(res)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 3000)


if __name__ == "__main__":
    unittest.main()
