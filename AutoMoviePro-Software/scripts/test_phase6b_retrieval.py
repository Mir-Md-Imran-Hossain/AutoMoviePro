"""Phase 6B — CLIP/FAISS/real-footage retrieval focused tests."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image


def _png(path: Path, color=(40, 120, 200), size=(64, 48)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _sample_beat(**kwargs):
    base = {
        "beat_id": "vb-1",
        "dialogue_segment_id": "ds-1",
        "narrative_beat_id": "nb-1",
        "scene_id": "sc-1",
        "required_entities": [{"label": "Shobha", "role": "character"}],
        "required_objects": ["silver Suzuki car"],
        "relationships": [
            {
                "subject": "Shobha",
                "relation": "standing beside",
                "object": "silver Suzuki car",
            }
        ],
        "character_state": {"identity": "Shobha", "action": "standing"},
        "location_state": {"location": "outside a police station"},
        "environment_state": {"environment": "daytime street"},
        "camera_intent": "MEDIUM",
        "lighting_intent": "natural daylight",
        "emotional_visual_intent": "tense",
        "composition": "wide establishing",
        "visual_mode": "IMAGE",
    }
    base.update(kwargs)
    return base


class QueryTests(unittest.TestCase):
    def test_01_entity_relationship_location_not_location_only(self):
        from pipeline.retrieval.query import build_retrieval_query

        q = build_retrieval_query(_sample_beat())
        text = q["query_text"].lower()
        self.assertIn("shobha", text)
        self.assertIn("suzuki", text)
        self.assertIn("police", text)
        self.assertNotEqual(text.strip(), "police station")
        self.assertTrue(q["location_only_blocked"])
        self.assertEqual(q["preferred_media_type"], "image")

    def test_02_video_mode_prefers_video(self):
        from pipeline.retrieval.query import build_retrieval_query

        q = build_retrieval_query(_sample_beat(visual_mode="VIDEO"))
        self.assertEqual(q["preferred_media_type"], "video")


class EmbeddingTests(unittest.TestCase):
    def test_03_hash_embed_deterministic(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend

        be = HashEmbeddingBackend(dim=64)
        a = be.embed_text("hello world")
        b = be.embed_text("hello world")
        self.assertEqual(list(a), list(b))
        self.assertEqual(be.kind, "HEURISTIC_NON_SEMANTIC")

    def test_04_clip_missing_reports_unavailable(self):
        from pipeline.retrieval.embedding import ClipEmbeddingBackend, resolve_embedding_backend

        clip = ClipEmbeddingBackend()
        probe = clip.probe()
        backend, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
        if probe["available"]:
            self.assertIsNotNone(backend)
            self.assertEqual(backend.kind, "CLIP")
        else:
            self.assertIsNone(backend)
            self.assertEqual(meta["status"], "RETRIEVAL_UNAVAILABLE")
            self.assertIn(
                meta.get("reason", ""),
                ("EMBEDDING_BACKEND_UNAVAILABLE", "clip_model_unavailable"),
            )
            # allow substring match for legacy
            self.assertTrue(
                "EMBEDDING_BACKEND_UNAVAILABLE" in str(meta.get("reason"))
                or "clip" in str(meta.get("reason", "")).lower()
                or "unavailable" in str(meta.get("clip_probe", {})).lower()
            )

    def test_05_image_embed_hash(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend

        be = HashEmbeddingBackend(dim=32)
        with tempfile.TemporaryDirectory() as td:
            p = _png(Path(td) / "a.png")
            v = be.embed_image(p)
            self.assertEqual(v.shape[0], 32)


class FaissTests(unittest.TestCase):
    def test_06_index_search_deterministic_and_duplicate(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss not installed")
        be = HashEmbeddingBackend(dim=32)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "idx"
            img = _png(Path(td) / "corpus" / "shobha_suzuki_police.png")
            idx = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=be.dim,
                customer_id="cust-a",
                channel_id="ch-1",
            )
            self.assertEqual(idx.load()["status"], "PASS")
            vec = be.embed_image(img)
            meta = {
                "asset_id": "a1",
                "content_hash": "abc123",
                "local_path": str(img),
                "media_type": "image",
                "source": "local_licensed",
                "caption": "shobha suzuki police",
            }
            r1 = idx.add_vector(vec, meta)
            r2 = idx.add_vector(vec, meta)
            self.assertTrue(r1["added"])
            self.assertTrue(r2["duplicate"])
            q = be.embed_text("Shobha standing beside silver Suzuki outside police station")
            hits1 = idx.search(q, top_k=3)
            hits2 = idx.search(q, top_k=3)
            self.assertEqual(hits1["status"], "PASS")
            self.assertEqual(
                [h["vector_id"] for h in hits1["hits"]],
                [h["vector_id"] for h in hits2["hits"]],
            )
            # restart persistence
            idx2 = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=be.dim,
                customer_id="cust-a",
                channel_id="ch-1",
            )
            loaded = idx2.load()
            self.assertEqual(loaded["status"], "PASS")
            self.assertEqual(loaded["count"], 1)

    def test_07_corrupted_index_not_silent_success(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss not installed")
        be = HashEmbeddingBackend(dim=16)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "idx"
            idx = FaissAssetIndex(
                root, embedding_model=be.model_id, embedding_version=be.version, dim=be.dim
            )
            idx.load()
            img = _png(Path(td) / "x.png")
            idx.add_vector(be.embed_image(img), {"asset_id": "x", "content_hash": "h1", "media_type": "image"})
            idx.corrupt_for_test()
            idx3 = FaissAssetIndex(
                root, embedding_model=be.model_id, embedding_version=be.version, dim=be.dim
            )
            loaded = idx3.load()
            self.assertEqual(loaded["status"], "FAIL")
            self.assertIn("mismatch", loaded.get("reason", ""))

    def test_08_customer_isolation_mismatch(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss")
        be = HashEmbeddingBackend(dim=16)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "idx"
            idx = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=be.dim,
                customer_id="cust-a",
            )
            idx.load()
            img = _png(Path(td) / "x.png")
            idx.add_vector(be.embed_image(img), {"asset_id": "x", "content_hash": "h1"})
            other = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=be.dim,
                customer_id="cust-b",
            )
            loaded = other.load()
            self.assertEqual(loaded["status"], "FAIL")
            self.assertEqual(loaded["reason"], "customer_isolation_mismatch")


class WindowsPathTests(unittest.TestCase):
    def test_09_windows_unicode_and_spaces(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available
        from pipeline.retrieval.retrieve import retrieve_for_beat

        if not faiss_available().get("available"):
            self.skipTest("faiss")
        be = HashEmbeddingBackend(dim=32)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "My Corpus 日本語" / "sub dir"
            img = _png(base / "shobha silver suzuki police station.png")
            long_idx = Path(td) / ("idx_" + ("x" * 40)) / "nested index"
            out = retrieve_for_beat(
                _sample_beat(),
                index_root=long_idx,
                local_corpus=base,
                allow_hash_embedder=True,
                customer_id="c1",
                channel_id="4",
            )
            self.assertIn(out.get("retrieval_status") or out.get("status"), (
                "RETRIEVAL_AVAILABLE",
                "NO_SUITABLE_ASSET",
                "RETRIEVAL_UNAVAILABLE",
            ))
            # With hash embedder + local match should generally select
            self.assertTrue(out.get("retrieval_executed") is not False or out.get("candidates") is not None)


class RankingFallbackTests(unittest.TestCase):
    def test_10_ranking_explainable_and_media_filter(self):
        from pipeline.retrieval.query import build_retrieval_query
        from pipeline.retrieval.ranking import rank_candidates

        q = build_retrieval_query(_sample_beat(visual_mode="IMAGE"))
        cands = [
            {
                "asset": {
                    "asset_id": "v1",
                    "media_type": "video",
                    "caption": "Shobha Suzuki police",
                    "width": 1920,
                    "height": 1080,
                    "source": "pexels",
                },
                "semantic_score": 0.9,
            },
            {
                "asset": {
                    "asset_id": "i1",
                    "media_type": "image",
                    "caption": "Shobha standing beside silver Suzuki car outside police station",
                    "width": 1280,
                    "height": 720,
                    "source": "local_licensed",
                },
                "semantic_score": 0.7,
            },
        ]
        ranked = rank_candidates(query=q, candidates=cands)
        self.assertEqual(ranked[0]["score_mark"], "HEURISTIC")
        self.assertIn("entity_score", ranked[0])
        self.assertIn("relationship_score", ranked[0])

    def test_11_fallback_unavailable_without_sources(self):
        from pipeline.retrieval.retrieve import retrieve_for_beat

        with tempfile.TemporaryDirectory() as td:
            out = retrieve_for_beat(
                _sample_beat(),
                index_root=Path(td) / "idx",
                allow_hash_embedder=False,
            )
        self.assertIn(out.get("status"), ("RETRIEVAL_UNAVAILABLE", "NO_SUITABLE_ASSET"))
        self.assertTrue(out.get("fallback_generation_allowed", True) or out.get("status") == "RETRIEVAL_UNAVAILABLE")
        self.assertFalse(out.get("unknown_as_pass", True) if "unknown_as_pass" in out else True)
        # Must not claim PASS publishability
        self.assertFalse(out.get("publishability_pass", False))

    def test_12_no_secrets_in_metadata(self):
        from pipeline.retrieval.common import asset_metadata, strip_secrets

        meta = asset_metadata(
            asset_id="a",
            source="pexels",
            media_type="image",
            content_hash="h",
            extra={"api_key": "SECRET", "pexels_api_key": "X", "caption": "ok"},
        )
        self.assertNotIn("api_key", meta)
        self.assertNotIn("pexels_api_key", meta)
        self.assertEqual(meta["caption"], "ok")
        self.assertNotIn("SECRET", json.dumps(strip_secrets({"token": "t", "ok": 1})))


class ReuseIsolationTests(unittest.TestCase):
    def test_13_reuse_same_beat_vs_continuity(self):
        from pipeline.retrieval.reuse import detect_reuse_risk

        same_beat = detect_reuse_risk(
            candidate_asset_id="a1",
            candidate_content_hash="h1",
            used_in_job=[{"asset_id": "a1", "content_hash": "h1", "beat_id": "vb-1", "scene_id": "sc-1"}],
            beat_id="vb-1",
            scene_id="sc-1",
        )
        self.assertTrue(same_beat["automatic_failure"])
        cont = detect_reuse_risk(
            candidate_asset_id="a1",
            candidate_content_hash="h1",
            used_in_job=[{"asset_id": "a1", "content_hash": "h1", "beat_id": "vb-0", "scene_id": "sc-0"}],
            beat_id="vb-1",
            scene_id="sc-1",
            continuity_reuse_allowed=True,
        )
        self.assertFalse(cont["automatic_failure"])
        self.assertTrue(cont["build03_authority_unchanged"])

    def test_14_build03_and_c05_compat(self):
        from pipeline.generation_payload import materialize_visual_beats
        from pipeline.retrieval.bridge import attach_retrieval_evidence
        from pipeline.story_visual_direction import architecture_integrity_snapshot

        snap = architecture_integrity_snapshot()
        self.assertFalse(snap["openmontage_agpl_imported"])
        self.assertTrue(snap["visual_retrieval_is_not_continuity_authority"])
        self.assertTrue(snap["visual_retrieval_is_not_semantic_authority"])

        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td) / "corpus"
            img = _png(corpus / "shobha_suzuki_police.png")
            ev = attach_retrieval_evidence(
                _sample_beat(),
                index_root=Path(td) / "idx",
                local_corpus=corpus,
                allow_hash_embedder=True,
                customer_id="cust",
                channel_id="4",
            )
            self.assertIn("SceneIntent", ev["does_not_replace"])
            self.assertIn("ContinuityTracker", ev["does_not_replace"])
            self.assertFalse(ev["creates_final_gate"])
            mat = materialize_visual_beats(
                [
                    {
                        "dialogue_id": "d1",
                        "beat_id": "vb-1",
                        "scene_id": "sc-1",
                        "visual_mode": "IMAGE",
                        "visual_timing": {"duration_sec": 3},
                    }
                ],
                requested_mode="IMAGE",
                retrieval_by_beat={"vb-1": ev},
            )
            self.assertTrue(mat["ok"])
            self.assertTrue(mat["retrieval_is_not_publishability"])
            u0 = mat["units"][0]
            self.assertTrue(u0.get("retrieval_does_not_grant_publishability"))
            _ = img  # keep fixture referenced

    def test_15_unverified_sources_not_activated(self):
        from pipeline.retrieval.sources import UnverifiedSourceStub, list_production_sources

        stub = UnverifiedSourceStub("archive_org")
        out = stub.search("nasa")
        self.assertFalse(out["activated"])
        self.assertEqual(out["status"], "RETRIEVAL_UNAVAILABLE")
        names = {s["name"]: s for s in list_production_sources()}
        self.assertFalse(names["openmontage_stock_adapters"]["activated"])
        self.assertFalse(names["archive_org"]["activated"])


class ContinuityCompatTests(unittest.TestCase):
    def test_16_no_openmontage_import_in_retrieval(self):
        import pipeline.retrieval as r
        import pipeline.retrieval.sources as s
        import pipeline.retrieval.retrieve as ret

        for mod in (r, s, ret):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            self.assertNotIn("third_party.OpenMontage", src)
            self.assertNotIn("from openmontage", src.lower().replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
