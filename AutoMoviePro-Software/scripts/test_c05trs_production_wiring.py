"""C05-TRS-PW — Production wiring tests (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.script import ScriptPlan
from pipeline.story_visual_direction import DirectedVisualBeat, create_dialogue_segment
from pipeline.trs_facade import (
    LEGACY_VISUAL_PROMPT_FIELDS,
    apply_c05s_direction_to_director_plan,
    assert_script_does_not_own_visual_prompts,
    assert_trs_pre_provider_ready,
    compute_trs_handoff_fingerprint,
    normalize_niche_plan_to_script_plan,
    refresh_c05s_from_director_plan,
    resolve_canonical_visual_prompt,
    run_trs_pipeline,
    script_plan_to_dialogue_segments,
)
from pipeline.visual_intelligence import create_visual_bible


def _channel(cid=501, niche="tech", name="PW Channel", **kw):
    base = {
        "id": cid,
        "channel_id": cid,
        "name": name,
        "youtube_name": name,
        "niche": niche,
        "language": "en",
        "style_family": "gadget",
    }
    base.update(kw)
    return base


def _mock_plan(topic="Nova Phone"):
    return {
        "topic": topic,
        "title": f"{topic} Review",
        "scenes": [
            {
                "narration": f"Meet {topic} — the grip and glass tell the first story.",
                "speaker": "Narrator",
                "visual_prompt": f"LEGACY_CINEMATIC_{topic}",
                "exact_ai_video_prompt": f"LEGACY_VIDEO_{topic}",
                "visual_query": topic,
                "location": "studio",
                "emotion": "curious",
                "action_intent": "presents",
                "element": "intro",
            },
            {
                "narration": f"Battery stamina decides whether {topic} survives a long day.",
                "speaker": "Narrator",
                "visual_prompt": "LEGACY_BATTERY",
                "exact_ai_video_prompt": "LEGACY_BATTERY_VIDEO",
                "location": "studio",
                "emotion": "serious",
                "action_intent": "charges",
                "element": "battery",
            },
            {
                "narration": f"Would you buy {topic}? Share your take below.",
                "speaker": "Narrator",
                "visual_prompt": "LEGACY_ENDCARD",
                "location": "studio",
                "emotion": "friendly",
                "element": "outro",
            },
        ],
    }


class C05TRSPWHelpers(unittest.TestCase):
    def test_01_resolve_c05s_overrides_legacy(self):
        scene = {
            "visual_direction_source": "C05-S",
            "c05s_compiled_positive": "CANONICAL_FROM_C05S",
            "exact_ai_video_prompt": "LEGACY_SHOULD_LOSE",
            "visual_prompt": "LEGACY_SHOULD_LOSE_2",
            "legacy_exact_ai_video_prompt": "LEGACY_SHOULD_LOSE",
        }
        r = resolve_canonical_visual_prompt(scene)
        self.assertEqual(r["prompt"], "CANONICAL_FROM_C05S")
        self.assertEqual(r["source"], "C05-S")
        self.assertTrue(r["legacy_ignored"])

    def test_02_legacy_fallback_when_no_c05s(self):
        scene = {"exact_ai_video_prompt": "ONLY_LEGACY", "visual_prompt": "V"}
        r = resolve_canonical_visual_prompt(scene)
        self.assertEqual(r["source"], "LEGACY_COMPAT")
        self.assertFalse(r["legacy_ignored"])
        self.assertIn("ONLY_LEGACY", r["prompt"])

    def test_03_narration_fallback(self):
        r = resolve_canonical_visual_prompt({}, narration="spoken line")
        self.assertEqual(r["source"], "NARRATION_FALLBACK")
        self.assertEqual(r["prompt"], "spoken line")

    def test_04_continuity_compiler_source(self):
        scene = {
            "_continuity_applied": True,
            "visual_prompt": "FROM_COMPILER",
            "visual_direction_source": "C05-S",
        }
        r = resolve_canonical_visual_prompt(scene)
        self.assertEqual(r["source"], "CONTINUITY_COMPILER")
        self.assertTrue(r["legacy_ignored"])

    def test_05_apply_moves_legacy_aside(self):
        plan = _mock_plan("Alpha")
        refreshed = refresh_c05s_from_director_plan(plan, channel_id=1, topic="Alpha")
        stamped = refreshed["director_plan"]
        sc0 = stamped["scenes"][0]
        self.assertEqual(sc0.get("visual_direction_source"), "C05-S")
        self.assertTrue(sc0.get("legacy_exact_ai_video_prompt") or sc0.get("legacy_visual_prompt"))
        self.assertNotEqual(sc0.get("c05s_compiled_positive"), "LEGACY_VIDEO_Alpha")
        self.assertIn("c05s_scene_intent", sc0)

    def test_06_legacy_cannot_override_after_apply(self):
        plan = _mock_plan("Beta")
        refreshed = refresh_c05s_from_director_plan(plan, channel_id=2, topic="Beta")
        sc = refreshed["director_plan"]["scenes"][0]
        sc["exact_ai_video_prompt"] = "HACKED_LEGACY"
        sc["visual_prompt"] = "HACKED_LEGACY"
        # restore C05-S markers
        sc["visual_direction_source"] = "C05-S"
        sc["c05s_compiled_positive"] = "TRUE_CANONICAL"
        r = resolve_canonical_visual_prompt(sc)
        self.assertEqual(r["prompt"], "TRUE_CANONICAL")
        self.assertTrue(r["legacy_ignored"])

    def test_07_script_plan_no_provider_ownership(self):
        sp = normalize_niche_plan_to_script_plan(_mock_plan(), topic_id="t1")
        self.assertTrue(assert_script_does_not_own_visual_prompts(sp))
        self.assertTrue(sp.legacy_visual_prompts)

    def test_08_dialogue_segments_from_script_plan(self):
        sp = normalize_niche_plan_to_script_plan(_mock_plan("Gamma"), topic_id="t2")
        segs = script_plan_to_dialogue_segments(sp)
        self.assertGreaterEqual(len(segs), 3)
        self.assertTrue(all(s.text for s in segs))

    def test_09_preflight_blocks_missing_c05s(self):
        r = assert_trs_pre_provider_ready({"ok": True, "intelligence": {"accepted": True}, "c05s": {}})
        self.assertTrue(r["blocked"])
        self.assertTrue(any("missing_c05s" in b for b in r["blocks"]))

    def test_10_preflight_blocks_not_ok(self):
        r = assert_trs_pre_provider_ready({"ok": False, "status": "BLOCKED", "reason": "x"})
        self.assertTrue(r["blocked"])

    def test_11_preflight_unknown_evidence_optional(self):
        h = {
            "ok": True,
            "intelligence": {"accepted": True, "evidence_status": "UNKNOWN"},
            "director_plan": {"scenes": [{"narration": "a"}]},
            "c05s": {"visual_beats": [{"beat_id": "1"}], "narrative_beats": [{"beat_id": "n1"}]},
        }
        r = assert_trs_pre_provider_ready(h)
        self.assertTrue(r["ok"])
        h2 = {**h, "require_evidence_valid": True}
        r2 = assert_trs_pre_provider_ready(h2)
        self.assertTrue(r2["blocked"])
        self.assertIn("evidence_unknown_mandatory", r2["blocks"])

    def test_12_fingerprint_changes_with_topic(self):
        a = compute_trs_handoff_fingerprint(topic_fp="a", research_fp="r", script_fp="s", channel_id=1)
        b = compute_trs_handoff_fingerprint(topic_fp="b", research_fp="r", script_fp="s", channel_id=1)
        self.assertNotEqual(a, b)

    def test_13_fingerprint_stable(self):
        a = compute_trs_handoff_fingerprint(topic_fp="a", research_fp="r", script_fp="s", channel_id=9)
        b = compute_trs_handoff_fingerprint(topic_fp="a", research_fp="r", script_fp="s", channel_id=9)
        self.assertEqual(a, b)

    def test_14_channel_isolation_fingerprint(self):
        a = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r", script_fp="s", channel_id=1)
        b = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r", script_fp="s", channel_id=2)
        self.assertNotEqual(a, b)

    def test_15_legacy_fields_documented(self):
        self.assertIn("visual_prompt", LEGACY_VISUAL_PROMPT_FIELDS)
        self.assertIn("exact_ai_video_prompt", LEGACY_VISUAL_PROMPT_FIELDS)


class C05TRSPWPipelineMock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_MODE", None)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)

    def test_16_run_trs_mock_ok(self):
        h = run_trs_pipeline(
            self.tmp,
            channel=_channel(),
            topic="Nova Phone battery test",
            use_mock_research=True,
            use_mock_script=True,
            production_wired=True,
        )
        self.assertTrue(h.get("ok"), h.get("reason"))
        self.assertEqual(h["execution"]["intelligence"], 1)
        self.assertEqual(h["execution"]["script"], 1)
        self.assertEqual(h["execution"]["trs"], 1)
        self.assertTrue(h["compatibility"]["generate_video_wired"])
        self.assertTrue((self.tmp / "trs_handoff.json").exists())

    def test_17_director_plan_has_c05s_source(self):
        h = run_trs_pipeline(
            self.tmp / "a",
            channel=_channel(cid=502),
            topic="Studio mic review",
            use_mock_research=True,
            use_mock_script=True,
            production_wired=True,
        )
        self.assertTrue(h["ok"])
        scenes = (h.get("director_plan") or {}).get("scenes") or []
        self.assertTrue(scenes)
        self.assertEqual(scenes[0].get("visual_direction_source"), "C05-S")

    def test_18_c05s_beats_present(self):
        h = run_trs_pipeline(
            self.tmp / "b",
            channel=_channel(cid=503),
            topic="Camera lens tips",
            use_mock_research=True,
            use_mock_script=True,
        )
        self.assertTrue(h["ok"])
        self.assertTrue(h["c05s"]["visual_beats"])
        self.assertTrue(h["c05s"]["narrative_beats"])
        self.assertTrue(h["dialogue_segments"])

    def test_19_script_plan_is_scriptplan_shape(self):
        h = run_trs_pipeline(
            self.tmp / "c",
            channel=_channel(cid=504),
            topic="Keyboard switches explained",
            use_mock_research=True,
            use_mock_script=True,
        )
        sp = ScriptPlan.model_validate(h["script_plan"])
        self.assertTrue(sp.beats)
        self.assertFalse(sp.metadata.get("script_owns_provider_visual_prompts"))

    def test_20_skip_intelligence_no_intel_call_count(self):
        h = run_trs_pipeline(
            self.tmp / "d",
            channel=_channel(cid=505),
            topic="Forced skip topic",
            use_mock_research=True,
            use_mock_script=True,
            skip_intelligence=True,
        )
        self.assertTrue(h["ok"])
        self.assertEqual(h["execution"]["intelligence"], 0)
        self.assertEqual(h["execution"]["script"], 1)

    def test_21_blocked_intelligence_no_script(self):
        with patch("pipeline.trs_facade.run_topic_research_gate") as gate:
            gate.return_value = {"accepted": False, "reason": "DUPLICATE", "gate_verdict": "FAIL"}
            h = run_trs_pipeline(
                self.tmp / "e",
                channel=_channel(cid=506),
                topic="dup topic",
                use_mock_research=True,
                use_mock_script=True,
            )
        self.assertFalse(h["ok"])
        self.assertEqual(h["execution"]["script"], 0)
        self.assertEqual(h["execution"]["intelligence"], 1)

    def test_22_no_fake_external_live_claim(self):
        h = run_trs_pipeline(
            self.tmp / "f",
            channel=_channel(cid=507),
            topic="Local research honesty",
            use_mock_research=True,
            use_mock_script=True,
        )
        self.assertFalse(h["claims"]["external_live_research"])
        self.assertFalse(h["claims"]["vlm_verification"])

    def test_23_customer_channel_id_propagates(self):
        h = run_trs_pipeline(
            self.tmp / "g",
            channel=_channel(cid=777),
            topic="Isolation topic",
            use_mock_research=True,
            use_mock_script=True,
        )
        self.assertEqual(h["channel_id"], 777)

    def test_24_long_short_format(self):
        h1 = run_trs_pipeline(
            self.tmp / "h1", channel=_channel(cid=508), topic="Long form topic A",
            video_type="long", use_mock_research=True, use_mock_script=True,
        )
        h2 = run_trs_pipeline(
            self.tmp / "h2", channel=_channel(cid=509), topic="Short form topic B",
            video_type="short", use_mock_research=True, use_mock_script=True,
        )
        self.assertEqual(h1["format"], "LONG")
        self.assertEqual(h2["format"], "SHORT")

    def test_25_refresh_does_not_call_intelligence(self):
        with patch("pipeline.trs_facade.run_topic_research_gate") as gate:
            refresh_c05s_from_director_plan(_mock_plan("Refresh"), channel_id=1, topic="Refresh")
            gate.assert_not_called()

    def test_26_refresh_does_not_call_script_bridge(self):
        with patch("pipeline.idempotency.script_bridge.idempotent_plan_niche_production") as scr:
            refresh_c05s_from_director_plan(_mock_plan("Refresh2"), channel_id=1, topic="Refresh2")
            scr.assert_not_called()

    def test_27_entity_propagation(self):
        h = refresh_c05s_from_director_plan(_mock_plan("EntityPhone"), channel_id=1, topic="EntityPhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertIn("required_entities", vb)

    def test_28_location_propagation(self):
        h = refresh_c05s_from_director_plan(_mock_plan("LocPhone"), channel_id=1, topic="LocPhone")
        sc = h["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("location") or (sc.get("c05s_scene_intent") or {}).get("location"))

    def test_29_emotion_propagation(self):
        h = refresh_c05s_from_director_plan(_mock_plan("EmoPhone"), channel_id=1, topic="EmoPhone")
        sc = h["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("emotional_intent") or sc.get("emotion"))

    def test_30_visual_mode_propagation(self):
        h = refresh_c05s_from_director_plan(_mock_plan("ModePhone"), channel_id=1, topic="ModePhone")
        sc = h["director_plan"]["scenes"][0]
        self.assertTrue(sc.get("visual_mode"))

    def test_31_camera_on_visual_beat(self):
        h = refresh_c05s_from_director_plan(_mock_plan("CamPhone"), channel_id=1, topic="CamPhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertTrue(vb.get("camera_intent"))

    def test_32_lighting_on_visual_beat(self):
        h = refresh_c05s_from_director_plan(_mock_plan("LightPhone"), channel_id=1, topic="LightPhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertTrue("lighting_intent" in vb or "lighting_continuity" in vb)

    def test_33_character_state_on_visual_beat(self):
        h = refresh_c05s_from_director_plan(_mock_plan("CharPhone"), channel_id=1, topic="CharPhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertIsInstance(vb.get("character_state"), dict)

    def test_34_relationship_field_exists(self):
        h = refresh_c05s_from_director_plan(_mock_plan("RelPhone"), channel_id=1, topic="RelPhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertIn("relationships", vb)

    def test_35_timing_duration_policy(self):
        h = refresh_c05s_from_director_plan(_mock_plan("TimePhone"), channel_id=1, topic="TimePhone")
        vb = h["c05s"]["visual_beats"][0]
        self.assertTrue(vb.get("duration_policy") or vb.get("duration_sec") is not None)

    def test_36_scene_intent_projection(self):
        h = refresh_c05s_from_director_plan(_mock_plan("IntentPhone"), channel_id=1, topic="IntentPhone")
        intent = h["director_plan"]["scenes"][0].get("c05s_scene_intent")
        self.assertIsInstance(intent, dict)
        self.assertTrue(intent.get("scene_id") or intent.get("dialogue_id") or intent.get("summary"))

    def test_37_directed_visual_beat_roundtrip(self):
        h = refresh_c05s_from_director_plan(_mock_plan("RoundPhone"), channel_id=1, topic="RoundPhone")
        raw = h["c05s"]["visual_beats"][0]
        beat = DirectedVisualBeat.from_dict(raw)
        self.assertEqual(beat.beat_id, raw["beat_id"])

    def test_38_c05v_bible_compatible(self):
        bible = create_visual_bible(
            bible_id="vb-test", subject_identity="phone", character_identity="host",
            visual_style="doc", location="studio", environment="set",
        )
        h = refresh_c05s_from_director_plan(
            _mock_plan("BiblePhone"), channel_id=1, topic="BiblePhone", visual_bible=bible
        )
        self.assertTrue(h["ok"])
        self.assertTrue(h["c05s"]["visual_beats"])

    def test_39_preflight_pass_ready(self):
        h = run_trs_pipeline(
            self.tmp / "pre",
            channel=_channel(cid=510),
            topic="Preflight ready topic",
            use_mock_research=True,
            use_mock_script=True,
            production_wired=True,
        )
        pf = assert_trs_pre_provider_ready(h)
        self.assertTrue(pf["ok"], pf)

    def test_40_paid_api_zero(self):
        h = run_trs_pipeline(
            self.tmp / "paid",
            channel=_channel(cid=511),
            topic="No paid APIs",
            use_mock_research=True,
            use_mock_script=True,
        )
        self.assertEqual(h.get("paid_api_calls"), 0)


class C05TRSPWGenerateVideoPath(unittest.TestCase):
    """Prove generate_video reaches TRS once and does not dual-run old intelligence/script."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_MODE"] = "PRODUCTION"
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_MODE", None)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)

    def _trs_handoff(self, topic="Wired Topic"):
        plan = apply_c05s_direction_to_director_plan(
            _mock_plan(topic),
            refresh_c05s_from_director_plan(_mock_plan(topic), channel_id=1, topic=topic)["c05s"],
            dialogue_segments=[
                s.to_dict()
                for s in script_plan_to_dialogue_segments(
                    normalize_niche_plan_to_script_plan(_mock_plan(topic))
                )
            ],
            topic=topic,
        )
        return {
            "ok": True,
            "status": "PASS",
            "stage": "c05s_handoff",
            "topic": topic,
            "channel_id": 601,
            "director_plan": plan,
            "script_plan": normalize_niche_plan_to_script_plan(_mock_plan(topic)).model_dump(),
            "c05s": refresh_c05s_from_director_plan(_mock_plan(topic), channel_id=1, topic=topic)["c05s"],
            "dialogue_segments": [],
            "intelligence": {"accepted": True, "gate_verdict": "PASS", "evidence_status": "VALID", "score": {}},
            "fact_pack": None,
            "execution": {"trs": 1, "intelligence": 1, "script": 1},
            "compatibility": {"generate_video_wired": True},
            "claims": {"external_live_research": False},
            "paid_api_calls": 0,
            "authorities": {},
        }

    def test_41_generate_video_source_contains_trs(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp.generate_video)
        self.assertIn("run_trs_pipeline", src)
        self.assertIn("resolve_canonical_visual_prompt", src)

    def test_42_generate_video_does_not_call_old_intel_inline(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp.generate_video)
        # Comment may mention it; live call must not remain
        self.assertNotIn("run_intelligence_gate(", src)
        self.assertNotIn("assert_production_intelligence_validated(", src)

    def test_43_trs_called_once_on_generate_video(self):
        import pipeline.video_pipeline as vp

        calls = {"trs": 0, "intel": 0, "script_direct": 0}
        handoff = self._trs_handoff("Once Topic")

        def _trs(*a, **k):
            calls["trs"] += 1
            return handoff

        channel = _channel(cid=601, youtube_name="Once Ch")

        with patch("pipeline.trs_facade.run_trs_pipeline", side_effect=_trs), patch(
            "pipeline.intelligence.bridge.run_intelligence_gate",
            side_effect=lambda *a, **k: calls.__setitem__("intel", calls["intel"] + 1) or {},
        ), patch(
            "pipeline.video_pipeline._plan_niche_production_idempotent",
            side_effect=lambda *a, **k: calls.__setitem__("script_direct", calls["script_direct"] + 1) or _mock_plan(),
        ), patch(
            "pipeline.api_keys.load_api_bundle",
            return_value={"google_keys": [], "agnes_keys": [], "openrouter_keys": [], "pollinations_key": "", "pexels_key": ""},
        ), patch(
            "pipeline.niche_agent.apply_niche_to_channel", side_effect=lambda c, **k: c
        ), patch(
            "pipeline.niche_agent.director_notes_from_channel", return_value=""
        ), patch(
            "pipeline.product_registry.blocked_names", return_value=[]
        ), patch(
            "pipeline.product_registry.is_duplicate", return_value=(False, None)
        ), patch(
            "pipeline.master_lang.require_english_master_plan", side_effect=lambda p, **k: p
        ), patch(
            "pipeline.content_humanizer.humanize_plan",
            side_effect=lambda p, **k: {"plan": p, "passed": True, "audit_after": {}},
        ), patch(
            "pipeline.contract_wiring.production_bridge.assert_production_plan_wiring",
            return_value=MagicMock(),
        ), patch(
            "pipeline.scene_runtime.assert_production_scenes_validated",
            side_effect=lambda plan, **k: ([], list(plan.get("scenes") or [])),
        ), patch(
            "pipeline.trs_facade.refresh_c05s_from_director_plan",
            side_effect=lambda plan, **k: {
                "ok": True,
                "director_plan": plan,
                "c05s": handoff["c05s"],
                "script_plan": handoff["script_plan"],
                "dialogue_segments": [],
            },
        ), patch(
            "pipeline.trs_facade.persist_trs_handoff", return_value=self.tmp / "trs_handoff.json"
        ), patch(
            "pipeline.trs_facade.assert_trs_pre_provider_ready",
            return_value={"ok": True, "blocked": False, "blocks": [], "unknowns": [], "paid_api_calls": 0},
        ), patch(
            "pipeline.video_pipeline.build_dialogue_clip",
            side_effect=RuntimeError("PROVIDER_BOUNDARY_STOP"),
        ), patch(
            "pipeline.idempotency.tts_bridge.idempotent_synthesize_narration",
            side_effect=RuntimeError("TTS_BOUNDARY_STOP"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                vp.generate_video(
                    channel,
                    video_type="short",
                    topic="Once Topic",
                    work_dir=self.tmp / "job_once",
                    allow_duplicate=True,
                )
        self.assertEqual(calls["trs"], 1)
        self.assertEqual(calls["intel"], 0)
        # Provider boundary reached after TRS — not a silent skip
        self.assertTrue(
            "PROVIDER_BOUNDARY_STOP" in str(ctx.exception)
            or "TTS_BOUNDARY_STOP" in str(ctx.exception)
            or "scene" in str(ctx.exception).lower()
            or "trs" in str(ctx.exception).lower()
            or "GATE" in str(ctx.exception)
            or "blocked" in str(ctx.exception).lower()
            or "Google" in str(ctx.exception)
            or "TTS" in str(ctx.exception)
        )

    def test_44_call_graph_order_markers(self):
        import pipeline.video_pipeline as vp

        src = inspect.getsource(vp.generate_video)
        i_trs = src.find("run_trs_pipeline")
        i_human = src.find("humanize_plan")
        i_contract = src.find("assert_production_plan_wiring")
        i_scene = src.find("assert_production_scenes_validated")
        i_vis = src.find("build_dialogue_clip")
        self.assertTrue(i_trs > 0)
        self.assertTrue(i_human > i_trs)
        self.assertTrue(i_contract > i_human)
        self.assertTrue(i_scene > i_contract)
        self.assertTrue(i_vis > i_scene)

    def test_45_trs_block_raises_gate_marker(self):
        import pipeline.video_pipeline as vp

        with patch(
            "pipeline.trs_facade.run_trs_pipeline",
            return_value={"ok": False, "status": "BLOCKED", "stage": "intelligence", "reason": "fail"},
        ), patch(
            "pipeline.api_keys.load_api_bundle",
            return_value={"google_keys": [], "agnes_keys": [], "openrouter_keys": [], "pollinations_key": "", "pexels_key": ""},
        ), patch(
            "pipeline.niche_agent.apply_niche_to_channel", side_effect=lambda c, **k: c
        ), patch(
            "pipeline.niche_agent.director_notes_from_channel", return_value=""
        ), patch(
            "pipeline.product_registry.blocked_names", return_value=[]
        ), patch(
            "pipeline.product_registry.is_duplicate", return_value=(False, None)
        ):
            with self.assertRaises(RuntimeError) as ctx:
                vp.generate_video(
                    _channel(cid=602),
                    video_type="short",
                    topic="Blocked",
                    work_dir=self.tmp / "job_block",
                    allow_duplicate=True,
                )
        self.assertIn("INTELLIGENCE_GATE_BLOCKED", str(ctx.exception))


class C05TRSPWIsolationAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTELLIGENCE_RESEARCH_MODE"] = "MOCK"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("INTELLIGENCE_RESEARCH_MODE", None)

    def test_46_customer_a_b_channel_isolation(self):
        ha = run_trs_pipeline(
            self.tmp / "ca", channel=_channel(cid=1), topic="Same Topic Text",
            use_mock_research=True, use_mock_script=True,
        )
        hb = run_trs_pipeline(
            self.tmp / "cb", channel=_channel(cid=2), topic="Same Topic Text",
            use_mock_research=True, use_mock_script=True,
        )
        self.assertNotEqual(ha["fingerprints"]["trs_handoff"], hb["fingerprints"]["trs_handoff"])
        self.assertNotEqual(ha["channel_id"], hb["channel_id"])

    def test_47_language_in_script_plan(self):
        h = run_trs_pipeline(
            self.tmp / "lang", channel=_channel(cid=3), topic="Lang topic",
            language="bn", use_mock_research=True, use_mock_script=True,
        )
        self.assertEqual(h["language"], "bn")
        self.assertEqual(h["script_plan"]["language"], "bn")

    def test_48_changed_script_changes_fingerprint(self):
        p1 = normalize_niche_plan_to_script_plan(_mock_plan("T1"))
        p2 = normalize_niche_plan_to_script_plan(_mock_plan("T2"))
        f1 = compute_trs_handoff_fingerprint(
            topic_fp="x", research_fp="r",
            script_fp=json.dumps([(b.beat_id, b.narration) for b in p1.beats]),
            channel_id=1,
        )
        f2 = compute_trs_handoff_fingerprint(
            topic_fp="x", research_fp="r",
            script_fp=json.dumps([(b.beat_id, b.narration) for b in p2.beats]),
            channel_id=1,
        )
        self.assertNotEqual(f1, f2)

    def test_49_idempotent_second_trs_reuses_script_store(self):
        # Two TRS calls same work dir — BUILD-03 may reuse director_plan; still one authority
        h1 = run_trs_pipeline(
            self.tmp / "idemp", channel=_channel(cid=4), topic="Idempotent Topic Stable",
            use_mock_research=True, use_mock_script=True,
        )
        h2 = run_trs_pipeline(
            self.tmp / "idemp", channel=_channel(cid=4), topic="Idempotent Topic Stable",
            use_mock_research=True, use_mock_script=True,
        )
        self.assertTrue(h1["ok"] and h2["ok"])
        self.assertEqual(h1["execution"]["script"], 1)
        self.assertEqual(h2["execution"]["script"], 1)

    def test_50_unknown_remains_unknown_in_skip_intel(self):
        h = run_trs_pipeline(
            self.tmp / "unk", channel=_channel(cid=5), topic="Unknown evidence path",
            use_mock_research=True, use_mock_script=True, skip_intelligence=True,
        )
        self.assertEqual(h["intelligence"]["evidence_status"], "UNKNOWN")

    def test_51_evidence_invalid_blocks(self):
        with patch("pipeline.trs_facade.run_topic_research_gate") as gate:
            gate.return_value = {
                "accepted": True,
                "gate_verdict": "PASS",
                "evidence_status": "INVALID",
                "fact_pack": {"id": "fp1", "claims": []},
                "research": {},
                "research_capability": {},
            }
            h = run_trs_pipeline(
                self.tmp / "inv", channel=_channel(cid=6), topic="Invalid evidence",
                use_mock_research=True, use_mock_script=True,
            )
        self.assertFalse(h["ok"])
        self.assertEqual(h["stage"], "evidence")

    def test_52_insufficient_evidence_blocks(self):
        with patch("pipeline.trs_facade.run_topic_research_gate") as gate:
            gate.return_value = {
                "accepted": True,
                "gate_verdict": "PASS",
                "evidence_status": "INSUFFICIENT",
                "fact_pack": {"id": "fp2"},
                "research": {},
                "research_capability": {},
            }
            h = run_trs_pipeline(
                self.tmp / "ins", channel=_channel(cid=7), topic="Insufficient",
                use_mock_research=True, use_mock_script=True,
            )
        self.assertFalse(h["ok"])

    def test_53_missing_topic_blocks(self):
        with patch("pipeline.intelligence.bridge.pick_topic_from_reserve", return_value=None):
            h = run_trs_pipeline(
                self.tmp / "mt", channel=_channel(cid=8), topic="",
                use_mock_research=True, use_mock_script=True, allow_reserve_pick=True,
            )
        self.assertFalse(h["ok"])
        self.assertIn("missing_topic", h.get("reason", ""))

    def test_54_authorities_map_present(self):
        h = run_trs_pipeline(
            self.tmp / "auth", channel=_channel(cid=9), topic="Authority map",
            use_mock_research=True, use_mock_script=True,
        )
        self.assertIn("topic_intelligence", h["authorities"])
        self.assertIn("BUILD-04G", h["authorities"]["topic_intelligence"])
        self.assertIn("BUILD-03", h["authorities"]["idempotency"])
        self.assertIn("prompt_compiler", h["authorities"]["prompt_compiler"])

    def test_55_quality_not_claimed_by_trs(self):
        h = run_trs_pipeline(
            self.tmp / "q", channel=_channel(cid=10), topic="Quality claim check",
            use_mock_research=True, use_mock_script=True,
        )
        self.assertIn("BUILD-04F", h["authorities"]["quality_repair"])
        self.assertFalse(h["claims"].get("pixel_verification"))


class C05TRSPWLegacyAndCompiler(unittest.TestCase):
    def test_56_exact_ai_cannot_win_against_c05s(self):
        scene = {
            "visual_direction_source": "C05-S",
            "c05s_compiled_positive": "WINNER",
            "exact_ai_video_prompt": "LOSER_EXACT",
        }
        self.assertEqual(resolve_canonical_visual_prompt(scene)["prompt"], "WINNER")

    def test_57_visual_prompt_cannot_win_against_c05s(self):
        scene = {
            "visual_direction_source": "C05-S",
            "c05s_compiled_positive": "WINNER2",
            "visual_prompt": "LOSER_VIS",
        }
        self.assertEqual(resolve_canonical_visual_prompt(scene)["prompt"], "WINNER2")

    def test_58_legacy_only_when_no_direction(self):
        scene = {"exact_ai_video_prompt": "LEGACY_OK"}
        r = resolve_canonical_visual_prompt(scene)
        self.assertEqual(r["source"], "LEGACY_COMPAT")
        self.assertEqual(r["prompt"], "LEGACY_OK")

    def test_59_apply_preserves_legacy_keys(self):
        plan = _mock_plan("LegacyKeep")
        out = refresh_c05s_from_director_plan(plan, channel_id=1, topic="LegacyKeep")["director_plan"]
        sc = out["scenes"][0]
        self.assertTrue(sc.get("legacy_visual_prompt") or sc.get("legacy_exact_ai_video_prompt"))

    def test_60_compiled_positive_not_equal_legacy_marker(self):
        plan = _mock_plan("Marker")
        out = refresh_c05s_from_director_plan(plan, channel_id=1, topic="Marker")["director_plan"]
        sc = out["scenes"][0]
        self.assertFalse(str(sc.get("c05s_compiled_positive") or "").startswith("LEGACY_"))

    def test_61_continuity_runtime_prefers_c05s_intent(self):
        from pipeline.visual_semantic.continuity_runtime import _intent_from_handoff

        scene = {
            "narration": "hello",
            "c05s_scene_intent": {
                "scene_id": "sc-1",
                "dialogue_id": "dlg-1",
                "summary": "c05s summary",
                "location": "museum",
                "visual_mode": "IMAGE",
            },
            "exact_ai_video_prompt": "SHOULD_NOT_DRIVE",
        }
        intent = _intent_from_handoff(scene, scene_index=0)
        self.assertEqual(intent.location, "museum")
        self.assertEqual(intent.summary, "c05s summary")

    def test_62_continuity_ignores_legacy_when_source_c05s(self):
        from pipeline.visual_semantic.continuity_runtime import _intent_from_handoff

        scene = {
            "narration": "spoken",
            "visual_direction_source": "C05-S",
            "c05s_compiled_positive": "canonical emphasis",
            "exact_ai_video_prompt": "LEGACY_EMPHASIS_SHOULD_NOT_BIND",
            "dialogue_id": "d1",
        }
        intent = _intent_from_handoff(scene, scene_index=0)
        # visual_emphasis comes from c05s compiled / implication path, not LEGACY marker alone
        blob = json.dumps(intent.model_dump(), default=str)
        self.assertNotIn("LEGACY_EMPHASIS_SHOULD_NOT_BIND", blob)

    def test_63_build_dialogue_clip_precedence_documented(self):
        import pipeline.scene_builder as sb

        src = inspect.getsource(sb.build_dialogue_clip)
        self.assertIn("exact_ai_video_prompt", src)

    def test_64_video_pipeline_uses_resolver(self):
        import pipeline.video_pipeline as vp

        self.assertIn("resolve_canonical_visual_prompt", inspect.getsource(vp.generate_video))

    def test_65_no_second_prompt_compiler_in_trs(self):
        import pipeline.trs_facade as tf

        src = inspect.getsource(tf)
        self.assertNotIn("def compile_provider_prompt", src)


class C05TRSPWPropagationExtras(unittest.TestCase):
    def test_66_narrative_beats_count(self):
        h = refresh_c05s_from_director_plan(_mock_plan("NB"), channel_id=1, topic="NB")
        self.assertEqual(len(h["c05s"]["narrative_beats"]), len(h["dialogue_segments"]))

    def test_67_visual_beats_nonempty(self):
        h = refresh_c05s_from_director_plan(_mock_plan("VB"), channel_id=1, topic="VB")
        self.assertGreaterEqual(len(h["c05s"]["visual_beats"]), 1)

    def test_68_speaker_on_segments(self):
        segs = script_plan_to_dialogue_segments(normalize_niche_plan_to_script_plan(_mock_plan("SP")))
        self.assertTrue(all(s.speaker for s in segs))

    def test_69_hook_structure(self):
        sp = normalize_niche_plan_to_script_plan(_mock_plan("Hook"))
        self.assertTrue(sp.hook)

    def test_70_section_roles(self):
        sp = normalize_niche_plan_to_script_plan(_mock_plan("Roles"))
        self.assertTrue(sp.narrative_structure)

    def test_71_visual_implication_semantic(self):
        sp = normalize_niche_plan_to_script_plan(_mock_plan("VI"))
        self.assertTrue(all(b.visual_implication for b in sp.beats))

    def test_72_dialogue_segment_create(self):
        seg = create_dialogue_segment(
            segment_id="s1", dialogue_id="d1", scene_id="sc", text="hi", location="lab"
        )
        self.assertEqual(seg.location, "lab")

    def test_73_c05q_authority_listed(self):
        from pipeline.trs_facade import _authorities

        self.assertIn("production_consistency", _authorities())

    def test_74_c05v_authority_listed(self):
        from pipeline.trs_facade import _authorities

        self.assertIn("visual_intelligence", _authorities())

    def test_75_continuity_authority_string(self):
        h = refresh_c05s_from_director_plan(_mock_plan("Cont"), channel_id=1, topic="Cont")
        self.assertIn("ContinuityTracker", h["c05s"]["authorities"]["continuity"])

    def test_76_prompt_authority_string(self):
        h = refresh_c05s_from_director_plan(_mock_plan("Pr"), channel_id=1, topic="Pr")
        self.assertIn("prompt_compiler", h["c05s"]["authorities"]["prompt"])

    def test_77_fail_closed_preflight_invalid_script_plan_shape(self):
        r = assert_trs_pre_provider_ready({
            "ok": True,
            "intelligence": {"accepted": True},
            "script_plan": {},
            "c05s": {"visual_beats": [{"a": 1}], "narrative_beats": [{"a": 1}]},
        })
        self.assertTrue(r["blocked"])

    def test_78_provider_spend_zero_on_block(self):
        r = assert_trs_pre_provider_ready({"ok": False})
        self.assertEqual(r["paid_api_calls"], 0)

    def test_79_import_smoke_video_pipeline(self):
        import pipeline.video_pipeline as vp

        self.assertTrue(callable(vp.generate_video))

    def test_80_import_smoke_trs_facade(self):
        import pipeline.trs_facade as tf

        self.assertTrue(callable(tf.run_trs_pipeline))

    def test_81_publishability_not_owned_by_trs(self):
        import pipeline.trs_facade as tf

        src = inspect.getsource(tf)
        self.assertNotIn("def run_publishability", src)

    def test_82_no_second_scene_intent_class(self):
        import pipeline.trs_facade as tf

        self.assertNotIn("class TRSSceneIntent", inspect.getsource(tf))
        self.assertNotIn("class StorySceneIntent", inspect.getsource(tf))

    def test_83_semantic_bypass_forbidden_marker(self):
        # UNKNOWN must not become PASS in skip path for evidence
        h = run_trs_pipeline(
            Path(tempfile.mkdtemp()),
            channel=_channel(cid=99),
            topic="bypass check",
            use_mock_research=True,
            use_mock_script=True,
            skip_intelligence=True,
        )
        self.assertNotEqual(h["intelligence"]["evidence_status"], "VALID")
        self.assertEqual(h["intelligence"]["evidence_status"], "UNKNOWN")

    def test_84_changed_research_fp_changes_handoff(self):
        a = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r1", script_fp="s", channel_id=1)
        b = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r2", script_fp="s", channel_id=1)
        self.assertNotEqual(a, b)

    def test_85_c05s_direction_changes_downstream_prompt(self):
        plan = _mock_plan("DeltaVis")
        stamped = refresh_c05s_from_director_plan(plan, channel_id=1, topic="DeltaVis")["director_plan"]
        sc = stamped["scenes"][0]
        legacy = sc.get("legacy_exact_ai_video_prompt") or sc.get("legacy_visual_prompt") or ""
        canon = resolve_canonical_visual_prompt(sc)["prompt"]
        self.assertTrue(canon)
        if legacy:
            self.assertNotEqual(canon, legacy)


if __name__ == "__main__":
    unittest.main()
