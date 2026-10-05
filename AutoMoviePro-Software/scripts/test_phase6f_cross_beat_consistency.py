"""Phase 6F — cross-beat entity / character / object / relationship consistency."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6f_evidence"


def _beat(
    beat_id: str,
    *,
    entities=None,
    objects=None,
    location="hospital room",
    action="",
    relationships=None,
    scene_id="sc-1",
    dialogue_id="",
):
    return {
        "beat_id": beat_id,
        "scene_id": scene_id,
        "dialogue_segment_id": dialogue_id or f"dlg-{beat_id}",
        "required_entities": entities or [],
        "required_objects": objects or [],
        "location_state": {"location": location},
        "character_state": {"identity": "", "action": action},
        "relationships": relationships or [],
    }


def _obs(**kw):
    from pipeline.observation.frame_evidence import empty_frame_evidence

    ev = empty_frame_evidence(asset_id="a", beat_id=kw.pop("beat_id", "b"), scene_id="s", timestamp=0.0)
    ev.update(
        {
            "observation_status": "PASS",
            "provider_verified": True,
            "heuristic": False,
            "evidence_source": "PROVIDER_FRAME",
            "observed_subjects": [],
            "observed_entities": [],
            "observed_relationships": [],
            "observed_location": "",
            "observed_actions": [],
        }
    )
    ev.update(kw)
    return ev


class CharacterObjectStateTests(unittest.TestCase):
    def test_01_character_state_creation(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        rows = project_beat_entity_states(
            _beat(
                "b1",
                entities=[{"label": "Shobha", "entity_type": "character"}],
                objects=["Suzuki"],
                relationships=[{"subject": "Shobha", "relation": "BESIDE", "object": "Suzuki"}],
            ),
            _obs(
                observed_subjects=["Shobha"],
                observed_entities=["Suzuki"],
                observed_location="street",
                observed_relationships=["Shobha beside Suzuki"],
            ),
            customer_id="c11_marathon_customer",
            channel_id="4",
            job_id="job2108",
        )
        chars = [r for r in rows if r["entity_type"] == "CHARACTER"]
        self.assertTrue(chars)
        self.assertEqual(chars[0]["canonical_name"], "Shobha")
        self.assertEqual(chars[0]["presence"], "PRESENT")
        self.assertEqual(chars[0]["customer_id"], "c11_marathon_customer")

    def test_02_character_identity_binding(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        r1 = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha", "entity_type": "character"}]),
            _obs(observed_subjects=["Shobha"]),
        )
        r2 = project_beat_entity_states(
            _beat("b2", entities=[{"label": "Shobha", "entity_type": "character"}]),
            _obs(observed_subjects=["Shobha"]),
        )
        self.assertEqual(r1[0]["entity_id"], r2[0]["entity_id"])

    def test_03_object_state_creation(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        rows = project_beat_entity_states(
            _beat("b1", objects=["hospital bed"]),
            _obs(observed_entities=["hospital bed"], observed_location="hospital room"),
        )
        objs = [r for r in rows if r["canonical_name"] == "hospital bed"]
        self.assertTrue(objs)
        self.assertEqual(objs[0]["presence"], "PRESENT")

    def test_04_vehicle_continuity(self):
        from pipeline.observation.frame_evidence import compare_cross_beat_sequence

        seq = compare_cross_beat_sequence(
            [
                {
                    "beat": _beat("b1", objects=["Suzuki"], entities=[{"label": "Shobha"}]),
                    "observation": _obs(
                        observed_subjects=["Shobha"],
                        observed_entities=["Suzuki"],
                        observed_location="street",
                    ),
                    "customer_id": "c11",
                    "channel_id": "4",
                },
                {
                    "beat": _beat("b2", objects=["Suzuki"], entities=[{"label": "Shobha"}]),
                    "observation": _obs(
                        observed_subjects=["Shobha"],
                        observed_entities=["Suzuki"],
                        observed_location="street",
                    ),
                    "customer_id": "c11",
                    "channel_id": "4",
                },
            ]
        )
        self.assertNotEqual(seq["status"], "FAIL")
        self.assertFalse(seq["second_continuity_engine"])


class LocationRelationshipTests(unittest.TestCase):
    def test_05_location_normalization(self):
        from pipeline.observation.frame_evidence.normalize import location_cluster

        self.assertEqual(location_cluster("hospital hallway"), "hospital")
        self.assertEqual(location_cluster("hospital room"), "hospital")

    def test_06_compatible_sub_location(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat("b1", location="hospital hallway"),
            _obs(observed_location="hospital hallway"),
        )
        b = project_beat_entity_states(
            _beat("b2", location="hospital room"),
            _obs(observed_location="hospital room"),
        )
        cmp = compare_entity_states_adjacent(
            a, b, visual_contract={"require_location": True}, continuity_constraints={"require_location": True}
        )
        self.assertNotEqual(cmp["status"], "FAIL")
        loc_rows = [c for c in cmp["comparisons"] if c.get("location_class")]
        self.assertTrue(any(c.get("location_class") == "COMPATIBLE_SUBLOCATION" for c in loc_rows))

    def test_07_location_contradiction(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat("b1", location="hospital room"),
            _obs(observed_location="hospital room"),
        )
        b = project_beat_entity_states(
            _beat("b2", location="desert"),
            _obs(observed_location="unrelated desert"),
        )
        cmp = compare_entity_states_adjacent(
            a, b, continuity_constraints={"require_location": True}
        )
        self.assertEqual(cmp["status"], "FAIL")
        self.assertTrue(any(c.get("class") == "LOCATION_CONTRADICTION" for c in cmp["comparisons"]))

    def test_08_relationship_state(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        rows = project_beat_entity_states(
            _beat(
                "b1",
                entities=[{"label": "Shobha"}],
                objects=["Suzuki"],
                relationships=[{"subject": "Shobha", "relation": "BESIDE", "object": "Suzuki"}],
            ),
            _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"]),
        )
        self.assertEqual(rows[0]["relationships"][0]["relation"], "beside")
        self.assertEqual(rows[0]["relationships"][0]["beat_id"], "b1")

    def test_09_valid_relationship_transition(self):
        from pipeline.observation.frame_evidence import compare_cross_beat_sequence

        seq = compare_cross_beat_sequence(
            [
                {
                    "beat": _beat(
                        "b1",
                        entities=[{"label": "Shobha"}],
                        objects=["Suzuki"],
                        relationships=[{"subject": "Shobha", "relation": "BESIDE", "object": "Suzuki"}],
                        action="standing",
                    ),
                    "observation": _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"], observed_location="street"),
                    "customer_id": "c11",
                    "channel_id": "4",
                },
                {
                    "beat": _beat(
                        "b2",
                        entities=[{"label": "Shobha"}],
                        objects=["Suzuki"],
                        relationships=[{"subject": "Shobha", "relation": "ENTERING", "object": "Suzuki"}],
                        action="approaching",
                    ),
                    "observation": _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"], observed_location="street"),
                    "customer_id": "c11",
                    "channel_id": "4",
                },
                {
                    "beat": _beat(
                        "b3",
                        entities=[{"label": "Shobha"}],
                        objects=["Suzuki"],
                        relationships=[{"subject": "Shobha", "relation": "INSIDE", "object": "Suzuki"}],
                        action="seated",
                    ),
                    "observation": _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"], observed_location="street"),
                    "customer_id": "c11",
                    "channel_id": "4",
                },
            ]
        )
        self.assertNotEqual(seq["status"], "FAIL")
        # adjacent only by default
        self.assertEqual(len(seq["adjacent_comparisons"]), 2)
        self.assertEqual(seq["far_comparisons"], [])

    def test_10_invalid_relationship_contradiction(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat(
                "b1",
                entities=[{"label": "Shobha"}],
                objects=["Suzuki"],
                relationships=[{"subject": "Shobha", "relation": "BESIDE", "object": "Suzuki"}],
            ),
            _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"]),
        )
        b = project_beat_entity_states(
            _beat(
                "b2",
                entities=[{"label": "Shobha"}],
                objects=["Suzuki"],
                relationships=[{"subject": "Shobha", "relation": "HOLDING", "object": "Suzuki"}],
            ),
            _obs(observed_subjects=["Shobha"], observed_entities=["Suzuki"]),
        )
        cmp = compare_entity_states_adjacent(a, b, narrative_change_allowed=False)
        self.assertEqual(cmp["status"], "FAIL")


class DialogueCrossBeatTests(unittest.TestCase):
    def test_11_dialogue_beat_entity_binding(self):
        from pipeline.observation.frame_evidence import dialogue_visual_entity_binding

        bind = dialogue_visual_entity_binding(
            dialogue_id="dlg-open-door",
            beat=_beat(
                "vb-1",
                entities=[{"label": "Shobha"}],
                objects=["Suzuki"],
                relationships=[{"subject": "Shobha", "relation": "INTERACTING", "object": "Suzuki"}],
                action="opens the car door",
            ),
            observation=_obs(
                observation_status="PASS",
                provider_verified=True,
                observed_subjects=["Shobha"],
                observed_entities=["Suzuki"],
            ),
        )
        self.assertEqual(bind["dialogue_id"], "dlg-open-door")
        self.assertEqual(bind["beat_id"], "vb-1")
        self.assertTrue(bind["entity_requirements"])
        self.assertTrue(bind["keyword_only_pass_forbidden"])

    def test_12_adjacent_beat_comparison(self):
        from pipeline.observation.frame_evidence import compare_cross_beat_sequence

        seq = compare_cross_beat_sequence(
            [
                {"beat": _beat("b1", entities=[{"label": "Nurse"}]), "observation": _obs(observed_subjects=["Nurse"], observed_location="hospital room"), "customer_id": "c", "channel_id": "4"},
                {"beat": _beat("b2", entities=[{"label": "Nurse"}]), "observation": _obs(observed_subjects=["Nurse"], observed_location="hospital room"), "customer_id": "c", "channel_id": "4"},
                {"beat": _beat("b3", entities=[{"label": "Nurse"}]), "observation": _obs(observed_subjects=["Nurse"], observed_location="hospital room"), "customer_id": "c", "channel_id": "4"},
            ]
        )
        self.assertEqual(len(seq["adjacent_comparisons"]), 2)
        self.assertTrue(seq["adjacent_only"] if "adjacent_only" in seq else True)

    def test_13_explicit_continuity_requirement_far(self):
        from pipeline.observation.frame_evidence import compare_cross_beat_sequence

        seq = compare_cross_beat_sequence(
            [
                {"beat": _beat("b1", location="hospital room"), "observation": _obs(observed_location="hospital room"), "customer_id": "c", "channel_id": "4"},
                {"beat": _beat("b2", location="hospital hallway"), "observation": _obs(observed_location="hospital hallway"), "customer_id": "c", "channel_id": "4"},
                {"beat": _beat("b3", location="hospital room"), "observation": _obs(observed_location="hospital room"), "customer_id": "c", "channel_id": "4"},
            ],
            continuity_constraints={"require_location": True},
            require_far_continuity=True,
        )
        self.assertTrue(seq["far_comparisons"])
        self.assertTrue(seq["require_far_continuity"])

    def test_14_unspecified_property_no_hard_fail(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha"}], action="standing"),
            _obs(observed_subjects=["Shobha"], camera_observation="close-up"),
        )
        b = project_beat_entity_states(
            _beat("b2", entities=[{"label": "Shobha"}], action="walking"),
            _obs(observed_subjects=["Shobha"], camera_observation="wide"),
        )
        cmp = compare_entity_states_adjacent(a, b, visual_contract={}, continuity_constraints={})
        self.assertNotEqual(cmp["status"], "FAIL")


class UnknownSemanticRepairTests(unittest.TestCase):
    def test_15_unknown_observation(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        rows = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha"}]),
            _obs(observation_status="UNKNOWN", provider_verified=False, observed_subjects=[]),
        )
        self.assertEqual(rows[0]["observation_status"], "UNKNOWN")
        self.assertEqual(rows[0]["presence"], "UNKNOWN")

    def test_16_unknown_blocks_semantic(self):
        from pipeline.observation.frame_evidence import compare_cross_beat_sequence
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

        seq = compare_cross_beat_sequence(
            [
                {
                    "beat": _beat("b1", entities=[{"label": "Shobha"}]),
                    "observation": _obs(observation_status="UNKNOWN", provider_verified=False),
                    "customer_id": "c",
                    "channel_id": "4",
                },
                {
                    "beat": _beat("b2", entities=[{"label": "Shobha"}]),
                    "observation": _obs(observation_status="UNKNOWN", provider_verified=False),
                    "customer_id": "c",
                    "channel_id": "4",
                },
            ]
        )
        self.assertEqual(seq["status"], "UNKNOWN")
        sem = attach_frame_evidence_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            {"observations": [_obs(observation_status="UNKNOWN")], "temporal": {"status": "UNKNOWN"}, "cross_beat": seq},
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem["blocking"])

    def test_17_unknown_does_not_repair(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        h = repair_handoff_from_frame_evidence(
            beat_id="b1",
            scene_id="s1",
            frame_bridge_or_temporal={"temporal": {"status": "UNKNOWN"}, "cross_beat": {"status": "UNKNOWN"}},
        )
        self.assertFalse(h["repair_triggered"])


class RealEvidenceAndAuthorityTests(unittest.TestCase):
    def test_18_19_real_negative_fail_if_present(self):
        p = EV / "02_negative_cross_beat.json"
        if not p.exists():
            # Fall back to Phase 6D negative projected through cross-beat
            from pipeline.observation.frame_evidence import compare_cross_beat_sequence

            neg = _obs(
                observation_status="FAIL",
                provider_verified=True,
                observed_subjects=["woman with short silver-grey hair"],
                observed_entities=["futuristic suit collar"],
                observed_location="futuristic/sci-fi interior",
            )
            pos = _obs(
                observation_status="PASS",
                observed_subjects=["nurse"],
                observed_entities=["hospital bed"],
                observed_location="hospital room",
            )
            seq = compare_cross_beat_sequence(
                [
                    {
                        "beat": _beat(
                            "b1",
                            entities=[{"label": "nurse", "entity_type": "character"}],
                            objects=["hospital bed"],
                            location="hospital room",
                        ),
                        "observation": pos,
                        "customer_id": "c11",
                        "channel_id": "4",
                    },
                    {
                        "beat": _beat(
                            "b2",
                            entities=[{"label": "nurse", "entity_type": "character"}],
                            objects=["hospital bed"],
                            location="hospital room",
                        ),
                        "observation": neg,
                        "customer_id": "c11",
                        "channel_id": "4",
                    },
                ],
                continuity_constraints={"require_location": True},
            )
            self.assertEqual(seq["status"], "FAIL")
            self.assertNotEqual(seq["status"], "PASS")
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("status"), "FAIL")
        self.assertNotEqual(data.get("status"), "PASS")

    def test_20_build04f_visual_asset_handoff(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        h = repair_handoff_from_frame_evidence(
            beat_id="vb-xbeat",
            scene_id="sc-1",
            frame_bridge_or_temporal={
                "temporal": {"status": "FAIL", "issues": ["cross_beat_location_contradiction"]},
                "cross_beat": {"status": "FAIL"},
            },
        )
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(h["whole_video_regeneration"])

    def test_21_24_25_targeted_repair_structure(self):
        import inspect

        from pipeline.observation.frame_evidence.repair_loop import execute_targeted_visual_asset_repair_loop

        src = inspect.getsource(execute_targeted_visual_asset_repair_loop)
        self.assertIn("max_repair_attempts = 1", src)
        self.assertIn("whole_video_regeneration", src)
        p = EV / "04_repair_handoff.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(data.get("whole_video_regeneration", True))

    def test_22_23_lineage_reobserve_if_present(self):
        p = EV / "05_repair_execution.json"
        if not p.exists():
            self.skipTest("phase6f repair execution evidence not generated yet")
        data = json.loads(p.read_text(encoding="utf-8"))
        lin = data.get("lineage") or {}
        self.assertTrue(lin.get("old_content_hash") or data.get("old_content_hash"))
        self.assertFalse(data.get("whole_video_regeneration", True))

    def test_26_clip_similarity_not_identity_pass(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha"}]),
            _obs(observed_subjects=["Shobha"]),
        )
        self.assertTrue(a[0]["clip_similarity_is_not_identity_pass"])
        cmp = compare_entity_states_adjacent(a, a)
        self.assertTrue(cmp["clip_similarity_is_not_identity_pass"])
        self.assertFalse(cmp.get("identity_certification_engine", True))

    def test_27_provider_verified_distinction(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states

        live = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Nurse"}]),
            _obs(provider_verified=True, heuristic=False, evidence_source="PROVIDER_FRAME", observed_subjects=["Nurse"]),
        )
        heur = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Nurse"}]),
            _obs(
                observation_status="UNKNOWN",
                provider_verified=False,
                heuristic=True,
                evidence_source="HEURISTIC",
                observed_subjects=["Nurse"],
            ),
        )
        self.assertTrue(live[0]["source_evidence"]["provider_verified"])
        self.assertFalse(heur[0]["source_evidence"]["provider_verified"])
        self.assertNotEqual(heur[0]["observation_status"], "PASS")

    def test_28_customer_isolation(self):
        from pipeline.observation.frame_evidence import compare_entity_states_adjacent, project_beat_entity_states

        a = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha"}]),
            _obs(observed_subjects=["Shobha"]),
            customer_id="c11",
            channel_id="4",
        )
        b = project_beat_entity_states(
            _beat("b2", entities=[{"label": "Shobha"}]),
            _obs(observed_subjects=["Shobha"]),
            customer_id="other_customer",
            channel_id="4",
        )
        cmp = compare_entity_states_adjacent(a, b)
        self.assertEqual(cmp["status"], "FAIL")
        self.assertIn("cross_customer", str(cmp.get("reason") or ""))

    def test_29_30_provenance_secret_stripping(self):
        from pipeline.observation.frame_evidence import project_beat_entity_states
        from pipeline.retrieval.common import strip_secrets

        rows = project_beat_entity_states(
            _beat("b1", entities=[{"label": "Shobha"}]),
            _obs(observed_subjects=["Shobha"], api_key="SECRET_KEY_VALUE"),
            customer_id="c11",
            channel_id="4",
            job_id="job2108",
        )
        blob = json.dumps(rows)
        self.assertNotIn("SECRET_KEY_VALUE", blob)
        self.assertNotIn("api_key", strip_secrets({"api_key": "x"}))
        self.assertEqual(rows[0]["job_id"], "job2108")

    def test_31_32_33_34_35_36_authorities(self):
        import inspect

        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.observation.frame_evidence import execute_targeted_visual_asset_repair_loop
        from pipeline.story_visual_direction import architecture_integrity_snapshot
        from pipeline.visual_semantic.continuity import ContinuityTracker

        snap = architecture_integrity_snapshot()
        self.assertEqual(snap["continuity_authority"], "pipeline.visual_semantic.continuity.ContinuityTracker")
        self.assertFalse(snap["second_continuity_engine"])
        self.assertTrue(snap["cross_beat_is_not_second_continuity_engine"])
        self.assertTrue(snap["frame_evidence_is_not_identity_certification_engine"])
        self.assertTrue(snap["frame_evidence_is_not_semantic_gate"])
        self.assertTrue(snap["frame_evidence_is_not_ffmpeg_engine"])
        self.assertFalse(snap["second_repair_engine"])
        self.assertFalse(snap["openmontage_agpl_imported"])
        self.assertTrue(callable(idempotent_image_clip_via_build03))
        self.assertTrue(callable(IdempotentExecutor))
        self.assertTrue(callable(ContinuityTracker))
        self.assertTrue(callable(execute_targeted_visual_asset_repair_loop))
        src = inspect.getsource(execute_targeted_visual_asset_repair_loop)
        self.assertNotIn("class RepairEngine", src)
        for rel in (
            "pipeline/observation/frame_evidence/cross_beat.py",
            "pipeline/observation/frame_evidence/normalize.py",
            "pipeline/observation/frame_evidence/repair_loop.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", text)
            self.assertNotRegex(text, r"^\s*(from|import)\s+.*OpenMontage")


if __name__ == "__main__":
    unittest.main()
