"""T009 — FFmpeg executor hang watchdog tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ffmpeg_exec import run_ffmpeg, safe_ffprobe_duration


class FFmpegExecTests(unittest.TestCase):
    def test_color_clip_ok(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.mp4"
            r = run_ffmpeg(
                [
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=160x120:d=0.4",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=stereo",
                    "-t",
                    "0.4",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(out),
                ],
                timeout_sec=60,
            )
            self.assertTrue(r.ok, r.stderr[-400:])
            self.assertFalse(r.timed_out)
            self.assertGreater(safe_ffprobe_duration(out), 0.2)

    def test_timeout_kills(self):
        # lavfi color with huge duration + tiny timeout → TimeoutExpired path
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "hang.mp4"
            r = run_ffmpeg(
                [
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=320x240:d=3600",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(out),
                ],
                timeout_sec=1.0,
            )
            self.assertFalse(r.ok)
            self.assertTrue(r.timed_out or r.classified == "timeout")
            self.assertEqual(r.classified, "timeout")

    def test_missing_probe_zero(self):
        self.assertEqual(safe_ffprobe_duration(Path("nope_missing_xyz.mp4")), 0.0)


if __name__ == "__main__":
    unittest.main()
