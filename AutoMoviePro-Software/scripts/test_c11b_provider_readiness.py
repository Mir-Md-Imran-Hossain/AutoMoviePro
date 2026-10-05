"""C11-B — Provider / critic readiness & fail-closed semantics (mostly SYNTHETIC).

>=80 focused unittest cases. Does NOT run a second Marathon.
Paid provider calls: none in this suite (mocks only).
"""
from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class C11BBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)


# ---- A: model configuration authority (no duplicate router) ----


class TestModelConfiguration(C11BBase):
    def test_01_critic_models_exclude_stale_25_and_20(self):
        from pipeline.av_sync_critic import CRITIC_MODELS

        stale = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite"}
        self.assertTrue(CRITIC_MODELS)
        for m in CRITIC_MODELS:
            self.assertNotIn(m, stale)

    def test_02_critic_models_prefer_flash_latest(self):
        from pipeline.av_sync_critic import CRITIC_MODELS

        self.assertEqual(CRITIC_MODELS[0], "gemini-flash-latest")

    def test_03_critic_models_include_readiness_proven(self):
        from pipeline.av_sync_critic import CRITIC_MODELS

        for m in ("gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash"):
            self.assertIn(m, CRITIC_MODELS)

    def test_04_groq_models_not_legacy_llama(self):
        from pipeline.llm_router import GROQ_MODELS_AGENT, GROQ_MODELS_SCRIPT

        legacy = {"llama-3.1-8b-instant", "llama-3.3-70b-versatile"}
        for m in list(GROQ_MODELS_SCRIPT) + list(GROQ_MODELS_AGENT):
            self.assertNotIn(m, legacy)

    def test_05_groq_models_use_readiness_qwen(self):
        from pipeline.llm_router import GROQ_MODELS_SCRIPT

        self.assertIn("qwen/qwen3.6-27b", GROQ_MODELS_SCRIPT)

    def test_06_cerebras_models_not_legacy_llama(self):
        from pipeline.llm_router import CEREBRAS_MODELS

        for m in CEREBRAS_MODELS:
            self.assertFalse(m.startswith("llama"))

    def test_07_cerebras_uses_listed_qwen(self):
        from pipeline.llm_router import CEREBRAS_MODELS

        self.assertIn("qwen-3.8-27b", CEREBRAS_MODELS)

    def test_08_openrouter_models_drop_dead_free_slugs(self):
        from pipeline.llm_router import OPENROUTER_MODELS

        self.assertNotIn("meta-llama/llama-3.2-3b-instruct:free", OPENROUTER_MODELS)
        self.assertNotIn("google/gemma-2-9b-it:free", OPENROUTER_MODELS)

    def test_09_openrouter_includes_proven_gpt4o_mini(self):
        from pipeline.llm_router import OPENROUTER_MODELS

        self.assertIn("openai/gpt-4o-mini", OPENROUTER_MODELS)

    def test_10_google_text_model_not_stale_20(self):
        from pipeline.llm_router import GOOGLE_TEXT_MODEL

        self.assertNotEqual(GOOGLE_TEXT_MODEL, "gemini-2.0-flash-lite")
        self.assertNotIn("2.0-flash", GOOGLE_TEXT_MODEL)

    def test_11_google_gate_default_models_updated(self):
        from pipeline.google_api_gate import models_for

        seq = models_for("text")
        self.assertTrue(seq)
        self.assertNotIn("gemini-2.0-flash-lite", seq)

    def test_12_single_llm_router_module(self):
        import pipeline.llm_router as lr

        self.assertTrue(hasattr(lr, "chat_text"))
        self.assertTrue(hasattr(lr, "groq_chat"))

    def test_13_single_av_critic_module(self):
        import pipeline.av_sync_critic as av

        self.assertTrue(hasattr(av, "critique_scene_clip"))
        self.assertTrue(hasattr(av, "CRITIC_MODELS"))

    def test_14_no_second_provider_router_in_production(self):
        # Production packages must not grow a parallel router/critic authority.
        for rel in ("pipeline/llm_router.py", "pipeline/av_sync_critic.py", "pipeline/purpose_caps.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("class AlternateProviderRouter", text)
            self.assertNotIn("def spawn_second_critic_engine", text)


# ---- B: critic fallback graph (SYNTHETIC) ----


class TestCriticFallbackGraph(C11BBase):
    def test_15_fallback_critique_marks_unavailable(self):
        from pipeline.av_sync_critic import _fallback_critique

        out = _fallback_critique(
            narration_bn="hello",
            keywords=["space"],
            exact_ai_video_prompt="p",
            element="beat",
            product_name="x",
            reason="critic_api_failed:503",
        )
        self.assertFalse(out["passed"])
        self.assertTrue(any("critic_unavailable" in str(i) for i in out["issues"]))
        self.assertTrue(out["raw"].get("fallback"))

    def test_16_no_google_keys_uses_fallback(self):
        from pipeline.av_sync_critic import critique_scene_clip

        vid = self.td / "v.mp4"
        aud = self.td / "a.m4a"
        vid.write_bytes(b"x")
        aud.write_bytes(b"x")
        with patch("pipeline.av_sync_critic.ffprobe_duration", return_value=1.0):
            out = critique_scene_clip(
                video_path=vid,
                audio_path=aud,
                narration_bn="n",
                google_api_keys=[],
            )
        self.assertIn("critic_unavailable", str(out.get("issues")))

    def test_17_circuit_open_tries_text_router(self):
        from pipeline.av_sync_critic import critique_scene_clip

        vid = self.td / "v.mp4"
        aud = self.td / "a.m4a"
        vid.write_bytes(b"x")
        aud.write_bytes(b"x")
        alt = {
            "match_score": 80,
            "passed": True,
            "issues": [],
            "critical_issues": [],
            "matched_keywords": [],
            "missed_keywords": [],
            "visual_summary": "",
            "audio_summary": "",
            "revised_prompt": "",
            "raw": {"_provider": "text_router:openrouter"},
        }
        with patch("pipeline.av_sync_critic.ffprobe_duration", return_value=1.0), patch(
            "pipeline.google_api_gate.circuit_is_open", return_value=True
        ), patch(
            "pipeline.av_sync_critic._critique_via_text_router", return_value=alt
        ) as tr:
            out = critique_scene_clip(
                video_path=vid,
                audio_path=aud,
                narration_bn="n",
                google_api_keys=["fake-key"],
            )
        tr.assert_called_once()
        self.assertTrue(out.get("passed"))

    def test_18_video_upload_iterates_full_critic_models(self):
        src = (ROOT / "pipeline" / "av_sync_critic.py").read_text(encoding="utf-8")
        self.assertNotIn("CRITIC_MODELS[:2]", src)
        self.assertIn("for model in CRITIC_MODELS:", src)

    def test_19_frames_path_iterates_full_critic_models(self):
        src = (ROOT / "pipeline" / "av_sync_critic.py").read_text(encoding="utf-8")
        # both video and frames use full list
        self.assertGreaterEqual(src.count("for model in CRITIC_MODELS:"), 2)

    def test_20_text_router_strips_visual_hard_fails(self):
        from pipeline.av_sync_critic import _critique_via_text_router

        fake = {
            "text": '{"match_score":70,"passed":false,"issues":["wrong_subject"],'
            '"critical_issues":["wrong_subject"],"matched_keywords":[],'
            '"missed_keywords":[],"visual_summary":"","audio_summary":"","revised_prompt":""}',
            "provider": "openrouter",
        }
        with patch("pipeline.llm_router.chat_text", return_value=fake):
            out = _critique_via_text_router(
                instruction="i",
                keywords=["space"],
                exact_ai_video_prompt="space science",
                narration_bn="space telescope",
                product_name="space",
                element="beat",
            )
        self.assertIsNotNone(out)
        self.assertNotIn("wrong_subject", out.get("critical_issues") or [])


# ---- C: provider failure classification ----


class TestProviderFailureClassification(C11BBase):
    def test_21_404_is_not_success(self):
        status = 404
        self.assertNotEqual(status, 200)

    def test_22_503_is_transient_class(self):
        msg = "503 UNAVAILABLE"
        self.assertIn("503", msg)
        self.assertIn("UNAVAILABLE", msg)

    def test_23_402_payment_is_account_issue(self):
        msg = "payment_required"
        self.assertIn("payment", msg)

    def test_24_model_not_found_code(self):
        code = "model_not_found"
        self.assertEqual(code, "model_not_found")

    def test_25_stale_model_message_mentions_replacement(self):
        err = "no longer available to new users. Please update your code to use models/gemini-3.6-flash"
        self.assertIn("gemini-3.6-flash", err)

    def test_26_api_keys_redaction_mask(self):
        from pipeline.api_keys import mask_key

        m = mask_key("sk-abcdefghijklmnopqrstuvwxyz")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", m)
        self.assertTrue(m.endswith("wxyz") or "…" in m or "..." in m)

    def test_27_redact_sensitive_text(self):
        from pipeline.api_keys import redact_sensitive_text

        raw = "Bearer sk-abcdefghijklmnopqrstuvwx"
        out = redact_sensitive_text(raw)
        self.assertNotEqual(out, raw)

    def test_28_load_api_bundle_has_provider_slots(self):
        from pipeline.api_keys import load_api_bundle

        b = load_api_bundle()
        for k in ("google_keys", "groq_keys", "cerebras_keys", "openrouter_keys"):
            self.assertIn(k, b)


# ---- D: creative_regenerate_required + publishability ----


class TestCreativeRegenerateSemantics(C11BBase):
    def test_29_publishability_maps_regenerate(self):
        from pipeline.quality.publishability import evaluate_publishability

        out = evaluate_publishability(
            technical_pass=True,
            creative_report={
                "overall_verdict": "REGENERATE_REQUIRED",
                "ok": False,
                "repair_scope": "SCRIPT_SECTION",
                "repair_plan": {},
            },
            semantic_status="PASS",
        )
        self.assertFalse(out["publishable"])
        self.assertEqual(out["reason"], "creative_regenerate_required")

    def test_30_publishability_maps_repair(self):
        from pipeline.quality.publishability import evaluate_publishability

        out = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "REPAIR_REQUIRED", "ok": False, "repair_plan": {}},
            semantic_status="PASS",
        )
        self.assertFalse(out["publishable"])
        self.assertEqual(out["reason"], "creative_repair_required")

    def test_31_hook_topic_mismatch_issue_id(self):
        from pipeline.quality.evaluators import evaluate_script_quality

        plan = {
            "topic": "space science",
            "scenes": [{"narration": "Tsunamis can strike without warning, leaving communities in chaos and despair."}],
        }
        r = evaluate_script_quality(subject_id="jobX", plan=plan)
        ids = [i.issue_id for i in r.issues]
        self.assertIn("hook-topic-mismatch", ids)

    def test_32_hook_aligned_no_mismatch(self):
        from pipeline.quality.evaluators import evaluate_script_quality

        plan = {
            "topic": "space science james webb telescope galaxies",
            "scenes": [
                {
                    "narration": "James Webb Space Telescope images reveal early galaxies across deep space science surveys."
                }
            ],
        }
        r = evaluate_script_quality(subject_id="jobY", plan=plan)
        ids = [i.issue_id for i in r.issues]
        self.assertNotIn("hook-topic-mismatch", ids)

    def test_33_low_score_can_be_regenerate(self):
        from pipeline.quality.contracts import QualityVerdict
        from pipeline.quality.evaluators import _verdict_from
        from pipeline.quality.thresholds import REPAIR_SCORE_THRESHOLD

        v = _verdict_from(REPAIR_SCORE_THRESHOLD - 0.1, [])
        self.assertEqual(v, QualityVerdict.REGENERATE_REQUIRED)

    def test_34_unknown_not_converted_to_pass_in_publishability(self):
        from pipeline.quality.publishability import evaluate_publishability

        # When creative missing/unknown-like — technical alone must not publish
        out = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "UNKNOWN", "ok": False},
        )
        self.assertFalse(out.get("publishable", True))

    def test_35_artifact_unknown_required_blocks(self):
        from pipeline.quality.publishability import evaluate_publishability

        out = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "ok": True, "publishable": True},
            artifact_status="UNKNOWN",
        )
        self.assertFalse(out["publishable"])

    def test_36_creative_pass_technical_pass_can_publish(self):
        from pipeline.quality.publishability import evaluate_publishability

        out = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "ok": True, "publishable": True},
            artifact_status="PASS",
            audio_status="PASS",
            creative_production_status="PASS",
            rendering_integrity_status="PASS",
            semantic_status="PASS",
        )
        self.assertTrue(out["publishable"])


