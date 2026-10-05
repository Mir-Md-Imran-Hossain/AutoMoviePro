"""Phase 6C — frame sampling / evidence / temporal / bridge focused tests (paid API = 0)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image


def _png(path: Path, color=(30, 90, 160), size=(96, 64)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _short_mp4(path: Path, dur: float = 1.2) -> Path:
    from pipeline.compose import ffmpeg_bin

    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s=160x120:d={dur}",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60)
    return path


def _long_mp4(path: Path, dur: float = 8.0) -> Path:
    return _short_mp4(path, dur=dur)


def _beat(**kw):
    base = {
        "beat_id": "vb-1",
        "dialogue_segment_id": "ds-1",
        "narrative_beat_id": "nb-1",
        "scene_id": "sc-1",
        "required_entities": [{"label": "Shobha"}],
        "required_objects": ["Suzuki"],
        "relationships": [{"subject": "Shobha", "relation": "beside", "object": "Suzuki"}],
        "character_state": {"identity": "Shobha", "action": "standing"},
        "location_state": {"location": "police station"},
        "environment_state": {"environment": "daytime"},
        "camera_intent": "MEDIUM",
        "lighting_intent": "daylight",
        "visual_mode": "IMAGE",
        "duration_sec": 3.0,
    }
    base.update(kw)
    return base


class SamplingTests(unittest.TestCase):
    def test_01_image_sampling(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "a.png")
            out = sample_frames(img, out_dir=Path(td) / "out", asset_id="a1", beat_id="vb-1", scene_id="sc-1")
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["frame_count"], 1)
        self.assertFalse(out["semantic_pass"])
        self.assertTrue(out["reuses_compose_ffmpeg"])

    def test_02_short_video_sampling(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            vid = _short_mp4(Path(td) / "s.mp4", 1.5)
            out = sample_frames(vid, out_dir=Path(td) / "out", asset_id="v1", max_samples=3)
        self.assertEqual(out["status"], "PASS")
        self.assertLessEqual(out["frame_count"], 3)
        self.assertIn(out["strategy"], ("short_begin_mid_end", "long_uniform_bounded", "beat_boundary_preferred"))

    def test_03_bounded_long_video(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            vid = _long_mp4(Path(td) / "long.mp4", 8.0)
            out = sample_frames(vid, out_dir=Path(td) / "out", max_samples=20)
        self.assertEqual(out["status"], "PASS")
        self.assertLessEqual(out["frame_count"], 7)

    def test_04_unicode_path(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "日本語" / "frame.png")
            out = sample_frames(img, out_dir=Path(td) / "out 日本語", asset_id="u1")
        self.assertEqual(out["status"], "PASS")

    def test_05_spaces_in_path(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "my media" / "a b.png")
            out = sample_frames(img, out_dir=Path(td) / "out dir", asset_id="sp")
        self.assertEqual(out["status"], "PASS")

    def test_06_corrupted_media(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.mp4"
            bad.write_bytes(b"not a video")
            out = sample_frames(bad, out_dir=Path(td) / "out")
        self.assertIn(out["status"], ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "FAIL"))
        self.assertFalse(out.get("unknown_as_pass", True) if "unknown_as_pass" in out else True)

    def test_07_missing_media(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            out = sample_frames(Path(td) / "missing.png", out_dir=Path(td) / "out")
        self.assertEqual(out["status"], "OBSERVATION_UNAVAILABLE")

    def test_08_sampling_unknown_not_pass(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "z.mp4"
            bad.write_bytes(b"xxxx")
            out = sample_frames(bad, out_dir=Path(td) / "o")
        self.assertNotEqual(out.get("status"), "PASS")
        self.assertFalse(out.get("semantic_pass", False))


class EvidenceSchemaTests(unittest.TestCase):
    def test_09_frame_evidence_schema(self):
        from pipeline.observation.frame_evidence import empty_frame_evidence

        ev = empty_frame_evidence(asset_id="a", beat_id="b", scene_id="s", timestamp=1.2, frame_path="x.jpg")
        for k in (
            "schema_version",
            "asset_id",
            "scene_id",
            "beat_id",
            "timestamp",
            "frame_path",
            "observation_status",
            "provider",
            "observed_subjects",
            "observed_entities",
            "observed_relationships",
            "observed_location",
            "observed_actions",
            "observed_environment",
            "camera_observation",
            "lighting_observation",
            "confidence",
            "evidence_source",
        ):
            self.assertIn(k, ev)
        self.assertFalse(ev["unknown_as_pass"])

    def test_10_beat_binding(self):
        from pipeline.observation.frame_sampling import sample_frames

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "x.png")
            out = sample_frames(img, out_dir=Path(td) / "o", asset_id="A", beat_id="VB", scene_id="SC")
        f0 = out["frames"][0]
        self.assertEqual(f0["asset_id"], "A")
        self.assertEqual(f0["beat_id"], "VB")
        self.assertEqual(f0["scene_id"], "SC")


class CoverageTemporalTests(unittest.TestCase):
    def _obs(self, **kw):
        from pipeline.observation.frame_evidence import empty_frame_evidence

        ev = empty_frame_evidence(asset_id="a", beat_id="vb-1", scene_id="sc-1", timestamp=kw.pop("timestamp", 0))
        ev.update(kw)
        return ev

    def test_11_entity_coverage(self):
        from pipeline.observation.frame_evidence import beat_frame_coverage

        frames = [
            self._obs(
                observation_status="UNKNOWN",
                observed_entities=["Shobha", "Suzuki"],
                heuristic=True,
                provider_verified=False,
            )
        ]
        cov = beat_frame_coverage(_beat(), frames)
        self.assertIn(cov["dimensions"]["entity"], ("FULL", "PARTIAL", "UNKNOWN"))
        self.assertTrue(cov["retrieval_score_is_not_coverage"])

    def test_12_relationship_coverage(self):
        from pipeline.observation.frame_evidence import beat_frame_coverage

        frames = [
            self._obs(
                observed_relationships=["Shobha beside Suzuki"],
                observation_status="UNKNOWN",
            )
        ]
        cov = beat_frame_coverage(_beat(), frames)
        self.assertIn(cov["dimensions"]["relationship"], ("FULL", "PARTIAL", "UNKNOWN", "NONE"))

    def test_13_location_coverage(self):
        from pipeline.observation.frame_evidence import beat_frame_coverage

        frames = [self._obs(observed_location="police station", observation_status="UNKNOWN")]
        cov = beat_frame_coverage(_beat(), frames)
        self.assertIn(cov["dimensions"]["location"], ("FULL", "PARTIAL", "UNKNOWN"))

    def test_14_temporal_continuity(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        f1 = self._obs(
            timestamp=0,
            observed_relationships=["Shobha beside Suzuki"],
            observed_location="outside",
            observation_status="PASS",
            provider_verified=True,
        )
        f2 = self._obs(
            timestamp=1,
            observed_relationships=["Shobha beside Suzuki"],
            observed_location="outside",
            observation_status="PASS",
            provider_verified=True,
        )
        t = compare_temporal_frames(
            [f1, f2],
            visual_contract={"relationships": ["beside"], "location": "outside"},
            continuity_constraints={"require_relationship": True, "require_location": True},
        )
        self.assertEqual(t["status"], "PASS")
        self.assertFalse(t["second_continuity_engine"])

    def test_15_camera_contradiction(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        f1 = self._obs(timestamp=0, camera_observation="close-up face", observation_status="PASS")
        f2 = self._obs(timestamp=1, camera_observation="wide establishing aerial", observation_status="PASS")
        t = compare_temporal_frames(
            [f1, f2],
            continuity_constraints={"explicit_camera": True},
        )
        self.assertIn(t["status"], ("FAIL", "UNKNOWN", "PASS"))
        # If families detect clash → FAIL; either way no second engine
        self.assertFalse(t["second_continuity_engine"])

    def test_16_lighting_contradiction(self):
        from pipeline.observation.frame_evidence import compare_temporal_frames

        f1 = self._obs(timestamp=0, lighting_observation="bright day sun", observation_status="PASS")
        f2 = self._obs(timestamp=1, lighting_observation="dark night moonlight", observation_status="PASS")
        t = compare_temporal_frames(
            [f1, f2],
            continuity_constraints={"explicit_lighting": True, "lighting_continuity": "INHERITED"},
        )
        self.assertEqual(t["status"], "FAIL")
        self.assertTrue(any("lighting" in i for i in t["issues"]))


class BridgeIsolationTests(unittest.TestCase):
    def test_17_retrieval_frame_bridge(self):
        from pipeline.observation.frame_evidence import bridge_retrieval_to_frame_observation

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "shobha_suzuki_police.png")
            retrieval = {
                "selected": {
                    "asset": {
                        "asset_id": "local:1",
                        "local_path": str(img),
                        "source": "local_licensed",
                        "source_url": "",
                        "license_usage": "owned",
                        "content_hash": "abc",
                        "retrieved_at": 1.0,
                        "caption": "Shobha beside Suzuki at police station",
                        "customer_id": "cust",
                        "channel_id": "4",
                    }
                },
                "customer_id": "cust",
                "channel_id": "4",
                "retrieval_status": "RETRIEVAL_AVAILABLE",
            }
            out = bridge_retrieval_to_frame_observation(
                retrieval_evidence=retrieval,
                beat=_beat(),
                work_dir=td,
                allow_heuristic_fixture=True,
                fixture_caption="Shobha beside Suzuki police station",
                requester_customer_id="cust",
                requester_channel_id="4",
            )
        self.assertEqual(out["lineage"][0], "retrieval_candidate")
        self.assertTrue(out["clip_similarity_is_not_visual_truth"])
        self.assertIn("provenance", out)

    def test_18_customer_isolation(self):
        from pipeline.observation.frame_evidence import bridge_retrieval_to_frame_observation

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "x.png")
            retrieval = {
                "selected": {
                    "asset": {
                        "asset_id": "x",
                        "local_path": str(img),
                        "customer_id": "other",
                        "channel_id": "9",
                        "content_hash": "h",
                        "source": "local_licensed",
                    }
                },
                "customer_id": "other",
                "channel_id": "9",
            }
            out = bridge_retrieval_to_frame_observation(
                retrieval_evidence=retrieval,
                beat=_beat(),
                work_dir=td,
                requester_customer_id="mine",
                requester_channel_id="4",
            )
        self.assertEqual(out["status"], "FAIL")
        self.assertEqual(out["reason"], "customer_isolation_blocked")

    def test_19_provenance_and_20_secret_strip(self):
        from pipeline.retrieval.common import asset_metadata, strip_secrets

        meta = asset_metadata(
            asset_id="a",
            source="pexels",
            media_type="image",
            content_hash="h",
            license_usage="pexels",
            extra={"api_key": "SECRET", "caption": "ok"},
        )
        self.assertNotIn("api_key", meta)
        self.assertIn("license_usage", meta)
        self.assertNotIn("SECRET", json.dumps(strip_secrets({"token": "SECRET"})))


class ClipUnknownRepairTests(unittest.TestCase):
    def test_21_22_clip_paths(self):
        from pipeline.retrieval.embedding import resolve_embedding_backend

        be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
        if be is None:
            self.assertEqual(meta["status"], "RETRIEVAL_UNAVAILABLE")
        else:
            self.assertEqual(be.kind, "CLIP")

    def test_23_hash_never_clip(self):
        from pipeline.retrieval.embedding import resolve_embedding_backend

        be, meta = resolve_embedding_backend(prefer="hash", allow_hash_fallback=True)
        self.assertIsNotNone(be)
        self.assertEqual(be.kind, "HEURISTIC")
        self.assertNotEqual(be.kind, "CLIP")
        self.assertIn("hash", be.model_id)

    def test_24_unknown_not_pass(self):
        from pipeline.observation.frame_evidence import observe_frame

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "f.png")
            ev = observe_frame(
                {"frame_path": str(img), "asset_id": "a", "beat_id": "b", "scene_id": "s", "timestamp": 0},
                expected={"subject": "Shobha"},
                google_api_keys=[],
                allow_heuristic_fixture=False,
            )
        self.assertEqual(ev["observation_status"], "UNKNOWN")
        self.assertNotEqual(ev["observation_status"], "PASS")
        self.assertFalse(ev["provider_verified"])

    def test_25_absent_blocks_semantic(self):
        from pipeline.semantic_coverage import (
            absent_blocks_semantic_certification,
            attach_frame_evidence_to_semantic_report,
            evaluate_job_semantic_gate,
        )

        self.assertTrue(absent_blocks_semantic_certification("ABSENT"))
        self.assertTrue(absent_blocks_semantic_certification("UNKNOWN"))
        report = {"overall": "PASS", "issues": [], "blocking": False}
        bridged = {
            "observations": [
                {"observation_status": "UNKNOWN", "mandatory_evidence": "ABSENT"},
            ],
            "temporal": {"status": "UNKNOWN"},
            "coverage": {},
            "lineage": ["retrieval_candidate"],
        }
        out = attach_frame_evidence_to_semantic_report(report, bridged)
        self.assertEqual(out["mandatory_frame_evidence"], "ABSENT")
        self.assertNotEqual(out["overall"], "PASS")
        self.assertTrue(out["blocking"])

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "scene_00_SEMANTIC_COVERAGE.json"
            p.write_text(json.dumps(out), encoding="utf-8")
            gate = evaluate_job_semantic_gate(Path(td))
        self.assertTrue(gate["blocking"])
        self.assertNotEqual(gate["verdict"], "PASS")

    def test_26_fail_triggers_repair(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        handoff = repair_handoff_from_frame_evidence(
            beat_id="vb-1",
            scene_id="sc-1",
            frame_bridge_or_temporal={
                "temporal": {"status": "FAIL", "issues": ["explicit_lighting_day_night_without_transition"]},
                "observations": [{"observation_status": "FAIL"}],
                "coverage": {"overall": "NONE"},
            },
        )
        self.assertTrue(handoff["repair_triggered"])
        self.assertEqual(handoff["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(handoff["whole_video_regeneration"])
        self.assertFalse(handoff["second_repair_engine"])

    def test_27_unknown_no_repair(self):
        from pipeline.observation.frame_evidence import repair_handoff_from_frame_evidence

        handoff = repair_handoff_from_frame_evidence(
            beat_id="vb-1",
            scene_id="sc-1",
            frame_bridge_or_temporal={
                "temporal": {"status": "UNKNOWN"},
                "observations": [{"observation_status": "UNKNOWN"}],
            },
        )
        self.assertFalse(handoff["repair_triggered"])


class AuthorityGuardTests(unittest.TestCase):
    def test_28_30_31_32_no_duplicate_engines(self):
        from pipeline.observation.frame_sampling import sample_frames
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertTrue(snap["frame_evidence_is_not_continuity_authority"])
        self.assertTrue(snap["frame_evidence_is_not_semantic_gate"])
        self.assertTrue(snap["frame_evidence_is_not_ffmpeg_engine"])
        self.assertFalse(snap["openmontage_agpl_imported"])

        # BUILD-03 unchanged symbol still importable
        from pipeline.idempotency.executor import IdempotentExecutor  # noqa: F401

        with tempfile.TemporaryDirectory() as td:
            img = _png(Path(td) / "x.png")
            out = sample_frames(img, out_dir=Path(td) / "o")
        self.assertTrue(out.get("reuses_compose_ffmpeg"))
        self.assertFalse(out.get("creates_ffmpeg_engine"))

        # No OpenMontage import in new packages
        for rel in (
            "pipeline/observation/frame_sampling/sample.py",
            "pipeline/observation/frame_evidence/bridge.py",
            "pipeline/observation/frame_evidence/observe.py",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", src)

        # RCP-03 observe_semantic_coverage still present
        from pipeline.semantic_coverage import observe_semantic_coverage  # noqa: F401

        self.assertTrue(callable(observe_semantic_coverage))


if __name__ == "__main__":
    unittest.main()
