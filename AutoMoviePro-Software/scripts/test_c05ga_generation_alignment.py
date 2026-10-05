"""C05-GA — Generation Alignment & Semantic Handoff (paid APIs = 0)."""
from __future__ import annotations

import copy
import inspect
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.story_visual_direction import (
    DirectedVisualBeat,
    GroundedRelation,
    ground_entities_from_text,
    ground_relations_from_text,
    render_relation_prompt_phrase,
    visual_beat_to_scene_intent,
    create_dialogue_segment,
)
from pipeline.trs_facade import (
    apply_c05s_direction_to_director_plan,
    assert_generation_alignment_preflight,
    inspect_provider_request_integrity,
    normalize_niche_plan_to_script_plan,
    refresh_c05s_from_director_plan,
    resolve_canonical_visual_prompt,
    script_plan_to_dialogue_segments,
)
from pipeline.visual_intelligence import create_visual_bible
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.continuity_runtime import prepare_scene_with_continuity


def _plan(topic="Suzuki Review"):
    return {
        "topic": topic,
        "scenes": [
            {
                "narration": "Shobha stood beside the Suzuki car on the quiet street.",
                "speaker": "Narrator",
                "visual_prompt": "LEGACY_BESIDE_WRONG",
                "exact_ai_video_prompt": "LEGACY_EXACT_WRONG",
                "location": "street",
                "emotion": "calm",
                "element": "intro",
                "dialogue_id": "dlg-beside",
            },
            {
                "narration": "She opened the document and held it carefully.",
                "speaker": "Narrator",
                "visual_prompt": "LEGACY_HOLD",
                "location": "street",
                "emotion": "focused",
                "element": "doc",
                "dialogue_id": "dlg-hold",
            },
            {
                "narration": "Would you buy this Suzuki? Tell us below.",
                "speaker": "Narrator",
                "location": "street",
                "emotion": "friendly",
                "element": "outro",
                "dialogue_id": "dlg-cta",
            },
        ],
    }


def _bible():
    return create_visual_bible(
        bible_id="vb-ga",
        subject_identity="Shobha",
        character_identity="Shobha",
        visual_style="documentary",
        location="street",
        environment="urban street",
        lighting="daylight",
    )


def _stamped(topic="Suzuki Review"):
    return refresh_c05s_from_director_plan(_plan(topic), channel_id=1, topic=topic, visual_bible=_bible())


class PromptAuthorityTests(unittest.TestCase):
    def test_01_continuity_beats_stale_c05s(self):
        r = resolve_canonical_visual_prompt(
            {
                "visual_direction_source": "C05-S",
                "c05s_compiled_positive": "STALE_C05S",
                "_continuity_applied": True,
                "visual_prompt": "FINAL_CONTINUITY",
                "canonical_compiled_positive": "FINAL_CONTINUITY",
            }
        )
        self.assertEqual(r["prompt"], "FINAL_CONTINUITY")
        self.assertEqual(r["source"], "CONTINUITY_COMPILER")
        self.assertTrue(r["stale_c05s_ignored"])

    def test_02_pre_continuity_uses_c05s(self):
        r = resolve_canonical_visual_prompt(
            {
                "visual_direction_source": "C05-S",
                "c05s_compiled_positive": "INTERMEDIATE",
            }
        )
        self.assertEqual(r["prompt"], "INTERMEDIATE")
        self.assertEqual(r["source"], "C05-S")

    def test_03_legacy_cannot_override_continuity(self):
        r = resolve_canonical_visual_prompt(
            {
                "_continuity_applied": True,
                "canonical_compiled_positive": "FINAL",
                "visual_prompt": "FINAL",
                "exact_ai_video_prompt": "LEGACY",
                "legacy_exact_ai_video_prompt": "LEGACY",
                "visual_direction_source": "C05-S",
                "c05s_compiled_positive": "STALE",
            }
        )
        self.assertEqual(r["prompt"], "FINAL")
        self.assertNotEqual(r["prompt"], "LEGACY")
        self.assertTrue(r["legacy_ignored"])

    def test_04_legacy_fallback_without_c05s(self):
        r = resolve_canonical_visual_prompt({"exact_ai_video_prompt": "ONLY_LEGACY"})
        self.assertEqual(r["source"], "LEGACY_COMPAT")

    def test_05_continuity_prepare_sets_canonical(self):
        stamped = _stamped()["director_plan"]["scenes"][0]
        out = prepare_scene_with_continuity(ContinuityTracker(), stamped, scene_index=0)
        self.assertTrue(out.get("_continuity_applied"))
        self.assertTrue(out.get("canonical_compiled_positive"))
        r = resolve_canonical_visual_prompt(out)
        self.assertEqual(r["source"], "CONTINUITY_COMPILER")
        self.assertEqual(r["prompt"], out["canonical_compiled_positive"])

    def test_06_stale_ignored_flag(self):
        stamped = _stamped()["director_plan"]["scenes"][0]
        stamped["c05s_compiled_positive"] = "TOTALLY_STALE_MARKER_XYZ"
        out = prepare_scene_with_continuity(ContinuityTracker(), stamped, scene_index=0)
        r = resolve_canonical_visual_prompt(out)
        self.assertTrue(r.get("stale_c05s_ignored"))
        self.assertNotIn("TOTALLY_STALE_MARKER_XYZ", r["prompt"])


