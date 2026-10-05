"""T007 — Visual QA frame evidence tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.compose import ffmpeg_bin
from pipeline.visual_qa import (
    evaluate_visual_qa,
    extract_evidence_frames,
    visual_qa_blocks_ship,
)
import subprocess


def _make_clip(dest: Path, *, mode: str = "motion", seconds: float = 2.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    if mode == "static":
        filt = "color=c=0x446688:s=320x240:d=2"
        cmd = [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            filt,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    elif mode == "black":
        filt = "color=c=black:s=320x240:d=2"
        cmd = [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            filt,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    else:
        # Motion: hue cycle / color source with geq changing over time
        cmd = [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=24:duration=2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg fixture failed: {(r.stderr or '')[-300:]}")
    return dest


class VisualQATests(unittest.TestCase):
    def test_extract_frames(self):
        with tempfile.TemporaryDirectory() as td:
            clip = _make_clip(Path(td) / "m.mp4", mode="motion")
            ex = extract_evidence_frames(clip, Path(td) / "frames")
            self.assertTrue(ex["ok"], ex)
            self.assertGreaterEqual(ex["extracted"], 3)

    def test_static_fails(self):
        with tempfile.TemporaryDirectory() as td:
            clip = _make_clip(Path(td) / "s.mp4", mode="static")
            qa = evaluate_visual_qa(clip, work_dir=td)
            self.assertEqual(qa["verdict"], "FAIL", qa)
            self.assertTrue(qa["static_visual"] or "static_visual" in str(qa.get("issues")))
            self.assertTrue(visual_qa_blocks_ship(qa))

    def test_motion_without_vlm_is_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            clip = _make_clip(Path(td) / "m.mp4", mode="motion")
            qa = evaluate_visual_qa(clip, work_dir=td, dialogue="excavators open trenches")
            self.assertEqual(qa["verdict"], "UNKNOWN", qa)
            self.assertTrue(qa["pixel_evidence"])
            self.assertTrue(qa["motion_present"])
            self.assertTrue(visual_qa_blocks_ship(qa))  # UNKNOWN ≠ PASS

    def test_vlm_pass(self):
        with tempfile.TemporaryDirectory() as td:
            clip = _make_clip(Path(td) / "m.mp4", mode="motion")
            qa = evaluate_visual_qa(
                clip,
                work_dir=td,
                vlm_result={
                    "subject_match": 0.9,
                    "action_match": 0.8,
                    "claim_match": 0.85,
                    "continuity_match": 0.7,
                    "wrong_subject": False,
                    "generic_broll": False,
                },
            )
            self.assertEqual(qa["verdict"], "PASS", qa)
            self.assertTrue(qa["passed"])
            self.assertFalse(visual_qa_blocks_ship(qa))

    def test_missing_media_fail(self):
        qa = evaluate_visual_qa(Path("no_such_file_xyz.mp4"))
        self.assertEqual(qa["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
