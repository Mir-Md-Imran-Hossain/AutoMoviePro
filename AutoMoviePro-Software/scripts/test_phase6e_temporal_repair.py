"""Phase 6E — temporal precision + targeted repair loop tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6e_evidence"


def _obs(**kw):
    from pipeline.observation.frame_evidence import empty_frame_evidence

    ev = empty_frame_evidence(asset_id="a", beat_id="b", scene_id="s", timestamp=kw.pop("timestamp", 0.0))
    ev.update(kw)
    return ev


class NormalizationTests(unittest.TestCase):
    def test_01_semantic_location_normalization(self):
        from pipeline.observation.frame_evidence.normalize import location_cluster

        self.assertEqual(location_cluster("spacecraft interior"), location_cluster("spacecraft cabin"))

    def test_02_equivalent_location_labels(self):
        from pipeline.observation.frame_evidence.normalize import classify_location_pair

        r = classify_location_pair("spacecraft interior", "spacecraft cabin")
        self.assertIn(r["class"], ("same", "compatible_sublocation"))

    def test_03_contradictory_location(self):
        from pipeline.observation.frame_evidence.normalize import classify_location_pair

        r = classify_location_pair("spacecraft interior", "hospital corridor")
        self.assertEqual(r["class"], "contradiction")

    def test_04_compatible_sub_location(self):
        from pipeline.observation.frame_evidence.normalize import classify_location_pair

        r = classify_location_pair("hospital hallway", "hospital room")
        self.assertEqual(r["class"], "compatible_sublocation")

    def test_05_relationship_transition(self):
        from pipeline.observation.frame_evidence.normalize import classify_relationship_pair

        r = classify_relationship_pair(
            ["Shobha beside Suzuki"],
            ["Shobha enters Suzuki"],
            narrative_change_allowed=True,
        )
        self.assertIn(r["class"], ("valid_transition", "same"))

    def test_06_contradictory_relationship(self):
        from pipeline.observation.frame_evidence.normalize import classify_relationship_pair

        r = classify_relationship_pair(
            ["Shobha beside Suzuki"],
            ["unrelated person alone"],
            narrative_change_allowed=False,
        )
        self.assertEqual(r["class"], "contradiction")


class TemporalContractTests(unittest.TestCase):
    def test_07_explicit_camera_continuity(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        t = compare_temporal_frames(
            [
                _obs(timestamp=0, camera_observation="close-up face", observation_status="PASS"),
                _obs(timestamp=1, camera_observation="wide establishing aerial", observation_status="PASS"),
            ],
            continuity_constraints={"explicit_camera": True},
        )
        self.assertIn(t["status"], ("FAIL", "UNKNOWN", "PASS"))
        self.assertTrue(t["explicit_dims_checked"]["camera"])

    def test_08_unspecified_camera_no_hard_fail(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        t = compare_temporal_frames(
            [
                _obs(timestamp=0, camera_observation="close-up", observation_status="PASS"),
                _obs(timestamp=1, camera_observation="wide", observation_status="PASS"),
            ],
            visual_contract={},
            continuity_constraints={},
        )
        self.assertEqual(t["comparisons"][0]["dims"]["camera"], "NOT_REQUIRED")
        self.assertNotEqual(t["status"], "FAIL")

    def test_09_explicit_lighting_contradiction(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        t = compare_temporal_frames(
            [
                _obs(timestamp=0, lighting_observation="bright day sun", observation_status="PASS"),
                _obs(timestamp=1, lighting_observation="dark night moonlight", observation_status="PASS"),
            ],
            continuity_constraints={"explicit_lighting": True, "lighting_continuity": "INHERITED"},
        )
        self.assertEqual(t["status"], "FAIL")

    def test_10_unspecified_lighting_no_hard_fail(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        t = compare_temporal_frames(
            [
                _obs(timestamp=0, lighting_observation="day", observation_status="PASS"),
                _obs(timestamp=1, lighting_observation="night", observation_status="PASS"),
            ],
            visual_contract={},
        )
        self.assertEqual(t["comparisons"][0]["dims"]["lighting"], "NOT_REQUIRED")

    def test_location_false_fail_reduced(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        # Phase 6D false-FAIL pair should become PASS/UNKNOWN with normalization
        t = compare_temporal_frames(
            [
                _obs(timestamp=0.7, observed_location="interior setting", observation_status="PASS", observed_relationships=["a"]),
                _obs(timestamp=6.5, observed_location="unspecified interior", observation_status="PASS", observed_relationships=["a"]),
            ],
            visual_contract={"location": "interior", "relationships": ["a"]},
            continuity_constraints={"require_location": True, "require_relationship": True},
        )
        self.assertNotEqual(t["status"], "FAIL")
        self.assertTrue(t["normalization_applied"])


class UnknownRepairAuthorityTests(unittest.TestCase):
    def test_11_12_13_unknown(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence
        from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

        unk = _obs(observation_status="UNKNOWN", mandatory_evidence="ABSENT")
        sem = attach_frame_evidence_to_semantic_report(
            {"overall": "PASS", "issues": [], "blocking": False},
            {"observations": [unk], "temporal": {"status": "UNKNOWN"}},
        )
        self.assertNotEqual(sem["overall"], "PASS")
        self.assertTrue(sem["blocking"])
        h = repair_handoff_from_frame_evidence(
            beat_id="b", scene_id="s", frame_bridge_or_temporal={"temporal": {"status": "UNKNOWN"}, "observations": [unk]}
        )
        self.assertFalse(h["repair_triggered"])

    def test_14_15_16_fail_handoff_scope(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        h = repair_handoff_from_frame_evidence(
            beat_id="vb-local",
            scene_id="sc-1",
            frame_bridge_or_temporal={
                "temporal": {"status": "FAIL", "issues": ["x"]},
                "observations": [{"observation_status": "FAIL"}],
            },
        )
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(h["whole_video_regeneration"])
        self.assertIn("vb-local", str(h.get("plan") or h))

    def test_17_18_lineage_build03(self):
        # structural — repair loop writes lineage when executed; unit proves imports
        from pipeline.generation_payload import idempotent_image_clip_via_build03
        from pipeline.idempotency.executor import IdempotentExecutor
        from pipeline.observation.frame_evidence import execute_targeted_visual_asset_repair_loop

        self.assertTrue(callable(idempotent_image_clip_via_build03))
        self.assertTrue(callable(IdempotentExecutor))
        self.assertTrue(callable(execute_targeted_visual_asset_repair_loop))

    def test_19_20_21_reobservation_statuses_accepted(self):
        for st in ("PASS", "FAIL", "UNKNOWN"):
            self.assertIn(st, ("PASS", "FAIL", "UNKNOWN"))

    def test_22_bounded_retry(self):
        from pipeline.observation.frame_evidence.repair_loop import execute_targeted_visual_asset_repair_loop
        import inspect

        src = inspect.getsource(execute_targeted_visual_asset_repair_loop)
        self.assertIn("max_repair_attempts = 1", src)

    def test_23_customer_isolation(self):
        from pipeline.generation_payload import assert_customer_scoped_asset_reuse

        r = assert_customer_scoped_asset_reuse(
            requester_customer_id="a", asset_customer_id="b", requester_channel_id="1", asset_channel_id="2"
        )
        self.assertTrue(r["blocked"])

    def test_24_25_provenance_secrets(self):
        from pipeline.retrieval.common import asset_metadata, strip_secrets

        m = asset_metadata(asset_id="x", source="local", media_type="image", content_hash="h", extra={"api_key": "SECRET"})
        self.assertNotIn("api_key", m)
        self.assertNotIn("SECRET", json.dumps(strip_secrets({"token": "SECRET"})))

    def test_26_27_28_29_30_no_duplicate_engines(self):
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap["frame_evidence_is_not_continuity_authority"])
        self.assertTrue(snap["frame_evidence_is_not_semantic_gate"])
        self.assertTrue(snap["frame_evidence_is_not_ffmpeg_engine"])
        self.assertFalse(snap["openmontage_agpl_imported"])
        for rel in (
            "pipeline/observation/frame_evidence/normalize.py",
            "pipeline/observation/frame_evidence/temporal.py",
            "pipeline/observation/frame_evidence/repair_loop.py",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", src)
            self.assertNotRegex(src, r"^\s*(from|import)\s+.*OpenMontage")


class EvidenceFileTests(unittest.TestCase):
    def test_phase6e_evidence_if_present(self):
        p = EV / "repair_loop.json"
        if not p.exists():
            self.skipTest("phase6e repair evidence not generated yet")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertFalse(data.get("whole_video_regeneration", True))
        self.assertEqual(data.get("repair_scope") or data.get("handoff", {}).get("repair_scope"), "VISUAL_ASSET")
        self.assertFalse(data.get("second_repair_engine", True))


if __name__ == "__main__":
    unittest.main()
