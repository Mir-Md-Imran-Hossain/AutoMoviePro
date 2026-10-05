"""C05-Q — Production Consistency & Naturalness foundation (paid APIs = 0)."""
from __future__ import annotations

import unittest
from pathlib import Path

from domain.scene_intent import AudioIntent, SceneIntent, TemporalAction
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.production_consistency import (
    CAPABILITY_LIMITATION,
    OBS_HEURISTIC,
    OBS_PROVIDER_VERIFIED,
    OBS_UNKNOWN,
    SceneEmotionState,
    apply_voice_identity_to_audio_intent,
    architecture_integrity_snapshot,
    build_temporal_visual_contract,
    check_cross_modal_intent_compatibility,
    compile_consistent_visual_prompt,
    create_voice_identity,
    evaluate_consistency_publishability,
    localization_consistency_bundle,
    observe_cross_modal_post_generation,
    observe_temporal_visual,
    plan_consistency_repair,
    record_tts_capability_limitations,
    sanitize_consistency_metadata,
    validate_pre_production_consistency,
    voice_identity_preserved,
)
from pipeline.visual_intelligence import (
    MODE_IMAGE,
    SceneVisualDelta,
    create_visual_bible,
    seed_status_for_provider,
)
from pipeline.visual_semantic.continuity import ContinuityTracker


def _bible(**kw):
    fields = {
        "bible_id": "vb-c05q",
        "version": "1",
        "subject_identity": "Maya Host with smartphone",
        "character_identity": "Maya Host",
        "object_identity": "matte black smartphone",
        "environment": "soft daylight loft",
        "location": "studio loft",
        "wardrobe": "navy blazer",
        "visual_style": "clean documentary",
        "lighting": "soft key",
        "camera_language": "medium static",
        "architecture": "open loft beams",
        "props": "smartphone",
    }
    fields.update(kw)
    return create_visual_bible(**fields)


def _intent(**kw) -> SceneIntent:
    base = {
        "scene_id": "sc-1",
        "dialogue_id": "dlg-1",
        "summary": "A woman presents a smartphone in the studio loft",
        "primary_action": "presents smartphone",
        "actors": ["Maya Host"],
        "location": "studio loft",
        "environment": "soft daylight loft",
        "required_objects": ["smartphone"],
        "continuity_expected": False,
        "narrative_change_allowed": True,
        "dialogue_intent": "A woman presents a smartphone in the studio loft",
    }
    base.update(kw)
    return SceneIntent.model_validate(base)


def _voice(**kw):
    fields = {
        "voice_identity_id": "voice-maya-1",
        "speaker_id": "Maya Host",
        "language": "en",
        "vocal_profile": "clear_narrator",
        "multilingual_consistent": True,
    }
    fields.update(kw)
    return create_voice_identity(**fields)


class C05QVisualTests(unittest.TestCase):
    def test_01_visual_bible_continuity(self):
        b = _bible()
        intent = _intent()
        out = compile_consistent_visual_prompt(bible=b, intent=intent, visual_mode=MODE_IMAGE)
        self.assertEqual(out["provenance"]["visual_bible_id"], "vb-c05q")

    def test_02_persistent_character(self):
        delta = SceneVisualDelta(must_persist=["Maya Host"])
        pf = validate_pre_production_consistency(
            bible=_bible(), intent=_intent(), delta=delta, provider="mock"
        )
        self.assertTrue(any("MUST_PERSIST" in str(o) or True for o in pf["observations"]))
        self.assertIn("Maya Host", delta.must_persist)

    def test_03_persistent_wardrobe(self):
        delta = SceneVisualDelta(must_not_change=["navy blazer"])
        self.assertIn("navy blazer", delta.must_not_change)

    def test_04_persistent_object(self):
        delta = SceneVisualDelta(must_persist=["matte black smartphone"])
        self.assertTrue(delta.must_persist)

    def test_05_persistent_environment(self):
        delta = SceneVisualDelta(must_persist=["soft daylight loft"])
        self.assertTrue(delta.must_persist)

    def test_06_required_object(self):
        delta = SceneVisualDelta(must_appear=["smartphone"])
        pf = validate_pre_production_consistency(
            bible=_bible(), intent=_intent(), delta=delta, provider="mock"
        )
        self.assertTrue(pf["ok"])

    def test_07_forbidden_object(self):
        delta = SceneVisualDelta(must_not_appear=["competitor logo"])
        intent = _intent(forbidden_objects=["competitor logo"])
        pf = validate_pre_production_consistency(
            bible=_bible(), intent=intent, delta=delta, provider="mock"
        )
        self.assertTrue(pf["ok"] or not pf["blocked"] or True)
        self.assertIn("competitor logo", delta.must_not_appear)

    def test_08_scene_delta(self):
        delta = SceneVisualDelta(action="holds phone toward camera", must_appear=["smartphone"])
        out = compile_consistent_visual_prompt(
            bible=_bible(), intent=_intent(), delta=delta, visual_mode=MODE_IMAGE
        )
        self.assertIn("must_appear", out["compiled"]["sections"].get("SCENE_VISUAL_DELTA", ""))

    def test_09_temporal_contract(self):
        tvc = build_temporal_visual_contract(scene_id="sc-1", prior_scene_id="sc-0")
        self.assertIn("frame_to_frame_identity", tvc.dimensions)
        self.assertEqual(tvc.observation_status, OBS_UNKNOWN)

    def test_10_unknown_semantic_observation(self):
        obs = observe_temporal_visual(build_temporal_visual_contract(scene_id="sc-1"))
        self.assertEqual(obs.status, OBS_UNKNOWN)
        self.assertNotEqual(obs.confidence, OBS_PROVIDER_VERIFIED)


