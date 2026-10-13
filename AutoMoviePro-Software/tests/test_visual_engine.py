"""Comprehensive unit & integration tests for Step 6: Visual Generation & Continuity.
Standard library unittest implementation (zero external dependency).

Tests:
- Aspect ratio selection (9:16 vertical for Short, 16:9 widescreen for Long)
- Real media file generation (decodable, non-zero size, valid signature)
- Strict QA rejection on empty (0-byte) or corrupted placeholder files
- MIME type and magic bytes verification (inspect_visual_asset)
- Provider fallback continuity (Veo -> Agnes -> Pollinations -> Pexels -> Local)
- Quota guard caching (re-using verified assets)
- Local agent surgical re-generation with fallback
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.visual_engine import (
    VisualClip,
    VisualEngine,
    inspect_visual_asset,
)


class TestVisualEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = VisualEngine(assets_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_short_form_aspect_ratio_and_resolution(self):
        """Short video visuals must be 9:16 vertical (1080x1920) and genuinely decodable."""
        clip = self.engine.generate_scene_visual(
            scene_index=1,
            prompt="Futuristic city with flying cars",
            narration="Look at the year 2026",
            required_duration_sec=3.0,
            video_format="short",
        )
        self.assertEqual(clip.aspect_ratio, "9:16")
        self.assertEqual(clip.resolution, "1080x1920")
        self.assertTrue(clip.passed_qa)
        p = Path(clip.file_path)
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 1000)
        self.assertGreater(clip.file_size_bytes, 1000)
        self.assertIn("Decoded successfully", clip.qa_notes)

    def test_long_form_aspect_ratio_and_resolution(self):
        """Long video visuals must be 16:9 horizontal (1920x1080) and genuinely decodable."""
        clip = self.engine.generate_scene_visual(
            scene_index=1,
            prompt="Ancient Roman forum architecture documentary",
            narration="Rome was not built in a day",
            required_duration_sec=3.0,
            video_format="long",
        )
        self.assertEqual(clip.aspect_ratio, "16:9")
        self.assertIn(clip.resolution, ["1920x1080", "3840x2160", "2560x1440"])
        self.assertTrue(clip.passed_qa)
        p = Path(clip.file_path)
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 1000)
        self.assertGreater(clip.file_size_bytes, 1000)

    def test_qa_rejects_empty_placeholder_file(self):
        """Validates that local agent QA strictly rejects 0-byte or touch() placeholders."""
        empty_file = Path(self.tmp_dir.name) / "empty_scene.mp4"
        empty_file.touch()

        dummy_clip = VisualClip(
            scene_index=1,
            provider_used="google_veo",
            asset_type="video",
            file_path=str(empty_file),
            duration_sec=5.0,
            aspect_ratio="9:16",
            resolution="1080x1920",
            passed_qa=True,  # Initially claims True
        )

        inspected = self.engine.inspect_clip(
            dummy_clip,
            prompt="Futuristic city",
            narration="Look at the future",
            expected_duration=5.0,
        )
        self.assertFalse(inspected.passed_qa)
        self.assertIn("Visual QA Failure", inspected.qa_notes)

    def test_qa_rejects_corrupted_magic_bytes(self):
        """Validates that local agent QA strictly rejects files with invalid magic bytes."""
        corrupt_file = Path(self.tmp_dir.name) / "corrupt_scene.png"
        corrupt_file.write_bytes(b"NOT_A_VALID_IMAGE_OR_VIDEO_SIGNATURE")

        dummy_clip = VisualClip(
            scene_index=2,
            provider_used="pollinations_image",
            asset_type="image",
            file_path=str(corrupt_file),
            duration_sec=0.0,
            aspect_ratio="9:16",
            resolution="1080x1920",
            passed_qa=True,
        )

        inspected = self.engine.inspect_clip(
            dummy_clip,
            prompt="City view",
            narration="Urban life",
            expected_duration=0.0,
        )
        self.assertFalse(inspected.passed_qa)
        self.assertIn("Visual QA Failure", inspected.qa_notes)

    def test_inspect_visual_asset_metrics(self):
        """Tests inspect_visual_asset directly on valid image/video vs invalid files."""
        # Generate valid clip
        clip = self.engine.generate_scene_visual(
            scene_index=5,
            prompt="Test visual inspection",
            narration="Inspection test",
            required_duration_sec=2.0,
            video_format="short",
        )
        info = inspect_visual_asset(Path(clip.file_path))
        self.assertTrue(info["valid"])
        self.assertEqual(info["resolution"], "1080x1920")
        self.assertEqual(info["aspect_ratio"], "9:16")
        self.assertGreater(info["file_size_bytes"], 1000)

        # Inspect missing file
        missing_info = inspect_visual_asset(Path(self.tmp_dir.name) / "missing.mp4")
        self.assertFalse(missing_info["valid"])
        self.assertEqual(missing_info["file_size_bytes"], 0)

    def test_quota_guard_caching(self):
        """Re-requesting identical visual returns cached asset without new generation."""
        clip1 = self.engine.generate_scene_visual(
            scene_index=2,
            prompt="Golden sunset over ocean waves",
            narration="Peaceful evening",
            required_duration_sec=2.0,
            video_format="short",
        )
        clip2 = self.engine.generate_scene_visual(
            scene_index=2,
            prompt="Golden sunset over ocean waves",
            narration="Peaceful evening",
            required_duration_sec=2.0,
            video_format="short",
        )
        self.assertEqual(clip1.file_path, clip2.file_path)
        self.assertEqual(clip2.provider_used, "cache")
        self.assertTrue(clip2.passed_qa)
        self.assertGreater(clip2.file_size_bytes, 1000)

    def test_surgical_regeneration_with_fallback(self):
        """Local agent re-generates flawed scene using a fallback provider."""
        clip = self.engine.regenerate_clip(
            scene_index=3,
            prompt="Microscope view of DNA replication",
            narration="Cellular biology in action",
            required_duration_sec=2.0,
            video_format="short",
            fallback_provider="pexels_stock",
        )
        self.assertEqual(clip.provider_used, "pexels_stock")
        self.assertTrue(clip.passed_qa)
        self.assertTrue(Path(clip.file_path).exists())
        self.assertGreater(clip.file_size_bytes, 1000)

    def test_qa_rejects_mock_visual_marker(self):
        """Validates that QA rejects visual assets containing mock or placeholder markers."""
        mock_png = Path(self.tmp_dir.name) / "mock_asset.png"
        mock_png.write_bytes(b"\x89PNG\r\n\x1a\nmock_visual_data_fixture_here" * 10)

        info = inspect_visual_asset(mock_png)
        self.assertFalse(info["valid"])
        self.assertIn("Mock artifact marker detected", info["error"])

        dummy_clip = VisualClip(
            scene_index=1,
            provider_used="pollinations_image",
            asset_type="image",
            file_path=str(mock_png),
            duration_sec=0.0,
            aspect_ratio="9:16",
            resolution="1080x1920",
            passed_qa=True,
        )
        inspected = self.engine.inspect_clip(dummy_clip, "Prompt", "Narration", 2.0)
        self.assertFalse(inspected.passed_qa)
        self.assertIn("Visual QA Failure", inspected.qa_notes)

    def test_qa_rejects_corrupted_image_pixel_decode(self):
        """Validates that QA rejects images whose headers may be valid but pixels fail decode."""
        corrupt_img = Path(self.tmp_dir.name) / "corrupt_pixels.png"
        # Valid PNG signature followed by corrupted chunks
        corrupt_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x048\x00\x00\x07\x80\x08\x02\x00\x00\x00\x55\xaa\xbb\xcc\x00\x00\x00\x20IDAT" + b"\xff" * 200)

        info = inspect_visual_asset(corrupt_img)
        self.assertFalse(info["valid"])
        self.assertTrue("decode" in info["error"].lower() or "signature" in info["error"].lower() or "error" in info["error"].lower())


if __name__ == "__main__":
    unittest.main()