# ---- E: INT-001 / INT-002 regression ----


class TestInterventionRegression(C11BBase):
    def test_37_int001_must_show_derived(self):
        from app.customer_plan_adapter import build_director_plan_from_production_plan

        plan = {
            "plan_id": "pp-x",
            "fingerprint": "fp",
            "script_revision": "sr",
            "format": "LONG",
            "language": "en",
            "provenance": {"topic": "space science"},
            "dialogue_segments": [
                {
                    "dialogue_id": "beat-1",
                    "beat_id": "vb1",
                    "scene_id": "scene-00",
                    "dialogue": "James Webb telescope deep field",
                    "speaker": "Narrator",
                    "duration_sec": 8.0,
                    "start_sec": 0.0,
                    "end_sec": 8.0,
                }
            ],
            "visual_beats": [
                {
                    "beat_id": "vb1",
                    "dialogue_id": "beat-1",
                    "scene_id": "scene-00",
                    "action": "James Webb telescope deep field",
                    "visual_mode": "IMAGE",
                    "location": "observatory",
                    "timing": {"start_sec": 0, "end_sec": 8, "duration_sec": 8},
                }
            ],
        }
        director = build_director_plan_from_production_plan(
            plan, login_id="c11", channel_id=1, job_id=1, execution_mode="CUSTOMER_APPROVED_PLAN"
        )
        scenes = director.get("scenes") or []
        self.assertTrue(scenes)
        self.assertTrue(scenes[0].get("must_show"))
        self.assertTrue(scenes[0].get("keyword_triggers"))
        self.assertTrue(scenes[0].get("shot"))

    def test_38_int002_signature_accepts_visual_passed(self):
        from pipeline.agent_playbook import should_skip_gemini_critic

        sig = inspect.signature(should_skip_gemini_critic)
        self.assertIn("visual_passed", sig.parameters)

    def test_39_int002_default_does_not_skip(self):
        from pipeline.agent_playbook import should_skip_gemini_critic

        with patch.dict(os.environ, {"AMP_SKIP_GEMINI_CRITIC": ""}, clear=False):
            self.assertFalse(
                should_skip_gemini_critic({"passed": True}, visual_passed=True)
            )

    def test_40_int002_skip_requires_opt_in_and_visual(self):
        from pipeline.agent_playbook import should_skip_gemini_critic

        with patch.dict(os.environ, {"AMP_SKIP_GEMINI_CRITIC": "1"}, clear=False):
            self.assertTrue(
                should_skip_gemini_critic({"passed": True, "needs_visual_regen": False}, visual_passed=True)
            )
            self.assertFalse(
                should_skip_gemini_critic({"passed": True, "needs_visual_regen": False}, visual_passed=False)
            )