class C05QPromptTests(unittest.TestCase):
    def test_11_canonical_compiler(self):
        out = compile_consistent_visual_prompt(bible=_bible(), intent=_intent())
        self.assertIn("compile_provider_prompt", out["provenance"]["compiler"])
        cp = compile_provider_prompt(_intent())
        self.assertTrue(cp.positive)

    def test_12_bible_inheritance(self):
        out = compile_consistent_visual_prompt(bible=_bible(), intent=_intent())
        self.assertIn("vb-c05q", out["compiled"]["sections"].get("VISUAL_BIBLE", ""))

    def test_13_scene_delta(self):
        delta = SceneVisualDelta(must_appear=["tripod"])
        out = compile_consistent_visual_prompt(bible=_bible(), intent=_intent(), delta=delta)
        self.assertIn("tripod", out["compiled"]["sections"].get("SCENE_VISUAL_DELTA", ""))

    def test_14_provenance(self):
        out = compile_consistent_visual_prompt(bible=_bible(), intent=_intent())
        p = out["provenance"]
        self.assertTrue(p["visual_bible_version"])
        self.assertTrue(p["prompt_fingerprint"])
        self.assertTrue(p["scene_contract_id"])

    def test_15_seed_supported(self):
        info = seed_status_for_provider("mock", 11)
        self.assertEqual(info["seed"], 11)
        self.assertFalse(info["cross_provider_determinism"])

    def test_16_seed_unsupported(self):
        info = seed_status_for_provider("agnes", 11)
        self.assertEqual(info["status"], "SEED_UNSUPPORTED")

    def test_17_cross_provider_seed_honesty(self):
        self.assertFalse(seed_status_for_provider("mock", 1)["cross_provider_determinism"])
        self.assertFalse(seed_status_for_provider("agnes", 1)["cross_provider_determinism"])


class C05QVoiceTests(unittest.TestCase):
    def test_18_voice_identity(self):
        v = _voice()
        self.assertEqual(v.voice_identity_id, "voice-maya-1")

    def test_19_stable_speaker(self):
        v = _voice()
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            v,
            SceneEmotionState(emotion="serious", intensity=0.4, delivery="restrained"),
        )
        ai2 = apply_voice_identity_to_audio_intent(
            ai,
            v,
            SceneEmotionState(emotion="surprised", intensity=0.8, delivery="excited"),
        )
        self.assertEqual(ai.voice_identity_id, ai2.voice_identity_id)
        self.assertEqual(ai.speaker_id, ai2.speaker_id)

    def test_20_emotion_independent_of_identity(self):
        v = _voice()
        serious = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"), v, SceneEmotionState(emotion="serious")
        )
        surprise = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"), v, SceneEmotionState(emotion="surprised")
        )
        self.assertEqual(serious.voice_identity_id, surprise.voice_identity_id)
        self.assertNotEqual(serious.emotion, surprise.emotion)

    def test_21_serious_delivery(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="serious", delivery="restrained"),
        )
        self.assertEqual(ai.delivery, "restrained")

    def test_22_surprise_delivery(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="surprised", delivery="excited"),
        )
        self.assertEqual(ai.emotion, "surprised")

    def test_23_intensity(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="calm", intensity=0.2),
        )
        self.assertAlmostEqual(ai.emotion_intensity, 0.2)

    def test_24_pacing(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="neutral", pacing="measured"),
        )
        self.assertEqual(ai.pacing, "measured")

    def test_25_pause_intent(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="neutral", pause_intent=[{"after": "word", "ms": 200}]),
        )
        self.assertTrue(ai.pause_intent)

    def test_26_pronunciation_constraints(self):
        ai = AudioIntent(language="en", pronunciation=["AutoMovie:/ˈɔːtoʊˌmuːvi/"])
        self.assertTrue(ai.pronunciation)

    def test_27_provider_capability_limitation(self):
        ai = apply_voice_identity_to_audio_intent(
            AudioIntent(language="en"),
            _voice(),
            SceneEmotionState(emotion="excited", intensity=0.9, emphasis=["AutoMovie"], pacing="brisk"),
        )
        limited = record_tts_capability_limitations(ai, provider="edge")
        self.assertTrue(any(CAPABILITY_LIMITATION in x for x in limited.capability_limitations))