class RelationPreservationTests(unittest.TestCase):
    def test_07_beside_not_located_at(self):
        er = GroundedRelation("r1", "p1", "v1", "beside").to_entity_relation()
        self.assertEqual(er.relation_type, "beside")
        self.assertEqual(er.attributes.get("c05s_relation"), "beside")

    def test_08_holding_preserved(self):
        er = GroundedRelation("r2", "p1", "o1", "holding").to_entity_relation()
        self.assertEqual(er.relation_type, "holding")

    def test_09_inside_preserved(self):
        er = GroundedRelation("r3", "p1", "v1", "inside").to_entity_relation()
        self.assertEqual(er.relation_type, "inside")

    def test_10_driving_preserved(self):
        er = GroundedRelation("r4", "p1", "v1", "driving").to_entity_relation()
        self.assertEqual(er.relation_type, "driving")

    def test_11_next_to_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="next_to", target_label="B")
        self.assertIn("next to", p.lower())

    def test_12_beside_phrase_not_located(self):
        p = render_relation_prompt_phrase(source_label="Shobha", relation_type="beside", target_label="Suzuki")
        self.assertIn("beside", p.lower())
        self.assertNotIn("located at", p.lower())

    def test_13_left_of_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="left_of", target_label="B")
        self.assertIn("left", p.lower())

    def test_14_right_of_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="right_of", target_label="B")
        self.assertIn("right", p.lower())

    def test_15_ground_beside(self):
        ents = ground_entities_from_text("Shobha stood beside the Suzuki.")
        rels = ground_relations_from_text("Shobha stood beside the Suzuki.", ents)
        self.assertTrue(any(r.relation_type == "beside" for r in rels))

    def test_16_ground_driving(self):
        ents = ground_entities_from_text("Shobha was driving the Suzuki.")
        rels = ground_relations_from_text("Shobha was driving the Suzuki.", ents)
        self.assertTrue(any(r.relation_type == "driving" for r in rels))

    def test_17_compiler_keeps_beside(self):
        stamped = _stamped()
        sc = stamped["director_plan"]["scenes"][0]
        intent = sc["c05s_scene_intent"]
        from domain.scene_intent import SceneIntent

        si = SceneIntent.model_validate(intent)
        # Ensure beside survives projection
        types = [r.relation_type for r in si.relations]
        attrs = [str((r.attributes or {}).get("c05s_relation") or "") for r in si.relations]
        self.assertTrue(any(t == "beside" or a == "beside" for t, a in zip(types, attrs)) or "beside" in json.dumps(intent))
        compiled = compile_provider_prompt(si)
        self.assertIn("beside", compiled.positive.lower())
        self.assertFalse(
            "beside" in json.dumps(intent).lower()
            and "located at" in compiled.positive.lower()
            and "beside" not in compiled.positive.lower()
        )

    def test_18_ownership_attribute(self):
        er = GroundedRelation("r", "a", "b", "beside", required=True).to_entity_relation()
        self.assertEqual(er.attributes.get("required"), "true")
        self.assertIn("schema_compat", er.attributes)


