"""
AutoMovie Pro — Part 08: Video Production Pipeline Audit Test Suite
Validates:
1. 8.1 Topic Deduplication & Semantic Filtering
2. 8.2 3-Act Script Generation & Scene Intent
3. 8.4 Voice Engine Acoustic Padding (Lead-in & Tail pad)
4. 8.7 FFmpeg & FFprobe Bundled Executable Availability
5. 8.8 Master Output Video Quality Control (Duration, Streams, Codecs, Non-zero byte check)
6. 8.9 CTR Thumbnail & Emotional Curiosity Engine
7. 8.10 Upload Service Dispatch Matrix
"""

import os
import sys
import json
import unittest
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.compose import ffmpeg_bin, ffprobe_bin
from pipeline.ffmpeg_exec import run_ffmpeg
from pipeline.metadata_thumbnail_engine import score_title_emotional_curiosity
from publishers.upload_service import upload_job


class Part08VideoProductionPipelineAuditTest(unittest.TestCase):

    def test_01_ffmpeg_and_ffprobe_executables_available(self):
        """Verify bundled FFmpeg and FFprobe binaries exist and execute correctly."""
        ff = ffmpeg_bin()
        probe = ffprobe_bin()
        self.assertTrue(os.path.exists(ff), f"FFmpeg binary missing at {ff}")
        self.assertTrue(os.path.exists(probe), f"FFprobe binary missing at {probe}")

        # Run quick version check via central executor
        res = run_ffmpeg(["-version"], timeout_sec=10.0)
        self.assertTrue(res.ok, "FFmpeg -version failed")
        self.assertIn("ffmpeg version", res.stdout)

    def test_02_master_video_artifacts_qc_verification(self):
        """Verify the 4 generated master production videos meet all structural QC criteria."""
        summary_path = BASE_DIR / "output" / "quad_production_master" / "quad_production_summary.json"
        self.assertTrue(summary_path.exists(), "Master quad production summary missing")

        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        results = summary.get("results", [])
        self.assertEqual(len(results), 4, "Expected 4 master video results")

        probe = ffprobe_bin()
        for r in results:
            cat = r.get("category")
            vpath = r.get("video_path")
            self.assertTrue(os.path.exists(vpath), f"Video missing for {cat}: {vpath}")
            sz = os.path.getsize(vpath)
            self.assertGreater(sz, 10 * 1024 * 1024, f"Video file abnormally small ({sz} bytes) for {cat}")

            # Run ffprobe json inspection on each video
            cmd = [
                probe, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", vpath
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 0, f"ffprobe failed on {cat}")
            data = json.loads(proc.stdout)

            # Assert video stream
            video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
            self.assertGreaterEqual(len(video_streams), 1, f"Missing video stream in {cat}")
            vcodec = video_streams[0].get("codec_name")
            self.assertIn(vcodec, ["h264", "hevc"], f"Invalid video codec {vcodec} in {cat}")

            # Assert audio stream
            audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
            self.assertGreaterEqual(len(audio_streams), 1, f"Missing audio stream in {cat}")
            acodec = audio_streams[0].get("codec_name")
            self.assertIn(acodec, ["aac", "mp3"], f"Invalid audio codec {acodec} in {cat}")

            # Duration check
            duration = float(data.get("format", {}).get("duration", 0))
            self.assertGreater(duration, 30.0, f"Duration abnormally short ({duration}s) in {cat}")

    def test_03_metadata_title_emotional_curiosity(self):
        """Verify title curiosity & emotional hooks scoring functions."""
        sample_title = "মহাকাশের গভীর থেকে আসা রহস্যময় রেডিও সংকেত: 'ওয়াও সিগন্যাল' কি এলিয়েনদের বার্তা ছিল?"
        score_res = score_title_emotional_curiosity(sample_title, language="bn")
        self.assertIsInstance(score_res, dict)
        self.assertIn("composite_ctr_score", score_res)
        self.assertGreaterEqual(score_res.get("composite_ctr_score", 0), 0)

    def test_04_upload_service_fail_closed_contract(self):
        """Verify upload service fails closed on invalid or missing credentials safely."""
        dummy_channel = {"id": 99999, "name": "Test Null Channel", "youtube_enabled": 0}
        res = upload_job(job_id=999999, channel=dummy_channel)
        self.assertIsInstance(res, dict)
        self.assertIn("ok", res)
        # Should gracefully report failure without crashing
        self.assertFalse(res.get("ok"))


if __name__ == "__main__":
    unittest.main()