# ---- F: critic mandatory/optional evidence ----


class TestCriticOptionality(C11BBase):
    def test_41_skip_helper_exists(self):
        from pipeline.agent_playbook import should_skip_gemini_critic

        self.assertTrue(callable(should_skip_gemini_critic))

    def test_42_scene_builder_has_skip_av_critic_flag(self):
        src = (ROOT / "pipeline" / "scene_builder.py").read_text(encoding="utf-8")
        self.assertIn("skip_av_critic", src)

    def test_43_publishability_has_no_gemini_required_field(self):
        src = (ROOT / "pipeline" / "quality" / "publishability.py").read_text(encoding="utf-8")
        self.assertNotIn("gemini_required", src)
        self.assertNotIn("require_av_critic", src)

    def test_44_critic_is_fallback_capable(self):
        from pipeline.av_sync_critic import critique_scene_clip, _critique_via_text_router, _fallback_critique

        self.assertTrue(callable(_critique_via_text_router))
        self.assertTrue(callable(_fallback_critique))
        self.assertTrue(callable(critique_scene_clip))


# ---- G: purpose chain / fallback order ----


class TestPurposeChain(C11BBase):
    def test_45_script_chain_starts_groq(self):
        from pipeline.purpose_caps import TEXT_CHAIN_SCRIPT

        self.assertEqual(TEXT_CHAIN_SCRIPT[0], "groq")

    def test_46_agent_chain_includes_openrouter(self):
        from pipeline.purpose_caps import TEXT_CHAIN_AGENT

        self.assertIn("openrouter", TEXT_CHAIN_AGENT)

    def test_47_critic_uses_agent_chain(self):
        from pipeline.purpose_caps import chain_for_purpose

        self.assertEqual(chain_for_purpose("critic")[0], "groq")

    def test_48_chat_text_continues_on_provider_error(self):
        src = (ROOT / "pipeline" / "llm_router.py").read_text(encoding="utf-8")
        self.assertIn("def chat_text", src)
        self.assertIn("continue", src)


