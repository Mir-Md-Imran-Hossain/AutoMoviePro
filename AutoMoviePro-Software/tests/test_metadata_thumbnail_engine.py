"""Comprehensive unit & integration tests for Step 10: Thumbnail, Title, Description & Tags Engine.
Standard library unittest implementation (zero external dependency).

Tests:
- Localized title, description, tags, and hashtags generation
- Genuine JPEG generation (magic bytes \\xff\\xd8\\xff, decodable, valid dimensions)
- 9:16 vertical (1080x1920) for Shorts vs 16:9 widescreen (1280x720) for Long videos
- Strict QA rejection of 0-byte or corrupted thumbnail files
- Magic bytes and PIL inspection validation
- Quota guard caching with integrity checking
- Surgical local agent thumbnail re-generation
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.metadata_thumbnail_engine import (
    MetadataThumbnailEngine,
    VideoMetadataPackage,
    inspect_thumbnail_image,
)


class TestMetadataThumbnailEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.engine = MetadataThumbnailEngine(thumbs_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_bangla_short_thumbnail_and_metadata(self):
        """Generates localized Bangla metadata package with genuine 9:16 JPEG thumbnail."""
        pkg = self.engine.generate_package(
            topic_title="5 AI Inventions",
            niche="Technology & AI Innovations",
            video_format="short",
            language="bn",
        )
        self.assertEqual(pkg.language, "bn")
        self.assertEqual(pkg.video_format, "short")
        self.assertIn("অবিশ্বাস্য তথ্য", pkg.title)
        self.assertIn("Timestamps", pkg.description)
        self.assertGreaterEqual(len(pkg.tags), 5)

        thumb_p = Path(pkg.thumbnail_image_path)
        self.assertTrue(thumb_p.exists())
        self.assertGreater(thumb_p.stat().st_size, 1000)

        # File signature magic bytes check
        header = thumb_p.read_bytes()[:3]
        self.assertEqual(header, b"\xff\xd8\xff")

        # Probed metadata check
        details = pkg.thumbnail_details
        self.assertTrue(details["valid"])
        self.assertEqual(details["aspect_ratio"], "9:16")
        self.assertEqual(details["width"], 1080)
        self.assertEqual(details["height"], 1920)
        self.assertTrue(pkg.passed_qa)
        self.assertGreaterEqual(pkg.seo_score, 80.0)

    def test_english_long_thumbnail_and_metadata(self):
        """Generates localized English metadata package with genuine 16:9 JPEG thumbnail."""
        pkg = self.engine.generate_package(
            topic_title="The Roman Empire Secrets",
            niche="World History & Geopolitics",
            video_format="long",
            language="en",
        )
        self.assertEqual(pkg.language, "en")
        self.assertEqual(pkg.video_format, "long")
        self.assertIn("The Untold Truth Revealed", pkg.title)

        thumb_p = Path(pkg.thumbnail_image_path)
        self.assertTrue(thumb_p.exists())
        self.assertGreater(thumb_p.stat().st_size, 1000)

        # File signature magic bytes check
        header = thumb_p.read_bytes()[:3]
        self.assertEqual(header, b"\xff\xd8\xff")

        details = pkg.thumbnail_details
        self.assertTrue(details["valid"])
        self.assertEqual(details["aspect_ratio"], "16:9")
        self.assertEqual(details["width"], 1280)
        self.assertEqual(details["height"], 720)
        self.assertTrue(pkg.passed_qa)
        self.assertGreaterEqual(pkg.seo_score, 80.0)

    def test_qa_rejects_empty_placeholder_thumbnail(self):
        """Validates that local agent strictly rejects 0-byte or touch() placeholders."""
        empty_file = Path(self.tmp_dir.name) / "empty_thumb.jpg"
        empty_file.touch()

        dummy_pkg = VideoMetadataPackage(
            language="en",
            video_format="long",
            title="Valid Catchy YouTube Title About Deep Space Exploration",
            description="Detailed description with timestamps and links.",
            tags=["space", "stars", "universe", "astronomy", "science"],
            hashtags=["#space", "#universe"],
            thumbnail_prompt="Space exploration thumbnail",
            thumbnail_image_path=str(empty_file),
            seo_score=95.0,
            passed_qa=True,  # Initially claims True
        )

        audited = self.engine.inspect_metadata_quality(dummy_pkg)
        self.assertFalse(audited.passed_qa)
        self.assertIn("Thumbnail QA Failure", audited.qa_notes)
        self.assertLess(audited.seo_score, 80.0)

    def test_qa_rejects_corrupted_magic_bytes_thumbnail(self):
        """Validates that local agent strictly rejects files with corrupt headers."""
        corrupt_file = Path(self.tmp_dir.name) / "corrupt_thumb.jpg"
        corrupt_file.write_bytes(b"NOT_A_VALID_JPEG_HEADER_SIGNATURE_AT_ALL" * 30)

        dummy_pkg = VideoMetadataPackage(
            language="bn",
            video_format="short",
            title="Valid Catchy YouTube Title About Deep Space Exploration",
            description="Detailed description with timestamps and links.",
            tags=["space", "stars", "universe", "astronomy", "science"],
            hashtags=["#space", "#universe"],
            thumbnail_prompt="Space exploration thumbnail",
            thumbnail_image_path=str(corrupt_file),
            seo_score=95.0,
            passed_qa=True,
        )

        audited = self.engine.inspect_metadata_quality(dummy_pkg)
        self.assertFalse(audited.passed_qa)
        self.assertIn("Thumbnail QA Failure", audited.qa_notes)
        self.assertIn("Invalid JPEG magic bytes", audited.qa_notes)

    def test_inspect_thumbnail_image_metrics(self):
        """Directly tests inspect_thumbnail_image on real vs missing files."""
        pkg = self.engine.generate_package(
            topic_title="Quantum Physics",
            niche="Science",
            video_format="long",
            language="en",
        )
        info = inspect_thumbnail_image(Path(pkg.thumbnail_image_path))
        self.assertTrue(info["valid"])
        self.assertEqual(info["width"], 1280)
        self.assertEqual(info["height"], 720)
        self.assertEqual(info["aspect_ratio"], "16:9")
        self.assertGreater(info["file_size_bytes"], 1000)

        # Missing file test
        missing_info = inspect_thumbnail_image(Path(self.tmp_dir.name) / "non_existent.jpg")
        self.assertFalse(missing_info["valid"])
        self.assertIn("not found", missing_info["error"])

    def test_thumbnail_quota_guard_caching(self):
        """Re-requesting identical package uses clean cached thumbnail."""
        pkg1 = self.engine.generate_package(
            topic_title="Ancient Egyptian Pyramids",
            niche="History",
            video_format="long",
            language="en",
        )
        pkg2 = self.engine.generate_package(
            topic_title="Ancient Egyptian Pyramids",
            niche="History",
            video_format="long",
            language="en",
        )
        self.assertEqual(pkg1.thumbnail_image_path, pkg2.thumbnail_image_path)
        self.assertTrue(pkg2.passed_qa)
        self.assertTrue(Path(pkg2.thumbnail_image_path).exists())

    def test_surgical_thumbnail_regeneration(self):
        """Surgically re-generates thumbnail with custom high-CTR prompt."""
        pkg = self.engine.generate_package(
            topic_title="Black Hole Secrets",
            niche="Cosmology",
            video_format="short",
            language="en",
        )
        old_path = pkg.thumbnail_image_path

        updated_pkg = self.engine.regenerate_thumbnail(
            pkg,
            custom_prompt="Ultra dramatic glowing event horizon with relativistic jet in 8k",
        )
        self.assertTrue(updated_pkg.passed_qa)
        self.assertTrue(Path(updated_pkg.thumbnail_image_path).exists())
        self.assertNotEqual(old_path, updated_pkg.thumbnail_image_path)
        self.assertGreater(Path(updated_pkg.thumbnail_image_path).stat().st_size, 1000)

    def test_qa_rejects_mock_thumbnail_marker(self):
        """Validates that QA strictly rejects thumbnails containing mock markers."""
        mock_file = Path(self.tmp_dir.name) / "mock_thumb.jpg"
        mock_file.write_bytes(b"\xff\xd8\xffmock_thumbnail_fixture_data" * 20)

        info = inspect_thumbnail_image(mock_file)
        self.assertFalse(info["valid"])
        self.assertIn("Mock artifact marker detected", info["error"])

        dummy_pkg = VideoMetadataPackage(
            language="en",
            video_format="short",
            title="Valid High-Converting YouTube Shorts Catchy Title",
            description="Detailed description for testing.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            hashtags=["#tag1"],
            thumbnail_prompt="Mock prompt",
            thumbnail_image_path=str(mock_file),
            seo_score=90.0,
            passed_qa=True,
        )
        audited = self.engine.inspect_metadata_quality(dummy_pkg)
        self.assertFalse(audited.passed_qa)
        self.assertIn("Thumbnail QA Failure", audited.qa_notes)

    def test_qa_rejects_corrupted_jpeg_pixel_decode(self):
        """Validates that QA strictly rejects JPEGs whose bytes fail pixel decoding."""
        corrupt_jpg = Path(self.tmp_dir.name) / "corrupt_pixels.jpg"
        # Valid SOI + APP0 marker but corrupted stream
        corrupt_jpg.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xaa\xbb\xcc\xdd" * 200)

        info = inspect_thumbnail_image(corrupt_jpg)
        self.assertFalse(info["valid"])
        self.assertTrue("decode" in info["error"].lower() or "verification" in info["error"].lower() or "error" in info["error"].lower())

    def test_ab_thumbnail_variants_and_chapters(self):
        """Validates generation of 3 distinct A/B thumbnail variants, 3 title candidates, chapters and SEO breakdown."""
        pkg = self.engine.generate_package(
            topic_title="Top 10 Quantum Computing Breakthroughs",
            niche="Future Technology & Science",
            video_format="long",
            language="en",
        )
        # Check title candidates
        self.assertEqual(len(pkg.title_candidates), 3)
        styles = [c["style"] for c in pkg.title_candidates]
        self.assertIn("viral_hook", styles)
        self.assertIn("curiosity_gap", styles)
        self.assertIn("authority_investigation", styles)

        # Check video chapters
        self.assertGreaterEqual(len(pkg.video_chapters), 4)
        self.assertEqual(pkg.video_chapters[0]["timestamp"], "00:00")

        # Check thumbnail variants
        self.assertEqual(len(pkg.thumbnail_variants), 3)
        for var in pkg.thumbnail_variants:
            v_path = Path(var["path"])
            self.assertTrue(v_path.exists())
            self.assertGreater(v_path.stat().st_size, 1000)
            self.assertEqual(var["details"]["aspect_ratio"], "16:9")
            self.assertEqual(var["details"]["width"], 1280)
            self.assertEqual(var["details"]["height"], 720)

        # Check SEO breakdown
        self.assertIn("title_length", pkg.seo_breakdown)
        self.assertIn("ctr_curiosity_score", pkg.seo_breakdown)
        self.assertTrue(pkg.seo_breakdown["has_chapters"])
        self.assertTrue(pkg.seo_breakdown["variants_verified"])
        self.assertEqual(pkg.seo_breakdown["variant_count"], 3)
        self.assertTrue(pkg.passed_qa)
        self.assertGreaterEqual(pkg.seo_score, 80.0)


if __name__ == "__main__":
    unittest.main()

