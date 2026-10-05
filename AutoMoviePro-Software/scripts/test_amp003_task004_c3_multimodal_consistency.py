#!/usr/bin/env python3
"""AMP-003 T004-C3 — Multimodal consistency + prompt grounding (40 scenarios)."""
from __future__ import annotations

import inspect
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

from domain.scene_intent import (
    AudioIntent,
    EntityRelation,
    LocalizationIntent,
    SceneIntent,
    SemanticEntity,
    SubtitleIntent,
    TemporalAction,
)
from pipeline.idempotency.mock_visual_provider import MockBehavior, get_mock_provider, reset_mock_provider
from pipeline.multimodal_consistency.boundary import run_multimodal_consistency_gate
from pipeline.multimodal_consistency.entity_grounding import infer_phone_camera_entities
from pipeline.multimodal_consistency.industrial_status import LayerStatus, ValidationLayer
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.multimodal_consistency.prompt_validator import validate_prompt_contradiction
from pipeline.multimodal_consistency.quality_bridge import multimodal_report_to_quality, plan_multimodal_repair
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.contracts import SemanticIssueCode
from pipeline.visual_semantic.fallback import FallbackAssetRecord, fallback_semantic_allowed, validate_fallback_asset
from pipeline.visual_semantic.scene_intent import build_scene_intent_from_dialogue, intent_fingerprint


def _minimal_mp4(path: Path) -> None:
    ftyp = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isom"
    mdat = b"\x00\x00\x00\x08mdat" + b"\x00" * 9000
    path.write_bytes(ftyp + mdat)


def _phone_intent(**over) -> SceneIntent:
    entities, relations = infer_phone_camera_entities(
        "He uses the mobile phone camera in low light.",
        "mobile phone",
    )
    base = dict(
        scene_id="7",
        dialogue_id="dlg-mm-phone",
        summary="He uses the mobile phone camera in low light.",
        primary_action="using phone camera",
        entities=entities,
        relations=relations,
        required_objects=["mobile phone", "phone camera module"],
        negative_constraints=["external DSLR camera", "broadcast camera"],
    )
    base.update(over)
    return SceneIntent(**base)


def _tea_intent(**over) -> SceneIntent:
    base = dict(
        scene_id="5",
        dialogue_id="dlg-mm-tea",
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
        audio_intent=AudioIntent(language="en", duration_target_sec=8.0),
        subtitle_intent=SubtitleIntent(language="en", cue_count=3, total_duration_sec=8.0),
        localization_intent=LocalizationIntent(
            source_language="en",
            target_language="bn",
            preserve_events=True,
            semantic_events=["pick", "drink", "put"],
        ),
    )
    base.update(over)
    return SceneIntent(**base)


