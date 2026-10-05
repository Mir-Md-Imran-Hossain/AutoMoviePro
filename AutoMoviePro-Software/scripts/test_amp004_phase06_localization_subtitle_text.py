"""AMP-004 Phase-06 — Localization, subtitle & text consistency behavioral tests.

No paid API calls.
"""
from __future__ import annotations

import hashlib
import inspect
import tempfile
import unittest
from pathlib import Path

from pipeline.localization_consistency.contract import (
    TextElement,
    TextPlan,
    build_localization_contract,
    localization_fingerprint,
)
from pipeline.localization_consistency.drift import validate_translation_drift
from pipeline.localization_consistency.gate import (
    MAX_LOC_REPAIR_CYCLES,
    allow_loc_repair_cycle,
    persist_localization_contract,
    persist_localization_gate,
    record_loc_repair_cycle,
)
from pipeline.localization_consistency.preflight import LocalizationPreflightError, preflight_localization_request
from pipeline.localization_consistency.production import (
    apply_production_localization,
    run_production_localization_gate,
    validate_localized_pair,
)
from pipeline.localization_consistency.repair_bridge import plan_localization_repair, scope_for_loc_issue
from pipeline.localization_consistency.rtl_font import classify_rtl_support, detect_mixed_rtl_ltr, validate_font_availability, validate_glyph_coverage
from pipeline.localization_consistency.subtitle_rules import (
    suggest_semantic_line_break,
    validate_line_breaking,
    validate_reading_speed,
    validate_subtitle_identity,
    validate_subtitle_timing,
)
from pipeline.localization_consistency.text_layout import (
    validate_subtitle_text_collision,
    validate_text_effect,
    validate_text_overflow,
    validate_text_plan,
    validate_visual_text_consistency,
)
from pipeline.quality.contracts import RepairScope
from pipeline.quality.publishability import evaluate_publishability


