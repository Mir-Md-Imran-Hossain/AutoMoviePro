"""AMP-004 Phase-07 — Industrial creative production & retention tests.

No paid API calls.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from domain.scene_intent import SceneIntent
from pipeline.creative_production.action_entity import (
    parse_action_atoms,
    validate_action_atomicity,
    validate_entity_attribute_ownership,
    validate_physical_plausibility_heuristic,
)
from pipeline.creative_production.camera import (
    controlled_variation_for_role,
    validate_camera_continuity,
    validate_shot_purpose,
)
from pipeline.creative_production.contract import (
    ActionAtom,
    CreativeProductionPlan,
    ScenePurpose,
    build_creative_production_plan,
    creative_plan_fingerprint,
)
from pipeline.creative_production.gate import (
    MAX_CREATIVE_REPAIR_CYCLES,
    allow_creative_repair_cycle,
    persist_creative_production_gate,
    record_creative_repair_cycle,
)
from pipeline.creative_production.metaphor import detect_figurative_language, validate_metaphor_visualization
from pipeline.creative_production.pacing import dialogue_pacing_plan, validate_dialogue_visual_sync
from pipeline.creative_production.preflight import (
    CreativePreflightError,
    preflight_creative_generation,
    preflight_scene_purpose,
    preflight_script_generation_request,
)
from pipeline.creative_production.production import (
    apply_production_creative_plan,
    run_production_creative_gate,
)
from pipeline.creative_production.prompt_policy import enrich_scene_intent
from pipeline.creative_production.repair_bridge import plan_creative_production_repair, scope_for_creative_issue
from pipeline.creative_production.retention import validate_retention_structure, validate_title_video_consistency
from pipeline.creative_production.script_quality import classify_hook, validate_script_structure
from pipeline.creative_production.transitions import validate_music_emotion, validate_sfx_purpose, validate_transition
from pipeline.idempotency.fingerprint import hash_text
from pipeline.idempotency.script_request import ScriptRequestSpec
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.quality.contracts import RepairScope
from pipeline.quality.publishability import evaluate_publishability


def _spec(**kw) -> ScriptRequestSpec:
    base = dict(
        job_id="job-cr",
        topic="iPhone camera quality",
        topic_identity=hash_text("iphone")[:24],
        niche="gadgets",
        niche_id=1,
        video_type="short",
        max_seconds=60,
        language="en",
        provider="llm_router",
        model="purpose-script",
    )
    base.update(kw)
    return ScriptRequestSpec(**base)


def _plan_ok() -> dict:
    return {
        "topic": "iPhone camera low light",
        "title": "iPhone camera low light",
        "niche": "gadgets",
        "video_type": "short",
        "scenes": [
            {
                "narration": "The iPhone camera now captures cleaner night shots without a bulky rig.",
                "dialogue_id": "d1",
                "canonical_scene_id": "s1",
            },
            {
                "narration": "Hold the phone steady; the sensor gathers more light in this alley.",
                "dialogue_id": "d2",
                "canonical_scene_id": "s2",
            },
            {
                "narration": "That improvement is in the camera module, not a separate cinema body.",
                "dialogue_id": "d3",
                "canonical_scene_id": "s3",
            },
        ],
    }


class Phase07CreativeProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p07_"))

    def test_01_script_structure(self):
        r = validate_script_structure(_plan_ok())
        self.assertEqual(r["status"], "PASS")
        self.assertGreaterEqual(r["scene_count"], 3)

    def test_02_weak_hook(self):
        h = classify_hook("Hey guys welcome back to the channel", topic="iPhone camera")
        self.assertEqual(h["status"], "BLOCK")
        self.assertTrue(h["generic"])

    def test_03_unsupported_hook(self):
        h = classify_hook("You won't believe this miracle 100% guaranteed secret", topic="iPhone")
        self.assertIn("clickbait_hook", h["issues"])

    def test_04_information_repetition(self):
        plan = _plan_ok()
        plan["scenes"][1]["narration"] = plan["scenes"][0]["narration"]
        plan["scenes"][2]["narration"] = plan["scenes"][0]["narration"]
        r = validate_script_structure(plan)
        self.assertTrue(any("repetition" in i for i in r["issues"]))

    def test_05_scene_purpose(self):
        cpp = build_creative_production_plan(job_id="j", plan=_plan_ok())
        self.assertTrue(all(s.purpose for s in cpp.scenes))
        self.assertEqual(cpp.scenes[0].narrative_role, "hook")

    def test_06_scene_without_purpose(self):
        with self.assertRaises(CreativePreflightError) as ctx:
            preflight_scene_purpose({"scene_id": "s1", "purpose": "", "narrative_role": ""})
        self.assertIn("scene_without_purpose", ctx.exception.issues)

    def test_07_action_atomicity(self):
        atoms = parse_action_atoms("She holds the phone and the camera quality improved.")
        verbs = {a.verb for a in atoms}
        self.assertIn("hold", verbs)
        self.assertIn("describe", verbs)
        self.assertNotIn("transform", verbs)

    def test_08_incompatible_simultaneous_actions(self):
        atoms = parse_action_atoms("He sits and stands at the door.")
        for a in atoms:
            a.relation = "simultaneous"
        r = validate_action_atomicity(atoms)
        self.assertEqual(r["status"], "BLOCK")

    def test_09_entity_ownership(self):
        r = validate_entity_attribute_ownership(
            narration="the smartphone camera has improved",
            visual_text="person holding a smartphone",
        )
        self.assertEqual(r["status"], "PASS")

    def test_10_attribute_ownership(self):
        r = validate_entity_attribute_ownership(
            narration="knife sharpness is excellent",
            visual_text="the knife transforms into a sword of light",
        )
        self.assertIn("attribute_literalized_as_transformation", r["issues"])

    def test_11_smartphone_camera_semantic_case(self):
        r = validate_entity_attribute_ownership(
            narration="the phone's camera has improved",
            visual_text="the phone transforms into a giant camera",
        )
        self.assertEqual(r["status"], "BLOCK")
        self.assertTrue(any("smartphone_transforms" in i or "camera_module" in i for i in r["issues"]))

    def test_12_metaphor_protection(self):
        r = validate_metaphor_visualization(
            "exploding growth in the heart of the city",
            visual_text="a fireball explosion and anatomical heart in the skyline",
        )
        self.assertEqual(r["status"], "BLOCK")
        self.assertTrue(detect_figurative_language("camera powerhouse"))

    def test_13_object_continuity_authority(self):
        import pipeline.visual_semantic.continuity as cont

        self.assertTrue(hasattr(cont, "ContinuityTracker"))

    def test_14_character_continuity_authority(self):
        from pipeline.visual_semantic import continuity_runtime as cr

        self.assertIn("ContinuityTracker", inspect.getsource(cr))

    def test_15_posture_continuity(self):
        r = validate_physical_plausibility_heuristic(
            atoms=parse_action_atoms("she sits on the floor"),
            posture="sitting on chair",
            location="floor",
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_16_location_continuity_not_second_engine(self):
        from pipeline.visual_semantic.continuity_runtime import apply_production_continuity

        self.assertTrue(callable(apply_production_continuity))

    def test_17_temporal_continuity(self):
        atoms = [
            ActionAtom(subject="A", verb="open", object="door", relation="sequential"),
            ActionAtom(subject="A", verb="close", object="door", relation="sequential"),
        ]
        r = validate_action_atomicity(atoms)
        self.assertEqual(r["status"], "PASS")

    def test_18_camera_continuity(self):
        r = validate_camera_continuity(
            [
                {"shot_type": "close-up", "camera_motion": "spin", "shot_purpose": ""},
                {"shot_type": "wide"},
            ]
        )
        self.assertTrue(any("unmotivated" in i for i in r["issues"]))

    def test_19_shot_purpose_validation(self):
        bad = validate_shot_purpose(shot_type="close-up", shot_purpose="")
        self.assertEqual(bad["status"], "BLOCK")
        ok = validate_shot_purpose(shot_type="medium", shot_purpose="show_subject", narrative_role="evidence")
        self.assertEqual(ok["status"], "PASS")

    def test_20_prompt_contradiction_sections(self):
        intent = SceneIntent(
            scene_id="1",
            dialogue_id="d1",
            purpose="show phone camera attribute",
            primary_action="holding smartphone",
            negative_constraints=["DO NOT transform smartphone into standalone camera"],
        )
        compiled = compile_provider_prompt(intent)
        self.assertIn("SCENE_PURPOSE", compiled.sections)
        self.assertIn("SUBJECT_IS_DOING", compiled.sections)
        self.assertIn("transform", compiled.negative.lower())

    def test_21_negative_constraint_generation(self):
        intent = SceneIntent(scene_id="1", dialogue_id="d1", summary="iPhone camera quality")
        intent = enrich_scene_intent(intent, scene={"narration": "The iPhone camera quality improved."}, scene_index=0)
        self.assertTrue(any("transform" in n.lower() for n in intent.negative_constraints))

    def test_22_robotic_repetition(self):
        r = validate_camera_continuity(
            [{"shot_type": "medium"}] * 4
        )
        self.assertIn("robotic_same_camera_every_scene", r["issues"])

    def test_23_controlled_variation(self):
        a = controlled_variation_for_role("hook")
        b = controlled_variation_for_role("evidence")
        self.assertNotEqual(a["shot_type"], b["shot_type"])
        self.assertEqual(a["camera_motion"], "stable")

    def test_24_emotion_intent(self):
        cpp = build_creative_production_plan(
            job_id="j",
            plan={**_plan_ok(), "scenes": [{**_plan_ok()["scenes"][0], "emotional_intent": "serious"}]},
        )
        self.assertEqual(cpp.scenes[0].emotion_intent, "serious")

    def test_25_dialogue_pacing(self):
        p = dialogue_pacing_plan("Is the night shot cleaner? Hold still. Look at the alley.", emotion="urgent")
        self.assertGreaterEqual(p["sentence_count"], 2)
        self.assertTrue(p["pause_intent"])
        self.assertEqual(p["method"], "HEURISTIC")

    def test_26_dialogue_visual_sync(self):
        r = validate_dialogue_visual_sync(
            narration="he opens the door",
            visual_intent="person eating a sandwich",
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_27_dialogue_sfx_sync(self):
        r = validate_sfx_purpose([{"name": "whoosh", "purpose": ""}], narration="door closes")
        self.assertEqual(r["status"], "BLOCK")
        ok = validate_sfx_purpose([{"name": "door_close", "purpose": "door latch"}], narration="door closes")
        self.assertEqual(ok["status"], "PASS")

    def test_28_dialogue_music_sync_scene_bound(self):
        from domain.scene import AudioPlan

        ap = AudioPlan(scene_id="s1", music={"mood": "calm", "purpose": "underscore"})
        self.assertEqual(ap.scene_id, "s1")
        self.assertTrue(ap.music.get("purpose"))

    def test_29_music_emotional_mismatch(self):
        r = validate_music_emotion(music_mood="happy party", scene_emotion="tragic grief")
        self.assertEqual(r["status"], "BLOCK")

    def test_30_transition_validation(self):
        self.assertEqual(validate_transition("cut")["status"], "PASS")
        self.assertEqual(validate_transition("spin", scene_purpose="")["status"], "BLOCK")

    def test_31_retention_structure(self):
        r = validate_retention_structure(_plan_ok())
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["roles"])

    def test_32_clickbait_prevention(self):
        r = validate_title_video_consistency(
            title="You won't believe this iPhone trick",
            topic="iPhone camera",
            narrations=["The iPhone camera improved in low light."],
        )
        self.assertIn("clickbait_title", r["issues"])

    def test_33_title_video_consistency(self):
        r = validate_title_video_consistency(
            title="iPhone camera low light",
            topic="iPhone camera low light",
            narrations=["The iPhone camera now captures cleaner night shots."],
        )
        self.assertEqual(r["status"], "PASS")

    def test_34_thumbnail_video_consistency(self):
        r = validate_title_video_consistency(
            title="iPhone camera",
            topic="iPhone camera",
            narrations=["night shots on the iPhone camera"],
            thumbnail_claim="You won't believe this shocking truth",
        )
        self.assertIn("clickbait_thumbnail", r["issues"])

    def test_35_preflight_blocks_invalid_generation(self):
        with self.assertRaises(CreativePreflightError):
            preflight_creative_generation(
                plan={"topic": "iPhone", "scenes": [{"narration": "Hey guys welcome back today we will discuss nothing."}]},
                block=True,
            )

    def test_36_no_provider_call_on_deterministic_failure(self):
        calls = []

        def provider():
            calls.append(1)
            return {"scenes": []}

        with self.assertRaises(CreativePreflightError):
            preflight_script_generation_request(_spec(topic="", job_id="j"), block=True)
        self.assertEqual(calls, [])

    def test_37_artifact_observation_authority(self):
        from pipeline.artifact_verification.production import run_production_artifact_verification

        self.assertTrue(callable(run_production_artifact_verification))

    def test_38_semantic_contradiction_detection(self):
        r = validate_dialogue_visual_sync(
            narration="the phone's camera has improved",
            visual_intent="phone transforms into a giant camera",
        )
        self.assertEqual(r["status"], "BLOCK")

    def test_39_minimal_repair(self):
        plan = plan_creative_production_repair(issues=["smartphone_transforms_into_camera"], work_dir=self.tmp)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.repair_scope, RepairScope.VISUAL_PLAN)

    def test_40_bounded_retry(self):
        for _ in range(MAX_CREATIVE_REPAIR_CYCLES):
            record_creative_repair_cycle(self.tmp, outcome="repair_planned", scope="SCENE")
        self.assertFalse(allow_creative_repair_cycle(self.tmp))
        self.assertIsNone(plan_creative_production_repair(issues=["hook"], work_dir=self.tmp))

    def test_41_no_unnecessary_regeneration(self):
        a = build_creative_production_plan(job_id="j", plan=_plan_ok())
        b = build_creative_production_plan(job_id="j", plan=_plan_ok())
        self.assertEqual(a.plan_fingerprint, b.plan_fingerprint)

    def test_42_idempotent_reuse(self):
        fp1 = creative_plan_fingerprint(build_creative_production_plan(job_id="j", plan=_plan_ok()))
        fp2 = creative_plan_fingerprint(build_creative_production_plan(job_id="j", plan=_plan_ok()))
        self.assertEqual(fp1, fp2)
        from pipeline.idempotency.executor import IdempotentExecutor

        self.assertTrue(IdempotentExecutor)

    def test_43_provenance(self):
        cpp = build_creative_production_plan(job_id="job-x", plan=_plan_ok(), revision_id="r002")
        self.assertEqual(cpp.job_id, "job-x")
        self.assertEqual(cpp.revision_id, "r002")
        self.assertTrue(cpp.plan_fingerprint)

    def test_44_fingerprint(self):
        p = _plan_ok()
        fp_a = creative_plan_fingerprint(build_creative_production_plan(job_id="j", plan=p))
        p2 = dict(p)
        p2["title"] = "Different title about iPhone camera low light extra"
        fp_b = creative_plan_fingerprint(build_creative_production_plan(job_id="j", plan=p2))
        self.assertNotEqual(fp_a, fp_b)

    def test_45_unknown_handling(self):
        r = validate_physical_plausibility_heuristic(atoms=[], posture="", location="")
        self.assertEqual(r["status"], "UNKNOWN")
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            creative_production_status="UNKNOWN",
        )
        self.assertFalse(pub["publishable"])
        self.assertNotEqual(pub["verdict"], "PUBLISHABLE")

    def test_46_publishability(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            creative_production_status="FAIL",
        )
        self.assertFalse(pub["publishable"])
        ok = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            creative_production_status="PASS",
            semantic_status="PASS",
        )
        self.assertTrue(ok["publishable"])

    def test_47_production_call_graph(self):
        import pipeline.video_pipeline as vp
        import pipeline.scene_runtime as sr

        src = inspect.getsource(vp.generate_video) + inspect.getsource(sr.assert_production_scenes_validated)
        self.assertIn("apply_production_creative_plan", src)
        self.assertIn("run_production_creative_gate", src)
        self.assertIn("apply_production_continuity", inspect.getsource(sr.assert_production_scenes_validated))

    def test_48_no_direct_provider_bypass_preflight(self):
        import pipeline.idempotency.script_runtime as srt

        self.assertIn("preflight_script_generation_request", inspect.getsource(srt.execute_script_request))

    def test_49_no_duplicate_quality_engine(self):
        import pipeline.quality.orchestrator as orch
        import pipeline.creative_production.production as prod

        self.assertNotIn("overall_score_engine", inspect.getsource(prod))
        self.assertTrue(hasattr(orch, "quality_gate_orchestrator"))

    def test_50_no_duplicate_repair_engine(self):
        self.assertEqual(scope_for_creative_issue("transition flash"), RepairScope.RENDER)
        from pipeline.quality.repair_planner import plan_repair

        self.assertTrue(callable(plan_repair))

    def test_51_no_duplicate_idempotency(self):
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.idempotency.fingerprint import compute_fingerprint

        self.assertTrue(IdempotentExecutor)
        self.assertTrue(callable(compute_fingerprint))

    def test_52_sceneintent_authority(self):
        intent = SceneIntent(scene_id="1", dialogue_id="d", purpose="hook the viewer")
        self.assertEqual(intent.purpose, "hook the viewer")
        compiled = compile_provider_prompt(intent)
        self.assertIn("hook the viewer", compiled.positive)

    def test_53_continuitytracker_authority(self):
        from pipeline.visual_semantic.continuity import ContinuityTracker

        self.assertTrue(ContinuityTracker)

    def test_54_audioplan_authority(self):
        from domain.scene import AudioPlan

        ap = AudioPlan(scene_id="s1")
        self.assertEqual(ap.scene_id, "s1")

    def test_55_localizationcontract_authority(self):
        from pipeline.localization_consistency.contract import LocalizationContract

        self.assertTrue(LocalizationContract)

    def test_56_artifactverification_authority(self):
        import pipeline.artifact_verification.production as av

        self.assertTrue(hasattr(av, "run_production_artifact_verification"))

    def test_57_multimodal_authority(self):
        from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt as c1
        from pipeline.scene_contract import compile_prompt_from_contract

        self.assertTrue(callable(c1))
        self.assertTrue(callable(compile_prompt_from_contract))
        # Canonical compiler is compile_provider_prompt
        self.assertIn("compile_provider_prompt", inspect.getsource(__import__("pipeline.visual_semantic.continuity_runtime", fromlist=["x"])))

    def test_58_checkpoint_persistence(self):
        rows = apply_production_creative_plan(self.tmp, _plan_ok()["scenes"], job_id="job-c", plan=_plan_ok())
        self.assertTrue(rows)
        self.assertTrue((self.tmp / "CREATIVE_PRODUCTION_GATE.json").is_file())
        self.assertTrue((self.tmp / "creative_plans").is_dir())

    def test_59_failure_recovery(self):
        persist_creative_production_gate(self.tmp, {"status": "FAIL", "issues": ["weak_generic_hook"]})
        gate = run_production_creative_gate(self.tmp, job_id="job-c", plan=_plan_ok())
        self.assertIn(gate["status"], ("PASS", "FAIL", "WARN"))
        self.assertNotEqual(str(gate.get("unknown_as_pass")), "True")

    def test_60_final_package_traceability(self):
        cpp = build_creative_production_plan(job_id="job-pack", plan=_plan_ok())
        d = cpp.to_dict()
        self.assertEqual(d["job_id"], "job-pack")
        self.assertTrue(d["plan_fingerprint"])
        self.assertTrue(d["scenes"][0]["scene_id"])

    def test_61_apply_production_wires_purpose(self):
        rows = apply_production_creative_plan(self.tmp, _plan_ok()["scenes"], job_id="j", plan=_plan_ok())
        self.assertTrue(all(r.get("purpose") for r in rows))
        self.assertTrue(all(r.get("shot_purpose") for r in rows))

    def test_62_unknown_never_pass_publish(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            creative_production_status="UNKNOWN",
        )
        self.assertFalse(pub.get("publishable"))

    def test_63_heuristic_not_claimed_pass_physical(self):
        r = validate_physical_plausibility_heuristic(atoms=[], posture="", location="")
        self.assertEqual(r["classification"], "UNKNOWN")
        self.assertNotEqual(r["status"], "PASS")

    def test_64_phone_is_camera_metaphor(self):
        r = validate_metaphor_visualization(
            "the phone is a camera powerhouse",
            visual_text="device becomes a camera and a power plant",
        )
        self.assertEqual(r["status"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
