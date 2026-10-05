#!/usr/bin/env python3
"""RCP-06B — Duration contract (no paid API / no generation)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from pipeline.duration_budget import (
    assert_all_planned_scenes_produced,
    contract_from_plan,
    planned_scene_count,
    planned_scene_count_for_contract,
    raise_if_budget_would_drop_scenes,
    resolve_duration_contract,
    trim_would_cut_coverage,
    validate_timeline_against_contract,
)


class Rcp06bDurationContractTests(unittest.TestCase):
    def test_01_settings_expose_target_and_max(self):
        self.assertEqual(settings.short_target_seconds, 60)
        self.assertEqual(settings.short_max_seconds, 120)
        self.assertEqual(settings.long_target_seconds, 180)
        self.assertEqual(settings.long_max_seconds, 300)
        self.assertLess(settings.short_target_seconds, settings.short_max_seconds)
        self.assertLessEqual(settings.long_target_seconds, settings.long_max_seconds)

    def test_02_short_long_contracts_distinct(self):
        s = resolve_duration_contract("short")
        l = resolve_duration_contract("long")
        self.assertEqual(s["target_seconds"], 60)
        self.assertEqual(s["max_seconds"], 120)
        self.assertEqual(l["target_seconds"], 180)
        self.assertEqual(l["max_seconds"], 300)
        self.assertNotEqual(s["max_seconds"], l["max_seconds"])

    def test_03_target_clamped_to_max(self):
        c = resolve_duration_contract("short", target_seconds=999, max_seconds=90)
        self.assertEqual(c["max_seconds"], 90)
        self.assertEqual(c["target_seconds"], 90)

    def test_04_script_and_runtime_share_authority(self):
        """Planning uses target; runtime ceiling is max — same resolver."""
        c = resolve_duration_contract("short")
        plan_n = planned_scene_count(c["target_seconds"], "short")
        ceiling_n = planned_scene_count(c["max_seconds"], "short")
        self.assertGreaterEqual(ceiling_n, plan_n)
        self.assertEqual(planned_scene_count_for_contract(c), plan_n)

    def test_05_timeline_exceeding_max_blocks(self):
        c = resolve_duration_contract("short")
        blocks = validate_timeline_against_contract(
            dialogue_duration_sec=200.0,
            visual_duration_sec=200.0,
            contract=c,
        )
        self.assertTrue(any("dialogue_exceeds_max_duration" in b for b in blocks))
        self.assertTrue(any("visual_exceeds_max_duration" in b for b in blocks))

    def test_06_timeline_within_max_ok(self):
        c = resolve_duration_contract("short")
        blocks = validate_timeline_against_contract(
            dialogue_duration_sec=40.0,
            visual_duration_sec=40.0,
            contract=c,
        )
        self.assertEqual(blocks, [])

    def test_07_silent_break_replaced_by_fail(self):
        with self.assertRaises(RuntimeError) as ctx:
            raise_if_budget_would_drop_scenes(
                scene_index=2,
                scene_count=6,
                accumulated_sec=119.0,
                max_seconds=120,
            )
        self.assertIn("duration_budget_exhausted_with_scenes_remaining", str(ctx.exception))

    def test_08_last_scene_may_reach_ceiling(self):
        # No remaining scenes → no raise
        raise_if_budget_would_drop_scenes(
            scene_index=5,
            scene_count=6,
            accumulated_sec=119.0,
            max_seconds=120,
        )

    def test_09_dropped_scenes_assert(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_all_planned_scenes_produced(planned_scene_count_n=6, produced_scene_count=3)
        self.assertIn("duration_budget_dropped_scenes", str(ctx.exception))
        assert_all_planned_scenes_produced(planned_scene_count_n=6, produced_scene_count=6)

    def test_10_trim_would_cut_coverage(self):
        self.assertTrue(trim_would_cut_coverage(130.0, 120.0))
        self.assertFalse(trim_would_cut_coverage(121.0, 120.0))  # within 2.5s slack

    def test_11_contract_from_plan(self):
        c = contract_from_plan({"video_type": "long", "target_duration_sec": 200})
        self.assertEqual(c["video_type"], "long")
        self.assertEqual(c["target_seconds"], 200)
        self.assertEqual(c["max_seconds"], 300)

    def test_12_pipeline_no_silent_break(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("Reached max duration budget at scene", src)
        self.assertIn("raise_if_budget_would_drop_scenes", src)
        self.assertIn("assert_all_planned_scenes_produced", src)
        self.assertIn("final_trim_would_cut_coverage", src)
        self.assertIn("DURATION_CONTRACT.json", src)

    def test_13_rcp02_coverage_gate_intact(self):
        src = (ROOT / "app" / "customer_production_plan.py").read_text(encoding="utf-8")
        self.assertIn("PRODUCTION_INCOMPLETE:missing_visual_for_dialogue", src)
        self.assertIn("visual_timeline_shorter_than_dialogue", src)
        self.assertIn("validate_timeline_against_contract", src)

    def test_14_rcp06a_semantic_intact(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("SEMANTIC_COVERAGE_BLOCKED:UNKNOWN", src)
        from pipeline.quality.publishability import evaluate_publishability

        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            semantic_status="UNKNOWN",
            multimodal_status="PASS",
            artifact_status="PASS",
            render_status="PASS",
        )
        self.assertFalse(pub["publishable"])

    def test_15_readiness_blocks_over_max(self):
        from app.customer_production_plan import evaluate_generation_readiness

        plan = {
            "dialogue_segments": [
                {"dialogue_id": "1", "duration_sec": 80},
                {"dialogue_id": "2", "duration_sec": 80},
            ],
            "visual_beats": [
                {"dialogue_id": "1", "timing": {"duration_sec": 80}},
                {"dialogue_id": "2", "timing": {"duration_sec": 80}},
            ],
            "narrative_beats": [{"id": "n1"}, {"id": "n2"}],
            "continuity": {"ok": True},
            "video_type": "short",
            "localization": {},
            "generation_modes": {},
        }
        out = evaluate_generation_readiness(plan)
        self.assertFalse(out.get("ready"))
        joined = " ".join(out.get("blocks") or [])
        self.assertIn("exceeds_max_duration", joined)


if __name__ == "__main__":
    unittest.main()