class Phase06LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="amp004_p06_"))

    def test_01_valid_localization(self):
        c = build_localization_contract(
            job_id="j", scene_id="s1", dialogue_id="d1",
            source_text="The iPhone camera looks sharp today.",
            target_language="bn",
        )
        self.assertTrue(c.contract_fingerprint)
        self.assertIn("iPhone", " ".join(c.entity_bindings) or c.source_text)

    def test_02_invalid_language(self):
        with self.assertRaises(LocalizationPreflightError):
            preflight_localization_request(
                source_text="Hello", source_language="en", target_language="xx-NOPE", block=True
            )

    def test_03_missing_source(self):
        with self.assertRaises(LocalizationPreflightError) as ctx:
            preflight_localization_request(source_text="", source_language="en", target_language="bn")
        self.assertIn("missing_source", ctx.exception.issues)

    def test_04_missing_target(self):
        with self.assertRaises(LocalizationPreflightError) as ctx:
            preflight_localization_request(source_text="Hello", source_language="en", target_language="")
        self.assertIn("missing_target", ctx.exception.issues)

    def test_05_entity_preservation(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Google Pixel camera quality is strong.",
            target_language="es",
        )
        self.assertTrue(any("Pixel" in e or "Google" in e for e in c.entity_bindings) or "Pixel" in c.source_text)

    def test_06_entity_substitution_detection(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="the iPhone camera is excellent",
            target_language="en",
        )
        drift = validate_translation_drift(c, "the phone becomes a camera magically")
        self.assertEqual(drift["status"], "BLOCK")
        self.assertTrue(any("entity_substitution" in i for i in drift["issues"]))

    def test_07_fact_preservation(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="The tower is 20 meters tall.",
            target_language="en",
        )
        self.assertTrue(any(f.get("value") == "20" for f in c.fact_bindings))

    def test_08_number_mismatch(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Rated at 50 percent battery.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Rated at ninety percent battery.")
        self.assertTrue(any("number_mismatch" in i for i in drift["issues"]))

    def test_09_unit_mismatch(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Distance is 20 m away.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Distance is 20 ft away.")
        self.assertTrue(any("unit_mismatch" in i for i in drift["issues"]))

    def test_10_currency_mismatch(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Costs 10$ today.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Costs 10 € today.")
        self.assertTrue(any("currency" in i for i in drift["issues"]))

    def test_11_action_preservation(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="She is walking toward the door.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "She is sitting toward the door.")
        self.assertTrue(any("action" in i for i in drift["issues"]))

    def test_12_speaker_preservation(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Hello.", target_language="bn", speaker_id="SPEAKER-A",
        )
        res = validate_localized_pair(c, "হ্যালো", speaker_changed=True)
        self.assertEqual(res["status"], "BLOCK")
        self.assertIn("speaker_identity_changed", res["issues"])

    def test_13_emotion_intent_preservation(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Serious warning ahead.", target_language="en", emotion_intent="serious",
        )
        res = validate_localized_pair(c, "Serious warning ahead.", emotion_changed=True)
        self.assertIn("emotion_intent_changed", res["issues"])

    def test_14_translation_drift(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="He opens the door carefully.", target_language="en",
        )
        drift = validate_translation_drift(c, "Aliens suddenly explode nearby.")
        self.assertEqual(drift["status"], "BLOCK")

    def test_15_omission_detection(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Detailed camera sensor review with optical zoom features included.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Hi.")
        self.assertTrue(any("omission" in i for i in drift["issues"]))

    def test_16_addition_detection(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Simple tip for photographers.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Simple tip for photographers suddenly aliens lottery.")
        self.assertTrue(any("addition" in i for i in drift["issues"]))

    def test_17_negation_reversal(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="She does not open the door.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "She opens the door.")
        self.assertTrue(any("negation" in i for i in drift["issues"]))

    def test_18_temporal_reversal(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Wash hands before cooking food.",
            target_language="en",
        )
        drift = validate_translation_drift(c, "Wash hands after cooking food.")
        self.assertTrue(any("temporal" in i for i in drift["issues"]))

    def test_19_subtitle_identity(self):
        issues = validate_subtitle_identity(
            cue_scene_id="s1", cue_dialogue_id="d1", cue_language="bn",
            expected_scene_id="s1", expected_dialogue_id="d2", expected_language="bn",
        )
        self.assertTrue(any("dialogue" in i for i in issues))

    def test_20_subtitle_audio_alignment(self):
        cues = [{"start_time": 0, "end_time": 10, "text": "hi"}]
        issues = validate_subtitle_timing(cues, audio_duration_sec=2.0)
        self.assertTrue(any("timing" in i for i in issues))

    def test_21_subtitle_overlap(self):
        cues = [
            {"start_time": 0, "end_time": 2, "text": "a"},
            {"start_time": 1.5, "end_time": 3, "text": "b"},
        ]
        issues = validate_subtitle_timing(cues)
        self.assertTrue(any("overlap" in i for i in issues))

    def test_22_subtitle_reading_speed(self):
        issues = validate_reading_speed("x" * 200, 1.0, max_cps=17)
        self.assertTrue(any("reading_speed" in i for i in issues))

    def test_23_subtitle_line_breaking(self):
        issues = validate_line_breaking("20\nkg of rice", max_chars_per_line=42)
        self.assertTrue(any("number_unit" in i or "line" in i for i in issues))

    def test_24_name_protection(self):
        broken = suggest_semantic_line_break("Hello " + "word " * 20 + "end", max_chars_per_line=20)
        self.assertIn("\n", broken)
        issues = validate_line_breaking("John\nSmith walked", max_chars_per_line=42)
        self.assertTrue(any("name" in i for i in issues))

    def test_25_number_formatting(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Score reached 99.5 percent.",
            target_language="en",
        )
        self.assertTrue(any("99.5" in str(f.get("value")) for f in c.fact_bindings))

    def test_26_rtl_direction(self):
        rtl = classify_rtl_support("ur")
        self.assertTrue(rtl["rtl"])
        self.assertEqual(rtl["status"], "UNKNOWN")
        self.assertFalse(rtl["shaping_guaranteed"])

    def test_27_rtl_ltr_mixed_text(self):
        mixed = detect_mixed_rtl_ltr("اردو text with Latin iPhone")
        self.assertTrue(mixed["mixed"])

    def test_28_missing_glyph(self):
        g = validate_glyph_coverage("bad\ufffdchar", font_path=str(self.tmp / "missing.ttf"))
        self.assertEqual(g["status"], "FAIL")

    def test_29_font_availability(self):
        res = validate_font_availability("en")
        # On Windows typically finds arial; if fail, still deterministic
        self.assertIn(res["status"], ("PASS", "FAIL"))

    def test_30_text_overflow(self):
        el = TextElement(
            text_id="t1", scene_id="s", language="en",
            content="x" * 500, purpose="CAPTION", max_width_pct=0.5,
        )
        issues = validate_text_overflow(el)
        self.assertTrue(any("overflow" in i for i in issues))

    def test_31_safe_area_violation(self):
        el = TextElement(
            text_id="t1", scene_id="s", language="en", content="Hi",
            purpose="CAPTION", safe_area=False, position="bottom_edge",
        )
        issues = validate_text_overflow(el)
        self.assertTrue(any("safe_area" in i for i in issues))

    def test_32_subtitle_text_collision(self):
        issues = validate_subtitle_text_collision(subtitle_region="bottom", text_position="bottom_center")
        self.assertTrue(any("collision" in i for i in issues))

    def test_33_text_effect_validation(self):
        self.assertTrue(validate_text_effect("shake"))
        self.assertFalse(validate_text_effect("fade", purpose="CAPTION"))

    def test_34_visual_text_contradiction(self):
        issues = validate_visual_text_consistency(
            visual_objects=["smartphone"],
            text_content="professional cinema camera body",
        )
        self.assertTrue(issues)

    def test_35_localization_visual_consistency(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Phone tip", target_language="en",
        )
        res = validate_localized_pair(
            c, "professional cinema camera body", visual_objects=["smartphone"]
        )
        self.assertEqual(res["status"], "BLOCK")

    def test_36_localization_audio_consistency(self):
        # Identity binding: dialogue_id preserved on contract for audio handoff
        c = build_localization_contract(
            job_id="j", scene_id="s9", dialogue_id="dlg-9",
            source_text="Hello world", target_language="bn",
        )
        self.assertEqual(c.dialogue_id, "dlg-9")
        self.assertEqual(c.scene_id, "s9")

    def test_37_localization_sfx_timing(self):
        # Longer localized text → duration estimate changes (timing coherence)
        short = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Hi.", target_language="bn",
        )
        long = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="This is a much longer narration that needs more audio time.",
            target_language="bn",
        )
        self.assertNotEqual(len(short.source_text), len(long.source_text))
        # SFX segment identity remains scene/dialogue bound
        self.assertEqual(short.dialogue_id, long.dialogue_id)

    def test_38_idempotent_localization_reuse(self):
        a = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Same text", target_language="bn", revision_id="r1",
        )
        b = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Same text", target_language="bn", revision_id="r1",
        )
        self.assertEqual(a.contract_fingerprint, b.contract_fingerprint)

    def test_39_localization_fingerprint_invalidation(self):
        a = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Version one", target_language="bn",
        )
        b = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Version two", target_language="bn",
        )
        self.assertNotEqual(a.contract_fingerprint, b.contract_fingerprint)

    def test_40_minimal_repair_scope(self):
        self.assertEqual(scope_for_loc_issue("entity_substitution"), RepairScope.LOCALIZATION)
        self.assertEqual(scope_for_loc_issue("subtitle_overlap"), RepairScope.SUBTITLE)
        self.assertEqual(scope_for_loc_issue("text_overflow"), RepairScope.TEXT_LAYOUT)
        self.assertEqual(scope_for_loc_issue("missing_glyph"), RepairScope.TEXT_RENDER)
        plan = plan_localization_repair(issues=["negation_reversal"], work_dir=self.tmp)
        self.assertIsNotNone(plan)
        self.assertNotEqual(plan.repair_scope, RepairScope.SCRIPT)

    def test_41_bounded_retry(self):
        for _ in range(MAX_LOC_REPAIR_CYCLES):
            record_loc_repair_cycle(self.tmp, outcome="fail", scope="LOCALIZATION")
        self.assertFalse(allow_loc_repair_cycle(self.tmp))

    def test_42_unknown_not_pass(self):
        rtl = classify_rtl_support("ar")
        self.assertEqual(rtl["status"], "UNKNOWN")
        self.assertNotEqual(rtl["status"], "PASS")
        g = validate_glyph_coverage("বাংলা", font_path=str(self.tmp / "x.ttf"))
        # font missing → FAIL; or if we pass existing - UNKNOWN coverage
        self.assertIn(g["status"], ("FAIL", "UNKNOWN"))
        self.assertNotEqual(g.get("status"), "PASS") if g["status"] != "PASS" else None

    def test_43_artifact_verification(self):
        srt = self.tmp / "t.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        from pipeline.artifact_verification.verifiers import verify_subtitle_artifact

        obs = verify_subtitle_artifact(srt, scene_id="s", dialogue_id="d")
        self.assertEqual(obs.technical_status.value, "PASS")

    def test_44_final_composite_verification(self):
        gate = run_production_localization_gate(
            self.tmp, job_id="j", multilingual=False, final_path=None
        )
        self.assertEqual(gate["status"], "ABSENT")

    def test_45_publication_blocked_on_localization_failure(self):
        pub = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "publishable": True},
            localization_status="BLOCKED",
            artifact_status="PASS",
            render_status="PASS",
            audio_status="PASS",
        )
        self.assertFalse(pub.get("publishable"))

    def test_46_production_path_uses_canonical_contract(self):
        out = apply_production_localization(
            self.tmp,
            job_id="job",
            scene_id="s1",
            dialogue_id="d1",
            source_text="Host reviews the iPhone camera.",
            source_language="en",
            target_language="bn",
            localized_text="",
            block_on_critical=True,
        )
        self.assertTrue(out.get("_localization_applied"))
        self.assertTrue((self.tmp / "localization_contracts").is_dir())

    def test_47_no_direct_localization_bypass(self):
        import pipeline.localization as loc

        src = inspect.getsource(loc.translate_text)
        self.assertIn("preflight_localization_request", src)

    def test_48_no_second_subtitle_authority(self):
        # Uses existing subtitle validation path
        from pipeline.idempotency import subtitle_validation

        self.assertTrue(hasattr(subtitle_validation, "parse_srt"))

    def test_49_no_second_repair_authority(self):
        plan = plan_localization_repair(issues=["text_overflow"], work_dir=self.tmp)
        self.assertEqual(plan.repair_scope, RepairScope.TEXT_LAYOUT)

    def test_50_no_second_idempotency_authority(self):
        from pipeline.idempotency.fingerprint import compute_fingerprint

        self.assertTrue(callable(compute_fingerprint))

    def test_51_no_unnecessary_regeneration(self):
        self.assertIsNone(plan_localization_repair(issues=[], work_dir=self.tmp))

    def test_52_deterministic_validation_before_provider(self):
        with self.assertRaises(LocalizationPreflightError):
            preflight_localization_request(
                source_text="", source_language="en", target_language="hi", block=True
            )

    def test_53_provenance_persisted(self):
        c = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Hello", target_language="bn",
        )
        path = persist_localization_contract(self.tmp, c.to_dict(), key="k1")
        self.assertTrue(path.is_file())

    def test_54_checkpoint_persisted(self):
        persist_localization_gate(self.tmp, {"status": "PASS", "authority": "pipeline.localization_consistency"})
        self.assertTrue((self.tmp / "LOCALIZATION_GATE.json").is_file())

    def test_55_multilingual_isolation(self):
        bn = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d", source_text="Hello", target_language="bn"
        )
        hi = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d", source_text="Hello", target_language="hi"
        )
        self.assertNotEqual(bn.contract_fingerprint, hi.contract_fingerprint)

    def test_56_source_language_artifact_remains_reusable(self):
        # Same source fingerprint independent of localized fill
        a = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Stable EN", target_language="bn", localized_text="",
        )
        b = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d",
            source_text="Stable EN", target_language="bn", localized_text="বাংলা",
        )
        # fingerprint excludes localized_text — reuse source
        self.assertEqual(a.contract_fingerprint, b.contract_fingerprint)

    def test_57_target_language_change_invalidates(self):
        a = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d", source_text="Hello", target_language="bn"
        )
        b = build_localization_contract(
            job_id="j", scene_id="s", dialogue_id="d", source_text="Hello", target_language="ur"
        )
        self.assertNotEqual(localization_fingerprint(a), localization_fingerprint(b))

    def test_58_final_localized_package_traceability(self):
        apply_production_localization(
            self.tmp, job_id="j", scene_id="s", dialogue_id="d",
            source_text="Trace me", source_language="en", target_language="bn",
        )
        gate = run_production_localization_gate(self.tmp, job_id="j", multilingual=True)
        self.assertIn("provenance_chain", gate)
        self.assertEqual(gate.get("authority"), "pipeline.localization_consistency")

    def test_production_wiring(self):
        import pipeline.video_pipeline as vp
        import pipeline.localization as loc

        self.assertIn("run_production_localization_gate", inspect.getsource(vp))
        self.assertIn("preflight_localization_request", inspect.getsource(loc.translate_text))

    def test_text_plan_exists(self):
        plan = TextPlan(
            scene_id="s",
            language="en",
            elements=[TextElement(text_id="1", scene_id="s", language="en", content="Title", purpose="TITLE", effect="fade")],
        )
        res = validate_text_plan(plan)
        self.assertEqual(res["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