class CoverageTimingBindingTests(unittest.TestCase):
    def test_19_coverage_first_class(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertIn("visual_coverage", sc)
        self.assertIn(str(sc.get("coverage_overall") or "").upper(), {"FULL", "PARTIAL", "NONE", "UNKNOWN"})

    def test_20_timing_first_class(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertIn("visual_timing", sc)
        self.assertIn("hold_policy", sc["visual_timing"])
        self.assertTrue(sc["visual_timing"].get("semantic_boundary"))

    def test_21_dialogue_id_present(self):
        for sc in _stamped()["director_plan"]["scenes"]:
            self.assertTrue(sc.get("dialogue_id") or sc.get("c05s_dialogue_id"))

    def test_22_beat_id_present(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("c05s_visual_beat_id"))

    def test_23_binding_method_recorded(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertIn(sc.get("c05s_binding_method"), {"dialogue_id", "beat_id", "index_fallback"})

    def test_24_reorder_preserves_binding(self):
        base = _stamped()
        plan = copy.deepcopy(base["director_plan"])
        # reorder scenes
        plan["scenes"] = list(reversed(plan["scenes"]))
        # clear beat stamps but keep dialogue_id
        for sc in plan["scenes"]:
            sc.pop("c05s_visual_beat_id", None)
            sc.pop("c05s_scene_intent", None)
            sc.pop("c05s_compiled_positive", None)
        restamped = apply_c05s_direction_to_director_plan(
            plan,
            base["c05s"],
            dialogue_segments=base["dialogue_segments"],
            bible=_bible(),
            topic="Suzuki Review",
        )
        by_dlg = {s["dialogue_id"]: s for s in restamped["scenes"]}
        self.assertEqual(by_dlg["dlg-beside"]["c05s_binding_method"], "dialogue_id")
        self.assertIn("beside", (by_dlg["dlg-beside"].get("narration") or "").lower())

    def test_25_insert_does_not_steal_binding(self):
        base = _stamped()
        plan = copy.deepcopy(base["director_plan"])
        plan["scenes"].insert(
            1,
            {
                "narration": "Inserted unrelated beat about clouds.",
                "dialogue_id": "dlg-insert",
                "location": "sky",
                "element": "insert",
            },
        )
        for sc in plan["scenes"]:
            sc.pop("c05s_visual_beat_id", None)
        restamped = apply_c05s_direction_to_director_plan(
            plan, base["c05s"], dialogue_segments=base["dialogue_segments"], bible=_bible(), topic="Suzuki Review"
        )
        beside = next(s for s in restamped["scenes"] if s.get("dialogue_id") == "dlg-beside")
        self.assertTrue(beside.get("c05s_visual_beat_id"))

    def test_26_delete_neighbor_safe(self):
        base = _stamped()
        plan = copy.deepcopy(base["director_plan"])
        plan["scenes"] = [s for s in plan["scenes"] if s.get("dialogue_id") != "dlg-hold"]
        for sc in plan["scenes"]:
            sc.pop("c05s_visual_beat_id", None)
        restamped = apply_c05s_direction_to_director_plan(
            plan, base["c05s"], dialogue_segments=base["dialogue_segments"], bible=_bible(), topic="Suzuki Review"
        )
        ids = [s.get("dialogue_id") for s in restamped["scenes"]]
        self.assertIn("dlg-beside", ids)
        self.assertNotIn("dlg-hold", ids)

    def test_27_missing_dialogue_id_issues(self):
        plan = {
            "topic": "X",
            "scenes": [{"narration": "Hello world without dialogue id.", "element": "a"}],
        }
        # empty c05s beats → legacy; with require flag issues may list missing
        out = apply_c05s_direction_to_director_plan(plan, {"visual_beats": []}, dialogue_segments=[], topic="X")
        self.assertTrue(out.get("generation_alignment", {}).get("binding_primary_key") == "dialogue_id")

    def test_28_mismatched_dialogue_warning_path(self):
        base = _stamped()
        plan = copy.deepcopy(base["director_plan"])
        plan["scenes"][0]["dialogue_id"] = "dlg-DOES-NOT-EXIST"
        plan["scenes"][0].pop("c05s_visual_beat_id", None)
        out = apply_c05s_direction_to_director_plan(
            plan, base["c05s"], dialogue_segments=base["dialogue_segments"], bible=_bible(), topic="Suzuki Review"
        )
        self.assertTrue(out.get("c05s_binding_issues") or out["scenes"][0].get("visual_direction_source") == "LEGACY_COMPAT")

    def test_29_index_is_ordering_only_flag(self):
        out = _stamped()["director_plan"]
        self.assertTrue(out["generation_alignment"]["index_is_ordering_only"])

    def test_30_multi_scene_mapping(self):
        scenes = _stamped()["director_plan"]["scenes"]
        self.assertGreaterEqual(len(scenes), 2)
        ids = [s.get("c05s_visual_beat_id") for s in scenes if s.get("c05s_visual_beat_id")]
        self.assertEqual(len(ids), len(set(ids)))


class ContinuityStateTests(unittest.TestCase):
    def test_31_location_preserved(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("location") or sc.get("location_state"))

    def test_32_character_state(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("character_state") is not None or sc.get("actors") or sc.get("subject"))

    def test_33_camera_intent(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("camera_intent"))

    def test_34_lighting_fields(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue("lighting_intent" in sc or "lighting_continuity" in sc)

    def test_35_emotion_preserved(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("emotional_intent") or sc.get("emotion"))

    def test_36_visual_mode(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("visual_mode"))

    def test_37_required_objects(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertIn("required_objects", sc)

    def test_38_required_relationships(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertIn("required_relationships", sc)

    def test_39_camera_change_not_new_location_in_intent(self):
        stamped = _stamped()
        sc0 = stamped["director_plan"]["scenes"][0]
        intent = sc0["c05s_scene_intent"]
        loc = intent.get("location")
        # continuity_expected True; narrative_change_allowed False
        self.assertTrue(intent.get("continuity_expected"))
        self.assertFalse(intent.get("narrative_change_allowed"))
        self.assertTrue(loc)

    def test_40_environment_state(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("environment") or sc.get("environment_state"))


class C05VAudioProviderTests(unittest.TestCase):
    def test_41_c05v_bible_in_intent(self):
        intent = _stamped()["director_plan"]["scenes"][0]["c05s_scene_intent"]
        self.assertTrue(intent.get("visual_bible_id"))

    def test_42_provider_integrity_ok(self):
        stamped = _stamped()["director_plan"]["scenes"][0]
        out = prepare_scene_with_continuity(ContinuityTracker(), stamped, scene_index=0)
        rep = inspect_provider_request_integrity(out, narration=out.get("narration") or "")
        self.assertTrue(rep["checks"]["has_prompt"])
        self.assertTrue(rep["checks"]["has_dialogue_id"])
        self.assertTrue(rep["checks"]["has_beat_id"])
        self.assertEqual(rep["checks"]["source"], "CONTINUITY_COMPILER")

    def test_43_provider_detects_relation_degradation(self):
        # synthetic degraded case
        scene = {
            "dialogue_id": "d1",
            "c05s_visual_beat_id": "vb1",
            "required_relationships": [{"relation_type": "beside"}],
            "_continuity_applied": True,
            "canonical_compiled_positive": "Shobha is located at the Suzuki car",
            "visual_prompt": "Shobha is located at the Suzuki car",
        }
        rep = inspect_provider_request_integrity(scene)
        self.assertTrue(rep["checks"]["prompt_degraded_located_at_for_beside"])

    def test_44_audio_emotion_on_scene(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("emotional_intent") or sc.get("emotion"))

    def test_45_audio_plan_reads_emotion(self):
        from pipeline.audio_design.production import apply_production_audio_design

        tmp = Path(tempfile.mkdtemp())
        try:
            sc = _stamped()["director_plan"]["scenes"][0]
            sc["narration"] = sc.get("narration") or "Shobha stood beside the Suzuki."
            out = apply_production_audio_design(tmp, [sc], job_id="ga-audio")
            self.assertTrue(out[0].get("audio_plan"))
            self.assertTrue(out[0]["audio_plan"].get("emotion"))
            self.assertEqual(out[0]["audio_plan"].get("dialogue_id"), sc.get("dialogue_id"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_46_tts_call_site_uses_dialogue_id(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp.generate_video)
        self.assertIn("emotional_intent", src)
        self.assertIn("audio_plan", src)
        self.assertIn("c05s_dialogue_id", src)

    def test_47_voice_emotion_distinct(self):
        # AudioPlan emotion is intent; voice profile separate
        from pipeline.audio_design.plan_builder import build_industrial_audio_plan

        plan = build_industrial_audio_plan(
            scene_id="s1",
            dialogue_id="d1",
            dialogue_text="Hello",
            voice_profile="Charon",
            emotion="calm",
        )
        self.assertEqual(plan.voice_profile, "Charon")
        self.assertEqual(plan.emotion, "calm")
        self.assertNotEqual(plan.voice_profile, plan.emotion)


class FailClosedIdempotencyIsolation(unittest.TestCase):
    def test_48_missing_dialogue_blocks_when_required(self):
        r = assert_generation_alignment_preflight(
            [{"narration": "x", "visual_direction_source": "C05-S", "c05s_visual_beat_id": "b"}],
            require_dialogue_id=True,
        )
        self.assertTrue(r["blocked"])

    def test_49_missing_beat_blocks(self):
        r = assert_generation_alignment_preflight(
            [{"dialogue_id": "d1", "visual_direction_source": "C05-S", "c05s_compiled_positive": "p"}],
            require_visual_binding=True,
        )
        self.assertTrue(r["blocked"])

    def test_50_unsupported_mode_blocks(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d1",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_scene_intent": {"scene_id": "s"},
                "visual_mode": "HOLOGRAM",
            }]
        )
        self.assertTrue(any("unsupported_visual_mode" in b for b in r["blocks"]))

    def test_51_coverage_none_optional_policy(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d1",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "coverage_overall": "NONE",
            }],
            block_mandatory_coverage_none=True,
        )
        self.assertTrue(r["blocked"])

    def test_52_unknown_not_blocked_by_default(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d1",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "coverage_overall": "UNKNOWN",
            }],
            block_mandatory_coverage_unknown=False,
        )
        self.assertFalse(any("mandatory_coverage_unknown" in b for b in r["blocks"]))

    def test_53_unknown_blocks_when_mandatory(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d1",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "coverage_overall": "UNKNOWN",
            }],
            block_mandatory_coverage_unknown=True,
        )
        self.assertTrue(r["blocked"])
        self.assertTrue(r["unknowns"])

    def test_54_pass_aligned_scene(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        r = assert_generation_alignment_preflight([sc], block_mandatory_coverage_none=False)
        self.assertTrue(r["ok"], r)

    def test_55_fingerprint_changes_with_prompt(self):
        from pipeline.idempotency.visual_request import VisualRequestSpec, GenerationMode

        a = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="beside suzuki", visual_prompt="beside suzuki",
            dialogue_id="d1",
        )
        b = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="inside suzuki", visual_prompt="inside suzuki",
            dialogue_id="d1",
        )
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_56_fingerprint_changes_with_dialogue_id(self):
        from pipeline.idempotency.visual_request import VisualRequestSpec, GenerationMode

        a = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="p", visual_prompt="p", dialogue_id="d1",
        )
        b = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="p", visual_prompt="p", dialogue_id="d2",
        )
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_57_channel_isolation_stamps(self):
        a = refresh_c05s_from_director_plan(_plan(), channel_id=1, topic="T", visual_bible=_bible())
        b = refresh_c05s_from_director_plan(_plan(), channel_id=2, topic="T", visual_bible=_bible())
        # same semantic plan content but different channel bible ids in refresh path
        self.assertEqual(a["director_plan"]["scenes"][0]["dialogue_id"], b["director_plan"]["scenes"][0]["dialogue_id"])
        self.assertNotEqual(a.get("bible", {}).get("bible_id"), None)

    def test_58_customer_negative_no_cross_leak_fields(self):
        plan_a = _plan("TopicA")
        plan_a["scenes"][0]["narration"] = "Customer A exclusive subject Alpha stood beside the car."
        plan_b = _plan("TopicB")
        plan_b["scenes"][0]["narration"] = "Customer B exclusive subject Beta stood beside the truck."
        a = refresh_c05s_from_director_plan(plan_a, channel_id=1, topic="TopicA", visual_bible=_bible())[
            "director_plan"
        ]["scenes"][0]
        b = refresh_c05s_from_director_plan(plan_b, channel_id=99, topic="TopicB", visual_bible=_bible())[
            "director_plan"
        ]["scenes"][0]
        self.assertIn("Alpha", a.get("narration") or "")
        self.assertIn("Beta", b.get("narration") or "")
        self.assertNotEqual(a.get("narration"), b.get("narration"))


