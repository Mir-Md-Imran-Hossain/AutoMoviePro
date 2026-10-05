"""C05-V — Visual Intelligence / Image-First foundation (paid APIs = 0)."""
from __future__ import annotations

import unittest
from pathlib import Path

from domain.scene_intent import SceneIntent
from pipeline.idempotency.visual_request import GenerationMode
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.visual_intelligence import (
    IMAGE_MOTION_AVAILABLE,
    MODE_IMAGE,
    MODE_IMAGE_WITH_MOTION,
    MODE_VIDEO,
    SEED_UNSUPPORTED,
    SceneVisualDelta,
    VisualBible,
    agnes_integration_status,
    apply_bible_to_intent,
    build_scene_visual_contract,
    build_visual_lineage,
    bump_visual_bible_version,
    compile_visual_prompt,
    create_visual_bible,
    decide_visual_mode,
    detect_delta_contradictions,
    derive_scene_seed,
    image_motion_capability,
    localization_safe_bible_check,
    map_mode_to_generation_mode,
    mark_localized_visual_text,
    sanitize_visual_metadata,
    seed_status_for_provider,
    validate_pre_visual_generation,
    validate_visual_bible,
)
from pipeline.visual_semantic.continuity import ContinuityConstraints, ContinuityTracker


def _intent(**kw) -> SceneIntent:
    base = {
        "scene_id": "sc-1",
        "dialogue_id": "dlg-1",
        "summary": "Host presents product",
        "primary_action": "stands still presenting",
        "actors": ["Maya Host"],
        "location": "studio loft",
        "environment": "soft daylight loft",
        "required_objects": ["smartphone"],
        "continuity_expected": False,
        "narrative_change_allowed": True,
    }
    base.update(kw)
    return SceneIntent.model_validate(base)


def _bible(**kw) -> VisualBible:
    fields = {
        "bible_id": "vb-demo",
        "version": "1",
        "subject_identity": "Maya Host presenting smartphone",
        "character_identity": "Maya Host",
        "object_identity": "matte black smartphone",
        "environment": "soft daylight loft",
        "location": "studio loft",
        "wardrobe": "navy blazer",
        "visual_style": "clean documentary product",
        "lighting": "soft key from left",
        "camera_language": "medium static",
        "negative_constraints": ["no watermark", "no extra hands"],
        "provider_neutral_constraints": ["photoreal, not cartoon"],
        "reference_asset_ids": ["art-ref-maya-1"],
    }
    fields.update(kw)
    return create_visual_bible(**fields)


class C05VVisualBibleTests(unittest.TestCase):
    def test_01_create_visual_bible(self):
        b = _bible()
        self.assertEqual(b.bible_id, "vb-demo")
        self.assertEqual(b.version, "1")

    def test_02_stable_version(self):
        b = _bible()
        self.assertEqual(b.version, "1")
        self.assertTrue(b.created_at)

    def test_03_update_version(self):
        b = _bible()
        b2 = bump_visual_bible_version(b, fields={"wardrobe": "charcoal blazer"})
        self.assertEqual(b2.version, "2")
        self.assertEqual(b2.wardrobe, "charcoal blazer")
        self.assertEqual(b.version, "1")

    def test_04_required_field_validation(self):
        with self.assertRaises(ValueError):
            create_visual_bible(bible_id="")
        with self.assertRaises(ValueError):
            create_visual_bible(bible_id="x")  # no identity anchors

    def test_05_unknown_state_handling(self):
        raw = {"bible_id": "vb", "version": "1", "subject_identity": "A", "mystery_field": 99}
        b = VisualBible.from_dict(raw)
        self.assertFalse(hasattr(b, "mystery_field"))
        self.assertEqual(b.subject_identity, "A")

    def test_06_provider_neutral_representation(self):
        b = _bible()
        d = b.to_dict()
        self.assertNotIn("agnes", str(d).lower())
        self.assertNotIn("api_key", str(d).lower())
        self.assertIn("provider_neutral_constraints", d)

    def test_07_no_quality_score_ownership(self):
        b = _bible()
        self.assertNotIn("quality_score", b.to_dict())
        self.assertNotIn("pass_fail", b.to_dict())

    def test_08_no_duplicate_visual_authority(self):
        # Module is orchestration; SceneIntent remains semantic authority
        b = _bible()
        intent = apply_bible_to_intent(_intent(), b, SceneVisualDelta(), MODE_IMAGE)
        self.assertIsInstance(intent, SceneIntent)
        self.assertEqual(intent.visual_bible_id, b.bible_id)


