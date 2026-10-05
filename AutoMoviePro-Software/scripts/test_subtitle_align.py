"""T008 — Subtitle alignment evaluation tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.subtitle_align import (
    cues_to_srt,
    evaluate_alignment_methods,
    proportional_cues,
    validate_cues,
    whisperx_available,
)


class SubtitleAlignTests(unittest.TestCase):
    def test_proportional_valid(self):
        text = (
            "Tonight we dig into the lost library. "
            "Excavators found ash layers under the aisle. "
            "The mystery still rewrites the map."
        )
        cues = proportional_cues(text, 12.0)
        self.assertGreaterEqual(len(cues), 2)
        v = validate_cues(cues, duration_sec=12.0, spoken_text=text)
        self.assertTrue(v["passed"], v)

    def test_overlap_detected(self):
        bad = [
            {"index": 1, "start": 0.0, "end": 2.0, "text": "a"},
            {"index": 2, "start": 1.5, "end": 3.0, "text": "b"},
        ]
        v = validate_cues(bad, duration_sec=5.0)
        self.assertFalse(v["passed"])
        self.assertTrue(any("overlap" in i for i in v["issues"]))

    def test_srt_roundtrip_shape(self):
        cues = proportional_cues("One sentence here. Two sentence there.", 5.0)
        srt = cues_to_srt(cues)
        self.assertIn("-->", srt)
        self.assertIn("One sentence", srt)

    def test_evaluation_decision_without_whisperx(self):
        ev = evaluate_alignment_methods(
            "Ancient ruins still hold unanswered questions about builders.",
            8.0,
        )
        self.assertIn(ev["decision"], {
            "DEFER_WHISPERX_KEEP_PROPORTIONAL",
            "KEEP_PROPORTIONAL_PRIMARY",
            "WRAP_WHISPERX_WITH_FALLBACK",
        })
        self.assertTrue(ev["proportional"]["validation"]["passed"])
        # Environment may or may not have whisperx; just ensure key exists
        self.assertIn("whisperx_installed", ev)
        _ = whisperx_available()


if __name__ == "__main__":
    unittest.main()