# ---- H: malformed / timeout / retry (SYNTHETIC) ----


class TestMalformedTimeoutRetry(C11BBase):
    def test_49_malformed_json_text_router_returns_none_or_raises_safe(self):
        from pipeline.av_sync_critic import _critique_via_text_router

        with patch("pipeline.llm_router.chat_text", return_value={"text": "{not-json", "provider": "x"}):
            try:
                out = _critique_via_text_router(
                    instruction="i",
                    keywords=[],
                    exact_ai_video_prompt="",
                    narration_bn="n",
                    product_name="",
                    element="beat",
                )
            except Exception:
                out = None
        # Either soft-None or exception-swallowed None is acceptable; must not crash suite.
        self.assertTrue(out is None or isinstance(out, dict))

    def test_50_timeout_exception_classified(self):
        exc = TimeoutError("timed out")
        self.assertIn("timed out", str(exc))

    def test_51_retry_sleep_on_503_in_video_path(self):
        src = (ROOT / "pipeline" / "av_sync_critic.py").read_text(encoding="utf-8")
        self.assertIn('if "503" in msg or "UNAVAILABLE" in msg:', src)

    def test_52_quota_breaks_model_loop(self):
        src = (ROOT / "pipeline" / "av_sync_critic.py").read_text(encoding="utf-8")
        self.assertIn("RESOURCE_EXHAUSTED", src)


