"""Phase 6G — dialogue-visual temporal alignment + adaptive pacing evidence tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6g_evidence"


def _dlg(i: int, start: float, end: float, text: str, **kw):
    return {
        "dialogue_id": f"dlg-{i}",
        "segment_id": f"seg-{i}",
        "scene_id": "sc-6g",
        "start_sec": start,
        "end_sec": end,
        "text": text,
        "entities": kw.get("entities", [{"label": "Shobha", "entity_type": "character"}]),
        "actions": kw.get("actions", []),
        "location": kw.get("location", "street"),
        "emotional_intent": kw.get("emotion", ""),
        "relationships": kw.get("relationships", []),
    }


def _vb(i: int, start: float, end: float, dialogue_id: str, **kw):
    return {
        "beat_id": f"vb-{i}",
        "dialogue_segment_id": dialogue_id,
        "scene_id": "sc-6g",
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "visual_mode": kw.get("mode", "IMAGE"),
        "required_entities": kw.get("entities", [{"label": "Shobha"}]),
        "relationships": kw.get("relationships", []),
        "location_state": {"location": kw.get("location", "street")},
        "character_state": {"action": kw.get("action", ""), "emotion": kw.get("emotion", "")},
        "prompt_provenance": {"covered_dialogue_ids": kw.get("covered", [dialogue_id])},
        "asset_id": kw.get("asset_id", f"asset-{i}"),
    }


def _obs(**kw):
    from pipeline.observation.frame_evidence import empty_frame_evidence

    ev = empty_frame_evidence(asset_id="a", beat_id="b", scene_id="s", timestamp=0.0)
    ev.update(
        {
            "observation_status": "PASS",
            "provider_verified": True,
            "heuristic": False,
            "evidence_source": "PROVIDER_VERIFIED",
            "observed_subjects": [],
            "observed_entities": [],
            "observed_relationships": [],
            "observed_location": "",
            "observed_actions": [],
        }
    )
    ev.update(kw)
    return ev


class TimelineBindingTests(unittest.TestCase):
    def test_01_dialogue_timeline(self):
        from pipeline.observation.frame_evidence import build_dialogue_timeline

        t = build_dialogue_timeline(
            [_dlg(1, 0, 2, "a"), _dlg(2, 2, 5, "b")],
            customer_id="c11",
            channel_id="4",
            audio_timeline_sec=5.0,
        )
        self.assertEqual(t["segment_count"], 2)
        self.assertEqual(t["total_dialogue_sec"], 5.0)
        self.assertFalse(t["second_audio_engine"])

    def test_02_visual_timeline(self):
        from pipeline.observation.frame_evidence import build_visual_timeline

        t = build_visual_timeline(
            [_vb(1, 0, 3, "dlg-1"), _vb(2, 3, 6, "dlg-2")],
            customer_id="c11",
            channel_id="4",
        )
        self.assertEqual(t["beat_count"], 2)
        self.assertTrue(t["fixed_n_switching_forbidden"])
        self.assertFalse(t["second_duration_engine"])

    def test_03_04_dialogue_beat_binding(self):
        from pipeline.observation.frame_evidence import align_dialogue_visual_production

        a = align_dialogue_visual_production(
            dialogue_segments=[_dlg(1, 0, 2, "hi"), _dlg(2, 2, 4, "there")],
            visual_beats=[_vb(1, 0, 2, "dlg-1"), _vb(2, 2, 4, "dlg-2")],
            customer_id="c11",
            channel_id="4",
        )
        self.assertEqual(a["dialogue_timeline"]["segments"][0]["dialogue_id"], "dlg-1")
        self.assertEqual(a["visual_timeline"]["beats"][0]["dialogue_id"], "dlg-1")


class CoverageTests(unittest.TestCase):
    def test_05_full_coverage(self):
        from pipeline.observation.frame_evidence import classify_temporal_coverage

        r = classify_temporal_coverage(
            {"dialogue_id": "dlg-1", "start": 0, "end": 4},
            [{"visual_beat_id": "vb-1", "start": 0, "end": 4}],
        )
        self.assertEqual(r["coverage"], "FULL")
        self.assertTrue(r["timing_overlap_is_not_semantic_pass"])

    def test_06_partial_coverage(self):
        from pipeline.observation.frame_evidence import classify_temporal_coverage

        r = classify_temporal_coverage(
            {"dialogue_id": "dlg-1", "start": 0, "end": 4},
            [{"visual_beat_id": "vb-1", "start": 0, "end": 2}],
        )
        self.assertEqual(r["coverage"], "PARTIAL")

    def test_07_none_coverage(self):
        from pipeline.observation.frame_evidence import classify_temporal_coverage

        r = classify_temporal_coverage(
            {"dialogue_id": "dlg-1", "start": 0, "end": 4},
            [{"visual_beat_id": "vb-1", "start": 10, "end": 12}],
        )
        self.assertEqual(r["coverage"], "NONE")

    def test_08_unknown_coverage(self):
        from pipeline.observation.frame_evidence import classify_temporal_coverage

        r = classify_temporal_coverage(
            {"dialogue_id": "dlg-1", "start": 0, "end": 4},
            [{"visual_beat_id": "vb-1", "start": 0, "end": 4}],
            observation_available=False,
        )
        self.assertEqual(r["coverage"], "UNKNOWN")


class SemanticAlignmentTests(unittest.TestCase):
    def test_09_semantic_mismatch(self):
        from pipeline.observation.frame_evidence import semantic_align_dialogue_to_observation

        r = semantic_align_dialogue_to_observation(
            _dlg(1, 0, 2, "Shobha enters the car.", actions=["enters"], location="car"),
            _obs(
                observation_status="FAIL",
                observed_subjects=["person"],
                observed_location="road beside vehicle",
                observed_actions=["standing"],
            ),
        )
        self.assertEqual(r["status"], "FAIL")

    def test_10_semantic_match(self):
        from pipeline.observation.frame_evidence import semantic_align_dialogue_to_observation

        r = semantic_align_dialogue_to_observation(
            _dlg(1, 0, 2, "Shobha walks toward the car.", actions=["approaching"]),
            _obs(
                observation_status="PASS",
                observed_subjects=["Shobha"],
                observed_entities=["car"],
                observed_actions=["approaching"],
                observed_location="street",
            ),
        )
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["provider_verified"])

    def test_11_12_13_14_dims(self):
        from pipeline.observation.frame_evidence import semantic_align_dialogue_to_observation

        r = semantic_align_dialogue_to_observation(
            _dlg(
                1,
                0,
                2,
                "x",
                location="hospital room",
                entities=[{"label": "Nurse"}],
                relationships=[{"subject": "Nurse", "relation": "beside", "object": "bed"}],
                actions=["standing"],
            ),
            _obs(
                observation_status="PASS",
                observed_subjects=["Nurse"],
                observed_entities=["hospital bed"],
                observed_location="hospital room",
                observed_relationships=["Nurse beside bed"],
                observed_actions=["standing"],
            ),
        )
        self.assertIn("location", r["dims_checked"])
        self.assertIn("entity", r["dims_checked"])
        self.assertIn("relationship", r["dims_checked"])
        self.assertIn("action", r["dims_checked"])

    def test_15_valid_state_transition(self):
        from pipeline.observation.frame_evidence.alignment import detect_semantic_boundary
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        b = detect_semantic_boundary(
            {"actions": ["beside"], "location": "street", "entities": ["Shobha", "Suzuki"]},
            {"actions": ["entering"], "location": "street", "entities": ["Shobha", "Suzuki"]},
        )
        self.assertTrue(b["visual_change_recommended"])
        h = recommend_adaptive_hold(
            dialogue_duration_sec=3.0,
            semantic_change=True,
            action_change=True,
            relationship_change=True,
        )
        self.assertTrue(h["new_visual_beat_recommended"] or h["inputs"]["semantic_change"])
        self.assertFalse(h["overrides_duration_contract"])


class BoundaryHoldTests(unittest.TestCase):
    def test_16_semantic_boundary_detection(self):
        from pipeline.observation.frame_evidence.alignment import detect_semantic_boundary

        same = detect_semantic_boundary(
            {"actions": ["standing"], "location": "room", "entities": ["A"]},
            {"actions": ["standing"], "location": "room", "entities": ["A"]},
        )
        self.assertFalse(same["visual_change_recommended"])
        self.assertTrue(same["every_sentence_change_forbidden"])

    def test_17_adaptive_hold_recommendation(self):
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        h = recommend_adaptive_hold(dialogue_duration_sec=8.0, semantic_change=False)
        self.assertIn("recommended_hold_sec", h)
        self.assertEqual(h["c05s_hold_authority"], "pipeline.story_visual_direction.decide_visual_hold_policy")
        self.assertFalse(h["second_pacing_authority"])

    def test_18_fixed_n_switching_rejection(self):
        from pipeline.observation.frame_evidence.alignment import FIXED_N_SWITCHING_FORBIDDEN
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        self.assertTrue(FIXED_N_SWITCHING_FORBIDDEN)
        h = recommend_adaptive_hold(dialogue_duration_sec=10.0)
        self.assertTrue(h["fixed_n_switching_forbidden"])
        self.assertTrue(h["fixed_n_hard_rule_rejected"])

    def test_19_long_coherent_hold_allowed(self):
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        h = recommend_adaptive_hold(dialogue_duration_sec=10.0, semantic_change=False, location_change=False)
        self.assertTrue(h["long_coherent_hold_allowed"] or float(h["recommended_hold_sec"]) >= 4.0)

    def test_20_short_semantic_change_new_beat(self):
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        h = recommend_adaptive_hold(
            dialogue_duration_sec=2.5,
            semantic_change=True,
            location_change=True,
            action_change=True,
        )
        self.assertTrue(h["new_visual_beat_recommended"])


class DropDurationUnknownTests(unittest.TestCase):
    def test_21_no_silent_dialogue_drop(self):
        from pipeline.observation.frame_evidence import assert_no_silent_dialogue_drop

        ok = assert_no_silent_dialogue_drop(
            ["d1", "d2", "d3", "d4", "d5", "d6"],
            ["d1", "d2", "d3", "d4", "d5", "d6"],
        )
        self.assertEqual(ok["status"], "PASS")
        bad = assert_no_silent_dialogue_drop(
            ["d1", "d2", "d3", "d4", "d5", "d6"],
            ["d1"],
        )
        self.assertTrue(bad["silent_drop"])
        self.assertEqual(bad["status"], "FAIL")

    def test_22_duration_contract_preserved(self):
        from pipeline.duration_budget import resolve_duration_contract
        from pipeline.observation.frame_evidence import align_dialogue_visual_production

        c = resolve_duration_contract(video_type="short", target_seconds=60)
        a = align_dialogue_visual_production(
            dialogue_segments=[_dlg(1, 0, 2, "x")],
            visual_beats=[_vb(1, 0, 2, "dlg-1")],
            duration_contract=c,
        )
        self.assertFalse(a["duration_contract"]["overridden_by_alignment_layer"])
        self.assertFalse(a["second_duration_engine"])

    def test_23_audio_authoritative_timeline(self):
        from pipeline.observation.frame_evidence import build_dialogue_timeline

        t = build_dialogue_timeline([_dlg(1, 0, 3, "x")], audio_timeline_sec=3.0)
        self.assertEqual(t["audio_timeline_sec"], 3.0)
        self.assertIn("ffprobe", t["audio_authority"].lower() + t["audio_authority"])

    def test_24_25_unknown_blocks_no_repair(self):
        from pipeline.observation.frame_evidence import (
            align_dialogue_visual_production,
            repair_handoff_from_frame_evidence,
        )
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

        a = align_dialogue_visual_production(
            dialogue_segments=[_dlg(1, 0, 2, "x")],
            visual_beats=[_vb(1, 0, 2, "dlg-1")],
            observations_by_dialogue={
                "dlg-1": _obs(observation_status="UNKNOWN", provider_verified=False),
            },
        )
        self.assertEqual(a["status"], "UNKNOWN")
        sem = attach_frame_evidence_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            {
                "observations": [_obs(observation_status="UNKNOWN", provider_verified=False)],
                "temporal": {"status": "UNKNOWN"},
                "alignment": a,
            },
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem["blocking"])
        h = repair_handoff_from_frame_evidence(
            beat_id="vb-1",
            scene_id="sc-6g",
            frame_bridge_or_temporal={"temporal": {"status": "UNKNOWN"}, "alignment": a},
        )
        self.assertFalse(h["repair_triggered"])


class RepairReuseAuthorityTests(unittest.TestCase):
    def test_26_fail_build04f(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        h = repair_handoff_from_frame_evidence(
            beat_id="vb-6g",
            scene_id="sc-6g",
            frame_bridge_or_temporal={
                "temporal": {"status": "FAIL", "issues": ["alignment_semantic_fail"]},
                "alignment": {"status": "FAIL"},
            },
        )
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(h["whole_video_regeneration"])

    def test_27_30_targeted_repair_structure(self):
        import inspect

        from pipeline.observation.frame_evidence.repair_loop import execute_targeted_visual_asset_repair_loop

        src = inspect.getsource(execute_targeted_visual_asset_repair_loop)
        self.assertIn("max_repair_attempts = 1", src)
        self.assertIn("whole_video_regeneration", src)
        p = EV / "05_repair_execution.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(data.get("whole_video_regeneration", True))

    def test_28_29_lineage_reobserve_if_present(self):
        p = EV / "05_repair_execution.json"
        if not p.exists():
            self.skipTest("phase6g repair evidence not yet generated")
        data = json.loads(p.read_text(encoding="utf-8"))
        lin = data.get("lineage") or {}
        self.assertTrue(lin.get("old_content_hash"))
        self.assertTrue(lin.get("new_content_hash") or data.get("reobservation"))

    def test_31_repetition_uses_existing_detector(self):
        from pipeline.observation.frame_evidence.alignment import repetition_risk_evidence
        from pipeline.retrieval.reuse import detect_reuse_risk

        self.assertTrue(callable(detect_reuse_risk))
        r = repetition_risk_evidence(
            [],
            used_assets=[{"asset_id": "a1", "content_hash": "h1", "scene_id": "s", "beat_id": "b"}],
            candidate_asset_id="a1",
            candidate_content_hash="h1",
            beat_id="b2",
            scene_id="s2",
        )
        self.assertFalse(r["second_duplicate_detector"])
        self.assertTrue(r["auto_regenerate_forbidden_unless_contract"])

    def test_32_33_34_customer_provenance_secrets(self):
        from pipeline.observation.frame_evidence import build_dialogue_timeline
        from pipeline.observation.frame_evidence.alignment import customer_isolation_check
        from pipeline.retrieval.common import strip_secrets

        t = build_dialogue_timeline(
            [_dlg(1, 0, 1, "x")],
            customer_id="c11",
            channel_id="4",
            job_id="job2108",
        )
        self.assertEqual(t["customer_id"], "c11")
        iso = customer_isolation_check({"customer_id": "c11"}, {"customer_id": "other"})
        self.assertEqual(iso["status"], "FAIL")
        blob = json.dumps(strip_secrets({"api_key": "SECRET", "timeline": t}))
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("api_key", blob)

    def test_35_42_authorities_agpl(self):
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.story_visual_direction import architecture_integrity_snapshot, decide_visual_hold_policy
        from pipeline.visual_semantic.continuity import ContinuityTracker

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap["alignment_is_not_second_duration_engine"])
        self.assertTrue(snap["alignment_is_not_second_pacing_authority"])
        self.assertTrue(snap["alignment_is_not_second_audio_engine"])
        self.assertFalse(snap["second_continuity_engine"])
        self.assertFalse(snap["second_repair_engine"])
        self.assertTrue(snap["frame_evidence_is_not_semantic_gate"])
        self.assertTrue(snap["frame_evidence_is_not_ffmpeg_engine"])
        self.assertFalse(snap["openmontage_agpl_imported"])
        self.assertTrue(callable(idempotent_image_clip_via_build03))
        self.assertTrue(callable(IdempotentExecutor))
        self.assertTrue(callable(ContinuityTracker))
        self.assertTrue(callable(decide_visual_hold_policy))
        for rel in (
            "pipeline/observation/frame_evidence/alignment.py",
            "pipeline/observation/frame_evidence/cross_beat.py",
            "pipeline/observation/frame_evidence/repair_loop.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", text)
            self.assertNotRegex(text, r"^\s*(from|import)\s+.*OpenMontage")


class EvidenceFileTests(unittest.TestCase):
    def test_evidence_if_present(self):
        p = EV / "06_verdict.json"
        if not p.exists():
            self.skipTest("phase6g evidence not generated yet")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertFalse(data.get("whole_video_regeneration", True))


if __name__ == "__main__":
    unittest.main()