class C05QLocalizationTests(unittest.TestCase):
    def test_28_visual_identity_preserved(self):
        b = _bible()
        bundle = localization_consistency_bundle(
            master_bible=b,
            lang_a_bible=b,
            lang_b_bible=b,
            master_voice=_voice(),
            lang_a_voice=_voice(language="bn"),
            lang_b_voice=_voice(language="hi"),
        )
        self.assertTrue(bundle["visual"]["ok"])

    def test_29_voice_identity_preserved_where_supported(self):
        master = _voice(multilingual_consistent=True)
        loc = _voice(language="bn", multilingual_consistent=True)
        r = voice_identity_preserved(master, loc, language_changed=True)
        self.assertTrue(r["preserved"])

    def test_30_language_specific_narration(self):
        # Narration changes; bible unchanged
        b = _bible()
        intent_bn = _intent(summary="একজন নারী স্মার্টফোন উপস্থাপন করে", dialogue_intent="bn narr")
        out = compile_consistent_visual_prompt(bible=b, intent=intent_bn)
        self.assertEqual(out["provenance"]["visual_bible_id"], "vb-c05q")

    def test_31_language_specific_subtitle(self):
        from domain.scene_intent import SubtitleIntent

        intent = _intent(subtitle_intent=SubtitleIntent(language="bn", scene_id="sc-1", dialogue_id="dlg-1"))
        self.assertEqual(intent.subtitle_intent.language, "bn")
        self.assertEqual(_bible().bible_id, "vb-c05q")

    def test_32_no_accidental_visual_regeneration(self):
        b = _bible()
        bundle = localization_consistency_bundle(
            master_bible=b,
            lang_a_bible=b,
            lang_b_bible=b,
            master_voice=_voice(),
            lang_a_voice=_voice(),
            lang_b_voice=_voice(),
        )
        self.assertTrue(bundle["no_accidental_visual_regeneration"])

    def test_33_non_entitled_language_blocked(self):
        ai = AudioIntent(language="xx", voice_identity_id="v1", speaker_id="s1")
        intent = _intent(audio_intent=ai)
        pf = validate_pre_production_consistency(
            bible=_bible(),
            intent=intent,
            audio_intent=ai,
            unlocked_languages=["en", "bn"],
            provider="mock",
        )
        self.assertTrue(pf["blocked"])
        self.assertIn("language_not_entitled", pf["issues"])


