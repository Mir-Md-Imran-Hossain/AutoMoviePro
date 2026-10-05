"""Comprehensive unit & integration tests for Steps 8 & 9: Final Video Composition, Branding & Cleanup.
Standard library unittest implementation (zero external dependency).

Tests:
- Production real FFmpeg rendering with real video/audio streams
- Media inspection (ffprobe) container, codec, resolution, and duration validation
- Short vs. Long full video composition
- Branding integration (Logo watermark & Intro video placement)
- Local agent frame-by-frame and audio-video sync QA
- Automated temporary files cleanup (garbage collection)
- Separation of Production and Simulation renderers
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from pipeline.compose import ffmpeg_bin, make_color_clip
from pipeline.final_video_composer import (
    FinalVideoComposer,
    FinalVideoResult,
    ProductionVideoComposer,
    SimulatedVideoComposer,
    VideoCompositionConfig,
    inspect_media,
    verify_audio_decode,
    verify_frame_decode,
)


class TestFinalVideoComposer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp_dir.name) / "Output"
        self.temp_dir = Path(self.tmp_dir.name) / "temp"
        self.composer = FinalVideoComposer(output_dir=self.out_dir, temp_dir=self.temp_dir)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_production_real_video_composition(self):
        """Tests real FFmpeg production rendering with actual media clips."""
        # Create 2 real source clips using ffmpeg make_color_clip
        clip1 = Path(self.tmp_dir.name) / "real_v1.mp4"
        clip2 = Path(self.tmp_dir.name) / "real_v2.mp4"
        make_color_clip(clip1, seconds=1.0, size="1080x1920")
        make_color_clip(clip2, seconds=1.0, size="1080x1920")

        config = VideoCompositionConfig(
            title="Real Production Composition Test",
            video_format="short",
            language="en",
            scenes_count=2,
            enable_bgm_ducking=False,
            hardware_acceleration="cpu",
            mode="production",
        )

        res = self.composer.compose_full_video(
            config=config,
            scene_visual_paths=[str(clip1), str(clip2)],
            scene_audio_paths=[],
            clean_temp_after_success=True,
        )

        self.assertFalse(res.is_simulated)
        self.assertTrue(res.passed_final_qa)
        self.assertEqual(res.resolution, "1080x1920")
        self.assertTrue(Path(res.final_output_path).exists())
        self.assertGreater(res.file_size_bytes, 5000)
        self.assertGreaterEqual(res.duration_sec, 1.8)
        self.assertIn("mp4", res.container_format.lower())
        self.assertIn("h264", res.video_codec.lower())
        self.assertIn("aac", res.audio_codec.lower())
        self.assertGreaterEqual(res.temp_files_cleaned, 2)

    def test_production_with_watermark_logo(self):
        """Tests real production rendering with a logo watermark overlay."""
        clip1 = Path(self.tmp_dir.name) / "wm_v1.mp4"
        make_color_clip(clip1, seconds=1.0, size="1080x1920")

        # Generate a small PNG watermark image via ffmpeg
        logo_png = Path(self.tmp_dir.name) / "logo.png"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:d=0.1",
            "-frames:v",
            "1",
            str(logo_png),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        config = VideoCompositionConfig(
            title="Watermark Logo Test",
            video_format="short",
            language="en",
            scenes_count=1,
            logo_watermark_path=str(logo_png),
            enable_bgm_ducking=False,
            hardware_acceleration="cpu",
            mode="production",
        )

        res = self.composer.compose_full_video(
            config=config,
            scene_visual_paths=[str(clip1)],
            scene_audio_paths=[],
            clean_temp_after_success=True,
        )

        self.assertFalse(res.is_simulated)
        self.assertTrue(res.passed_final_qa)
        self.assertIn("logo watermark verified", res.qa_report.lower())

    def test_media_inspection_and_validation(self):
        """Tests ffprobe media inspection on valid vs 0-byte/corrupted files."""
        # Valid clip
        valid_clip = Path(self.tmp_dir.name) / "valid.mp4"
        make_color_clip(valid_clip, seconds=1.0, size="1920x1080")
        info = inspect_media(valid_clip)
        self.assertTrue(info["valid"])
        self.assertTrue(info["has_video"])
        self.assertTrue(info["has_audio"])
        self.assertTrue(info["is_valid_mp4"])
        self.assertEqual(info["resolution"], "1920x1080")
        self.assertGreaterEqual(info["duration_sec"], 0.9)

        # Zero-byte invalid file
        zero_file = Path(self.tmp_dir.name) / "empty.mp4"
        zero_file.touch()
        zero_info = inspect_media(zero_file)
        self.assertFalse(zero_info["valid"])
        self.assertEqual(zero_info["file_size_bytes"], 0)

        # Missing file
        missing_info = inspect_media(Path(self.tmp_dir.name) / "non_existent.mp4")
        self.assertFalse(missing_info["valid"])

    def test_qa_rejects_corrupted_media(self):
        """Tests that local agent QA rejects 0-byte or invalid containers."""
        corrupt_file = Path(self.tmp_dir.name) / "corrupt.mp4"
        corrupt_file.write_bytes(b"NOT_A_VALID_MP4")
        info = inspect_media(corrupt_file)

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(corrupt_file),
            media_info=info,
            format_type="short",
            has_logo=False,
            has_intro=False,
            is_simulated=False,
        )
        self.assertFalse(passed)
        self.assertIn("validity failure", msg.lower())

    def test_short_video_composition_simulated(self):
        """Composes a short video in simulation mode, validates branding, and ensures temp cleanup."""
        config = VideoCompositionConfig(
            title="5 AI Inventions",
            video_format="short",
            language="bn",
            scenes_count=5,
            intro_video_path="/assets/intro.mp4",
            logo_watermark_path="/assets/logo.png",
            enable_bgm_ducking=True,
            hardware_acceleration="qsv",
            simulate=True,
        )

        res = self.composer.compose_full_video(
            config=config,
            scene_visual_paths=["v1.mp4", "v2.mp4", "v3.mp4", "v4.mp4", "v5.mp4"],
            scene_audio_paths=["a1.mp3", "a2.mp3", "a3.mp3", "a4.mp3", "a5.mp3"],
            clean_temp_after_success=True,
        )

        self.assertTrue(res.is_simulated)
        self.assertTrue(res.passed_final_qa)
        self.assertEqual(res.resolution, "1080x1920")
        self.assertTrue(Path(res.final_output_path).exists())
        self.assertIn("logo watermark verified", res.qa_report.lower())
        self.assertIn("intro successfully placed", res.qa_report.lower())
        self.assertEqual(res.temp_files_cleaned, 5)

    def test_long_video_composition_simulated(self):
        """Composes a 16:9 widescreen long video in simulation mode."""
        config = VideoCompositionConfig(
            title="Complete History of Rome",
            video_format="long",
            language="en",
            scenes_count=12,
            logo_watermark_path="/assets/logo.png",
            simulate=True,
        )

        res = self.composer.compose_full_video(
            config=config,
            scene_visual_paths=[f"v{i}.mp4" for i in range(12)],
            scene_audio_paths=[f"a{i}.mp3" for i in range(12)],
            clean_temp_after_success=True,
        )

        self.assertTrue(res.is_simulated)
        self.assertTrue(res.passed_final_qa)
        self.assertEqual(res.resolution, "1920x1080")
        self.assertEqual(res.duration_sec, 420.0)

    def test_separation_of_production_and_simulation_renderers(self):
        """Validates that ProductionVideoComposer and SimulatedVideoComposer are cleanly separated."""
        prod = ProductionVideoComposer(self.out_dir, self.temp_dir)
        sim = SimulatedVideoComposer(self.out_dir, self.temp_dir)

        self.assertIsInstance(prod, ProductionVideoComposer)
        self.assertIsInstance(sim, SimulatedVideoComposer)

        # Calling production directly on missing input files raises FileNotFoundError
        config = VideoCompositionConfig(
            title="Missing Files Test",
            video_format="short",
            language="en",
            scenes_count=1,
            mode="production",
        )
        with self.assertRaises(FileNotFoundError):
            prod.compose(
                config=config,
                scene_visual_paths=["non_existent_clip.mp4"],
                scene_audio_paths=[],
            )

    def test_qa_rejects_missing_video_track(self):
        """Validates that QA rejects media without a video stream."""
        valid_clip = Path(self.tmp_dir.name) / "test_no_v.mp4"
        make_color_clip(valid_clip, seconds=1.0, size="1080x1920")
        info = inspect_media(valid_clip)
        info["has_video"] = False
        info["video_codec"] = ""

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_clip),
            media_info=info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("video track is missing", msg.lower())

    def test_qa_rejects_missing_audio_track(self):
        """Validates that QA rejects media without an audio stream."""
        valid_clip = Path(self.tmp_dir.name) / "test_no_a.mp4"
        make_color_clip(valid_clip, seconds=1.0, size="1080x1920")
        info = inspect_media(valid_clip)
        info["has_audio"] = False
        info["audio_codec"] = ""

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_clip),
            media_info=info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("audio track is missing", msg.lower())

    def test_qa_rejects_invalid_codecs(self):
        """Validates that QA rejects unrecognized video or audio codecs."""
        valid_clip = Path(self.tmp_dir.name) / "test_codecs.mp4"
        make_color_clip(valid_clip, seconds=1.0, size="1080x1920")
        info = inspect_media(valid_clip)

        # Invalid video codec
        bad_v_info = dict(info)
        bad_v_info["video_codec"] = "unknown_raw_format"
        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_clip),
            media_info=bad_v_info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("invalid video codec", msg.lower())

        # Invalid audio codec
        bad_a_info = dict(info)
        bad_a_info["audio_codec"] = "unknown_noise_format"
        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_clip),
            media_info=bad_a_info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("invalid audio codec", msg.lower())

    def test_qa_rejects_aspect_ratio_mismatch(self):
        """Validates that short format rejects horizontal 16:9 video."""
        horiz_clip = Path(self.tmp_dir.name) / "horiz.mp4"
        make_color_clip(horiz_clip, seconds=1.0, size="1920x1080")
        info = inspect_media(horiz_clip)

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(horiz_clip),
            media_info=info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("resolution mismatch", msg.lower())

    def test_qa_rejects_duration_budget_exceeded(self):
        """Validates that short format rejects durations exceeding 90 seconds."""
        valid_clip = Path(self.tmp_dir.name) / "test_dur.mp4"
        make_color_clip(valid_clip, seconds=1.0, size="1080x1920")
        info = dict(inspect_media(valid_clip))
        info["duration_sec"] = 120.5

        passed, msg = FinalVideoComposer._local_agent_final_qa(
            final_path=str(valid_clip),
            media_info=info,
            format_type="short",
            require_frame_decode=False,
            require_audio_decode=False,
        )
        self.assertFalse(passed)
        self.assertIn("exceeds 90s limit", msg.lower())

    def test_frame_and_audio_decode_verification(self):
        """Validates verify_frame_decode and verify_audio_decode on real generated media."""
        valid_clip = Path(self.tmp_dir.name) / "decode_valid.mp4"
        make_color_clip(valid_clip, seconds=1.5, size="1080x1920")

        frame_ok, frame_msg = verify_frame_decode(valid_clip, frames_to_decode=5)
        self.assertTrue(frame_ok, f"Frame decode failed: {frame_msg}")

        audio_ok, audio_msg = verify_audio_decode(valid_clip, packets_to_decode=50)
        self.assertTrue(audio_ok, f"Audio decode failed: {audio_msg}")


if __name__ == "__main__":
    unittest.main()

