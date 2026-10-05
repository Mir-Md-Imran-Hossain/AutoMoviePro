"""Wave 3 feature unit tests."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.job_context import budget_consume, set_job_work
from pipeline.api_budget import ApiBudget
from pipeline.plan_quality import enforce_plan_quality
from pipeline.fact_pack import build_fact_pack
from pipeline.robot_detector import robot_score
from pipeline.comment_classifier import classify_comment
from pipeline.watchdog import Watchdog
from pipeline.prompt_registry import bump_prompt, get_prompt_meta
from pipeline.subtitle_align import proportional_cues, cues_to_srt


class Wave3Tests(unittest.TestCase):
    def test_budget_via_context(self):
        with tempfile.TemporaryDirectory() as td:
            set_job_work(td)
            ApiBudget(Path(td), limits={"max_tts_calls": 1})
            self.assertTrue(budget_consume("tts")["ok"])
            self.assertFalse(budget_consume("tts")["ok"])
            set_job_work(None)

    def test_plan_quality(self):
        plan = {
            "topic": "Lost Library of Alexandria",
            "scenes": [
                {"narration": "Ash layers dated by carbon samples under a collapsed aisle."},
                {"narration": "Tonight we dig into mysteries of the stacks."},
            ],
        }
        pack = build_fact_pack(
            "Lost Library of Alexandria",
            notes="Ash layers dated by carbon samples under a collapsed aisle.",
        )
        out = enforce_plan_quality(plan, pack)
        self.assertIn("speech_audit", out)
        self.assertIn("quality_enforcement", out)

    def test_robot_generic_opener_fails(self):
        r = robot_score(["In today's video we will unlock seamless revolutionary synergy."])
        self.assertFalse(r["passed"])

    def test_robot_specific_passes(self):
        r = robot_score(
            [
                "Excavators logged ash layers dated 48 BCE under aisle three.",
                "That single trench rewrote the map.",
            ]
        )
        self.assertTrue(r["passed"], r)

    def test_comment_classifier(self):
        self.assertEqual(classify_comment("How much does it cost?")["category"], "PRICE")
        self.assertEqual(classify_comment("Amazing work!")["category"], "PRAISE")
        self.assertEqual(classify_comment("http://spam.example buy now")["category"], "SPAM")
        self.assertFalse(classify_comment("Amazing work!")["needs_llm"])

    def test_watchdog_hang(self):
        with tempfile.TemporaryDirectory() as td:
            w = Watchdog("t", deadline_sec=0.2, work_dir=Path(td))
            time.sleep(0.35)
            c = w.check()
            self.assertTrue(c["hung"])
            self.assertEqual(c["state"], "HANG_DETECTED")

    def test_prompt_registry(self):
        bump_prompt("director_system", version="v13", change_reason="test")
        self.assertEqual(get_prompt_meta("director_system")["version"], "v13")

    def test_write_srt_align_shape(self):
        srt = cues_to_srt(proportional_cues("Hello world. Second line here.", 4.0))
        self.assertIn("-->", srt)


if __name__ == "__main__":
    unittest.main()
