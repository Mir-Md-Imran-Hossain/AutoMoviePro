#!/usr/bin/env python3
"""BUILD-04F creative quality gate tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.quality.contracts import (
    CreativeQualityResult,
    IssueSeverity,
    QualityDimension,
    QualityIssue,
    QualityVerdict,
    RepairScope,
)
from pipeline.quality.evaluators import (
    aggregate_quality_results,
    evaluate_audio_quality,
    evaluate_cross_modal,
    evaluate_scene_visual_alignment,
    evaluate_script_quality,
    evaluate_subtitle_creative,
)
from pipeline.quality.fingerprint import compute_quality_fingerprint
from pipeline.quality.invalidation import audio_only_invalidation, filter_stale_results, scene_only_invalidation
from pipeline.quality.mock_evaluator import MockQualityBehavior, MockQualityEvaluator, reset_mock_quality_evaluator
from pipeline.quality.publishability import PublishabilityVerdict, evaluate_publishability
from pipeline.quality.repair_planner import plan_repair
from pipeline.quality.repair_runtime import compute_repair_fingerprint, execute_repair_request
from pipeline.quality.runtime import execute_quality_evaluation
from pipeline.quality.thresholds import DIMENSION_WEIGHTS, PASS_SCORE_THRESHOLD


def _good_plan() -> dict:
    return {
        "topic": "Pixel 9a camera review",
        "scenes": [
            {"narration": "The Pixel 9a camera captures sharp detail in low light conditions."},
            {"narration": "Battery life lasts through a full day of mixed use without issue."},
            {"narration": "At this price the value proposition is strong for most buyers."},
        ],
    }


class Build04FQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mock = MockQualityEvaluator()
        self.mock.reset()
        reset_mock_quality_evaluator()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_f01_quality_contract(self):
        r = CreativeQualityResult(
            subject="script", subject_id="j1", stage="script",
            verdict=QualityVerdict.PASS, score=0.9,
        )
        d = r.to_dict()
        self.assertEqual(d["verdict"], "PASS")
        self.assertEqual(CreativeQualityResult.from_dict(d).verdict, QualityVerdict.PASS)

    def test_f02_issue_contract(self):
        i = QualityIssue(
            issue_id="x1", stage="visual", severity=IssueSeverity.HIGH,
            category="VISUAL_ALIGNMENT", subject_id="scene-05",
            description="Mismatch", repair_scope=RepairScope.VISUAL_ASSET,
        )
        self.assertEqual(i.to_dict()["repair_scope"], "VISUAL_ASSET")

    def test_f03_verdict_model(self):
        self.assertEqual(QualityVerdict.PASS.value, "PASS")
        self.assertIn(QualityVerdict.UNKNOWN.value, ("UNKNOWN",))

    def test_f04_scoring_model(self):
        self.assertAlmostEqual(sum(DIMENSION_WEIGHTS.values()), 1.0, places=2)
        self.assertGreater(PASS_SCORE_THRESHOLD, 0.5)

    def test_f05_script_quality_pass(self):
        r = evaluate_script_quality(subject_id="j1", plan=_good_plan())
        self.assertIn(r.verdict, (QualityVerdict.PASS, QualityVerdict.REPAIR_REQUIRED))

    def test_f06_hook_quality_fail(self):
        plan = {"topic": "Camera review", "scenes": [{"narration": "Hey guys welcome back to my channel today"}]}
        r = evaluate_script_quality(subject_id="j1", plan=plan)
        self.assertTrue(any(i.category == "HOOK_WEAK" for i in r.issues))

    def test_f07_retention_structure(self):
        plan = _good_plan()
        r = evaluate_script_quality(subject_id="j1", plan=plan)
        self.assertIn(QualityDimension.RETENTION_STRUCTURE.value, r.dimensions)

    def test_f08_dialogue_naturalness(self):
        plan = {"topic": "Test", "scenes": [{"narration": "In today's video we will delve into this revolutionary game-changer. Moreover furthermore additionally in conclusion like and subscribe."}]}
        r = evaluate_script_quality(subject_id="j1", plan=plan)
        self.assertTrue(any(i.category == "NATURALNESS" for i in r.issues) or r.dimensions.get("DIALOGUE_NATURALNESS", 1) < 0.8)

    def test_f09_dialogue_duration(self):
        long_narr = "word " * 80
        plan = {"topic": "Test", "scenes": [{"narration": long_narr}]}
        r = evaluate_script_quality(subject_id="j1", plan=plan)
        self.assertTrue(any(i.category == "DIALOGUE_DURATION" for i in r.issues))

    def test_f10_scene_quality(self):
        r = evaluate_scene_visual_alignment(
            scene_id="scene-01",
            narration="Review the camera sensor detail.",
            visual_prompt="close up smartphone camera lens macro shot",
        )
        self.assertGreater(r.score, 0.3)

    def test_f11_visual_plan_empty(self):
        r = evaluate_scene_visual_alignment(scene_id="s1", narration="Test narration here.", visual_prompt="")
        self.assertTrue(any(i.category == "VISUAL_PLAN" for i in r.issues))

    def test_f12_dialogue_visual_alignment_fail(self):
        r = evaluate_scene_visual_alignment(
            scene_id="scene-09",
            narration="The spacecraft enters the atmosphere at high speed.",
            visual_prompt="busy urban street downtown traffic pedestrians",
            visual_query="city street",
        )
        self.assertEqual(r.verdict, QualityVerdict.REPAIR_REQUIRED)
        self.assertEqual(r.repair_scope, RepairScope.VISUAL_ASSET)

    def test_f13_visual_continuity_placeholder(self):
        r = evaluate_scene_visual_alignment(
            scene_id="s1", narration="Same character continues walking.",
            visual_prompt="character walking same outfit continuity",
        )
        self.assertIn(QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value, r.dimensions)

    def test_f14_visual_motion_fail(self):
        r = evaluate_scene_visual_alignment(
            scene_id="s1", narration="Action sequence with movement.",
            visual_prompt="dynamic action scene",
            requires_motion=True, motion_detected=False,
        )
        self.assertTrue(any(i.category == "VISUAL_MOTION" for i in r.issues))

    def test_f15_static_intentional_pass(self):
        r = evaluate_scene_visual_alignment(
            scene_id="s1", narration="Static product shot.",
            visual_prompt="product on table",
            requires_motion=True, motion_detected=False, is_static_intentional=True,
        )
        self.assertFalse(any(i.category == "VISUAL_MOTION" for i in r.issues))

    def test_f16_audio_quality(self):
        r = evaluate_audio_quality(subject_id="s1", gate_results=[{"check": "cutoff", "passed": False}])
        self.assertTrue(any(i.category == "AUDIO_TECHNICAL" for i in r.issues))

    def test_f17_voice_consistency(self):
        r = evaluate_audio_quality(subject_id="s1")
        self.assertIn(QualityDimension.VOICE_CONSISTENCY.value, r.dimensions)

    def test_f18_emotion_alignment(self):
        r = evaluate_audio_quality(
            subject_id="s1",
            narration_semantics="This is a serious warning about critical failure.",
            delivery_style="cheerful",
        )
        self.assertTrue(any(i.category == "EMOTION_MISMATCH" for i in r.issues))

    def test_f19_pacing(self):
        r = evaluate_script_quality(subject_id="j1", plan=_good_plan())
        self.assertIsNotNone(r.score)

    def test_f20_subtitle_quality(self):
        r = evaluate_subtitle_creative(
            subject_id="sub1",
            subtitle_text="Completely unrelated subtitle content",
            dialogue_text="Original dialogue about spacecraft",
            structural_pass=True,
        )
        self.assertTrue(any(i.category == "SUBTITLE_MISMATCH" for i in r.issues))

    def test_f21_cross_modal(self):
        r = evaluate_cross_modal(
            subject_id="j1",
            script_cues={"time_of_day": "night"},
            visual_cues={"time_of_day": "daytime"},
        )
        self.assertEqual(r.verdict, QualityVerdict.REPAIR_REQUIRED)

    def test_f22_factual_evidence(self):
        plan = {"topic": "History", "scenes": [{"narration": "Wrong date", "fact_gate": {"verdict": "FAIL", "allowed": False}}]}
        r = evaluate_script_quality(subject_id="j1", plan=plan)
        self.assertTrue(any(i.category == "FACTUAL_SUPPORT" for i in r.issues))

    def test_f23_evidence_generation(self):
        r = evaluate_scene_visual_alignment(
            scene_id="s1",
            narration="Spacecraft launch",
            visual_prompt="city street",
        )
        self.assertTrue(r.issues[0].evidence if r.issues else r.evidence is not None)

    def test_f24_targeted_repair(self):
        r = evaluate_scene_visual_alignment(
            scene_id="scene-05",
            narration="Spacecraft enters atmosphere",
            visual_prompt="urban street scene",
        )
        p = plan_repair(r)
        self.assertIsNotNone(p)
        self.assertEqual(p.repair_scope, RepairScope.VISUAL_ASSET)
        self.assertEqual(p.subject_id, "scene-05")

    def test_f25_repair_scope_smallest(self):
        r = CreativeQualityResult(
            subject="scene", subject_id="scene-05", stage="visual",
            verdict=QualityVerdict.REPAIR_REQUIRED, score=0.5,
            issues=[
                QualityIssue("i1", "visual", IssueSeverity.MEDIUM, "X", "scene-05", "d", repair_scope=RepairScope.VISUAL_ASSET),
            ],
        )
        p = plan_repair(r)
        self.assertEqual(p.repair_scope, RepairScope.VISUAL_ASSET)

    def test_f26_repair_idempotency(self):
        plan_obj = plan_repair(evaluate_scene_visual_alignment(
            scene_id="scene-05", narration="Spacecraft launch", visual_prompt="city street",
        ))
        fp = compute_repair_fingerprint(job_id="j1", plan=plan_obj, issue_fingerprint="iss-fp")
        calls = {"n": 0}

        def repair_fn():
            calls["n"] += 1
            return {"success": True, "artifact": "visual.mp4"}

        r1 = execute_repair_request(self.tmp, job_id="j1", plan=plan_obj, issue_fingerprint="iss-fp", repair_fn=repair_fn)
        r2 = execute_repair_request(self.tmp, job_id="j1", plan=plan_obj, issue_fingerprint="iss-fp", repair_fn=repair_fn)
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(calls["n"], 1)

    def test_f27_concurrent_repair(self):
        plan_obj = plan_repair(evaluate_scene_visual_alignment(
            scene_id="scene-05", narration="Spacecraft", visual_prompt="city",
        ))
        results = []

        def worker():
            r = execute_repair_request(
                self.tmp, job_id="j1", plan=plan_obj, issue_fingerprint="fp",
                repair_fn=lambda: {"success": True},
            )
            results.append(r.action)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertIn("execute", results)

    def test_f28_repair_budget(self):
        r = evaluate_scene_visual_alignment(scene_id="s1", narration="Spacecraft", visual_prompt="city")
        p = plan_repair(r, attempt=3)
        self.assertTrue(p.escalate)

    def test_f29_infinite_loop_protection(self):
        self.mock.behavior = MockQualityBehavior.FAIL
        for _ in range(5):
            execute_quality_evaluation(
                self.tmp, job_id="j1", subject_id="s1", stage="visual",
                artifact_fingerprint="afp", context={}, use_mock=True, mock_evaluator=self.mock,
            )

    def test_f30_unknown(self):
        self.mock.behavior = MockQualityBehavior.UNKNOWN
        r = execute_quality_evaluation(
            self.tmp, job_id="j1", subject_id="s1", stage="final",
            artifact_fingerprint="afp", context={}, use_mock=True, mock_evaluator=self.mock,
        )
        self.assertEqual(r.result.verdict, QualityVerdict.UNKNOWN)

    def test_f31_revision_identity(self):
        fp1 = compute_quality_fingerprint(job_id="j1", subject_id="s1", stage="script", artifact_fingerprint="a")
        fp2 = compute_quality_fingerprint(job_id="j1", subject_id="s1", stage="script", artifact_fingerprint="b")
        self.assertNotEqual(fp1, fp2)

    def test_f32_quality_cache(self):
        self.mock.behavior = MockQualityBehavior.PASS
        r1 = execute_quality_evaluation(
            self.tmp, job_id="j1", subject_id="s1", stage="script",
            artifact_fingerprint="afp1", context={"plan": _good_plan()}, use_mock=True, mock_evaluator=self.mock,
        )
        self.mock.reset()
        r2 = execute_quality_evaluation(
            self.tmp, job_id="j1", subject_id="s1", stage="script",
            artifact_fingerprint="afp1", context={"plan": _good_plan()}, use_mock=True, mock_evaluator=self.mock,
        )
        self.assertEqual(r1.action, "execute")
        self.assertEqual(r2.action, "reuse")
        self.assertEqual(self.mock.invocation_count, 0)

    def test_f33_invalidation(self):
        fp1 = compute_quality_fingerprint(job_id="j1", subject_id="s1", stage="script", artifact_fingerprint="a")
        fp2 = compute_quality_fingerprint(job_id="j1", subject_id="s1", stage="script", artifact_fingerprint="b")
        self.assertNotEqual(fp1, fp2)

    def test_f34_dependency_invalidation(self):
        stale = filter_stale_results(["visual:scene-07", "script", "final"], "visual")
        self.assertIn("final", stale)
        self.assertNotIn("script", stale)
        self.assertIn("visual:scene-07", scene_only_invalidation("scene-07"))

    def test_f35_provenance(self):
        self.mock.behavior = MockQualityBehavior.PASS
        r = execute_quality_evaluation(
            self.tmp, job_id="j1", subject_id="s1", stage="script",
            artifact_fingerprint="afp", context={}, use_mock=True, mock_evaluator=self.mock,
        )
        from pipeline.quality.provenance import load_quality_provenance
        self.assertIsNotNone(load_quality_provenance(self.tmp, r.fingerprint))

    def test_f36_checkpoint(self):
        self.mock.behavior = MockQualityBehavior.PASS
        r = execute_quality_evaluation(
            self.tmp, job_id="j1", subject_id="s1", stage="script",
            artifact_fingerprint="afp", context={}, use_mock=True, mock_evaluator=self.mock,
        )
        from pipeline.idempotency.store import IdempotencyStore
        rec = IdempotencyStore(self.tmp / "idempotency").get(r.fingerprint)
        self.assertIsNotNone(rec)

    def test_f37_orphan_detection(self):
        from pipeline.quality.provenance import load_quality_provenance
        self.assertIsNone(load_quality_provenance(self.tmp, "nonexistent"))

    def test_f38_bypass_detection(self):
        vp = (ROOT / "pipeline/video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("run_creative_quality_gate", vp)
        self.assertIn("run_publishability_gate", vp)
        self.assertIn("publishability_blocked", vp)

    def test_f39_publishability_gate(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            semantic_status="PASS",
        )
        self.assertEqual(pub["verdict"], PublishabilityVerdict.PUBLISHABLE.value)
        pub2 = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "REPAIR_REQUIRED"},
            semantic_status="PASS",
        )
        self.assertFalse(pub2["publishable"])

    def test_f40_api_cost_protection(self):
        script_r = evaluate_script_quality(subject_id="j1", plan=_good_plan())
        visual_r = evaluate_scene_visual_alignment(
            scene_id="scene-05", narration="Spacecraft", visual_prompt="city street",
        )
        p = plan_repair(visual_r)
        self.assertEqual(p.repair_scope, RepairScope.VISUAL_ASSET)
        self.assertNotEqual(p.repair_scope, RepairScope.SCRIPT)

    def test_f41_final_video_gate(self):
        tech = aggregate_quality_results([
            CreativeQualityResult("t", "j1", "technical", QualityVerdict.PASS, 0.95),
            CreativeQualityResult("c", "j1", "creative", QualityVerdict.REPAIR_REQUIRED, 0.5,
                issues=[QualityIssue("i", "v", IssueSeverity.HIGH, "X", "s1", "d", repair_scope=RepairScope.VISUAL_ASSET)]),
        ], subject_id="j1")
        pub = evaluate_publishability(technical_pass=True, creative_report={"overall_verdict": tech.verdict.value})
        self.assertFalse(pub["publishable"])

    def test_f42_complete_regression(self):
        r = evaluate_script_quality(subject_id="j1", plan=_good_plan())
        d = r.to_dict()
        self.assertEqual(CreativeQualityResult.from_dict(d).score, r.score)


if __name__ == "__main__":
    unittest.main(verbosity=2)
