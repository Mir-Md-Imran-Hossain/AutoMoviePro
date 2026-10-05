import os
import io
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.audio_localization_engine import AudioLocalizationEngine, inspect_audio_file
from pipeline.metadata_thumbnail_engine import MetadataThumbnailEngine, inspect_thumbnail_image
from pipeline.final_video_composer import FinalVideoComposer, inspect_media
from publishers.customer_publish_provider import (
    get_publish_provider,
    resolve_publish_provider,
    YouTubeDataApiProvider,
    MockPublishProvider,
)
from app.customer_plan_adapter import (
    resolve_execution_mode,
    EXECUTION_MODE_APPROVED,
    EXECUTION_MODE_MOCK,
)
from app.scheduler_service import SchedulerService
from app.customer_generation_orchestrator import is_mock_or_invalid_media_artifact


class TestF01ToF08Hardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- F-01 & F-04: Audio Cache & Exception Logging ---
    def test_F01_and_F04_audio_cache_eviction_on_invalid_file(self):
        """F-04: Audio cache evicts invalid/corrupted files and only records files that pass QA."""
        import hashlib
        engine = AudioLocalizationEngine(audio_dir=self.work_path)

        text = "Clean test sentence"
        lang = "en"
        text_hash = hashlib.md5(f"{text}_{lang}".encode("utf-8")).hexdigest()

        # Write a dummy corrupt file to cache
        corrupt_audio = self.work_path / "corrupt.mp3"
        corrupt_audio.write_bytes(b"corrupted_garbage_bytes_not_audio")
        engine._cache[text_hash] = str(corrupt_audio)

        # Synthesize with the same text and lang should detect corrupt file, evict it, and generate valid audio
        result = engine.synthesize_speech(
            scene_index=1,
            text=text,
            target_lang=lang,
            expected_duration_sec=3.0,
            provider="auto",
        )
        self.assertTrue(result.passed_qa)
        # Old corrupt file was evicted, new valid audio is cached
        cached_path = Path(engine._cache.get(text_hash, ""))
        self.assertNotEqual(str(cached_path), str(corrupt_audio))
        self.assertTrue(cached_path.is_file())

    # --- F-02: Publishing Default Mock Provider ---
    def test_F02_publishing_provider_requires_live_in_production(self):
        """F-02: In production, get_publish_provider raises RuntimeError instead of silently downgrading to mock."""
        with patch("app.config.is_production_runtime", return_value=True):
            with self.assertRaises(RuntimeError) as ctx:
                get_publish_provider(
                    "youtube",
                    allow_live=False,
                    require_live_in_production=True,
                )
            self.assertIn("LIVE_PUBLISH_REQUIRED", str(ctx.exception))

    def test_F02_publishing_provider_resolves_live_with_credentials(self):
        """F-02: resolve_publish_provider returns YouTubeDataApiProvider when credentials exist."""
        channel_with_oauth = {
            "platform": "youtube",
            "oauth_token": "valid_mock_token_for_test",
        }
        with patch("app.config.is_production_runtime", return_value=True):
            prov = resolve_publish_provider("youtube", channel=channel_with_oauth)
            self.assertIsInstance(prov, YouTubeDataApiProvider)

    # --- F-03: Mock Render Provider Boundary ---
    def test_F03_mock_render_artifacts_strictly_rejected(self):
        """F-03: is_mock_or_invalid_media_artifact strictly rejects mock byte headers."""
        mock_file = self.work_path / "fake.mp4"
        mock_file.write_bytes(b"ftypisommock_video_data_fake_stream_bytes")
        is_mock, reason = is_mock_or_invalid_media_artifact(mock_file)
        self.assertTrue(is_mock)
        self.assertIn("mock_marker_detected", reason)

    # --- F-04 & F-07: Thumbnail Cache & Platform Upload Limits ---
    def test_F04_and_F07_thumbnail_platform_upload_limits(self):
        """F-07: Rejects thumbnails exceeding YouTube 2MB limit or with invalid dimensions."""
        # 1. Test oversize thumbnail (> 2MB)
        oversize_thumb = self.work_path / "oversize.jpg"
        oversize_thumb.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * (2 * 1024 * 1024 + 100))
        res_oversize = inspect_thumbnail_image(oversize_thumb)
        self.assertFalse(res_oversize["valid"])
        self.assertIn("2MB upload limit", res_oversize["error"])

        # 2. Test valid JPEG conforms to upload limits
        valid_thumb = self.work_path / "valid.jpg"
        img = Image.new("RGB", (1280, 720), color=(100, 150, 200))
        img.save(valid_thumb, format="JPEG", quality=90)
        res_valid = inspect_thumbnail_image(valid_thumb)
        self.assertTrue(res_valid["valid"])
        self.assertEqual(res_valid["width"], 1280)
        self.assertEqual(res_valid["height"], 720)
        self.assertEqual(res_valid["aspect_ratio"], "16:9")

    def test_F04_thumbnail_cache_eviction_on_invalid_file(self):
        """F-04: Thumbnail cache evicts corrupted cached entries."""
        import hashlib
        engine = MetadataThumbnailEngine(thumbs_dir=self.work_path)

        topic = "Science Insights"
        fmt = "long"
        prompt = (
            f"Hyper-realistic, viral YouTube thumbnail for '{topic}', dramatic lighting, "
            f"high contrast, expressive face or central intrigue object, glowing neon accents, 8k resolution"
        )
        thumb_hash = hashlib.md5(f"{prompt}_{fmt}".encode("utf-8")).hexdigest()

        corrupt_thumb = self.work_path / "corrupt.jpg"
        corrupt_thumb.write_bytes(b"not_a_valid_image")
        engine._cache[thumb_hash] = str(corrupt_thumb)

        pkg = engine.generate_package(
            topic_title=topic,
            niche="education",
            video_format=fmt,
            language="en",
        )
        self.assertTrue(pkg.passed_qa)
        self.assertTrue(Path(pkg.thumbnail_image_path).is_file())
        self.assertNotEqual(str(pkg.thumbnail_image_path), str(corrupt_thumb))

    # --- F-05: Customer Job Automation Boundary ---
    def test_F05_execution_mode_defaults_to_approved_in_production(self):
        """F-05: In production runtime, execution mode defaults to EXECUTION_MODE_APPROVED."""
        with patch("app.config.is_production_runtime", return_value=True):
            mode = resolve_execution_mode()
            self.assertEqual(mode, EXECUTION_MODE_APPROVED)

    def test_F05_execution_mode_defaults_to_mock_in_development(self):
        """F-05: In development runtime, execution mode defaults to EXECUTION_MODE_MOCK."""
        with patch("app.config.is_production_runtime", return_value=False):
            mode = resolve_execution_mode()
            self.assertEqual(mode, EXECUTION_MODE_MOCK)

    # --- F-06: Scheduler Dependency & Degraded Mode ---
    def test_F06_scheduler_operates_in_degraded_mode_without_apscheduler(self):
        """F-06: SchedulerService starts safely in degraded mode when APScheduler is missing."""
        with patch("app.scheduler_service.HAS_APSCHEDULER", False):
            with patch("app.scheduler_service.BackgroundScheduler", None):
                service = SchedulerService()
                self.assertFalse(service.is_available)
                self.assertIsNone(service.scheduler)
                service.start()
                self.assertFalse(service._started)

    # --- F-08: Final QA AV Sync Drift Inspection ---
    def test_F08_final_qa_detects_av_sync_drift(self):
        """F-08: _local_agent_final_qa rejects media where video and audio durations drift by > 3.0s."""
        valid_video = self.work_path / "av_test.mp4"
        valid_video.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 2000)

        drift_media_info = {
            "valid": True,
            "container_format": "mov,mp4,m4a,3gp,3g2,mj2",
            "has_video": True,
            "has_audio": True,
            "video_codec": "h264",
            "audio_codec": "aac",
            "resolution": "1080x1920",
            "width": 1080,
            "height": 1920,
            "duration_sec": 4.0,
            "video_duration_sec": 4.0,
            "audio_duration_sec": 8.0,  # 4s drift (> 3s limit)
        }

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_video),
            media_info=drift_media_info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("Audio-video desynchronization failure", msg)


if __name__ == "__main__":
    unittest.main()
