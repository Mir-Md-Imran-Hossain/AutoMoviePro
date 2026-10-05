#!/usr/bin/env python3
"""AMP-003 T004-C3 — Visual semantic consistency & fallback quality boundary tests."""
from __future__ import annotations

import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.scene_intent import SceneIntent, TemporalAction
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.visual_semantic.boundary import (
    analysis_from_fixture,
    run_visual_semantic_gate,
    semantic_gate_for_spec,
    validate_visual_complete,
)
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.contracts import SemanticIssueCode, SemanticValidationStatus
from pipeline.visual_semantic.fallback import FallbackAssetRecord, fallback_semantic_allowed, validate_fallback_asset
from pipeline.visual_semantic.repair_bridge import plan_semantic_repair, semantic_result_to_quality
from pipeline.visual_semantic.scene_intent import build_scene_intent_from_dialogue, intent_fingerprint


def _minimal_mp4(path: Path) -> None:
    ftyp = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isom"
    mdat = b"\x00\x00\x00\x08mdat" + b"\x00" * 9000
    path.write_bytes(ftyp + mdat)


def _tea_intent(**over) -> SceneIntent:
    base = dict(
        scene_id="5",
        dialogue_id="dlg-c3-uuid",
        summary="The person drinks tea calmly at the table.",
        primary_action="drinking tea",
        location="chair",
        environment="living room with chair",
        posture="sitting on chair",
        required_objects=["tea", "cup"],
        forbidden_objects=["knife"],
        action_order=[
            TemporalAction(action="pick up", order=0),
            TemporalAction(action="drink", order=1),
            TemporalAction(action="put down", order=2),
        ],
    )
    base.update(over)
    return SceneIntent(**base)