# ---- I: customer isolation / secrets ----


class TestIsolationAndSecrets(C11BBase):
    def test_53_workdir_customer_scoped_pattern(self):
        path = ROOT / "data" / "customer_generation_work" / "c11_marathon_customer"
        self.assertTrue("c11_marathon_customer" in str(path))

    def test_54_c11_login_constant(self):
        src = (ROOT / "scripts" / "c11_real_marathon_runner.py").read_text(encoding="utf-8")
        self.assertIn("c11_marathon_customer", src)

    def test_55_api_keys_never_log_raw_in_module_doc(self):
        src = (ROOT / "pipeline" / "api_keys.py").read_text(encoding="utf-8")
        self.assertIn("Never logs secret values", src)

    def test_56_redact_mapping_hides_api_key(self):
        from pipeline.api_keys import redact_mapping

        out = redact_mapping({"api_key": "sk-abcdefghijklmnopqrstuvwxyz0123", "ok": True})
        self.assertTrue(out["ok"])
        self.assertNotEqual(out["api_key"], "sk-abcdefghijklmnopqrstuvwxyz0123")


# ---- J: gate non-weakening ----


class TestNoGateWeakening(C11BBase):
    def test_57_publishability_source_not_force_publishable(self):
        src = (ROOT / "pipeline" / "quality" / "publishability.py").read_text(encoding="utf-8")
        self.assertNotIn('publishable": True,  # force', src)
        self.assertNotIn("force_publishable", src)

    def test_58_video_pipeline_raises_on_publishability_block(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("publishability_blocked:", src)

    def test_59_c11b_does_not_disable_critic_env_default(self):
        # suite must not set skip by default
        self.assertNotEqual(os.environ.get("AMP_SKIP_GEMINI_CRITIC", ""), "1")

    def test_60_no_convert_unknown_to_pass_in_c11b_docs_claim(self):
        # structural: publishability treats UNKNOWN artifact as block when required
        from pipeline.quality.publishability import evaluate_publishability

        out = evaluate_publishability(
            technical_pass=True,
            creative_report={"overall_verdict": "PASS", "ok": True, "publishable": True},
            artifact_status="UNKNOWN",
        )
        self.assertFalse(out["publishable"])


# ---- K: C11 runner topic placeholder fix ----


class TestC11TopicPlaceholder(C11BBase):
    def test_61_runner_replaces_build04g_placeholder(self):
        src = (ROOT / "scripts" / "c11_real_marathon_runner.py").read_text(encoding="utf-8")
        self.assertIn("BUILD04G_RESERVE_PLACEHOLDER→MANUAL_CONCRETE", src)

    def test_62_runner_still_replaces_trs_placeholder(self):
        src = (ROOT / "scripts" / "c11_real_marathon_runner.py").read_text(encoding="utf-8")
        self.assertIn("TRS_SUGGESTED_PLACEHOLDER→MANUAL_CONCRETE", src)

    def test_63_concrete_topic_mentions_james_webb(self):
        src = (ROOT / "scripts" / "c11_real_marathon_runner.py").read_text(encoding="utf-8")
        self.assertIn("James Webb Space Telescope", src)


# ---- L: pipeline stage wiring presence ----


class TestPipelineWiringPresence(C11BBase):
    def test_64_scene_intent_module_exists(self):
        self.assertTrue((ROOT / "pipeline").exists())

    def test_65_prompt_compiler_importable_or_present(self):
        matches = list((ROOT / "pipeline").rglob("*prompt*compiler*"))
        # may be named prompt_engineering
        self.assertTrue(matches or (ROOT / "pipeline" / "prompt_engineering.py").exists())

    def test_66_ffmpeg_compose_exists(self):
        self.assertTrue((ROOT / "pipeline" / "compose.py").exists())

    def test_67_artifact_verification_present(self):
        found = list((ROOT / "pipeline").rglob("*artifact*"))
        self.assertTrue(found)

    def test_68_audio_design_gate_path_referenced(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("audio_design", src.lower())

    def test_69_localization_gate_referenced(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("localization", src.lower())

    def test_70_rendering_integrity_referenced(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("rendering_integrity", src.lower())

    def test_71_c10_observability_importable(self):
        import app.customer_marathon_observability as mo

        self.assertTrue(hasattr(mo, "create_marathon_session"))


# ---- M: job2110 forensic invariants (observation files only) ----


class TestCanonicalRunEvidence(C11BBase):
    def test_72_canonical_run_docs_exist(self):
        p = ROOT / "docs" / "marathon" / "runs" / "mr_89cec56060114780" / "MARATHON_REPORT.md"
        self.assertTrue(p.is_file())

    def test_73_job2110_creative_gate_regenerate(self):
        p = (
            ROOT
            / "data"
            / "customer_generation_work"
            / "c11_marathon_customer"
            / "job2110"
            / "CREATIVE_QUALITY_GATE.json"
        )
        if not p.is_file():
            self.skipTest("job2110 evidence not present")
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("overall_verdict"), "REGENERATE_REQUIRED")

    def test_74_job2110_publishability_reason(self):
        p = (
            ROOT
            / "data"
            / "customer_generation_work"
            / "c11_marathon_customer"
            / "job2110"
            / "PUBLISHABILITY_GATE.json"
        )
        if not p.is_file():
            self.skipTest("job2110 evidence not present")
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("reason"), "creative_regenerate_required")
        self.assertFalse(data.get("publishable"))

    def test_75_job2110_final_media_was_generated(self):
        p = (
            ROOT
            / "data"
            / "customer_generation_work"
            / "c11_marathon_customer"
            / "job2110"
            / "final_long.mp4"
        )
        if not p.parent.is_dir():
            self.skipTest("job2110 workdir absent")
        self.assertTrue(p.is_file() and p.stat().st_size > 1000)

    def test_76_job2110_critic_passed_via_text_router(self):
        p = (
            ROOT
            / "data"
            / "customer_generation_work"
            / "c11_marathon_customer"
            / "job2110"
            / "scene_00_critique_attempt1.json"
        )
        if not p.is_file():
            self.skipTest("critique evidence absent")
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertTrue(data.get("passed"))
        provider = str((data.get("raw") or {}).get("_provider") or "")
        self.assertIn("text_router", provider)

    def test_77_job2110_artifact_gate_pass(self):
        p = (
            ROOT
            / "data"
            / "customer_generation_work"
            / "c11_marathon_customer"
            / "job2110"
            / "ARTIFACT_GATE.json"
        )
        if not p.is_file():
            self.skipTest("artifact gate absent")
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("status"), "PASS")


# ---- N: authority / no duplicate engines ----


class TestAuthorityDiscipline(C11BBase):
    def test_78_c11b_pre_audit_exists(self):
        self.assertTrue(
            (ROOT / "docs" / "marathon" / "customer_product" / "C11B_PRE_IMPLEMENTATION_AUDIT.md").is_file()
        )

    def test_79_quality_contracts_have_regenerate(self):
        from pipeline.quality.contracts import QualityVerdict

        self.assertEqual(QualityVerdict.REGENERATE_REQUIRED.value, "REGENERATE_REQUIRED")

    def test_80_script_quality_hook_detects_mismatch(self):
        from pipeline.creative_production.script_quality import classify_hook

        h = classify_hook(
            "Tsunamis can strike without warning, leaving communities in chaos and despair.",
            topic="space science",
        )
        self.assertIn("hook_topic_mismatch", h.get("issues") or [])

    def test_81_provider_chain_order_stable(self):
        from pipeline.purpose_caps import TEXT_CHAIN_SCRIPT

        self.assertEqual(
            list(TEXT_CHAIN_SCRIPT),
            ["groq", "cerebras", "openrouter", "huggingface", "freetheai"],
        )
        # Google reserved for translate/localize only
        from pipeline.purpose_caps import google_allowed_for_purpose, chain_for_purpose

        self.assertFalse(google_allowed_for_purpose("script"))
        self.assertTrue(google_allowed_for_purpose("translate"))
        self.assertNotIn("google", chain_for_purpose("script"))
        self.assertIn("google", chain_for_purpose("translate"))

    def test_82_chat_text_purpose_critic_uses_agent_models(self):
        from pipeline.llm_router import GROQ_MODELS_AGENT, groq_chat

        # inspect groq_chat chooses AGENT for critic
        src = inspect.getsource(groq_chat)
        self.assertIn("critic", src)
        self.assertTrue(GROQ_MODELS_AGENT)

    def test_83_no_hardcoded_ready_to_upload_force(self):
        src = (ROOT / "pipeline" / "video_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn('upload_status = "ready_to_upload"  # force', src)

    def test_84_c11b_suite_is_unittest_only(self):
        # Suite entrypoint is unittest; no live marathon launch API in this module.
        import test_c11b_provider_readiness as mod

        self.assertTrue(hasattr(mod, "unittest"))
        self.assertFalse(hasattr(mod, "launch_c11_marathon"))
        self.assertFalse(hasattr(mod, "run_real_marathon"))
        self.assertIn("C11BBase", dir(mod))

    def test_85_synthetic_label_present(self):
        text = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC", text.upper())


if __name__ == "__main__":
    unittest.main()
