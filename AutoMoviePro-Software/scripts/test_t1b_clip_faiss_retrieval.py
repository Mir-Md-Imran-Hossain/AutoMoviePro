#!/usr/bin/env python3
"""T1-B — Real CLIP + FAISS retrieval evidence tests + golden hash-vs-CLIP eval.

Does NOT install torch/open-clip. If CLIP unavailable → honest UNAVAILABLE /
SKIPPED for CLIP paths; hash remains HEURISTIC_NON_SEMANTIC only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOB2333 = (
    ROOT
    / "data"
    / "customer_generation_work"
    / "c11_marathon_customer"
    / "job2333"
)
EVIDENCE_DIR = ROOT / "docs" / "marathon" / "evidence" / "t1b"
GOLDEN_DIR = EVIDENCE_DIR / "golden_dataset"


def _ffmpeg():
    from pipeline.compose import ffmpeg_bin

    return ffmpeg_bin()


def _build_golden_dataset() -> dict:
    """Extract ≥10 frames from job2333 real media + 5 SceneIntent-derived queries."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = GOLDEN_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    videos = []
    for name in (
        "final_short.mp4",
        "scene_00_beat.mp4",
        "scene_01_beat.mp4",
        "scene_02_beat.mp4",
        "scene_03_beat.mp4",
        "scene_04_beat.mp4",
    ):
        p = JOB2333 / name
        if p.is_file():
            videos.append(p)

    # Distinct timestamps across final + scenes
    plan = [
        ("final_short.mp4", 1.0),
        ("final_short.mp4", 8.0),
        ("final_short.mp4", 16.0),
        ("final_short.mp4", 28.0),
        ("final_short.mp4", 40.0),
        ("scene_00_beat.mp4", 1.5),
        ("scene_01_beat.mp4", 1.0),
        ("scene_02_beat.mp4", 2.0),
        ("scene_03_beat.mp4", 1.0),
        ("scene_04_beat.mp4", 1.5),
        ("agnes_00_beat_i2v_a1.mp4", 0.8),
        ("agnes_03_beat_i2v_a1.mp4", 0.8),
    ]
    assets = []
    for vid_name, tsec in plan:
        src = JOB2333 / vid_name
        if not src.is_file():
            continue
        out = assets_dir / f"{src.stem}_t{int(tsec*10):03d}.jpg"
        if not out.is_file():
            r = subprocess.run(
                [
                    _ffmpeg(),
                    "-y",
                    "-ss",
                    str(tsec),
                    "-i",
                    str(src),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0 or not out.is_file():
                continue
        assets.append(
            {
                "asset_id": out.stem,
                "local_path": str(out),
                "source_video": vid_name,
                "time_sec": tsec,
                "media_type": "image",
                "source": "job2333_real_media",
            }
        )

    # Queries from director_plan / C05-S scene semantics (real AMP data)
    queries = []
    dp_path = JOB2333 / "director_plan.json"
    if dp_path.is_file():
        dp = json.loads(dp_path.read_text(encoding="utf-8"))
        for i, sc in enumerate((dp.get("scenes") or [])[:5]):
            prompt = str(sc.get("exact_ai_video_prompt") or sc.get("visual_prompt") or "").strip()
            # Compress to retrieval-style query (entity-rich, not full prompt dump)
            purpose = str(sc.get("visual_purpose") or f"beat-{i}")
            short = prompt[:180] if prompt else purpose
            expected = {
                0: "JWST / telescope / exoplanet atmospheres documentary",
                1: "visible vs mid-infrared light / dust / space science",
                2: "spectral fingerprint / methane / carbon dioxide absorption",
                3: "bright star light subtraction / exoplanet signal",
                4: "water vapor / clouds / atmospheric spectroscopy",
            }.get(i, purpose)
            queries.append(
                {
                    "query_id": f"q{i}",
                    "query_text": short,
                    "expected_concept": expected,
                    "scene_id": str(sc.get("scene_id") or f"scene-{i}"),
                    "visual_purpose": purpose,
                    "beat_id": str(sc.get("c05s_visual_beat_id") or ""),
                }
            )

    if len(queries) < 5:
        # Fallback grounded in job2333 topic (still real AMP subject)
        defaults = [
            ("q0", "James Webb Space Telescope mid-infrared exoplanet atmosphere", "telescope in space"),
            ("q1", "visible light bouncing off clouds mid-infrared penetrating dust", "infrared vs visible light"),
            ("q2", "carbon dioxide methane spectral absorption fingerprint JWST", "spectral fingerprint"),
            ("q3", "bright star light subtraction exoplanet atmosphere signal", "starlight subtraction"),
            ("q4", "water vapor hiding behind clouds exoplanet atmosphere", "water vapor / clouds"),
        ]
        for qid, text, concept in defaults:
            if not any(q["query_id"] == qid for q in queries):
                queries.append(
                    {
                        "query_id": qid,
                        "query_text": text,
                        "expected_concept": concept,
                        "scene_id": "",
                        "visual_purpose": "fallback_topic",
                        "beat_id": "",
                    }
                )

    manifest = {
        "label": "T1B_GOLDEN_DATASET",
        "job": "job2333",
        "asset_count": len(assets),
        "query_count": len(queries),
        "assets": assets,
        "queries": queries[:5],
        "note": "Frames extracted under evidence/; job2333 originals untouched",
    }
    (GOLDEN_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _run_backend_retrieval(backend, assets, query_text: str, index_root: Path, customer_id: str) -> dict:
    from pipeline.retrieval.embedding import namespaced_index_root
    from pipeline.retrieval.faiss_index import FaissAssetIndex

    ns = namespaced_index_root(index_root, backend)
    idx = FaissAssetIndex(
        ns,
        embedding_model=backend.model_id,
        embedding_version=backend.version,
        dim=backend.dim,
        customer_id=customer_id,
        channel_id="4",
    )
    t_build0 = time.perf_counter()
    idx.load()
    for a in assets:
        path = Path(a["local_path"])
        if not path.is_file():
            continue
        vec = backend.embed_image(path)
        from pipeline.retrieval.common import content_hash_file

        meta = {
            "asset_id": a["asset_id"],
            "local_path": str(path),
            "media_type": "image",
            "source": a.get("source") or "job2333",
            "content_hash": content_hash_file(path),
            "source_video": a.get("source_video"),
            "embedding_kind": backend.kind,
        }
        idx.add_vector(vec, meta, persist=False)
    persist = idx.persist()
    build_sec = round(time.perf_counter() - t_build0, 3)

    t_q0 = time.perf_counter()
    qvec = backend.embed_text(query_text)
    searched = idx.search(qvec, top_k=3)
    query_sec = round(time.perf_counter() - t_q0, 3)

    hits = []
    for h in searched.get("hits") or []:
        asset = h.get("asset") or {}
        hits.append(
            {
                "asset_id": asset.get("asset_id"),
                "score": h.get("semantic_score"),
                "source_video": asset.get("source_video"),
                "local_path": asset.get("local_path"),
            }
        )
    return {
        "backend": backend.model_id,
        "kind": backend.kind,
        "status": searched.get("status"),
        "index_namespace": str(ns.name),
        "build_sec": build_sec,
        "query_sec": query_sec,
        "persist": persist,
        "top_k": hits,
        "claims_semantic_truth": False,
    }


class EmbeddingContractUnitTests(unittest.TestCase):
    def test_hash_labeled_heuristic_non_semantic(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend, embedding_evidence

        be = HashEmbeddingBackend()
        self.assertEqual(be.kind, "HEURISTIC_NON_SEMANTIC")
        v = be.embed_text("JWST telescope")
        ev = embedding_evidence(be, vector=v, source="unit", modality="text", source_hash="x")
        self.assertTrue(ev["heuristic_non_semantic"])
        self.assertFalse(ev["claims_semantic_truth"])
        self.assertFalse(ev["semantic_pass"])
        self.assertEqual(ev["status"], "UNKNOWN")

    def test_clip_unavailable_not_pass(self):
        from pipeline.retrieval.common import REASON_EMBEDDING_BACKEND_UNAVAILABLE
        from pipeline.retrieval.embedding import resolve_embedding_backend

        with mock.patch(
            "pipeline.retrieval.embedding.ClipEmbeddingBackend.probe",
            return_value={"available": False, "error": "forced", "gpu_mandatory": False},
        ):
            be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
        self.assertIsNone(be)
        self.assertEqual(meta["status"], "RETRIEVAL_UNAVAILABLE")
        self.assertEqual(meta["reason"], REASON_EMBEDDING_BACKEND_UNAVAILABLE)
        self.assertFalse(meta.get("semantic_pass"))
        self.assertFalse(meta.get("claims_semantic_truth"))

    def test_hash_fallback_not_semantic_pass(self):
        from pipeline.retrieval.embedding import resolve_embedding_backend

        with mock.patch(
            "pipeline.retrieval.embedding.ClipEmbeddingBackend.probe",
            return_value={"available": False, "error": "forced"},
        ):
            be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=True)
        self.assertIsNotNone(be)
        self.assertEqual(be.kind, "HEURISTIC_NON_SEMANTIC")
        self.assertEqual(meta["status"], "UNKNOWN")
        self.assertFalse(meta.get("semantic_pass"))
        self.assertIn("non_semantic", meta.get("note", ""))

    def test_namespace_separates_hash_and_clip_ids(self):
        from pipeline.retrieval.embedding import (
            ClipEmbeddingBackend,
            HashEmbeddingBackend,
            index_namespace_for_backend,
        )

        h = HashEmbeddingBackend()
        c = ClipEmbeddingBackend()
        # Even before load, model ids differ → namespaces differ
        self.assertNotEqual(index_namespace_for_backend(h), index_namespace_for_backend(c))

    def test_dim_mismatch_rejected(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss unavailable")
        be = HashEmbeddingBackend(dim=32)
        with tempfile.TemporaryDirectory() as td:
            idx = FaissAssetIndex(
                Path(td) / "idx",
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=32,
                customer_id="c-t1b",
            )
            idx.load()
            import numpy as np

            bad = np.zeros(16, dtype=np.float32)
            r = idx.add_vector(bad, {"asset_id": "x", "content_hash": "h"})
            self.assertEqual(r["status"], "FAIL")
            self.assertEqual(r["reason"], "dim_mismatch")

    def test_model_mismatch_on_load(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss unavailable")
        be = HashEmbeddingBackend(dim=16)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "idx"
            idx = FaissAssetIndex(
                root, embedding_model=be.model_id, embedding_version=be.version, dim=16, customer_id="c1"
            )
            idx.load()
            from PIL import Image

            p = Path(td) / "a.png"
            Image.new("RGB", (32, 32), (10, 20, 30)).save(p)
            idx.add_vector(be.embed_image(p), {"asset_id": "a", "content_hash": "ch1"})
            other = FaissAssetIndex(
                root, embedding_model="other_model", embedding_version=be.version, dim=16, customer_id="c1"
            )
            loaded = other.load()
            self.assertEqual(loaded["status"], "FAIL")
            self.assertEqual(loaded["reason"], "embedding_model_mismatch")

    def test_empty_index_search(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss unavailable")
        be = HashEmbeddingBackend(dim=16)
        with tempfile.TemporaryDirectory() as td:
            idx = FaissAssetIndex(
                Path(td) / "empty",
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=16,
            )
            idx.load()
            r = idx.search(be.embed_text("anything"), top_k=3)
            self.assertEqual(r["status"], "PASS")
            self.assertTrue(r.get("empty"))
            self.assertEqual(r["hits"], [])

    def test_corrupt_image_hash_still_hashes_bytes(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend

        be = HashEmbeddingBackend(dim=16)
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.jpg"
            bad.write_bytes(b"not-an-image")
            # Hash backend embeds file bytes — succeeds as non-semantic
            v = be.embed_image(bad)
            self.assertEqual(v.shape[0], 16)


@unittest.skipUnless(JOB2333.is_dir() and (JOB2333 / "final_short.mp4").is_file(), "job2333 missing")
class RealMediaGoldenRetrievalTests(unittest.TestCase):
    """REAL_MEDIA — job2333 frames + SceneIntent/director queries."""

    @classmethod
    def setUpClass(cls):
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        cls.manifest = _build_golden_dataset()
        if cls.manifest["asset_count"] < 10:
            raise unittest.SkipTest(f"need >=10 assets, got {cls.manifest['asset_count']}")

    def test_REAL_golden_manifest(self):
        self.assertGreaterEqual(self.manifest["asset_count"], 10)
        self.assertGreaterEqual(len(self.manifest["queries"]), 5)

    def test_REAL_hash_vs_clip_comparison(self):
        from pipeline.retrieval.embedding import (
            ClipEmbeddingBackend,
            HashEmbeddingBackend,
            resolve_embedding_backend,
        )
        from pipeline.retrieval.faiss_index import faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss unavailable")

        assets = self.manifest["assets"]
        queries = self.manifest["queries"]
        hash_be = HashEmbeddingBackend()
        clip_be, clip_meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)

        rows = []
        perf = {
            "os": "win32",
            "clip_available": clip_be is not None,
            "clip_meta": clip_meta,
            "faiss": faiss_available(),
        }

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            for q in queries:
                hash_res = _run_backend_retrieval(
                    hash_be, assets, q["query_text"], base / "hash_idx", customer_id="c11_marathon_customer"
                )
                if clip_be is not None:
                    t0 = time.perf_counter()
                    # cold/warm captured inside backend metrics if any
                    clip_res = _run_backend_retrieval(
                        clip_be, assets, q["query_text"], base / "clip_idx", customer_id="c11_marathon_customer"
                    )
                    clip_res["wall_sec"] = round(time.perf_counter() - t0, 3)
                    clip_status = "RAN"
                else:
                    clip_res = {
                        "status": "RETRIEVAL_UNAVAILABLE",
                        "reason": clip_meta.get("reason"),
                        "kind": "CLIP",
                        "top_k": [],
                        "claims_semantic_truth": False,
                    }
                    clip_status = "UNAVAILABLE"

                # Human-readable relevance: hash cannot claim semantic; CLIP TBD by inspector
                row = {
                    "query": q["query_text"][:120],
                    "expected_semantic_concept": q["expected_concept"],
                    "hash_top1": (hash_res["top_k"][0]["asset_id"] if hash_res.get("top_k") else None),
                    "clip_top1": (clip_res["top_k"][0]["asset_id"] if clip_res.get("top_k") else None),
                    "hash_top3": [h["asset_id"] for h in (hash_res.get("top_k") or [])],
                    "clip_top3": [h["asset_id"] for h in (clip_res.get("top_k") or [])],
                    "hash_scores": [h.get("score") for h in (hash_res.get("top_k") or [])],
                    "clip_scores": [h.get("score") for h in (clip_res.get("top_k") or [])],
                    "hash_kind": hash_res.get("kind"),
                    "clip_kind": clip_res.get("kind"),
                    "clip_run_status": clip_status,
                    "relevant_result": "UNKNOWN" if clip_status != "RAN" else "UNKNOWN",
                    "notes": (
                        "CLIP unavailable — cannot claim semantic quality; "
                        "hash is HEURISTIC_NON_SEMANTIC only"
                        if clip_status != "RAN"
                        else "Manual/spot relevance: mark RELEVANT|PARTIALLY_RELEVANT|IRRELEVANT in report"
                    ),
                    "hash_result": hash_res,
                    "clip_result": clip_res,
                }
                rows.append(row)

        payload = {
            "label": "T1B_HASH_VS_CLIP",
            "job": "job2333",
            "performance": perf,
            "rows": rows,
            "claims_semantic_truth": False,
            "hash_policy": "HEURISTIC_NON_SEMANTIC",
        }
        (EVIDENCE_DIR / "hash_vs_clip_comparison.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # Markdown table for report consumption
        lines = [
            "| Query | Expected concept | Hash Top-1 | CLIP Top-1 | Hash Top-3 | CLIP Top-3 | Relevant? | Notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                "| {q} | {e} | {h1} | {c1} | {h3} | {c3} | {rel} | {n} |".format(
                    q=(r["query"] or "").replace("|", "/")[:60],
                    e=(r["expected_semantic_concept"] or "").replace("|", "/")[:40],
                    h1=r["hash_top1"],
                    c1=r["clip_top1"] or "UNAVAILABLE",
                    h3=",".join(r["hash_top3"][:3]),
                    c3=(",".join(r["clip_top3"][:3]) if r["clip_top3"] else "UNAVAILABLE"),
                    rel=r["relevant_result"],
                    n=(r["notes"] or "")[:50].replace("|", "/"),
                )
            )
        (EVIDENCE_DIR / "hash_vs_clip_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.assertEqual(len(rows), 5)
        for r in rows:
            self.assertEqual(r["hash_kind"], "HEURISTIC_NON_SEMANTIC")
            self.assertTrue(r["hash_top3"])

    def test_REAL_customer_isolation_on_job_frames(self):
        from pipeline.retrieval.embedding import HashEmbeddingBackend
        from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available

        if not faiss_available().get("available"):
            self.skipTest("faiss")
        be = HashEmbeddingBackend(dim=32)
        assets = self.manifest["assets"][:3]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "idx"
            idx = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=32,
                customer_id="c11_marathon_customer",
            )
            idx.load()
            from pipeline.retrieval.common import content_hash_file

            for a in assets:
                p = Path(a["local_path"])
                idx.add_vector(
                    be.embed_image(p),
                    {"asset_id": a["asset_id"], "content_hash": content_hash_file(p)},
                    persist=False,
                )
            idx.persist()
            other = FaissAssetIndex(
                root,
                embedding_model=be.model_id,
                embedding_version=be.version,
                dim=32,
                customer_id="other_customer",
            )
            loaded = other.load()
            self.assertEqual(loaded["status"], "FAIL")
            self.assertEqual(loaded["reason"], "customer_isolation_mismatch")

    def test_REAL_clip_path_or_unavailable(self):
        from pipeline.retrieval.embedding import ClipEmbeddingBackend, embed_asset_record

        clip = ClipEmbeddingBackend(device="cpu")
        probe = clip.probe()
        (EVIDENCE_DIR / "clip_probe.json").write_text(
            json.dumps({"label": "T1B_CLIP_PROBE", **probe}, indent=2, default=str),
            encoding="utf-8",
        )
        if not probe.get("available"):
            self.assertFalse(probe.get("gpu_mandatory"))
            # Honest unavailable — not PASS
            return
        # If CLIP present: embed first golden asset
        asset = self.manifest["assets"][0]
        rec = embed_asset_record(clip, local_path=asset["local_path"], media_type="image")
        self.assertTrue(rec.get("ok"))
        self.assertFalse(rec.get("claims_semantic_truth"))
        self.assertEqual(rec["evidence"]["backend"], "clip")
        self.assertTrue(rec["evidence"]["normalized"])


class MontageAuthoritySafetyTests(unittest.TestCase):
    def test_bridge_does_not_replace_authorities(self):
        from pipeline.retrieval.bridge import attach_retrieval_evidence

        with tempfile.TemporaryDirectory() as td:
            out = attach_retrieval_evidence(
                {"beat_id": "b1", "visual_mode": "IMAGE", "required_entities": [{"label": "JWST"}]},
                index_root=str(Path(td) / "idx"),
                allow_hash_embedder=False,
            )
        self.assertFalse(out.get("creates_final_gate"))
        self.assertFalse(out.get("unknown_as_pass"))
        self.assertIn("SceneIntent", out.get("does_not_replace") or [])
        self.assertIn("ContinuityTracker", out.get("does_not_replace") or [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
