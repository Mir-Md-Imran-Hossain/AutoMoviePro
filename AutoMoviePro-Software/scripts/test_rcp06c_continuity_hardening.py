#!/usr/bin/env python3
"""RCP-06C — Continuity hardening: explicit camera / lighting / relationship contracts.

Extends ContinuityTracker only. No paid API. Heuristic results are never PASS/PROVIDER_VERIFIED.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.scene_intent import EntityRelation, SceneIntent
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.contracts import SemanticIssueCode


def _intent(**over) -> SceneIntent:
    base = dict(
        scene_id="1",
        dialogue_id="dlg-1",
        summary="Alex sits in the office holding a smartphone.",
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


def _critical_breaks(issues):
    return [
        i
        for i in issues
        if i.severity == "CRITICAL" and i.code == SemanticIssueCode.CONTINUITY_BREAK
    ]


class Rcp06cContinuityHardeningTests(unittest.TestCase):
    def test_01_explicit_camera_contradiction_blocks(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                camera_position="extreme close-up",
                framing="tight face",
                continuity_refs={"explicit_camera": True, "camera_language": "extreme close-up"},
            )
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Wide establishing shot of the whole office floor.",
            camera_position="wide establishing",
            framing="full room",
            continuity_refs={"explicit_camera": True, "camera_language": "wide establishing aerial-style"},
        )
        # Make contradiction clearer: wide + aerial family vs close
        nxt.continuity_refs["camera_language"] = "wide aerial drone"
        c = t.build_constraints_for_next(nxt)
        self.assertTrue(c.require_camera_contract)
        issues = t.validate_pre_generation(nxt, c)
        msgs = [i.message for i in _critical_breaks(issues)]
        self.assertTrue(any("camera" in m.lower() for m in msgs), msgs)
        for i in _critical_breaks(issues):
            self.assertNotIn("PASS", str(i.evidence))
            self.assertNotIn("PROVIDER_VERIFIED", str(i.evidence))
            self.assertIn("heuristic_contract_compare_not_provider_verified", str(i.evidence.get("note", "")))

    def test_02_non_explicit_camera_does_not_hard_block(self):
        t = ContinuityTracker()
        # Adapter-style soft defaults only — no explicit_camera / no field-level contract
        t.initialize_from_intent(
            _intent(continuity_refs={"camera_language": "medium", "camera": "medium"})
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex checks the phone.",
            continuity_refs={"camera_language": "wide", "camera": "wide"},
        )
        c = t.build_constraints_for_next(nxt)
        self.assertFalse(c.require_camera_contract)
        issues = t.validate_pre_generation(nxt, c)
        self.assertFalse(any("camera" in i.message.lower() for i in _critical_breaks(issues)))

    def test_03_explicit_lighting_contradiction_blocks(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                continuity_refs={
                    "explicit_lighting": True,
                    "lighting": "bright daylight sunny noon",
                }
            )
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex still in the office.",
            continuity_refs={
                "explicit_lighting": True,
                "lighting": "pitch night moonlight dark",
            },
        )
        c = t.build_constraints_for_next(nxt)
        self.assertTrue(c.require_lighting_contract)
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(any("lighting" in i.message.lower() for i in _critical_breaks(issues)))

    def test_04_non_explicit_lighting_does_not_hard_block(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(continuity_refs={"lighting": "natural"}))
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            continuity_refs={"lighting": "night"},
        )
        c = t.build_constraints_for_next(nxt)
        self.assertFalse(c.require_lighting_contract)
        issues = t.validate_pre_generation(nxt, c)
        self.assertFalse(any("lighting" in i.message.lower() for i in _critical_breaks(issues)))

    def test_05_explicit_relationship_contradiction_blocks(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                relations=[
                    EntityRelation(
                        relation_id="r1",
                        source_id="Alex",
                        target_id="Sam",
                        relation_type="sitting-with",
                    )
                ]
            )
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex and Sam in the office.",
            relations=[
                EntityRelation(
                    relation_id="r2",
                    source_id="Alex",
                    target_id="Sam",
                    relation_type="separated",
                )
            ],
        )
        c = t.build_constraints_for_next(nxt)
        self.assertTrue(c.required_relationships)
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(any("relationship" in i.message.lower() for i in _critical_breaks(issues)))

    def test_06_relationship_without_next_explicit_does_not_block(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                relations=[
                    EntityRelation(
                        relation_id="r1",
                        source_id="Alex",
                        target_id="PHONE_01",
                        relation_type="beside",
                    )
                ]
            )
        )
        nxt = _intent(scene_id="2", dialogue_id="dlg-2", summary="Alex looks at the screen.", relations=[])
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        self.assertFalse(any("relationship" in i.message.lower() for i in _critical_breaks(issues)))

    def test_07_lighting_transition_words_allow(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(continuity_refs={"explicit_lighting": True, "lighting": "daylight sunny"})
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Hours later at night, moonlight fills the office.",
            continuity_refs={"explicit_lighting": True, "lighting": "night moonlight dark"},
        )
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        self.assertFalse(any("lighting" in i.message.lower() for i in _critical_breaks(issues)))

    def test_08_character_location_rules_still_block(self):
        t = ContinuityTracker()
        t.initialize_from_intent(_intent(actors=["Alex"], location="office"))
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            actors=["Jordan Celebrity"],
            location="beach",
            summary="Jordan stands on the beach.",
            metadata={"explicit_location": True},
        )
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        critical = _critical_breaks(issues)
        self.assertTrue(critical)
        self.assertTrue(any("location" in i.message.lower() for i in critical))

    def test_09_heuristic_never_labeled_pass_or_provider_verified(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                camera_position="close-up",
                continuity_refs={"explicit_camera": True, "camera_language": "close-up tight"},
            )
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            camera_position="wide aerial",
            continuity_refs={"explicit_camera": True, "camera_language": "wide aerial drone"},
        )
        c = t.build_constraints_for_next(nxt)
        # Must not stamp verification outcomes on constraints / evidence
        self.assertNotEqual(c.to_dict().get("verification_status"), "PASS")
        self.assertNotEqual(c.to_dict().get("verification_status"), "PROVIDER_VERIFIED")
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(_critical_breaks(issues))
        for i in issues:
            ev = i.evidence or {}
            self.assertNotEqual(ev.get("status"), "PASS")
            self.assertNotEqual(ev.get("status"), "PROVIDER_VERIFIED")
            self.assertNotEqual(ev.get("verification"), "PASS")
            self.assertNotEqual(ev.get("verification"), "PROVIDER_VERIFIED")
            note = str(ev.get("note") or "")
            if note:
                self.assertIn("not_provider_verified", note)

    def test_10_beside_vs_inside_blocks(self):
        t = ContinuityTracker()
        t.initialize_from_intent(
            _intent(
                relations=[
                    EntityRelation(
                        relation_id="r1",
                        source_id="Alex",
                        target_id="BOX",
                        relation_type="beside",
                    )
                ]
            )
        )
        nxt = _intent(
            scene_id="2",
            dialogue_id="dlg-2",
            summary="Alex and the box.",
            relations=[
                EntityRelation(
                    relation_id="r2",
                    source_id="Alex",
                    target_id="BOX",
                    relation_type="inside",
                )
            ],
        )
        c = t.build_constraints_for_next(nxt)
        issues = t.validate_pre_generation(nxt, c)
        self.assertTrue(any("relationship" in i.message.lower() for i in _critical_breaks(issues)))


if __name__ == "__main__":
    unittest.main()