class T004C3VisualSemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.asset = self.tmp / "clip.mp4"
        _minimal_mp4(self.asset)
        reset_mock_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_matching_action_pass(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture(
            {"actions": ["drinking"], "objects": ["tea", "cup"], "location": "chair", "posture": "sitting on chair", "dialogue_id": "dlg-c3-uuid"}
        )
        result = run_visual_semantic_gate(intent, analysis, request_dialogue_id="dlg-c3-uuid", strict=True)
        self.assertIn(result.status, (SemanticValidationStatus.SEMANTIC_PASS, SemanticValidationStatus.SEMANTIC_PARTIAL))
        self.assertFalse(result.blocked)

    def test_02_wrong_action_block(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating", "cutting"], "objects": ["plate", "knife"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertTrue(result.blocked)
        codes = {i.code for i in result.issues}
        self.assertTrue(codes & {SemanticIssueCode.UNEXPECTED_ACTION, SemanticIssueCode.CONFLICTING_ACTION})

    def test_03_conflicting_action_block(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking", "eating"], "objects": ["tea", "biscuit"], "simultaneous_actions": True})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertTrue(result.blocked)
        self.assertIn(SemanticIssueCode.CONFLICTING_ACTION, {i.code for i in result.issues})

    def test_04_unexpected_object_flag(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup", "biscuit"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        codes = {i.code for i in result.issues}
        self.assertIn(SemanticIssueCode.UNEXPECTED_OBJECT, codes)

    def test_05_correct_object_pass(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertFalse(result.blocked)

    def test_06_correct_location_pass(self):
        intent = _tea_intent(location="chair", environment="chair")
        analysis = analysis_from_fixture({"location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertFalse(result.blocked)

    def test_07_wrong_location_block(self):
        intent = _tea_intent(location="chair", posture="sitting on chair")
        analysis = analysis_from_fixture({"location": "floor", "posture": "sitting on floor", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertTrue(result.blocked)

    def test_08_correct_posture_pass(self):
        intent = _tea_intent(posture="sitting on chair")
        analysis = analysis_from_fixture({"posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertFalse(result.blocked)

    def test_09_wrong_posture_block(self):
        intent = _tea_intent(posture="sitting on chair")
        analysis = analysis_from_fixture({"posture": "sitting on floor", "location": "floor", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertTrue(result.blocked)

    def test_10_continuity_preserved_pass(self):
        tracker = ContinuityTracker()
        intent1 = _tea_intent(scene_id="1")
        a1 = analysis_from_fixture({"location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]})
        tracker.update_from_intent(intent1, a1)
        intent2 = _tea_intent(scene_id="2")
        a2 = analysis_from_fixture({"location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent2, a2, continuity=tracker, strict=True)
        self.assertFalse(result.blocked)

    def test_11_legitimate_continuity_change_pass(self):
        tracker = ContinuityTracker()
        intent2 = _tea_intent(scene_id="2", narrative_change_allowed=True, location="kitchen")
        a2 = analysis_from_fixture({"location": "kitchen", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent2, a2, continuity=tracker, strict=True)
        self.assertFalse(result.blocked)

    def test_12_unexplained_continuity_change_block(self):
        tracker = ContinuityTracker()
        intent1 = _tea_intent(scene_id="1")
        a1 = analysis_from_fixture({"location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]})
        tracker.update_from_intent(intent1, a1)
        intent2 = _tea_intent(scene_id="2")
        a2 = analysis_from_fixture({"location": "floor", "posture": "sitting on floor", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent2, a2, continuity=tracker, strict=True)
        self.assertTrue(result.blocked)
        self.assertIn(SemanticIssueCode.CONTINUITY_BREAK, {i.code for i in result.issues})

    def test_13_dialogue_visual_identity_mismatch_block(self):
        intent = _tea_intent(dialogue_id="dlg-a")
        analysis = analysis_from_fixture({"dialogue_id": "dlg-b", "actions": ["drinking"], "objects": ["tea", "cup"]})
        result = run_visual_semantic_gate(intent, analysis, request_dialogue_id="dlg-a", strict=True)
        self.assertTrue(result.blocked)

    def test_14_temporal_action_order_valid_pass(self):
        intent = _tea_intent(
            summary="Pick up cup. Drink tea. Put cup down.",
            action_order=[
                TemporalAction(action="pick up", order=0),
                TemporalAction(action="drink", order=1),
                TemporalAction(action="put down", order=2),
            ],
        )
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"], "simultaneous_actions": False})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertFalse(result.blocked)

    def test_15_temporal_contradiction_block(self):
        intent = _tea_intent(
            summary="Pick up cup then drink then put down.",
            action_order=[
                TemporalAction(action="pick up", order=0),
                TemporalAction(action="drink", order=1),
            ],
        )
        analysis = analysis_from_fixture({"actions": ["drinking", "eating"], "simultaneous_actions": True})
        result = run_visual_semantic_gate(intent, analysis, strict=True)
        self.assertTrue(result.blocked)
        self.assertIn(SemanticIssueCode.TEMPORAL_CONTRADICTION, {i.code for i in result.issues})

    def test_16_technical_valid_semantic_invalid_not_pass(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        result = validate_visual_complete(str(self.asset), intent, analysis, strict=True)
        self.assertTrue(result.technical_ok)
        self.assertFalse(result.semantic_ok)
        self.assertNotEqual(result.status, SemanticValidationStatus.SEMANTIC_PASS)

    def test_17_technical_invalid_block(self):
        bad = self.tmp / "bad.mp4"
        bad.write_bytes(b"x")
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"]})
        result = validate_visual_complete(str(bad), intent, analysis)
        self.assertFalse(result.technical_ok)
        self.assertTrue(result.blocked)

    def test_18_fallback_asset_retains_provenance(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"]})
        record = FallbackAssetRecord(
            asset_path=str(self.asset),
            fallback_reason="agnes_failed",
            source_provider="image_fallback",
            scene_id="5",
            dialogue_id="dlg-c3-uuid",
        )
        validate_fallback_asset(record, intent, analysis)
        self.assertFalse(record.is_agnes_success)
        self.assertTrue(record.intent_fingerprint)
        self.assertEqual(record.dialogue_id, "dlg-c3-uuid")

    def test_19_fallback_cannot_bypass_semantic_validation(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating", "cutting"], "objects": ["knife"]})
        record = FallbackAssetRecord(
            asset_path=str(self.asset),
            fallback_reason="agnes_failed",
            source_provider="image_fallback",
            scene_id="5",
            dialogue_id="dlg-c3-uuid",
        )
        result = validate_fallback_asset(record, intent, analysis)
        self.assertFalse(fallback_semantic_allowed(record, result))

    def test_20_targeted_repair_only(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        sem = run_visual_semantic_gate(intent, analysis, strict=True)
        quality = semantic_result_to_quality(sem, subject_id="scene-05")
        self.assertEqual(quality.repair_scope.value, "VISUAL_ASSET")
        self.assertNotEqual(quality.recommended_action, "regenerate_script")

    def test_21_repair_revision_identity(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        sem = run_visual_semantic_gate(intent, analysis, strict=True)
        plan = plan_semantic_repair(sem, attempt=1, old_fingerprint=intent_fingerprint(intent))
        self.assertIsNotNone(plan)
        self.assertTrue(plan.revision_id.startswith("r"))
        self.assertEqual(plan.repair_scope.value, "VISUAL_ASSET")

    def test_22_repair_budget_respected(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        sem = run_visual_semantic_gate(intent, analysis, strict=True)
        plan = plan_semantic_repair(sem, attempt=99, old_fingerprint="fp")
        self.assertIsNotNone(plan)
        self.assertTrue(plan.escalate)

    def test_23_repeated_repair_no_infinite_loop(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        sem = run_visual_semantic_gate(intent, analysis, strict=True)
        plans = [plan_semantic_repair(sem, attempt=i) for i in range(1, 5)]
        self.assertTrue(all(p is not None for p in plans))
        self.assertTrue(plans[-1].escalate)

    def test_24_deterministic_same_input(self):
        intent = _tea_intent()
        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"]})
        r1 = run_visual_semantic_gate(intent, analysis)
        r2 = run_visual_semantic_gate(intent, analysis)
        self.assertEqual(r1.status, r2.status)
        self.assertEqual(intent_fingerprint(intent), r1.intent_fingerprint)

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_25_no_new_direct_provider_bypass(self, direct_mock):
        mock = get_mock_provider()
        mock.behavior = MockBehavior.SUCCESS
        from pipeline.idempotency.agnes_bridge import idempotent_generate_agnes_beat_result

        out = self.tmp / "agnes_out.mp4"
        idempotent_generate_agnes_beat_result(
            work_dir=self.tmp,
            job_id="job-c3",
            scene_id=3,
            part_index=0,
            attempt=1,
            product_name="prod",
            element="beat",
            visual_prompt="person drinks tea with cup",
            out_path=out,
            narration_hint="The person drinks tea at the table.",
            dialogue_id="dlg-c3",
            canonical_scene_id="scene-c3",
            use_mock=True,
        )
        direct_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