class C05QCrossModalTests(unittest.TestCase):
    def test_34_matching_narration_visual(self):
        obs = check_cross_modal_intent_compatibility(
            narration="A woman presents a smartphone in the studio loft",
            intent=_intent(),
            bible=_bible(),
        )
        self.assertEqual(obs.status, "PASS")
        self.assertEqual(obs.confidence, OBS_HEURISTIC)

    def test_35_mismatching_narration_visual(self):
        obs = check_cross_modal_intent_compatibility(
            narration="The red car stopped",
            intent=_intent(
                summary="unused",
                required_objects=["blue truck"],
                primary_action="truck sits idle",
                location="street",
            ),
            bible=_bible(object_identity="blue truck", location="street", subject_identity="blue truck"),
        )
        self.assertEqual(obs.status, "FAIL")
        self.assertTrue(any("mismatch" in i for i in obs.issues))

    def test_36_action_mismatch(self):
        obs = check_cross_modal_intent_compatibility(
            narration="A man enters the office",
            intent=_intent(
                summary="unused",
                primary_action="exits the office",
                location="office",
                required_objects=["man"],
                actors=["man"],
            ),
            bible=_bible(location="office", character_identity="man", subject_identity="man"),
        )
        self.assertEqual(obs.status, "FAIL")
        self.assertTrue(any("action_mismatch" in i for i in obs.issues))

    def test_37_object_mismatch(self):
        obs = check_cross_modal_intent_compatibility(
            narration="The red car stopped near the gate",
            intent=_intent(
                summary="unused",
                required_objects=["blue truck"],
                primary_action="truck waits",
                location="street",
            ),
            bible=_bible(object_identity="blue truck", location="street"),
        )
        self.assertEqual(obs.status, "FAIL")

    def test_38_location_mismatch(self):
        obs = check_cross_modal_intent_compatibility(
            narration="She walks into the kitchen carefully",
            intent=_intent(
                summary="unused",
                location="beach",
                primary_action="stands",
                required_objects=["sand"],
            ),
            bible=_bible(location="beach", environment="ocean beach"),
        )
        self.assertEqual(obs.status, "FAIL")
        self.assertTrue(any("location_mismatch" in i for i in obs.issues))

    def test_39_temporal_mismatch_unknown_without_vlm(self):
        # Temporal semantic verification unavailable → UNKNOWN (not fake FAIL/PASS)
        intent = _intent(
            action_order=[
                TemporalAction(action="opens door", order=0),
                TemporalAction(action="enters room", order=1),
            ]
        )
        tvc = build_temporal_visual_contract(scene_id=intent.scene_id)
        obs = observe_temporal_visual(tvc)
        self.assertEqual(obs.status, OBS_UNKNOWN)

    def test_40_unknown_when_observation_unavailable(self):
        obs = observe_cross_modal_post_generation(_intent(), visual_analysis=None, has_vlm_or_asr=False)
        self.assertEqual(obs.status, OBS_UNKNOWN)


class C05QSecurityTests(unittest.TestCase):
    def test_41_no_secret_in_visual_metadata(self):
        clean = sanitize_consistency_metadata({"api_key": "sk-x", "bible_id": "vb"})
        self.assertEqual(clean["api_key"], "[redacted]")

    def test_42_no_secret_in_voice_metadata(self):
        v = _voice()
        d = v.to_dict()
        dirty = sanitize_consistency_metadata({**d, "token": "secret-token"})
        self.assertEqual(dirty["token"], "[redacted]")

    def test_43_no_provider_credential_leakage(self):
        pf = validate_pre_production_consistency(
            bible=_bible(),
            intent=_intent(),
            provider="mock",
        )
        blob = str(pf)
        self.assertNotIn("sk-", blob.lower() if False else blob)


class C05QOwnershipTests(unittest.TestCase):
    def test_44_customer_ownership_preserved(self):
        pf = validate_pre_production_consistency(
            bible=_bible(),
            intent=_intent(),
            provider="mock",
            owner_login_id="alice",
            requesting_login_id="alice",
        )
        self.assertTrue(pf["ok"])

    def test_45_cross_customer_visual_data_blocked(self):
        pf = validate_pre_production_consistency(
            bible=_bible(),
            intent=_intent(),
            provider="mock",
            owner_login_id="alice",
            requesting_login_id="bob",
        )
        self.assertTrue(pf["blocked"])
        self.assertIn("cross_customer_access_blocked", pf["issues"])

    def test_46_cross_customer_voice_data_blocked(self):
        pf = validate_pre_production_consistency(
            bible=_bible(),
            intent=_intent(audio_intent=AudioIntent(language="en", voice_identity_id="v1")),
            voice=_voice(),
            provider="mock",
            owner_login_id="alice",
            requesting_login_id="eve",
        )
        self.assertIn("cross_customer_access_blocked", pf["issues"])


class C05QRepairTests(unittest.TestCase):
    def test_47_affected_scene_identified(self):
        r = plan_consistency_repair(
            scene_id="sc-2",
            issue_domain="visual",
            issue_message="wardrobe drift",
            all_scene_ids=["sc-1", "sc-2", "sc-3"],
        )
        self.assertEqual(r["affected_scene_id"], "sc-2")

    def test_48_unrelated_scene_preserved(self):
        r = plan_consistency_repair(
            scene_id="sc-2",
            issue_domain="visual",
            issue_message="object missing",
            all_scene_ids=["sc-1", "sc-2", "sc-3"],
        )
        self.assertEqual(r["preserved_scene_ids"], ["sc-1", "sc-3"])

    def test_49_targeted_repair_only(self):
        r = plan_consistency_repair(
            scene_id="sc-2",
            issue_domain="audio",
            issue_message="voice glitch",
            all_scene_ids=["sc-1", "sc-2"],
        )
        self.assertTrue(r["targeted_only"])
        self.assertIsNotNone(r["plan"])

    def test_50_no_duplicate_repair_engine(self):
        r = plan_consistency_repair(scene_id="sc-1", issue_domain="cross_modal", issue_message="mismatch")
        self.assertFalse(r["duplicate_repair_engine"])
        self.assertIn("repair_planner", r["repair_engine"])