class T004C3MultimodalConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.asset = self.tmp / "clip.mp4"
        _minimal_mp4(self.asset)
        reset_mock_provider()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _gate(self, intent: SceneIntent, fixture: dict, **kw):
        return run_multimodal_consistency_gate(
            intent,
            asset_path=str(self.asset),
            analysis_fixture=fixture,
            strict=True,
            **kw,
        )

    def test_01_matching_entity_pass(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "entities": ["mobile phone", "phone camera module"],
            "objects": ["mobile phone", "phone camera module"],
            "actions": ["using phone camera"],
        }
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_02_entity_substitution_block(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "substituted_entity": "dslr camera",
            "objects": ["dslr camera"],
            "entities": ["dslr camera"],
        }
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_03_attribute_binding_correct_pass(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "objects": ["mobile phone", "phone camera module"],
            "attributes": {"low_light_performance": "enabled", "low_light_performance_entity": "CAMERA_MODULE_01"},
        }
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_04_attribute_misbinding_block(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "objects": ["mobile phone"],
            "attributes": {
                "low_light_performance": "enabled",
                "low_light_performance_entity": "MOBILE_PHONE_01",
            },
        }
        report = self._gate(intent, fixture)
        sem = next(l for l in report.layers if l.layer == ValidationLayer.SEMANTIC)
        self.assertTrue(any("Attribute" in i.get("message", "") for i in sem.issues) or report.blocked)

    def test_05_component_ownership_correct_pass(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "objects": ["mobile phone", "phone camera module"],
            "entities": ["mobile phone", "phone camera module"],
        }
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_06_component_becomes_separate_object_block(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "component_as_separate_object": True,
            "objects": ["phone camera module"],
            "entities": ["phone camera module"],
        }
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_07_correct_relation_pass(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "objects": ["mobile phone", "phone camera module"],
            "relations": [
                {
                    "source_id": "MOBILE_PHONE_01",
                    "target_id": "CAMERA_MODULE_01",
                    "relation_type": "part_of",
                }
            ],
        }
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_08_relation_confusion_block(self):
        intent = _phone_intent()
        fixture = {
            "source": "OFFLINE_TEST_ONLY",
            "objects": ["mobile phone", "phone camera module"],
            "relations": [
                {
                    "source_id": "CAMERA_MODULE_01",
                    "target_id": "MOBILE_PHONE_01",
                    "relation_type": "owns",
                }
            ],
        }
        report = self._gate(intent, fixture)
        sem = next(l for l in report.layers if l.layer == ValidationLayer.SEMANTIC)
        self.assertTrue(sem.issues)

    def test_09_correct_action_pass(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"], "location": "chair", "posture": "sitting on chair", "dialogue_id": "dlg-mm-tea"}
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_10_wrong_action_block(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating", "cutting"], "objects": ["plate", "knife"]}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_11_incompatible_simultaneous_action_block(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking", "eating"], "objects": ["tea", "biscuit"], "simultaneous_actions": True}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_12_valid_action_sequence_pass(self):
        intent = _tea_intent(
            summary="Pick up cup. Drink tea. Put cup down.",
            action_order=[
                TemporalAction(action="pick up", order=0),
                TemporalAction(action="drink", order=1),
                TemporalAction(action="put down", order=2),
            ],
        )
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"], "simultaneous_actions": False}
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_13_invalid_action_order_block(self):
        intent = _tea_intent(
            action_order=[
                TemporalAction(action="pick up", order=0),
                TemporalAction(action="drink", order=1),
            ],
        )
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking", "eating"], "simultaneous_actions": True}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_14_correct_location_pass(self):
        intent = _tea_intent(location="chair", environment="chair")
        fixture = {"source": "OFFLINE_TEST_ONLY", "location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_15_wrong_location_block(self):
        intent = _tea_intent(location="chair", posture="sitting on chair")
        fixture = {"source": "OFFLINE_TEST_ONLY", "location": "floor", "posture": "sitting on floor", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_16_correct_posture_pass(self):
        intent = _tea_intent(posture="sitting on chair")
        fixture = {"source": "OFFLINE_TEST_ONLY", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(intent, fixture)
        self.assertNotEqual(report.final_status, LayerStatus.BLOCKED)

    def test_17_wrong_posture_block(self):
        intent = _tea_intent(posture="sitting on chair")
        fixture = {"source": "OFFLINE_TEST_ONLY", "posture": "sitting on floor", "location": "floor", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_18_continuity_preserved_pass(self):
        tracker = ContinuityTracker()
        intent1 = _tea_intent(scene_id="1")
        a1 = {"source": "OFFLINE_TEST_ONLY", "location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]}
        run_multimodal_consistency_gate(intent1, analysis_fixture=a1, continuity=tracker, strict=True)
        intent2 = _tea_intent(scene_id="2")
        a2 = {"source": "OFFLINE_TEST_ONLY", "location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = run_multimodal_consistency_gate(intent2, analysis_fixture=a2, continuity=tracker, strict=True)
        cont = next(l for l in report.layers if l.layer == ValidationLayer.CONTINUITY)
        self.assertNotEqual(cont.status, LayerStatus.BLOCKED)

    def test_19_legitimate_continuity_change_pass(self):
        tracker = ContinuityTracker()
        intent2 = _tea_intent(scene_id="2", narrative_change_allowed=True, location="kitchen")
        a2 = {"source": "OFFLINE_TEST_ONLY", "location": "kitchen", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = run_multimodal_consistency_gate(intent2, analysis_fixture=a2, continuity=tracker, strict=True)
        cont = next(l for l in report.layers if l.layer == ValidationLayer.CONTINUITY)
        self.assertNotEqual(cont.status, LayerStatus.BLOCKED)

    def test_20_unexplained_continuity_change_block(self):
        tracker = ContinuityTracker()
        intent1 = _tea_intent(scene_id="1")
        a1 = {"source": "OFFLINE_TEST_ONLY", "location": "chair", "posture": "sitting on chair", "actions": ["drinking"], "objects": ["tea", "cup"]}
        run_multimodal_consistency_gate(intent1, analysis_fixture=a1, continuity=tracker, strict=True)
        intent2 = _tea_intent(scene_id="2")
        a2 = {"source": "OFFLINE_TEST_ONLY", "location": "floor", "posture": "sitting on floor", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = run_multimodal_consistency_gate(intent2, analysis_fixture=a2, continuity=tracker, strict=True)
        cont = next(l for l in report.layers if l.layer == ValidationLayer.CONTINUITY)
        self.assertTrue(cont.issues)

    def test_21_dialogue_visual_match_pass(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"], "description": "person drinks tea at table", "dialogue_id": "dlg-mm-tea"}
        report = self._gate(intent, fixture)
        cross = next(l for l in report.layers if l.layer == ValidationLayer.CROSS_MODAL)
        self.assertNotEqual(cross.status, LayerStatus.BLOCKED)

    def test_22_dialogue_visual_contradiction_block(self):
        intent = _tea_intent(summary="The person drinks tea calmly.")
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["running"], "objects": ["shoes"], "description": "person runs marathon", "contradiction": "Visual contradicts dialogue"}
        report = self._gate(intent, fixture)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_23_audio_dialogue_identity_match_pass(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"], "dialogue_id": "dlg-mm-tea"}
        report = self._gate(intent, fixture, audio_meta={"dialogue_id": "dlg-mm-tea", "scene_id": "5"})
        cross = next(l for l in report.layers if l.layer == ValidationLayer.CROSS_MODAL)
        self.assertNotEqual(cross.status, LayerStatus.BLOCKED)

    def test_24_audio_dialogue_identity_mismatch_block(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(intent, fixture, audio_meta={"dialogue_id": "dlg-other", "scene_id": "5"})
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_25_subtitle_timing_valid_pass(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(
            intent,
            fixture,
            audio_duration_sec=8.0,
            subtitle_duration_sec=8.1,
            scene_duration_sec=8.0,
            subtitle_meta={"dialogue_id": "dlg-mm-tea", "text": "person drinks tea"},
        )
        cross = next(l for l in report.layers if l.layer == ValidationLayer.CROSS_MODAL)
        timing_issues = [i for i in cross.issues if "Timeline" in i.get("message", "")]
        self.assertFalse(timing_issues)

    def test_26_subtitle_timing_mismatch_block(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(
            intent,
            fixture,
            audio_duration_sec=8.0,
            subtitle_duration_sec=20.0,
            scene_duration_sec=8.0,
        )
        cross = next(l for l in report.layers if l.layer == ValidationLayer.CROSS_MODAL)
        self.assertTrue(any("Timeline" in i.get("message", "") for i in cross.issues))

    def test_27_localization_meaning_preserved_pass(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"]}
        report = self._gate(
            intent,
            fixture,
            localized={"text": "He picked up the cup, drank tea, and put it down.", "source": "OFFLINE_TEST_ONLY"},
        )
        loc = next(l for l in report.layers if l.layer == ValidationLayer.LOCALIZATION)
        self.assertNotEqual(loc.status, LayerStatus.BLOCKED)

    def test_28_localization_semantic_drift_block(self):
        intent = _tea_intent(
            summary="He picked up the phone and called his friend.",
            localization_intent=LocalizationIntent(
                preserve_events=True,
                semantic_events=["pick", "call"],
            ),
        )
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["walking"], "objects": ["shoes"]}
        report = self._gate(
            intent,
            fixture,
            localized={"text": "He walked to the park.", "source": "OFFLINE_TEST_ONLY", "order_changed": True},
        )
        loc = next(l for l in report.layers if l.layer == ValidationLayer.LOCALIZATION)
        self.assertEqual(loc.status, LayerStatus.BLOCKED)

    def test_29_prompt_matches_canonical_intent_pass(self):
        intent = _phone_intent()
        compiled = compile_provider_prompt(intent)
        issues = validate_prompt_contradiction(intent, compiled)
        self.assertFalse(any(i.severity == "CRITICAL" for i in issues))
        self.assertIn("mobile phone", compiled.positive.lower())

    def test_30_prompt_contradiction_block(self):
        intent = _phone_intent(posture="sitting on chair")
        compiled = compile_provider_prompt(intent)
        issues = validate_prompt_contradiction(
            intent,
            compiled,
            provider_prompt="professional DSLR camera standing in studio broadcast setup",
        )
        self.assertTrue(any(i.severity == "CRITICAL" for i in issues))

    def test_31_forbidden_object_action_enforced(self):
        intent = _tea_intent(forbidden_objects=["knife"], forbidden_actions=["cutting"])
        compiled = compile_provider_prompt(intent)
        issues = validate_prompt_contradiction(intent, compiled, provider_prompt="person cutting vegetables with knife")
        codes = {i.code for i in issues}
        self.assertTrue(SemanticIssueCode.FORBIDDEN_OBJECT in codes or any("forbidden" in i.message.lower() for i in issues))

    def test_32_technical_valid_semantic_invalid_block(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating"], "objects": ["knife"]}
        report = self._gate(intent, fixture)
        tech = next(l for l in report.layers if l.layer == ValidationLayer.TECHNICAL)
        self.assertEqual(tech.status, LayerStatus.PASS)
        self.assertEqual(report.final_status, LayerStatus.BLOCKED)

    def test_33_fallback_provenance_retained(self):
        intent = _tea_intent()
        from pipeline.visual_semantic.boundary import analysis_from_fixture

        analysis = analysis_from_fixture({"actions": ["drinking"], "objects": ["tea", "cup"]})
        record = FallbackAssetRecord(
            asset_path=str(self.asset),
            fallback_reason="agnes_failed",
            source_provider="image_fallback",
            scene_id="5",
            dialogue_id="dlg-mm-tea",
            revision_id="rev-1",
        )
        validate_fallback_asset(record, intent, analysis)
        self.assertFalse(record.is_agnes_success)
        self.assertTrue(record.intent_fingerprint)
        self.assertEqual(record.dialogue_id, "dlg-mm-tea")

    def test_34_fallback_cannot_bypass_validation(self):
        intent = _tea_intent()
        from pipeline.visual_semantic.boundary import analysis_from_fixture

        analysis = analysis_from_fixture({"actions": ["eating"], "objects": ["knife"]})
        record = FallbackAssetRecord(
            asset_path=str(self.asset),
            fallback_reason="agnes_failed",
            source_provider="image_fallback",
            scene_id="5",
            dialogue_id="dlg-mm-tea",
        )
        result = validate_fallback_asset(record, intent, analysis)
        self.assertFalse(fallback_semantic_allowed(record, result))

    def test_35_targeted_repair_only(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating"], "objects": ["knife"]}
        report = self._gate(intent, fixture)
        quality = multimodal_report_to_quality(report, subject_id="scene-05")
        self.assertEqual(quality.repair_scope.value, "VISUAL_ASSET")
        self.assertNotEqual(quality.recommended_action, "regenerate_script")

    def test_36_repair_revision_identity(self):
        intent = _tea_intent(revision_id="rev-42")
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating"], "objects": ["knife"]}
        report = self._gate(intent, fixture)
        plan = plan_multimodal_repair(report, attempt=1, old_fingerprint=intent_fingerprint(intent))
        self.assertIsNotNone(plan)
        self.assertTrue(plan.revision_id.startswith("r"))

    def test_37_repair_budget_respected(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating"], "objects": ["knife"]}
        report = self._gate(intent, fixture)
        plan = plan_multimodal_repair(report, attempt=99, old_fingerprint="fp")
        self.assertIsNotNone(plan)
        self.assertTrue(plan.escalate)

    def test_38_no_infinite_repair(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["eating"], "objects": ["knife"]}
        report = self._gate(intent, fixture)
        plans = [plan_multimodal_repair(report, attempt=i) for i in range(1, 5)]
        self.assertTrue(all(p is not None for p in plans))
        self.assertTrue(plans[-1].escalate)

    def test_39_deterministic_identical_semantic_input(self):
        intent = _tea_intent()
        fixture = {"source": "OFFLINE_TEST_ONLY", "actions": ["drinking"], "objects": ["tea", "cup"], "dialogue_id": "dlg-mm-tea"}
        r1 = self._gate(intent, fixture)
        r2 = self._gate(intent, fixture)
        self.assertEqual(r1.final_status, r2.final_status)
        self.assertEqual(r1.intent_fingerprint, r2.intent_fingerprint)

    @mock.patch("pipeline.media_assets.generate_agnes_dialogue_clip")
    def test_40_no_new_production_provider_bypass(self, direct_mock):
        mock = get_mock_provider()
        mock.behavior = MockBehavior.SUCCESS
        from pipeline.idempotency.agnes_bridge import idempotent_generate_agnes_beat_result

        out = self.tmp / "agnes_out.mp4"
        idempotent_generate_agnes_beat_result(
            work_dir=self.tmp,
            job_id="job-mm-c3",
            scene_id=3,
            part_index=0,
            attempt=1,
            product_name="prod",
            element="beat",
            visual_prompt="person drinks tea with cup",
            out_path=out,
            narration_hint="The person drinks tea at the table.",
            dialogue_id="dlg-mm",
            canonical_scene_id="scene-mm",
            use_mock=True,
        )
        direct_mock.assert_not_called()

    def test_scene_intent_builder_infers_phone_entities(self):
        intent = build_scene_intent_from_dialogue(
            scene_id="9",
            dialogue_id="dlg-build",
            narration="She tests the mobile phone camera at night.",
            visual_prompt="mobile phone camera low light",
        )
        self.assertTrue(any("phone" in e.label.lower() for e in intent.entities))
        self.assertTrue(intent.negative_constraints)


if __name__ == "__main__":
    unittest.main(verbosity=2)
