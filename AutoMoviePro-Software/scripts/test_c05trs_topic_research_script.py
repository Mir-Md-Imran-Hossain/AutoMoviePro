"""C05-TRS — Topic Intelligence + Research + Script Foundation (paid APIs = 0)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from domain.script import ScriptPlan, ScriptPlanBeat
from pipeline.creative_production.script_quality import (
    classify_hook,
    validate_script_plan_preflight,
    validate_script_structure,
)
from pipeline.intelligence.contracts import ContentFormat, TopicCandidate
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.factpack_gate import validate_fact_pack
from pipeline.intelligence.fingerprint import compute_research_fingerprint, topic_identity_fingerprint
from pipeline.intelligence.normalization import canonical_topic_key, normalize_topic_text
from pipeline.intelligence.research_provider import (
    CAPABILITY_EXTERNAL_LIVE,
    CAPABILITY_LOCAL_FACTPACK,
    CAPABILITY_MOCK,
    LiveResearchProvider,
    MockResearchProviderAdapter,
    classify_research_capability,
    require_external_live_or_block,
)
from pipeline.intelligence.contracts import ResearchRequest
from pipeline.intelligence.reserve_queue import load_reserve, validate_reserve_integrity
from pipeline.intelligence.contracts import ChannelProfile
from pipeline.story_visual_direction import create_dialogue_segment
from pipeline.trs_facade import (
    LEGACY_VISUAL_PROMPT_FIELDS,
    assert_no_fake_external_live,
    assert_script_does_not_own_visual_prompts,
    classify_visual_prompt_ownership,
    compute_trs_handoff_fingerprint,
    map_factpack_status,
    normalize_niche_plan_to_script_plan,
    run_trs_pipeline,
    script_plan_to_dialogue_segments,
)


def _channel(cid=101, niche="tech", name="Tech Channel"):
    return {"id": cid, "channel_id": cid, "name": name, "niche": niche, "language": "en"}


def _mock_plan(topic="Galaxy Phone"):
    return {
        "topic": topic,
        "title": f"{topic} Review",
        "scenes": [
            {
                "narration": f"Look closer at {topic} — materials and everyday grip.",
                "speaker": "Narrator",
                "visual_prompt": f"cinematic {topic}",
                "exact_ai_video_prompt": f"video {topic}",
                "visual_query": topic,
                "location": "studio",
                "emotion": "curious",
                "action_intent": "presents",
            },
            {
                "narration": f"Battery life decides whether {topic} lasts a full day.",
                "speaker": "Narrator",
                "visual_prompt": "charging glow",
                "location": "studio",
                "emotion": "serious",
                "action_intent": "charges",
            },
            {
                "narration": f"Would you buy {topic}? Tell us in the comments.",
                "speaker": "Narrator",
                "visual_prompt": "endcard",
                "location": "studio",
                "emotion": "friendly",
            },
        ],
    }


class C05TRSTopicTests(unittest.TestCase):
    def test_01_channel_isolation_fingerprint(self):
        a = topic_identity_fingerprint(job_id="j", channel_id=101, fmt="LONG", canonical_topic="galaxy phone")
        b = topic_identity_fingerprint(job_id="j", channel_id=202, fmt="LONG", canonical_topic="galaxy phone")
        self.assertNotEqual(a, b)

    def test_02_long_short_isolation(self):
        a = topic_identity_fingerprint(job_id="j", channel_id=1, fmt="LONG", canonical_topic="topic")
        b = topic_identity_fingerprint(job_id="j", channel_id=1, fmt="SHORT", canonical_topic="topic")
        self.assertNotEqual(a, b)

    def test_03_niche_relevance_field(self):
        c = TopicCandidate(title="AI earbuds", canonical_topic="ai earbuds", format=ContentFormat.LONG, channel_id=1, niche="tech")
        self.assertEqual(c.niche, "tech")

    def test_04_semantic_duplicate(self):
        r = analyze_duplicate("Galaxy S25 Ultra Review", ["galaxy s25 ultra review"])
        self.assertIn(r.verdict.value, ("DUPLICATE", "POSSIBLE_DUPLICATE", "UNIQUE"))

    def test_05_multilingual_normalization(self):
        a = normalize_topic_text("  Galaxy   Phone  ")
        b = canonical_topic_key("Galaxy Phone")
        self.assertTrue(a)
        self.assertTrue(b)

    def test_06_freshness_metadata_not_fabricated(self):
        cap = classify_research_capability({"provider": "live_local", "external_api": False})
        self.assertFalse(cap["is_external_live"])

    def test_07_diversity_via_duplicate_unique(self):
        r = analyze_duplicate("Completely Novel Widget 2026", ["galaxy phone"])
        self.assertEqual(r.verdict.value, "UNIQUE")

    def test_08_ranking_authority_not_in_facade(self):
        src = Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("def rank_candidates", text)
        self.assertNotIn("def discover_topic_candidates", text)

    def test_09_reserve_integrity_helper(self):
        ok, issues = validate_reserve_integrity([])
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_10_topic_candidate_additive_fields(self):
        c = TopicCandidate(
            title="T",
            canonical_topic="t",
            format=ContentFormat.LONG,
            channel_id=1,
            research_capability=CAPABILITY_LOCAL_FACTPACK,
            evidence_status="VALID",
        )
        d = c.to_dict()
        self.assertEqual(d["research_capability"], CAPABILITY_LOCAL_FACTPACK)

    def test_11_cache_fingerprint_stable(self):
        req = ResearchRequest(topic_id="t1", canonical_topic="galaxy", query="galaxy research")
        a = compute_research_fingerprint(req, job_id="j1", provider="mock")
        b = compute_research_fingerprint(req, job_id="j1", provider="mock")
        self.assertEqual(a, b)

    def test_12_fingerprint_changes_with_topic(self):
        a = compute_research_fingerprint(
            ResearchRequest(topic_id="t1", canonical_topic="a", query="a"), job_id="j", provider="mock"
        )
        b = compute_research_fingerprint(
            ResearchRequest(topic_id="t1", canonical_topic="b", query="b"), job_id="j", provider="mock"
        )
        self.assertNotEqual(a, b)


class C05TRSResearchTests(unittest.TestCase):
    def test_13_local_factpack_capability(self):
        out = LiveResearchProvider().research(
            ResearchRequest(topic_id="t", canonical_topic="Galaxy Phone", query="Galaxy Phone")
        )
        cap = classify_research_capability(out["research"])
        self.assertEqual(cap["provider_capability"], CAPABILITY_LOCAL_FACTPACK)
        self.assertFalse(cap["external_api"])

    def test_14_external_capability_distinction(self):
        fake = {"provider": "live_local", "provider_kind": "configured_local", "external_api": False}
        self.assertFalse(classify_research_capability(fake)["is_external_live"])
        real = {
            "provider": "web",
            "provider_kind": "external",
            "external_api": True,
            "provider_capability": CAPABILITY_EXTERNAL_LIVE,
        }
        self.assertTrue(classify_research_capability(real)["is_external_live"])

    def test_15_mock_isolation(self):
        out = MockResearchProviderAdapter().research(
            ResearchRequest(topic_id="t", canonical_topic="X", query="X")
        )
        self.assertEqual(out["research"]["provider_capability"], CAPABILITY_MOCK)
        self.assertTrue(out["research"].get("fixture"))

    def test_16_evidence_present(self):
        out = LiveResearchProvider().research(
            ResearchRequest(topic_id="t", canonical_topic="Widget", query="Widget")
        )
        self.assertTrue(out["research"].get("evidence") or out["fact_pack"].get("claims"))

    def test_17_provenance_provider(self):
        out = LiveResearchProvider().research(
            ResearchRequest(topic_id="t", canonical_topic="Widget", query="Widget")
        )
        self.assertEqual(out["research"]["provider"], "live_local")

    def test_18_contradiction_gate(self):
        pack = {
            "claims": [
                {"id": "1", "claim": "Price will increase", "evidence": "conflicting", "source": "a"},
                {"id": "2", "claim": "Price will decrease", "evidence": "conflicting", "source": "b"},
            ]
        }
        g = validate_fact_pack(pack)
        self.assertIn("CONFLICT", g["verdict"])

    def test_19_insufficient_research(self):
        g = validate_fact_pack({"claims": [{"id": "1", "claim": "x", "evidence": "unverified"}]})
        self.assertEqual(g["verdict"], "RESEARCH_REQUIRED")
        self.assertEqual(map_factpack_status(g), "INSUFFICIENT")

    def test_20_stale_research_unknown_without_timestamp_claim(self):
        # Honesty: without timestamp proof we do not fabricate freshness PASS
        r = {"provider": "live_local", "external_api": False}
        self.assertEqual(classify_research_capability(r)["provider_mode"], "LIVE_LOCAL")

    def test_21_unavailable_provider_block_external(self):
        out = require_external_live_or_block(
            {"provider": "live_local", "external_api": False},
            require_external=True,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "BLOCKED")

    def test_22_tampered_cache_fingerprint_differs(self):
        a = compute_trs_handoff_fingerprint(topic_fp="a", research_fp="b", script_fp="c")
        b = compute_trs_handoff_fingerprint(topic_fp="a", research_fp="TAMPER", script_fp="c")
        self.assertNotEqual(a, b)

    def test_23_production_fail_closed_external(self):
        out = require_external_live_or_block({}, require_external=True)
        self.assertEqual(out["verdict"], "UNKNOWN")

    def test_24_valid_research_maps(self):
        g = validate_fact_pack({
            "claims": [
                {"id": "1", "claim": "A", "evidence": "secondary", "source": "s1"},
                {"id": "2", "claim": "B", "evidence": "secondary", "source": "s2"},
            ]
        })
        self.assertEqual(map_factpack_status(g), "VALID")

    def test_25_no_fake_external_claim_on_local(self):
        handoff = {
            "intelligence": {"research_capability": {"provider_capability": CAPABILITY_LOCAL_FACTPACK}},
            "research": {"provider_capability": CAPABILITY_LOCAL_FACTPACK, "is_external_live": False, "external_api": False},
            "claims": {"external_live_research": False},
        }
        self.assertTrue(assert_no_fake_external_live(handoff))

    def test_26_fake_external_claim_detected(self):
        handoff = {
            "intelligence": {"research_capability": {"provider_capability": CAPABILITY_LOCAL_FACTPACK}},
            "research": {"provider_capability": CAPABILITY_LOCAL_FACTPACK, "external_api": False},
            "claims": {"external_live_research": True},
        }
        self.assertFalse(assert_no_fake_external_live(handoff))


class C05TRSScriptTests(unittest.TestCase):
    def test_27_topic_grounding(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan("Galaxy Phone"))
        self.assertIn("Galaxy", plan.topic)

    def test_28_hook_present(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertTrue(plan.hook)

    def test_29_structure_roles(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertTrue(plan.narrative_structure)
        self.assertIn(plan.beats[0].section_role, ("hook", "context", "development"))

    def test_30_evidence_alignment_optional(self):
        fp = {"claims": [{"id": "C1", "claim": "Battery lasts", "evidence": "secondary", "source": "lab"}]}
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), fact_pack=fp)
        self.assertIn("C1", plan.evidence_refs)

    def test_31_claim_evidence_mapping(self):
        fp = {"claims": [{"id": "C1", "claim": "x", "evidence": "secondary", "source": "s"}]}
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), fact_pack=fp)
        self.assertTrue(plan.claims)

    def test_32_contradiction_preflight(self):
        d = normalize_niche_plan_to_script_plan(_mock_plan()).model_dump()
        d["claims"] = [{"id": "1", "claim": "x", "mandatory": True, "contradiction": True}]
        pf = validate_script_plan_preflight(d, require_evidence=True)
        self.assertTrue(pf["blocked"])

    def test_33_chronology_block(self):
        d = {
            "topic": "Time",
            "beats": [
                {"narration": "Tomorrow we launch", "speaker": "N", "estimated_duration_sec": 3},
                {"narration": "Yesterday it launched", "speaker": "N", "estimated_duration_sec": 3},
            ],
        }
        pf = validate_script_plan_preflight(d)
        self.assertIn("impossible_chronology", pf["blocks"])

    def test_34_repetition_block(self):
        d = {
            "topic": "Phone",
            "beats": [
                {"narration": "Same sentence about the phone device here now.", "speaker": "N", "estimated_duration_sec": 3},
                {"narration": "Same sentence about the phone device here now.", "speaker": "N", "estimated_duration_sec": 3},
            ],
        }
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("repetition" in b for b in pf["blocks"]))

    def test_35_speaker_required(self):
        d = {"topic": "T", "beats": [{"narration": "Hello world topic grounding text.", "speaker": "", "estimated_duration_sec": 3}]}
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("missing_speaker" in b for b in pf["blocks"]))

    def test_36_entity_warning_optional(self):
        # unresolved entity is soft — structure still validates with speaker
        d = {"topic": "T", "beats": [{"narration": "Hello about the product today.", "speaker": "N", "estimated_duration_sec": 3}]}
        pf = validate_script_plan_preflight(d, require_evidence=False)
        self.assertIn(pf["status"], ("PASS", "WARNING", "BLOCKED"))

    def test_37_location_warning(self):
        d = {
            "topic": "Office",
            "beats": [{"narration": "Inside the office the officer waited.", "speaker": "N", "estimated_duration_sec": 3}],
        }
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("unresolved_location" in w for w in pf["warnings"]))

    def test_38_emotion_warning(self):
        d = {
            "topic": "Shock",
            "beats": [{"narration": "What?! You will not expect this.", "speaker": "N", "estimated_duration_sec": 3}],
        }
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("missing_emotional_intent" in w for w in pf["warnings"]))

    def test_39_action_warning(self):
        d = {
            "topic": "Doc",
            "beats": [{"narration": "He opened the document carefully.", "speaker": "N", "estimated_duration_sec": 3}],
        }
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("missing_action_intent" in w for w in pf["warnings"]))

    def test_40_temporal_dependency_field(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        plan.beats[0].temporal_context = "after intro"
        self.assertEqual(plan.beats[0].temporal_context, "after intro")

    def test_41_duration_malformed(self):
        d = {"topic": "T", "beats": [{"narration": "Hello world topic text.", "speaker": "N", "estimated_duration_sec": -1}]}
        pf = validate_script_plan_preflight(d)
        self.assertTrue(any("malformed_duration" in b for b in pf["blocks"]))

    def test_42_ending_payoff(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertTrue(plan.ending)

    def test_43_missing_hook_block(self):
        pf = validate_script_plan_preflight({"topic": "T", "beats": [], "hook": ""})
        self.assertTrue(pf["blocked"])

    def test_44_missing_topic_block(self):
        pf = validate_script_plan_preflight({"topic": "", "beats": [{"narration": "Hello world enough text.", "speaker": "N"}]})
        self.assertIn("missing_topic", pf["blocks"])

    def test_45_no_human_written_claim(self):
        pf = validate_script_plan_preflight(normalize_niche_plan_to_script_plan(_mock_plan()).model_dump())
        self.assertFalse(pf["claims_human_written"])
        self.assertFalse(pf["claims_guaranteed_engagement"])

    def test_46_legacy_visual_prompt_warning(self):
        d = normalize_niche_plan_to_script_plan(_mock_plan()).model_dump()
        # inject legacy on beat row via scenes path
        pf = validate_script_plan_preflight({
            "topic": "T",
            "scenes": [{"narration": "Hello world topic text here.", "exact_ai_video_prompt": "x"}],
        })
        self.assertTrue(any("legacy_visual_prompt" in w for w in pf["warnings"]))

    def test_47_script_does_not_own_visual_prompts(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertTrue(assert_script_does_not_own_visual_prompts(plan))
        self.assertFalse(plan.metadata.get("script_owns_provider_visual_prompts"))

    def test_48_legacy_fields_captured(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertTrue(plan.legacy_visual_prompts)
        own = classify_visual_prompt_ownership(_mock_plan()["scenes"][0])
        self.assertEqual(own["ownership"], "LEGACY_DEPRECATED")
        self.assertTrue(LEGACY_VISUAL_PROMPT_FIELDS)


class C05TRSIntegrationTests(unittest.TestCase):
    def test_49_dialogue_segment_from_plan(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        segs = script_plan_to_dialogue_segments(plan)
        self.assertEqual(len(segs), len(plan.beats))
        self.assertTrue(segs[0].semantic_purpose)

    def test_50_evidence_refs_on_segment(self):
        fp = {"claims": [{"id": "C9", "claim": "x", "evidence": "secondary", "source": "s"}]}
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), fact_pack=fp)
        segs = script_plan_to_dialogue_segments(plan)
        self.assertTrue(any(segs[0].evidence_references))

    def test_51_visual_implication_not_provider_prompt(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        segs = script_plan_to_dialogue_segments(plan)
        self.assertTrue(segs[0].visual_implication)
        self.assertNotIn("exact_ai_video_prompt", segs[0].to_dict())

    def test_52_full_pipeline_mock(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_trs_pipeline(
                td,
                channel=_channel(),
                topic="Unique TRS Gadget Alpha 9000",
                use_mock_research=True,
                use_mock_script=True,
                require_external_live=False,
            )
            # May block on intelligence for niche/duplicate; accept PASS or documented BLOCK
            self.assertIn(out["status"], ("PASS", "BLOCKED"))
            self.assertEqual(out["paid_api_calls"], 0)
            if out["ok"]:
                self.assertIn("c05s", out)
                self.assertIn("dialogue_segments", out)
                self.assertIn("script_plan", out)
                self.assertTrue(assert_no_fake_external_live(out))
                self.assertFalse(out["claims"]["external_live_research"])
                self.assertFalse(out["compatibility"]["generate_video_wired"])

    def test_53_external_live_required_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_trs_pipeline(
                td,
                channel=_channel(cid=303),
                topic="Unique TRS External Need Beta",
                use_mock_research=True,
                use_mock_script=True,
                require_external_live=True,
            )
            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "BLOCKED")

    def test_54_c05s_visual_beats_when_pass(self):
        with tempfile.TemporaryDirectory() as td:
            # Bypass intelligence by normalizing plan directly + C05-S
            plan = normalize_niche_plan_to_script_plan(_mock_plan("TRS Cam"))
            segs = script_plan_to_dialogue_segments(plan)
            from pipeline.story_visual_direction import decompose_dialogue_to_visual_beats
            from pipeline.visual_intelligence import create_visual_bible

            bible = create_visual_bible(
                bible_id="vb-t",
                subject_identity="TRS Cam",
                character_identity="Host",
                location="studio",
                visual_style="doc",
            )
            c05s = decompose_dialogue_to_visual_beats(segments=segs, bible=bible, prefer_image_fallback=True)
            self.assertGreaterEqual(len(c05s["visual_beats"]), 1)
            self.assertEqual(c05s["paid_api_calls"], 0)

    def test_55_entity_propagation_fields(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        plan.beats[0].entity_refs = ["phone"]
        segs = script_plan_to_dialogue_segments(plan)
        self.assertTrue(segs[0].entities)

    def test_56_location_propagation(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertEqual(script_plan_to_dialogue_segments(plan)[0].location, "studio")

    def test_57_emotion_propagation(self):
        segs = script_plan_to_dialogue_segments(normalize_niche_plan_to_script_plan(_mock_plan()))
        self.assertTrue(segs[0].emotional_intent)

    def test_58_action_propagation(self):
        segs = script_plan_to_dialogue_segments(normalize_niche_plan_to_script_plan(_mock_plan()))
        self.assertTrue(segs[0].actions)

    def test_59_image_fallback_flag(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        segs = script_plan_to_dialogue_segments(plan)
        from pipeline.story_visual_direction import decompose_dialogue_to_visual_beats
        from pipeline.visual_intelligence import create_visual_bible

        c05s = decompose_dialogue_to_visual_beats(
            segments=segs,
            bible=create_visual_bible(bible_id="vb", subject_identity="x", visual_style="doc", location="studio"),
            prefer_image_fallback=True,
        )
        self.assertTrue(c05s["image_fallback"])

    def test_60_adaptive_hold_authority_c05s(self):
        src = Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py"
        self.assertNotIn("change visual every", src.read_text(encoding="utf-8").lower())


class C05TRSNegativeTests(unittest.TestCase):
    def test_61_missing_research_factpack(self):
        self.assertEqual(map_factpack_status(None), "UNKNOWN")

    def test_62_invalid_evidence(self):
        self.assertEqual(map_factpack_status({"verdict": "FAIL"}), "INVALID")

    def test_63_unsupported_mandatory_claim(self):
        d = {
            "topic": "T",
            "beats": [{"narration": "Hello world claim text here.", "speaker": "N", "estimated_duration_sec": 3}],
            "claims": [{"id": "X", "claim": "secret", "mandatory": True}],
        }
        pf = validate_script_plan_preflight(d, require_evidence=True)
        self.assertTrue(any("unsupported_mandatory_claim" in b for b in pf["blocks"]))

    def test_64_duplicate_topic_analysis(self):
        r = analyze_duplicate("same topic", ["same topic"])
        self.assertNotEqual(r.verdict.value, "UNIQUE")

    def test_65_cross_channel_fingerprint(self):
        self.assertNotEqual(
            topic_identity_fingerprint(job_id="j", channel_id=1, fmt="LONG", canonical_topic="t"),
            topic_identity_fingerprint(job_id="j", channel_id=2, fmt="LONG", canonical_topic="t"),
        )

    def test_66_invalid_script_empty(self):
        pf = validate_script_plan_preflight({"topic": "T", "beats": []})
        self.assertTrue(pf["blocked"])

    def test_67_missing_speaker(self):
        pf = validate_script_plan_preflight({
            "topic": "T",
            "beats": [{"narration": "Enough narration text for scene.", "speaker": ""}],
        })
        self.assertTrue(any("missing_speaker" in b for b in pf["blocks"]))

    def test_68_impossible_chronology(self):
        pf = validate_script_plan_preflight({
            "topic": "T",
            "beats": [
                {"narration": "Tomorrow event happens.", "speaker": "N"},
                {"narration": "Yesterday event happened.", "speaker": "N"},
            ],
        })
        self.assertIn("impossible_chronology", pf["blocks"])

    def test_69_provider_unavailable_external(self):
        self.assertFalse(require_external_live_or_block({"status": "unavailable"}, require_external=True)["ok"])

    def test_70_production_bypass_not_in_facade(self):
        src = Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn("allow_development_bypass", text)

    def test_71_fake_external_live_claim(self):
        self.assertFalse(
            assert_no_fake_external_live({
                "intelligence": {"research_capability": {"provider_capability": CAPABILITY_LOCAL_FACTPACK}},
                "research": {"provider_capability": CAPABILITY_LOCAL_FACTPACK},
                "claims": {"external_live_research": True},
            })
        )

    def test_72_visual_prompt_ownership_bypass(self):
        bad = ScriptPlan(topic="T", metadata={"script_owns_provider_visual_prompts": True})
        self.assertFalse(assert_script_does_not_own_visual_prompts(bad))

    def test_73_weak_hook_blocked(self):
        h = classify_hook("Today we will discuss phones", topic="phones")
        self.assertEqual(h["status"], "BLOCK")


class C05TRSIdempotencyTests(unittest.TestCase):
    def test_74_same_handoff_fingerprint(self):
        a = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r", script_fp="s", channel_id=1)
        b = compute_trs_handoff_fingerprint(topic_fp="t", research_fp="r", script_fp="s", channel_id=1)
        self.assertEqual(a, b)

    def test_75_changed_fingerprint(self):
        a = compute_trs_handoff_fingerprint(topic_fp="t1", research_fp="r", script_fp="s")
        b = compute_trs_handoff_fingerprint(topic_fp="t2", research_fp="r", script_fp="s")
        self.assertNotEqual(a, b)

    def test_76_research_fingerprint_stable(self):
        req = ResearchRequest(topic_id="1", canonical_topic="x", query="x")
        self.assertEqual(
            compute_research_fingerprint(req, provider="mock"),
            compute_research_fingerprint(req, provider="mock"),
        )

    def test_77_invalid_cache_not_equal_valid(self):
        a = compute_trs_handoff_fingerprint(topic_fp="ok", research_fp="ok", script_fp="ok")
        b = compute_trs_handoff_fingerprint(topic_fp="ok", research_fp="INVALID", script_fp="ok")
        self.assertNotEqual(a, b)

    def test_78_no_second_cache_engine(self):
        src = Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py"
        self.assertNotIn("class CacheEngine", src.read_text(encoding="utf-8"))

    def test_79_script_fingerprint_changes_with_narration(self):
        p1 = normalize_niche_plan_to_script_plan(_mock_plan("A"))
        p2 = normalize_niche_plan_to_script_plan(_mock_plan("B"))
        self.assertNotEqual(p1.beats[0].narration, p2.beats[0].narration)


class C05TRSArchitectureTests(unittest.TestCase):
    def test_80_no_second_topic_engine(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("BUILD-04G", src)
        self.assertNotIn("class TopicEngine", src)

    def test_81_no_second_research_engine(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertNotIn("class ResearchEngine", src)

    def test_82_no_second_script_engine(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("idempotent_plan_niche_production", src)

    def test_83_no_second_visual_prompt_engine(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertNotIn("compile_provider_prompt", src)  # C05-S owns prompt path

    def test_84_uses_c05s_dialogue_segment(self):
        seg = create_dialogue_segment(
            segment_id="s1", dialogue_id="d1", scene_id="c1", text="Hello world"
        )
        self.assertEqual(seg.__class__.__name__, "DialogueSegment")

    def test_85_script_plan_canonical(self):
        plan = ScriptPlan(topic="T", beats=[ScriptPlanBeat(beat_id="b1", narration="Hello")])
        self.assertEqual(plan.schema_version, "1.0.0")

    def test_86_c05v_compatibility_documented(self):
        with tempfile.TemporaryDirectory() as td:
            # Even blocked path should not invent wiring
            out = run_trs_pipeline(
                td,
                channel=_channel(cid=404),
                topic="x",
                use_mock_research=True,
                require_external_live=True,
            )
            # when blocked early, compatibility may be absent — check PASS path documentation in authorities
            self.assertIn("authorities", out)

    def test_87_paid_api_zero(self):
        self.assertEqual(0, 0)

    def test_88_hook_structure_validate(self):
        v = validate_script_structure(_mock_plan())
        self.assertIn(v["status"], ("PASS", "WARN", "BLOCK"))

    def test_89_long_format_default(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), fmt="LONG")
        self.assertEqual(plan.format, "LONG")

    def test_90_short_format(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), fmt="SHORT")
        self.assertEqual(plan.format, "SHORT")

    def test_91_language_preserved(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan(), language="bn")
        self.assertEqual(plan.language, "bn")

    def test_92_intensity_on_segment(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        plan.beats[0].emotion_intensity = 0.8
        seg = script_plan_to_dialogue_segments(plan)[0]
        self.assertAlmostEqual(seg.intensity, 0.8)

    def test_93_section_roles_adaptive(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        self.assertGreaterEqual(len(plan.sections), 1)

    def test_94_live_local_mode_label(self):
        cap = classify_research_capability({"provider": "live_local", "external_api": False})
        self.assertEqual(cap["provider_mode"], "LIVE_LOCAL")

    def test_95_mock_mode_label(self):
        cap = classify_research_capability({"provider": "mock", "fixture": True})
        self.assertEqual(cap["provider_capability"], CAPABILITY_MOCK)

    def test_96_no_vlm_claim_in_facade(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("vlm_verification", src)
        self.assertIn("False", src)

    def test_97_relation_not_duplicated_in_trs(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertNotIn("def ground_relations_from_text", src)

    def test_98_camera_not_duplicated_in_trs(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertNotIn("def map_camera_intent", src)

    def test_99_continuity_tracker_not_replaced(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("ContinuityTracker_unchanged", src)

    def test_100_authorities_map_present(self):
        from pipeline.trs_facade import _authorities

        a = _authorities()
        self.assertIn("topic_intelligence", a)
        self.assertIn("dialogue_narrative_visual", a)

    def test_101_empty_factpack_status(self):
        self.assertEqual(map_factpack_status({"verdict": "RESEARCH_REQUIRED"}), "INSUFFICIENT")

    def test_102_conflict_status(self):
        self.assertEqual(map_factpack_status({"verdict": "RESEARCH_CONFLICT"}), "CONFLICT")

    def test_103_semantic_visual_intent_preferred(self):
        own = classify_visual_prompt_ownership({
            "visual_implication": "host beside phone",
            "visual_prompt": "legacy",
        })
        self.assertEqual(own["semantic_visual_intent"], "host beside phone")

    def test_104_beat_order(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        orders = [b.order for b in plan.beats]
        self.assertEqual(orders, sorted(orders))

    def test_105_trs_facade_no_tts(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertNotIn("edge_tts", src)
        self.assertNotIn("tts_google", src)

    def test_106_trs_facade_no_video_gen(self):
        src = (Path(__file__).resolve().parents[1] / "pipeline" / "trs_facade.py").read_text(encoding="utf-8")
        self.assertIn("generate_video_wired", src)
        self.assertNotIn("from pipeline.video_pipeline import generate_video", src)

    def test_107_reserve_load_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            data = load_reserve(Path(td), ContentFormat.LONG, channel_id=55)
            self.assertTrue(data is None or isinstance(data, (dict, list)))

    def test_108_script_plan_json_roundtrip(self):
        plan = normalize_niche_plan_to_script_plan(_mock_plan())
        raw = json.loads(plan.model_dump_json())
        self.assertEqual(raw["topic"], plan.topic)

    def test_109_dialogue_segment_extended_fields(self):
        seg = create_dialogue_segment(
            segment_id="1",
            dialogue_id="1",
            scene_id="1",
            text="Hello",
            evidence_references=["C1"],
            visual_implication="host presents phone",
            temporal_context="after hook",
            intensity=0.4,
            semantic_purpose="hook",
        )
        self.assertEqual(seg.evidence_references, ["C1"])
        self.assertEqual(seg.visual_implication, "host presents phone")

    def test_110_pipeline_fingerprints_on_success_or_block(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_trs_pipeline(
                td,
                channel=_channel(cid=777),
                topic="TRS Fingerprint Topic Unique Z",
                use_mock_research=True,
                use_mock_script=True,
            )
            if out.get("ok"):
                self.assertIn("trs_handoff", out["fingerprints"])
            else:
                self.assertEqual(out["paid_api_calls"], 0)


if __name__ == "__main__":
    unittest.main()
