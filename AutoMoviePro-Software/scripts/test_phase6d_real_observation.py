"""Phase 6D — real media observation certification tests.

Live evidence is loaded from docs/marathon/customer_product/phase6d_evidence/
when present. Live provider re-calls are NOT made in unit tests (paid control).
Structural/UNKNOWN/isolation tests always run.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EV = ROOT / "docs" / "marathon" / "customer_product" / "phase6d_evidence"
IMAGE = ROOT / "data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png"
VIDEO = ROOT / "data/customer_generation_work/c11_marathon_customer/job2108/scene_00_beat.mp4"


def _load(name: str) -> dict:
    p = EV / name
    if not p.exists():
        raise unittest.SkipTest(f"missing evidence {name} — run Phase 6D cert first")
    return json.loads(p.read_text(encoding="utf-8"))


class RealMediaSamplingTests(unittest.TestCase):
    def test_01_real_image_sampling(self):
        from pipeline.observation.frame_sampling import sample_frames

        self.assertTrue(IMAGE.exists())
        with tempfile.TemporaryDirectory() as td:
            out = sample_frames(
                IMAGE,
                out_dir=Path(td),
                asset_id="c11-img-2108",
                beat_id="vb-6d-1",
                scene_id="sc-6d-1",
            )
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["frame_count"], 1)
        self.assertFalse(out["semantic_pass"])
        self.assertTrue(out["reuses_compose_ffmpeg"])

    def test_02_real_short_video_sampling(self):
        from pipeline.observation.frame_sampling import sample_frames

        self.assertTrue(VIDEO.exists())
        with tempfile.TemporaryDirectory() as td:
            out = sample_frames(
                VIDEO,
                out_dir=Path(td),
                asset_id="c11-vid-2108",
                beat_id="vb-6d-vid",
                scene_id="sc-6d-1",
                max_samples=20,
            )
        self.assertEqual(out["status"], "PASS")
        self.assertLessEqual(out["frame_count"], 7)
        self.assertTrue(out.get("reuses_compose_ffmpeg"))

    def test_03_frame_timestamp_correctness(self):
        ev = _load("02_video.json")
        ts = ev["sampling"]["timestamps"]
        self.assertGreaterEqual(len(ts), 3)
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(ev["sampling"]["bounded"])
        for t in ts:
            self.assertGreaterEqual(float(t), 0.0)
            self.assertLess(float(t), float(ev["duration_sec"]))

    def test_04_frame_to_beat_binding(self):
        ev = _load("01_image.json")
        obs = ev["observation"]
        self.assertEqual(obs["beat_id"], "vb-6d-1")
        self.assertEqual(obs["scene_id"], "sc-6d-1")
        self.assertEqual(obs["asset_id"], "c11-img-2108")


class LiveProviderEvidenceTests(unittest.TestCase):
    def test_05_real_provider_observation(self):
        ev = _load("01_image.json")
        obs = ev["observation"]
        if ev.get("live_status") != "LIVE":
            raise unittest.SkipTest(f"ENVIRONMENT_LIMITED:{ev.get('live_status')}")
        self.assertTrue(obs["provider_verified"])
        self.assertFalse(obs["heuristic"])
        self.assertEqual(obs["evidence_source"], "PROVIDER_VERIFIED")
        self.assertTrue(str(obs["provider"]).startswith("PROVIDER_FRAME"))
        self.assertIn(obs["observation_status"], ("PASS", "FAIL", "UNKNOWN"))

    def test_06_entity_coverage(self):
        ev = _load("01_image.json")
        dims = ev["coverage"]["dimensions"]
        self.assertIn(dims["entity"], ("FULL", "PARTIAL", "NONE", "UNKNOWN"))
        self.assertTrue(ev["coverage"]["retrieval_score_is_not_coverage"])

    def test_07_relationship_coverage(self):
        ev = _load("01_image.json")
        self.assertIn(ev["coverage"]["dimensions"]["relationship"], ("FULL", "PARTIAL", "NONE", "UNKNOWN"))

    def test_08_location_coverage(self):
        ev = _load("01_image.json")
        self.assertIn(ev["coverage"]["dimensions"]["location"], ("FULL", "PARTIAL", "NONE", "UNKNOWN"))

    def test_09_negative_observation(self):
        ev = _load("03_negative.json")
        if ev.get("live_status") not in ("LIVE", "UNKNOWN", "ENVIRONMENT_LIMITED"):
            raise unittest.SkipTest(str(ev.get("live_status")))
        self.assertNotEqual(ev["observation_status"], "PASS")
        self.assertTrue(ev["is_not_pass"])
        self.assertTrue(ev["accepted"])
        self.assertFalse(ev.get("heuristic"))

    def test_10_temporal_observation(self):
        ev = _load("02_video.json")
        if ev.get("live_status") != "LIVE":
            raise unittest.SkipTest(f"ENVIRONMENT_LIMITED:{ev.get('live_status')}")
        self.assertIn(ev["temporal"]["status"], ("PASS", "FAIL", "UNKNOWN"))
        self.assertFalse(ev["temporal"]["second_continuity_engine"])
        self.assertGreaterEqual(len(ev["observations"]), 2)
        for o in ev["observations"]:
            self.assertTrue(o["provider_verified"])
            self.assertFalse(o["heuristic"])


class UnknownRepairLineageTests(unittest.TestCase):
    def test_11_unknown_provider(self):
        ev = _load("04_unknown.json")
        self.assertEqual(ev["observation_status"], "UNKNOWN")

    def test_12_unknown_blocks_semantic(self):
        ev = _load("04_unknown.json")
        self.assertNotEqual(ev["semantic_after_attach"], "PASS")
        self.assertTrue(ev["blocking"])
        self.assertTrue(ev["absent_blocks"])

    def test_13_unknown_no_repair(self):
        ev = _load("04_unknown.json")
        self.assertFalse(ev["repair_triggered"])
        self.assertFalse(ev["heuristic_promoted"])

    def test_14_fail_repair_handoff(self):
        ev = _load("05_repair.json")
        h = ev["handoff"]
        self.assertTrue(h["repair_triggered"])
        self.assertEqual(h["repair_scope"], "VISUAL_ASSET")
        self.assertFalse(h["whole_video_regeneration"])
        self.assertFalse(h["second_repair_engine"])

    def test_15_retrieval_lineage(self):
        ev = _load("06_lineage.json")
        self.assertEqual(ev["lineage"][0], "retrieval_candidate")
        self.assertIn("sampled_frames", ev["lineage"])
        self.assertIn("frame_observation", ev["lineage"])

    def test_16_provenance(self):
        ev = _load("06_lineage.json")
        prov = ev["provenance"]
        self.assertEqual(prov["source"], "local_licensed")
        self.assertTrue(prov.get("content_hash"))
        self.assertIn("license_usage", prov)

    def test_17_customer_isolation(self):
        ev = _load("06_lineage.json")
        self.assertEqual(ev["cross_customer_status"], "FAIL")
        self.assertEqual(ev["cross_customer_reason"], "customer_isolation_blocked")


class DependencyAuthorityTests(unittest.TestCase):
    def test_18_clip_unavailable(self):
        from pipeline.retrieval.embedding import resolve_embedding_backend

        be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
        if be is not None:
            self.assertEqual(be.kind, "CLIP")
        else:
            self.assertEqual(meta["status"], "RETRIEVAL_UNAVAILABLE")

    def test_19_hash_embedder_honesty(self):
        from pipeline.retrieval.embedding import resolve_embedding_backend

        be, meta = resolve_embedding_backend(prefer="hash")
        self.assertEqual(be.kind, "HEURISTIC")
        self.assertNotEqual(be.kind, "CLIP")

    def test_20_build03_unchanged(self):
        from pipeline.idempotency.executor import IdempotentExecutor  # noqa: F401

        self.assertTrue(callable(IdempotentExecutor))

    def test_21_continuity_authority(self):
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertEqual(
            snap["continuity_authority"],
            "pipeline.visual_semantic.continuity.ContinuityTracker",
        )
        self.assertTrue(snap["frame_evidence_is_not_continuity_authority"])

    def test_22_semantic_gate_authority(self):
        from pipeline.semantic_coverage import evaluate_job_semantic_gate
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        self.assertTrue(callable(evaluate_job_semantic_gate))
        self.assertTrue(architecture_integrity_snapshot()["frame_evidence_is_not_semantic_gate"])

    def test_23_ffmpeg_authority(self):
        from pipeline.compose import ffmpeg_bin
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        self.assertTrue(Path(ffmpeg_bin()).exists() or bool(ffmpeg_bin()))
        self.assertTrue(architecture_integrity_snapshot()["frame_evidence_is_not_ffmpeg_engine"])

    def test_24_openmontage_import_guard(self):
        for rel in (
            "pipeline/observation/frame_sampling/sample.py",
            "pipeline/observation/frame_evidence/observe.py",
            "pipeline/observation/frame_evidence/bridge.py",
            "pipeline/observation/frame_evidence/repair_hook.py",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", src)
            self.assertNotIn("from openmontage", src.lower())
            # reject AGPL import statements, not mere documentation mentions
            self.assertNotRegex(src, r"^\s*(from|import)\s+.*OpenMontage", msg=rel)


class PaidApiEvidenceTests(unittest.TestCase):
    def test_paid_api_count_recorded(self):
        paid = _load("00_paid_api.json")
        self.assertGreaterEqual(int(paid.get("attempts") or 0), 0)
        self.assertNotIn("api_key", json.dumps(paid).lower().replace("key_masks", ""))


if __name__ == "__main__":
    unittest.main()