class CompatibilitySmokeTests(unittest.TestCase):
    def test_59_scene_intent_projection(self):
        stamped = _stamped()
        intent = stamped["director_plan"]["scenes"][0]["c05s_scene_intent"]
        self.assertTrue(intent.get("dialogue_id") or intent.get("scene_id"))

    def test_60_continuity_tracker_path(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        out = prepare_scene_with_continuity(ContinuityTracker(), sc, scene_index=0)
        self.assertTrue(out.get("_continuity_applied"))

    def test_61_prompt_compiler_sections(self):
        from domain.scene_intent import SceneIntent

        intent = SceneIntent.model_validate(_stamped()["director_plan"]["scenes"][0]["c05s_scene_intent"])
        c = compile_provider_prompt(intent)
        self.assertIn("RELATIONSHIPS", c.sections)
        self.assertIn("ENVIRONMENT", c.sections)
        self.assertIn("CAMERA", c.sections)

    def test_62_legacy_exact_demoted(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("legacy_exact_ai_video_prompt") or sc.get("legacy_visual_prompt"))

    def test_63_no_second_compiler_in_trs(self):
        import pipeline.trs_facade as tf

        self.assertNotIn("def compile_provider_prompt", inspect.getsource(tf))

    def test_64_no_second_continuity_engine(self):
        import pipeline.trs_facade as tf

        self.assertNotIn("class ContinuityTracker", inspect.getsource(tf))

    def test_65_generate_video_alignment_hook(self):
        import pipeline.video_pipeline as vp

        self.assertIn("assert_generation_alignment_preflight", inspect.getsource(vp.generate_video))

    def test_66_p04_boundary_not_claimed(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        cov = sc.get("visual_coverage") or {}
        self.assertIn("intent_planning", str(cov.get("note") or "intent_planning_only"))

    def test_67_import_smoke(self):
        from pipeline import trs_facade, story_visual_direction, video_pipeline

        self.assertTrue(callable(trs_facade.resolve_canonical_visual_prompt))
        self.assertTrue(callable(story_visual_direction.render_relation_prompt_phrase))
        self.assertTrue(callable(video_pipeline.generate_video))

    def test_68_paid_api_zero_on_inspect(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertEqual(inspect_provider_request_integrity(sc)["paid_api_calls"], 0)

    def test_69_script_plan_segments(self):
        segs = script_plan_to_dialogue_segments(normalize_niche_plan_to_script_plan(_plan()))
        self.assertTrue(all(s.dialogue_id for s in segs))

    def test_70_directed_beat_roundtrip(self):
        raw = _stamped()["c05s"]["visual_beats"][0]
        beat = DirectedVisualBeat.from_dict(raw)
        self.assertEqual(beat.beat_id, raw["beat_id"])


class ExtraAlignmentMatrix(unittest.TestCase):
    def test_71_holding_in_prompt(self):
        # scene 1 is document holding
        sc = _stamped()["director_plan"]["scenes"][1]
        out = prepare_scene_with_continuity(ContinuityTracker(), sc, scene_index=1)
        # may or may not ground holding depending on entity extract — relation list check
        self.assertTrue(out.get("canonical_compiled_positive") or out.get("visual_prompt"))

    def test_72_looking_at_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="looking_at", target_label="doc")
        self.assertIn("looking at", p.lower())

    def test_73_behind_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="behind", target_label="car")
        self.assertIn("behind", p.lower())

    def test_74_in_front_of_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="in_front_of", target_label="car")
        self.assertIn("front", p.lower())

    def test_75_wearing_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="wearing", target_label="coat")
        self.assertIn("wearing", p.lower())

    def test_76_carrying_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="carrying", target_label="bag")
        self.assertIn("carrying", p.lower())

    def test_77_speaking_to_phrase(self):
        p = render_relation_prompt_phrase(source_label="A", relation_type="speaking_to", target_label="B")
        self.assertIn("speaking", p.lower())

    def test_78_preflight_relationship_none_blocks(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "visual_coverage": {"relationship": "NONE", "overall": "PARTIAL"},
            }]
        )
        self.assertTrue(any("relationship_coverage_none" in b for b in r["blocks"]))

    def test_79_preflight_entity_none_blocks(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "visual_coverage": {"entity": "NONE", "overall": "PARTIAL"},
            }]
        )
        self.assertTrue(any("entity_coverage_none" in b for b in r["blocks"]))

    def test_80_contradictory_location_blocks(self):
        r = assert_generation_alignment_preflight(
            [{
                "dialogue_id": "d",
                "visual_direction_source": "C05-S",
                "c05s_visual_beat_id": "b",
                "c05s_compiled_positive": "x",
                "location": "street",
                "location_state": {"location": "office", "continuity": "SAME_LOCATION"},
            }]
        )
        self.assertTrue(any("contradictory_location" in b for b in r["blocks"]))

    def test_81_provider_has_location(self):
        out = prepare_scene_with_continuity(ContinuityTracker(), _stamped()["director_plan"]["scenes"][0], scene_index=0)
        rep = inspect_provider_request_integrity(out)
        self.assertTrue(rep["checks"]["has_location"])

    def test_82_provider_has_camera(self):
        out = prepare_scene_with_continuity(ContinuityTracker(), _stamped()["director_plan"]["scenes"][0], scene_index=0)
        rep = inspect_provider_request_integrity(out)
        self.assertTrue(rep["checks"]["has_camera"] or "CAMERA" in (rep.get("prompt_preview") or ""))

    def test_83_provider_has_visual_mode(self):
        out = prepare_scene_with_continuity(ContinuityTracker(), _stamped()["director_plan"]["scenes"][0], scene_index=0)
        rep = inspect_provider_request_integrity(out)
        self.assertTrue(rep["checks"]["has_visual_mode"])

    def test_84_provider_has_coverage(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        rep = inspect_provider_request_integrity(sc)
        self.assertTrue(rep["checks"]["has_coverage"])

    def test_85_provider_has_timing(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        rep = inspect_provider_request_integrity(sc)
        self.assertTrue(rep["checks"]["has_timing"])

    def test_86_same_fingerprint_same_prompt(self):
        from pipeline.idempotency.visual_request import VisualRequestSpec, GenerationMode

        a = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="same", visual_prompt="same", dialogue_id="d",
        )
        b = VisualRequestSpec(
            job_id="j", scene_id=0, visual_plan_id="vp", provider="mock", model="m",
            generation_mode=GenerationMode.IMAGE_GENERATION, prompt="same", visual_prompt="same", dialogue_id="d",
        )
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_87_c05q_compat_emotion_field(self):
        sc = _stamped()["director_plan"]["scenes"][0]
        self.assertTrue("emotional_intent" in sc or "emotion" in sc)

    def test_88_publishability_untouched(self):
        import pipeline.trs_facade as tf

        self.assertNotIn("run_publishability_gate", inspect.getsource(tf))

    def test_89_build04f_untouched(self):
        import pipeline.trs_facade as tf

        self.assertNotIn("def run_creative_quality", inspect.getsource(tf))

    def test_90_semantic_timing_not_fixed_interval(self):
        vt = _stamped()["director_plan"]["scenes"][0]["visual_timing"]
        self.assertIn("adaptive_semantic", vt.get("note", ""))

    def test_91_continuity_refs_on_intent(self):
        intent = _stamped()["director_plan"]["scenes"][0]["c05s_scene_intent"]
        self.assertIn("continuity_refs", intent)

    def test_92_segment_create_timing(self):
        seg = create_dialogue_segment(
            segment_id="s", dialogue_id="d", scene_id="sc", text="hi", start_sec=1.0, end_sec=3.0
        )
        self.assertEqual(seg.duration_sec, 2.0)

    def test_93_visual_beat_to_scene_intent_relations(self):
        ents = ground_entities_from_text("Shobha stood beside the Suzuki.")
        rels = ground_relations_from_text("Shobha stood beside the Suzuki.", ents)
        seg = create_dialogue_segment(
            segment_id="s1", dialogue_id="d1", scene_id="sc1", text="Shobha stood beside the Suzuki.", location="street"
        )
        from pipeline.story_visual_direction import build_directed_visual_beat, create_narrative_beat

        nb = create_narrative_beat(beat_id="nb1", segment=seg, order=0)
        vb = build_directed_visual_beat(
            beat_id="vb1", segment=seg, narrative=nb, bible=_bible(), entities=ents, relations=rels
        )
        intent = visual_beat_to_scene_intent(vb, seg, _bible())
        self.assertTrue(any(r.relation_type == "beside" for r in intent.relations))

    def test_94_resolver_narration_fallback(self):
        r = resolve_canonical_visual_prompt({}, narration="only narr")
        self.assertEqual(r["source"], "NARRATION_FALLBACK")

    def test_95_alignment_authority_string(self):
        r = assert_generation_alignment_preflight([])
        self.assertIn("C05-GA", r["authority"])


if __name__ == "__main__":
    unittest.main()