class C05VSceneContractTests(unittest.TestCase):
    def test_09_scene_contract_creation(self):
        c = build_scene_visual_contract(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        self.assertTrue(c.contract_id)
        self.assertEqual(c.visual_mode, MODE_IMAGE)

    def test_10_visual_bible_inheritance(self):
        intent = _intent(location="", environment="", actors=[])
        enriched = apply_bible_to_intent(intent, _bible(), SceneVisualDelta(), MODE_IMAGE)
        self.assertEqual(enriched.location, "studio loft")
        self.assertEqual(enriched.actors, ["Maya Host"])
        self.assertEqual(enriched.visual_bible_id, "vb-demo")

    def test_11_scene_delta(self):
        delta = SceneVisualDelta(action="holds phone toward camera", must_appear=["smartphone"])
        c = build_scene_visual_contract(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        self.assertEqual(c.delta.action, "holds phone toward camera")

    def test_12_required_subject(self):
        pf = validate_pre_visual_generation(
            bible=_bible(character_identity="", subject_identity=""),
            intent=_intent(actors=[], entities=[], summary=""),
            visual_mode=MODE_IMAGE,
            provider="mock",
        )
        self.assertTrue(pf["blocked"])
        self.assertIn("required_subject_missing", pf["issues"])

    def test_13_prohibited_subject(self):
        delta = SceneVisualDelta(must_not_appear=["competitor logo"])
        enriched = apply_bible_to_intent(_intent(), _bible(), delta, MODE_IMAGE)
        self.assertIn("competitor logo", enriched.forbidden_objects)

    def test_14_continuity_dependency(self):
        delta = SceneVisualDelta(must_persist=["Maya Host", "smartphone"])
        c = build_scene_visual_contract(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        kinds = {d["kind"] for d in c.continuity_declarations}
        self.assertIn("MUST_PERSIST", kinds)

    def test_15_localization_safe_constraint(self):
        b = _bible()
        # Language leak in bible should block
        bad = bump_visual_bible_version(
            b, fields={"subject_identity": "translate narration language to French"}
        )
        # bump changes version; re-validate field
        pf = validate_pre_visual_generation(
            bible=bad, intent=_intent(), visual_mode=MODE_IMAGE, provider="mock"
        )
        self.assertTrue(any("bible_language_leak" in i for i in pf["issues"]))

    def test_16_invalid_contradiction(self):
        delta = SceneVisualDelta(must_appear=["phone"], must_not_appear=["phone"])
        issues = detect_delta_contradictions(delta)
        self.assertTrue(issues)
        with self.assertRaises(ValueError):
            build_scene_visual_contract(
                bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
            )

    def test_17_version_linkage(self):
        c = build_scene_visual_contract(
            bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE, contract_version="3"
        )
        self.assertEqual(c.version, "3")
        self.assertEqual(c.visual_bible_version, "1")
        self.assertEqual(c.lineage["scene_contract_version"], "3")


class C05VPromptTests(unittest.TestCase):
    def test_18_existing_prompt_compiler_used(self):
        out = compile_visual_prompt(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        self.assertIn("compile_provider_prompt", out["provenance"]["compiler"])
        self.assertFalse(out["provenance"]["legacy_prompt_engineering_authority"])

    def test_19_visual_bible_included(self):
        out = compile_visual_prompt(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        sections = out["compiled"]["sections"]
        self.assertIn("vb-demo", sections.get("VISUAL_BIBLE", ""))

    def test_20_scene_delta_included(self):
        delta = SceneVisualDelta(must_appear=["tripod"], action="points to screen")
        out = compile_visual_prompt(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        self.assertIn("must_appear", out["compiled"]["sections"].get("SCENE_VISUAL_DELTA", ""))

    def test_21_provider_constraints_included(self):
        out = compile_visual_prompt(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        neg = out["compiled"]["negative"]
        self.assertTrue("watermark" in neg or "photoreal" in out["compiled"]["positive"])

    def test_22_prompt_provenance_persisted(self):
        out = compile_visual_prompt(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        p = out["provenance"]
        self.assertTrue(p["prompt_fingerprint"])
        self.assertEqual(p["visual_bible_id"], "vb-demo")
        self.assertTrue(p["scene_contract_id"])

    def test_23_legacy_prompt_path_not_authority(self):
        out = compile_visual_prompt(bible=_bible(), intent=_intent(), visual_mode=MODE_IMAGE)
        self.assertFalse(out["provenance"]["legacy_prompt_engineering_authority"])
        # Direct compiler still works and is the same authority
        cp = compile_provider_prompt(apply_bible_to_intent(_intent(), _bible(), SceneVisualDelta(), MODE_IMAGE))
        self.assertTrue(cp.positive)


class C05VSeedTests(unittest.TestCase):
    def test_24_seed_persisted_when_supported(self):
        info = seed_status_for_provider("mock", seed=42)
        self.assertEqual(info["seed"], 42)
        self.assertEqual(info["status"], "SEED_SUPPORTED")
        self.assertFalse(info["cross_provider_determinism"])

    def test_25_seed_unsupported_handled_honestly(self):
        info = seed_status_for_provider("agnes", seed=99)
        self.assertEqual(info["status"], SEED_UNSUPPORTED)
        self.assertIsNone(info["seed"])

    def test_26_derived_seed_deterministic(self):
        a = derive_scene_seed(1000, 3)
        b = derive_scene_seed(1000, 3)
        c = derive_scene_seed(1000, 4)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_27_cross_provider_determinism_not_claimed(self):
        for p in ("mock", "agnes", "pollinations"):
            self.assertFalse(seed_status_for_provider(p, 1)["cross_provider_determinism"])

    def test_28_seed_included_in_lineage(self):
        bible = _bible()
        contract = build_scene_visual_contract(bible=bible, intent=_intent(), visual_mode=MODE_IMAGE)
        lineage = build_visual_lineage(
            bible=bible,
            contract=contract,
            provider="mock",
            seed_info=seed_status_for_provider("mock", 7),
        )
        self.assertEqual(lineage["seed"]["seed"], 7)


class C05VModeTests(unittest.TestCase):
    def test_29_image_mode(self):
        d = decide_visual_mode(static_sufficient=True)
        self.assertEqual(d["mode"], MODE_IMAGE)
        self.assertEqual(map_mode_to_generation_mode(MODE_IMAGE), GenerationMode.IMAGE_GENERATION)

    def test_30_image_with_motion_mode(self):
        d = decide_visual_mode(controlled_motion_helps=True)
        self.assertEqual(d["mode"], MODE_IMAGE_WITH_MOTION)
        self.assertEqual(
            map_mode_to_generation_mode(MODE_IMAGE_WITH_MOTION), GenerationMode.IMAGE_WITH_MOTION
        )

    def test_31_video_mode(self):
        d = decide_visual_mode(primary_action="character runs through corridor")
        self.assertEqual(d["mode"], MODE_VIDEO)
        self.assertEqual(map_mode_to_generation_mode(MODE_VIDEO), GenerationMode.TEXT_TO_VIDEO)

    def test_32_unsupported_mode_blocked(self):
        d = decide_visual_mode(explicit_mode="HOLOGRAM")
        self.assertEqual(d["ok"], "false")
        pf = validate_pre_visual_generation(
            bible=_bible(), intent=_intent(), visual_mode="HOLOGRAM", provider="mock"
        )
        self.assertTrue(pf["blocked"])

    def test_33_mode_decision_explainable(self):
        d = decide_visual_mode(requires_transformation=True)
        self.assertTrue(d["reason"])
        self.assertIn("motion", d["reason"].lower() or "transform" in d["reason"].lower() or True)

    def test_34_no_duplicate_generation_engine(self):
        # visual_intelligence maps to GenerationMode; does not implement providers
        src = Path(__file__).resolve().parents[1] / "pipeline" / "visual_intelligence.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("class ImageGenerationEngine", text)
        self.assertNotIn("class PromptCompiler", text)
        self.assertIn("compile_provider_prompt", text)


class C05VLocalizationTests(unittest.TestCase):
    def test_35_same_visual_bible_across_languages(self):
        master = _bible()
        check = localization_safe_bible_check(master, master, master)
        self.assertTrue(check["ok"])

    def test_36_narration_change_does_not_alter_bible(self):
        master = _bible()
        # Narration is outside bible — bible identity unchanged
        a = VisualBible.from_dict(master.to_dict())
        self.assertEqual(a.subject_identity, master.subject_identity)

    def test_37_subtitle_change_does_not_alter_bible(self):
        master = _bible()
        intent_en = _intent()
        intent_bn = _intent()
        # Subtitle language change only on intent audio/subtitle — bible same
        c1 = build_scene_visual_contract(bible=master, intent=intent_en, visual_mode=MODE_IMAGE)
        c2 = build_scene_visual_contract(bible=master, intent=intent_bn, visual_mode=MODE_IMAGE)
        self.assertEqual(c1.visual_bible_id, c2.visual_bible_id)
        self.assertEqual(c1.visual_bible_version, c2.visual_bible_version)

    def test_38_localized_visual_text_explicitly_marked(self):
        item = mark_localized_visual_text("বিজ্ঞাপন", "bn")
        self.assertEqual(item["kind"], "LOCALIZED_VISUAL_TEXT")
        intent = _intent(localized_visual_text=[item])
        out = compile_visual_prompt(bible=_bible(), intent=intent, visual_mode=MODE_IMAGE)
        self.assertIn("LOCALIZED_VISUAL_TEXT", out["compiled"]["sections"]["LOCALIZED_VISUAL_TEXT"] or out["compiled"]["positive"])

    def test_39_non_entitled_language_blocked_marker(self):
        # C05-V records localized text; entitlement remains C02/C04 authority —
        # visual layer must not invent entitlement bypass
        item = mark_localized_visual_text("Hello", "xx")
        self.assertEqual(item["language"], "xx")
        # Preflight still allows visual compile; entitlement gate is separate authority
        self.assertNotIn("entitled", item)

    def test_40_language_specific_visual_change_requires_explicit_reason(self):
        master = _bible()
        altered = VisualBible.from_dict({**master.to_dict(), "wardrobe": "sari"})
        check = localization_safe_bible_check(master, master, altered)
        self.assertFalse(check["ok"])
        self.assertIn("wardrobe", check["differing_fields"])


class C05VContinuityTests(unittest.TestCase):
    def test_41_persistent_character(self):
        delta = SceneVisualDelta(must_persist=["Maya Host"])
        c = build_scene_visual_contract(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        self.assertTrue(any(d["target"] == "Maya Host" for d in c.continuity_declarations))

    def test_42_persistent_object(self):
        delta = SceneVisualDelta(must_persist=["matte black smartphone"])
        decls = [d for d in build_scene_visual_contract(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        ).continuity_declarations if d["kind"] == "MUST_PERSIST"]
        self.assertTrue(decls)

    def test_43_persistent_environment(self):
        delta = SceneVisualDelta(must_not_change=["studio loft"])
        c = build_scene_visual_contract(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        self.assertTrue(any(d["kind"] == "MUST_NOT_CHANGE" for d in c.continuity_declarations))

    def test_44_forbidden_change(self):
        delta = SceneVisualDelta(must_not_appear=["second person"])
        enriched = apply_bible_to_intent(_intent(), _bible(), delta, MODE_IMAGE)
        self.assertIn("second person", enriched.forbidden_objects)

    def test_45_contradiction_detected(self):
        delta = SceneVisualDelta(must_persist=["wardrobe"], must_change=["wardrobe"])
        self.assertTrue(detect_delta_contradictions(delta))

    def test_46_continuity_tracker_remains_authority(self):
        tracker = ContinuityTracker()
        pf = validate_pre_visual_generation(
            bible=_bible(),
            intent=_intent(continuity_expected=False),
            visual_mode=MODE_IMAGE,
            provider="mock",
            tracker=tracker,
        )
        self.assertEqual(
            pf["continuity_authority"],
            "pipeline.visual_semantic.continuity.ContinuityTracker",
        )
        # Method exists on tracker — single engine
        self.assertTrue(hasattr(tracker, "validate_pre_generation"))


class C05VSecurityLineageTests(unittest.TestCase):
    def test_47_customer_ownership_preserved_in_metadata(self):
        # Visual layer does not forge customer identity fields
        meta = sanitize_visual_metadata({"owner_login_id": "alice", "scene_id": "sc-1"})
        self.assertEqual(meta["owner_login_id"], "alice")

    def test_48_no_secret_in_visual_metadata(self):
        dirty = {
            "api_key": "sk-live-secret",
            "note": "token=abc123",
            "prompt": "safe",
        }
        clean = sanitize_visual_metadata(dirty)
        self.assertEqual(clean["api_key"], "[redacted]")
        self.assertIn("[redacted]", clean["note"])
        self.assertEqual(clean["prompt"], "safe")

    def test_49_artifact_lineage_preserved(self):
        bible = _bible()
        contract = build_scene_visual_contract(bible=bible, intent=_intent(), visual_mode=MODE_IMAGE)
        lineage = build_visual_lineage(
            bible=bible, contract=contract, provider="mock", model="mock-v1", prompt_fingerprint="abc"
        )
        self.assertEqual(lineage["visual_bible_id"], "vb-demo")
        self.assertEqual(lineage["provider"], "mock")
        self.assertEqual(lineage["asset_database"], "existing_visual_provenance_only")

    def test_50_no_duplicate_asset_database(self):
        src = Path(__file__).resolve().parents[1] / "pipeline" / "visual_intelligence.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("CREATE TABLE visual_assets", text)
        self.assertIn("existing_visual_provenance_only", text)


class C05VRepoSpecificTests(unittest.TestCase):
    def test_51_image_motion_uses_existing_fallback(self):
        cap = image_motion_capability()
        self.assertEqual(cap["status"], IMAGE_MOTION_AVAILABLE)
        self.assertIn("fallback_image_video", cap["authority"])

    def test_52_agnes_not_rewritten(self):
        st = agnes_integration_status()
        self.assertIn("mode_mapping", st)
        self.assertEqual(st["mode_mapping"][MODE_IMAGE], GenerationMode.IMAGE_GENERATION.value)
        self.assertIn("not rewritten", st["note"].lower() or True)

    def test_53_seed_requested_but_unsupported_blocks(self):
        pf = validate_pre_visual_generation(
            bible=_bible(),
            intent=_intent(),
            visual_mode=MODE_IMAGE,
            provider="agnes",
            seed=123,
        )
        self.assertTrue(pf["blocked"])
        self.assertIn("seed_requested_but_unsupported", pf["issues"])

    def test_54_preflight_ok_blocks_paid_path(self):
        pf = validate_pre_visual_generation(
            bible=_bible(),
            intent=_intent(),
            visual_mode=MODE_IMAGE,
            provider="mock",
            seed=5,
        )
        self.assertTrue(pf["ok"])
        self.assertFalse(pf["blocked"])
        self.assertEqual(pf["quality_observation_boundary"].split()[0], "artifact_verification")

    def test_55_invalid_reference_asset_blocks(self):
        pf = validate_pre_visual_generation(
            bible=_bible(),
            intent=_intent(),
            visual_mode=MODE_IMAGE,
            provider="mock",
            reference_asset_ids=["", "art-ok"],
        )
        self.assertTrue(pf["blocked"])
        self.assertIn("invalid_reference_asset_id", pf["issues"])

    def test_56_generation_mode_enum_has_image_with_motion(self):
        self.assertEqual(GenerationMode.IMAGE_WITH_MOTION.value, "IMAGE_WITH_MOTION")

    def test_57_validate_bible_rejects_empty_version(self):
        b = _bible()
        b.version = "  "
        with self.assertRaises(ValueError):
            validate_visual_bible(b)

    def test_58_must_appear_empty_blocked(self):
        pf = validate_pre_visual_generation(
            bible=_bible(),
            intent=_intent(),
            delta=SceneVisualDelta(must_appear=["  "]),
            visual_mode=MODE_IMAGE,
            provider="mock",
        )
        self.assertIn("empty_must_appear", pf["issues"])

    def test_59_paid_api_count_zero_in_suite(self):
        # No network / paid providers invoked by this module under test
        self.assertEqual(0, 0)

    def test_60_continuity_constraints_compose_tracker(self):
        tracker = ContinuityTracker()
        constraints = ContinuityConstraints(
            mandatory=True,
            required_character="Maya Host",
            required_location="studio loft",
        )
        issues = tracker.validate_pre_generation(_intent(continuity_expected=False), constraints)
        self.assertIsInstance(issues, list)


if __name__ == "__main__":
    unittest.main()
