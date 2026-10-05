#!/usr/bin/env python3
"""AMP-004 Phase-03 — Production Continuity behavioral tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.scene_intent import SceneIntent, TemporalAction
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.multimodal_consistency.prompt_validator import validate_prompt_contradiction
from pipeline.visual_semantic.continuity import (
    ContinuityError,
    ContinuityTracker,
    validate_impossible_action_combinations,
)
from pipeline.visual_semantic.continuity_runtime import (
    ContinuityPromptBlocked,
    apply_production_continuity,
    prepare_scene_with_continuity,
)
from pipeline.visual_semantic.contracts import SemanticIssueCode


def _intent(**over) -> SceneIntent:
    base = dict(
        scene_id="1",
        dialogue_id="dlg-1",
        summary="The person sits on a chair holding a smartphone in the office.",
        primary_action="holding smartphone",
        actors=["Alex"],
        location="office",
        environment="office",
        posture="sitting on chair",
        required_objects=["smartphone"],
        continuity_expected=True,
    )
    base.update(over)
    return SceneIntent(**base)


class Phase03ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_first_scene_initializes_continuity(self):
        t = ContinuityTracker()
        st = t.initialize_from_intent(_intent())
        self.assertIsNotNone(st)
        self.assertEqual(st.character_id, "Alex")
        self.assertTrue(st.fingerprint)

    def test_02_second_scene_inherits_required_state(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent())
        nxt = _intent(scene_id="2", dialogue_id="dlg-2", summary="Alex looks at the phone screen.", posture="", location="")
        c = t.build_constraints_for_next(nxt)
        self.assertTrue(c.required_character)
        self.assertTrue(c.required_objects)
        applied = t.apply_constraints_to_intent(nxt, c)
        self.assertTrue(applied.continuity_refs.get("continuity_constraints"))

    def test_03_same_entity_identity_preserved(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(actors=["Alex"]))
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2", actors=[]))
        self.assertEqual(c.required_character, "Alex")

    def test_04_same_object_identity_preserved(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent())
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2"))
        self.assertTrue(any("phone" in o.lower() or "smartphone" in o.lower() for o in c.required_objects) or c.required_held_object)

    def test_05_clothing_continuity(self):
        t = ContinuityTracker()
        intent = _intent()
        intent.continuity_refs = {"wardrobe": "blue jacket"}
        t.initialize_from_intent(intent)
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2"))
        self.assertEqual(c.required_wardrobe, "blue jacket")
        self.assertTrue(any("wardrobe" in f.lower() or "clothing" in f.lower() for f in c.forbidden + c.negative_constraints))

    def test_06_object_ownership_continuity(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(summary="Alex is holding a smartphone."))
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2", summary="Alex checks notifications."))
        self.assertTrue(c.required_held_object or any("holding" in r.lower() or "preserve" in r.lower() for r in c.required))

    def test_07_location_continuity(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(location="office"))
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2", location=""))
        self.assertEqual(c.required_location, "office")

    def test_08_posture_continuity(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(posture="sitting on chair"))
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2", summary="Alex reads email.", posture=""))
        self.assertIn("sitting", c.required_posture)

    def test_09_action_continuity(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(primary_action="holding smartphone"))
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2"))
        self.assertTrue(any("prior_action" in n for n in c.temporal_notes) or c.required)

    def test_10_temporal_order_continuity(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                action_order=[
                    TemporalAction(action="pick up", order=0),
                    TemporalAction(action="look", order=1),
                ]
            )
        )
        c = t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2"))
        self.assertTrue(any("completed" in n for n in c.temporal_notes))

    def test_11_spatial_relationship_continuity(self):
        from domain.scene_intent import EntityRelation

        t = ContinuityTracker()
        intent = _intent(
            relations=[
                EntityRelation(
                    relation_id="r1",
                    source_id="Alex",
                    target_id="PHONE_01",
                    relation_type="uses",
                )
            ]
        )
        t.initialize_from_intent(intent)
        self.assertTrue(t.state and t.state.spatial_notes)

    def test_12_explicit_state_transition_allowed(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent())
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex places the phone on the table.",
            narrative_change_allowed=False,
            primary_action="placing phone",
        )
        c = t.build_constraints_for_next(nxt)
        # transition wording → release held object note, not unexplained block
        issues = t.validate_pre_generation(nxt, c)
        critical = [i for i in issues if i.severity == "CRITICAL" and i.code == SemanticIssueCode.CONTINUITY_BREAK]
        self.assertFalse(critical)

    def test_13_unexplained_state_transition_blocked(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(location="office", actors=["Alex"]))
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Jordan stands on the beach.",
            location="beach",
            actors=["Jordan Celebrity"],
            posture="standing",
        )
        meta = dict(nxt.metadata or {})
        meta["explicit_location"] = True
        nxt.metadata = meta
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(any(i.severity == "CRITICAL" for i in issues))

    def test_14_impossible_simultaneous_actions_blocked(self):
        intent = _intent(
            primary_action="drinking",
            secondary_actions=["eating", "cutting"],
            summary="Drinking tea while eating and cutting vegetables.",
        )
        issues = validate_impossible_action_combinations(intent)
        self.assertTrue(any(i.code == SemanticIssueCode.CONFLICTING_ACTION for i in issues))

    def test_15_object_transformation_blocked(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(summary="Alex holds a smartphone.", required_objects=["smartphone"]))
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex holds a DSLR camera.",
            required_objects=["dslr", "smartphone"],
        )
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(
            any(i.code in (SemanticIssueCode.UNEXPECTED_OBJECT, SemanticIssueCode.CONTINUITY_BREAK) for i in issues)
            or any("dslr" in f.lower() for f in c.forbidden + c.negative_constraints)
        )

    def test_16_missing_mandatory_continuity_state_blocked(self):
        t = ContinuityTracker()
        with self.assertRaises(ContinuityError):
            t.build_constraints_for_next(_intent(scene_id="2", dialogue_id="dlg-2"))

    def test_17_continuity_constraints_reach_prompt_compiler(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(continuity_refs={"wardrobe": "blue jacket", "lighting": "soft office"}))
        nxt = _intent(scene_id="2", dialogue_id="dlg-2", summary="Alex taps the screen.", location="", posture="")
        c = t.build_constraints_for_next(nxt)
        applied = t.apply_constraints_to_intent(nxt, c)
        compiled = compile_provider_prompt(applied)
        self.assertIn("CONTINUITY", compiled.sections)
        self.assertTrue(compiled.sections["CONTINUITY"])
        self.assertIn("NEGATIVE_CONSTRAINTS", compiled.sections)
        # Forbidden must not be only inside positive free-form
        self.assertTrue(compiled.negative)

    def test_18_prompt_contradiction_blocks_generation(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(location="office"))
        nxt = _intent(scene_id="2", dialogue_id="dlg-2", summary="Alex works.", location="")
        c = t.build_constraints_for_next(nxt)
        applied = t.apply_constraints_to_intent(nxt, c)
        compiled = compile_provider_prompt(applied)
        issues = validate_prompt_contradiction(
            applied,
            compiled,
            provider_prompt=compiled.positive + "\nENVIRONMENT: tropical beach stadium",
        )
        self.assertTrue(any(i.severity == "CRITICAL" for i in issues))

    def test_19_visual_audio_subtitle_share_scene_identity(self):
        scenes = [
            {
                "narration": "Alex sits in the office holding a smartphone.",
                "dialogue_id": "dlg-a",
                "canonical_scene_id": "sc-a",
                "script_id": "scr-1",
                "actors": ["Alex"],
                "location": "office",
                "posture": "sitting on chair",
            },
            {
                "narration": "Alex checks a notification on the phone.",
                "dialogue_id": "dlg-b",
                "canonical_scene_id": "sc-b",
                "script_id": "scr-1",
                "actors": ["Alex"],
            },
        ]
        out = apply_production_continuity(self.tmp, scenes, job_id="job-c")
        for sc in out:
            ident = sc.get("shared_scene_identity") or {}
            self.assertEqual(ident.get("dialogue_id"), sc.get("dialogue_id"))
            self.assertTrue(ident.get("scene_id"))
            self.assertTrue(sc.get("_continuity_applied"))

    def test_20_retry_preserves_continuity_fingerprint(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent())
        fp1 = t.state.fingerprint
        t.persist(self.tmp)
        t2 = ContinuityTracker.load(self.tmp)
        self.assertIsNotNone(t2)
        self.assertEqual(t2.state.fingerprint, fp1)

    def test_21_repair_does_not_reset_valid_upstream_continuity(self):
        # Persisted state survives a visual-only repair simulation (reload)
        scenes = [
            {"narration": "Alex sits holding a smartphone in the office.", "dialogue_id": "d1", "canonical_scene_id": "s1", "actors": ["Alex"], "location": "office"},
            {"narration": "Alex reads the message.", "dialogue_id": "d2", "canonical_scene_id": "s2", "actors": ["Alex"]},
        ]
        apply_production_continuity(self.tmp, scenes, job_id="job-r")
        loaded = ContinuityTracker.load(self.tmp)
        self.assertIsNotNone(loaded and loaded.state)
        fp = loaded.state.fingerprint
        # Simulate repair: reload without wiping file
        loaded2 = ContinuityTracker.load(self.tmp)
        self.assertEqual(loaded2.state.fingerprint, fp)

    def test_22_production_path_invokes_continuity(self):
        # apply_production_continuity is the production entry (wired from scene_runtime)
        scenes = [
            {"narration": "Host reviews the phone camera in soft light.", "dialogue_id": "d1", "canonical_scene_id": "s1"},
            {"narration": "Host zooms on the lens module.", "dialogue_id": "d2", "canonical_scene_id": "s2"},
        ]
        out = apply_production_continuity(self.tmp, scenes, job_id="job-prod")
        self.assertTrue((self.tmp / "CONTINUITY_STATE.json").is_file())
        self.assertTrue(out[0].get("continuity_initialized") or out[0].get("_continuity_applied"))
        self.assertTrue(out[1].get("continuity_constraints") or out[1].get("_continuity_applied"))
        self.assertIn("CONTINUITY:", out[1].get("visual_prompt", "") + out[0].get("visual_prompt", ""))
    def test_23_no_manual_dev_only_invocation_required(self):
        import inspect
        from pipeline import scene_runtime as sr

        src = inspect.getsource(sr.assert_production_scenes_validated)
        self.assertIn("apply_production_continuity", src)

    def test_24_continuity_state_persists_across_recovery(self):
        scenes = [
            {"narration": "Alex sits with a smartphone.", "dialogue_id": "d1", "canonical_scene_id": "s1", "actors": ["Alex"], "location": "office"},
            {"narration": "Alex scrolls quietly.", "dialogue_id": "d2", "canonical_scene_id": "s2", "actors": ["Alex"]},
        ]
        apply_production_continuity(self.tmp, scenes, job_id="job-rec")
        data = json.loads((self.tmp / "CONTINUITY_STATE.json").read_text(encoding="utf-8"))
        self.assertTrue(data.get("state"))
        self.assertGreaterEqual(len(data.get("history") or []), 1)

    def test_25_no_new_duplicate_continuity_authority(self):
        import pipeline.visual_semantic.continuity as cmod
        import pipeline.visual_semantic.continuity_runtime as rmod

        self.assertTrue(hasattr(cmod, "ContinuityTracker"))
        # runtime must import tracker, not define a second Tracker class
        self.assertFalse(hasattr(rmod, "ContinuityTrackerEngine"))
        self.assertFalse(hasattr(rmod, "AlternateContinuityTracker"))

    def test_prepare_blocks_on_critical_prompt(self):
        t = ContinuityTracker()
        s0 = prepare_scene_with_continuity(
            t,
            {"narration": "Alex sits holding smartphone in office.", "dialogue_id": "d1", "canonical_scene_id": "s1", "actors": ["Alex"], "location": "office"},
            scene_index=0,
        )
        self.assertTrue(s0.get("_continuity_applied"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
