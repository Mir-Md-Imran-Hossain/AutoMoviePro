"""Phase 6J — multimodal evidence projection / certification fusion tests."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6j_evidence"


def _vis(**kw):
    base = {
        "observation_status": "PASS",
        "provider_verified": True,
        "heuristic": False,
        "evidence_source": "PROVIDER_VERIFIED",
        "provider": "PROVIDER_FRAME:test",
        "observed_subjects": ["nurse"],
        "observed_entities": ["hospital bed"],
        "observed_location": "hospital room",
        "observed_actions": ["standing"],
        "observed_relationships": ["nurse beside hospital bed"],
    }
    base.update(kw)
    return base


def _aud(**kw):
    base = {
        "status": "PASS",
        "speech": {
            "observation_status": "PASS",
            "status": "PASS",
            "provider_verified": True,
            "provider": "faster-whisper",
            "evidence_source": "LOCAL_ASR",
            "transcript": "She enters the hospital.",
        },
        "transcript_alignments": [{"class": "MATCH"}],
        "coverages": [{"coverage": "FULL"}],
        "content_hash": "audiohash",
    }
    base.update(kw)
    return base


class BeatContractTests(unittest.TestCase):
    def test_01_02_beat_provenance(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        p = project_beat_evidence(
            beat_id="vb-1",
            scene_id="sc-1",
            dialogue_id="dlg-1",
            visual_asset_id="v1",
            audio_asset_id="a1",
            intent={
                "subject": "Nurse",
                "entities": [{"label": "Nurse"}, {"label": "bed"}],
                "relationships": [{"relation": "beside"}],
                "actions": ["standing"],
                "location": "hospital room",
                "emotion": "calm",
                "dialogue": "She stands beside the bed.",
            },
            visual_observation=_vis(),
            audio_observation=_aud(),
            acoustic_observation={"VOICE_IDENTITY_OBSERVATION": "UNKNOWN", "delivery": {"class": "NORMAL"}},
            timing={"planned_start": 0, "planned_end": 2, "visual_coverage": "FULL", "dialogue_coverage": "FULL"},
            continuity={"status": "PASS", "location": "hospital"},
            customer_id="c11",
            channel_id="4",
            job_id="j",
        )
        self.assertEqual(p["beat_id"], "vb-1")
        self.assertTrue(p["provenance"]["HEURISTIC_is_not_PROVIDER_VERIFIED"])
        self.assertTrue(p["never_directly_publishable"])
        self.assertFalse(p["creates_final_gate"])
        self.assertEqual(p["observed_audio"]["voice_identity_observation"], "UNKNOWN")

    def test_03_07_joins(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        p = project_beat_evidence(
            beat_id="vb-1",
            dialogue_id="dlg-1",
            intent={"location": "hospital room", "dialogue": "She enters the hospital.", "relationships": [{"relation": "beside"}]},
            visual_observation=_vis(),
            audio_observation=_aud(),
            continuity={"status": "PASS", "character": "Nurse", "object": "bed", "location": "hospital"},
            timing={"planned_start": 0, "planned_end": 3},
        )
        m = p["certification_matrix"]
        self.assertIn("VISUAL", m)
        self.assertIn("AUDIO", m)
        self.assertIn("DIALOGUE", m)
        self.assertIn("TIMING", m)
        self.assertIn("CONTINUITY", m)
        self.assertEqual(m["CONTINUITY"]["authority"], "pipeline.visual_semantic.continuity.ContinuityTracker")
        self.assertFalse(m["CONTINUITY"]["second_continuity_engine"])

    def test_08_09_entity_relationship(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        p = project_beat_evidence(
            beat_id="vb-1",
            intent={"relationships": [{"relation": "beside"}, {"relation": "inside"}], "entities": ["Nurse", "Suzuki"]},
            visual_observation=_vis(observed_relationships=["Nurse beside Suzuki"]),
        )
        self.assertIn("beside", str(p["intent"]["relationships"]))
        self.assertNotIn("located_at", str(p["intent"]["relationships"]))
        self.assertFalse(p["certification_matrix"]["CROSS_MODAL"].get("relationship_collapsed_to_located_at", False))

    def test_10_12_continuity_dims(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        p = project_beat_evidence(
            beat_id="vb-1",
            continuity={"status": "PASS", "location": "hospital", "character": "Nurse", "object": "Suzuki"},
            intent={"location": "hospital"},
            visual_observation=_vis(),
        )
        self.assertEqual(p["continuity"]["location"], "hospital")
        self.assertEqual(p["continuity"]["character"], "Nurse")
        self.assertEqual(p["continuity"]["object"], "Suzuki")


class AlignmentContradictionTests(unittest.TestCase):
    def test_13_15_alignment_coverage(self):
        from pipeline.multimodal_consistency import project_beat_evidence
        from pipeline.observation.frame_evidence import classify_temporal_coverage

        self.assertEqual(
            classify_temporal_coverage({"dialogue_id": "d", "start": 0, "end": 2}, [{"start": 0, "end": 2, "visual_beat_id": "v"}])[
                "coverage"
            ],
            "FULL",
        )
        p = project_beat_evidence(
            beat_id="vb-1",
            intent={"location": "hospital room", "dialogue": "ok"},
            visual_observation=_vis(),
            audio_observation=_aud(),
            alignment={"status": "PASS"},
        )
        self.assertEqual(p["certification_matrix"]["CROSS_MODAL"]["status"], "PASS")

    def test_16_17_hospital_spacecraft_negative(self):
        from pipeline.multimodal_consistency import project_beat_evidence, fuse_production_evidence

        p = project_beat_evidence(
            beat_id="vb-neg",
            intent={"location": "hospital room", "dialogue": "She enters the hospital."},
            visual_observation=_vis(
                observation_status="FAIL",
                observed_location="spacecraft interior",
                observed_subjects=["astronaut"],
            ),
            audio_observation=_aud(),
        )
        self.assertEqual(p["certification_matrix"]["CROSS_MODAL"]["status"], "FAIL")
        fused = fuse_production_evidence(beats=[p], customer_id="c11")
        self.assertEqual(fused["status"], "FAIL")
        self.assertFalse(fused["never_directly_publishable"] is False)

    def test_18_relationship_contradiction(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        p = project_beat_evidence(
            beat_id="vb-1",
            intent={"relationships": [{"relation": "beside"}], "location": "street"},
            visual_observation=_vis(observation_status="FAIL", provider_verified=True, observed_location="street"),
        )
        self.assertEqual(p["certification_matrix"]["CROSS_MODAL"]["status"], "FAIL")


class UnknownHeuristicTests(unittest.TestCase):
    def test_19_22_unknown_propagation(self):
        from pipeline.multimodal_consistency import (
            attach_evidence_projection_to_semantic_report,
            fuse_production_evidence,
            project_beat_evidence,
            repair_handoff_from_evidence_projection,
        )

        p = project_beat_evidence(
            beat_id="vb-u",
            intent={"location": "hospital room", "dialogue": "hello"},
            visual_observation=_vis(observation_status="UNKNOWN", provider_verified=False),
            audio_observation=_aud(speech={"observation_status": "UNKNOWN", "status": "UNKNOWN", "provider_verified": False}),
            acoustic_observation={"VOICE_IDENTITY_OBSERVATION": "UNKNOWN"},
        )
        self.assertEqual(p["certification_matrix"]["CROSS_MODAL"]["status"], "UNKNOWN")
        self.assertEqual(p["observed_audio"]["voice_identity_observation"], "UNKNOWN")
        fused = fuse_production_evidence(beats=[p])
        self.assertEqual(fused["status"], "UNKNOWN")
        sem = attach_evidence_projection_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            fused,
            mandatory=True,
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem.get("blocking") or sem["overall"] == "UNKNOWN")
        h = repair_handoff_from_evidence_projection(beat_id="vb-u", scene_id="sc", evidence=p)
        self.assertFalse(h["repair_triggered"])

    def test_23_24_heuristic_vs_provider(self):
        from pipeline.multimodal_consistency import project_beat_evidence

        heur = project_beat_evidence(
            beat_id="vb-1",
            visual_observation=_vis(provider_verified=False, heuristic=True, evidence_source="HEURISTIC", observation_status="UNKNOWN"),
        )
        self.assertEqual(heur["observed_visual"]["confidence"], "HEURISTIC")
        prov = project_beat_evidence(beat_id="vb-1", visual_observation=_vis())
        self.assertEqual(prov["observed_visual"]["confidence"], "PROVIDER_VERIFIED")
        self.assertTrue(prov["provenance"]["generation_success_is_not_semantic_pass"])


class PacingRepairAuthorityTests(unittest.TestCase):
    def test_25_26_adaptive_pacing(self):
        from pipeline.multimodal_consistency import project_beat_evidence
        from pipeline.observation.frame_evidence import recommend_adaptive_hold

        p = project_beat_evidence(beat_id="vb-1", timing={"planned_start": 0, "planned_end": 8})
        self.assertTrue(p["fixed_n_switching_forbidden"])
        self.assertTrue(p["adaptive_pacing_reuses_phase6g"])
        h = recommend_adaptive_hold(dialogue_duration_sec=8.0, semantic_change=False)
        self.assertTrue(h["fixed_n_switching_forbidden"])

    def test_27_no_silent_drop(self):
        from pipeline.observation.frame_evidence import assert_no_silent_dialogue_drop

        self.assertEqual(
            assert_no_silent_dialogue_drop(["a", "b", "c"], ["a", "b", "c"])["status"],
            "PASS",
        )
        self.assertTrue(assert_no_silent_dialogue_drop(["a", "b", "c"], ["a"])["silent_drop"])

    def test_28_30_repair(self):
        from pipeline.multimodal_consistency import project_beat_evidence, repair_handoff_from_evidence_projection

        p = project_beat_evidence(
            beat_id="vb-neg",
            scene_id="sc-1",
            intent={"location": "hospital"},
            visual_observation=_vis(observation_status="FAIL", observed_location="spacecraft interior"),
        )
        h = repair_handoff_from_evidence_projection(beat_id="vb-neg", scene_id="sc-1", evidence=p)
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(h["whole_video_regeneration"])
        evp = EV / "05_repair.json"
        if evp.exists():
            data = json.loads(evp.read_text(encoding="utf-8"))
            self.assertFalse(data.get("whole_video_regeneration", True))
            self.assertTrue((data.get("lineage") or {}).get("old_content_hash") or data.get("execution"))

    def test_31_36_authorities_agpl(self):
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.multimodal_consistency import fuse_production_evidence
        from pipeline.quality.publishability import evaluate_publishability
        from pipeline.retrieval.common import strip_secrets
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        self.assertTrue(callable(idempotent_image_clip_via_build03))
        self.assertTrue(callable(evaluate_publishability))
        self.assertTrue(callable(attach_frame_evidence_to_semantic_report))
        snap = architecture_integrity_snapshot()
        self.assertEqual(snap.get("multimodal_authority"), "pipeline.multimodal_consistency")
        self.assertFalse(snap["openmontage_agpl_imported"])
        bad = fuse_production_evidence(
            beats=[{"beat_id": "b", "customer_id": "other", "intent": {}, "visual_observation": _vis()}],
            customer_id="c11",
        )
        self.assertEqual(bad["status"], "FAIL")
        self.assertIn("cross_customer", bad.get("reason", ""))
        self.assertNotIn("SECRET", json.dumps(strip_secrets({"api_key": "SECRET"})))
        text = (ROOT / "pipeline/multimodal_consistency/evidence_projection.py").read_text(encoding="utf-8")
        self.assertNotIn("third_party.OpenMontage", text)
        self.assertNotRegex(text, r"^\s*(from|import)\s+.*OpenMontage")
        self.assertNotIn("multimodal_quality_gate", text)


if __name__ == "__main__":
    unittest.main()