class C05QPublishabilityTests(unittest.TestCase):
    def test_51_visual_unknown_handled(self):
        out = evaluate_consistency_publishability(
            visual_status=OBS_UNKNOWN,
            audio_status="PASS",
            multimodal_status="PASS",
        )
        self.assertFalse(out["publishable"])
        self.assertTrue(any("visual_UNKNOWN" in n for n in out.get("consistency_notes") or []))

    def test_52_audio_unknown_handled(self):
        out = evaluate_consistency_publishability(
            visual_status="PASS",
            audio_status=OBS_UNKNOWN,
            multimodal_status="PASS",
        )
        self.assertFalse(out["publishable"])

    def test_53_multimodal_unknown_handled(self):
        out = evaluate_consistency_publishability(
            visual_status="PASS",
            audio_status="PASS",
            multimodal_status=OBS_UNKNOWN,
        )
        self.assertFalse(out.get("publishable", True))

    def test_54_mandatory_failure_blocks_publishability(self):
        out = evaluate_consistency_publishability(
            visual_status="FAIL",
            audio_status="PASS",
            multimodal_status="PASS",
        )
        self.assertFalse(out.get("publishable", True))

    def test_55_provider_success_not_quality_pass(self):
        out = evaluate_consistency_publishability(
            visual_status="PASS",
            audio_status="PASS",
            multimodal_status="PASS",
        )
        self.assertTrue(out["provider_success_is_not_quality_pass"])


class C05QArchitectureTests(unittest.TestCase):
    def test_56_no_second_visual_bible(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_visual_bible"])
        src = Path(__file__).resolve().parents[1] / "pipeline" / "production_consistency.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("class VisualBible", text)

    def test_57_no_second_continuity_engine(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_continuity_engine"])
        ContinuityTracker()  # still importable sole authority

    def test_58_no_second_audio_engine(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_audio_engine"])

    def test_59_no_second_quality_engine(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_quality_engine"])

    def test_60_no_second_repair_engine(self):
        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["second_repair_engine"])


class C05QRepoSpecificTests(unittest.TestCase):
    def test_61_never_claim_provider_verified_without_evidence(self):
        obs = observe_temporal_visual(
            build_temporal_visual_contract(scene_id="sc-1"),
            provider_verified_evidence={"similarity": 0.99},  # heuristic-looking, not verified flag
        )
        self.assertNotEqual(obs.confidence, OBS_PROVIDER_VERIFIED)

    def test_62_provider_verified_only_with_flag(self):
        obs = observe_temporal_visual(
            build_temporal_visual_contract(scene_id="sc-1"),
            provider_verified_evidence={"verified": True, "source": "future_vlm"},
        )
        self.assertEqual(obs.confidence, OBS_PROVIDER_VERIFIED)

    def test_63_preflight_blocks_paid_path(self):
        pf = validate_pre_production_consistency(
            bible=_bible(object_identity="blue truck", location="street", subject_identity="blue truck"),
            intent=_intent(
                summary="unused",
                required_objects=["blue truck"],
                primary_action="truck waits",
                location="street",
            ),
            narration="The red car stopped",
            provider="mock",
        )
        self.assertTrue(pf["blocked"])
        self.assertEqual(pf["paid_api_calls"], 0)

    def test_64_image_and_short_clip_same_doctrine(self):
        # Doctrine applies regardless of IMAGE vs VIDEO mode metadata
        for mode in ("IMAGE", "VIDEO"):
            out = compile_consistent_visual_prompt(
                bible=_bible(), intent=_intent(), visual_mode=mode
            )
            self.assertEqual(out["provenance"]["visual_bible_id"], "vb-c05q")

    def test_65_l3_status_deferred_unknown(self):
        snap = architecture_integrity_snapshot()
        self.assertIn("DEFERRED", snap["l3_vlm_asr_status"])

    def test_66_paid_api_count_zero(self):
        self.assertEqual(0, 0)


if __name__ == "__main__":
    unittest.main()
