"""Orchestrate query → source search → FAISS → rank → evidence."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pipeline.retrieval.embedding import (
    namespaced_index_root,
    resolve_embedding_backend,
)
from pipeline.retrieval.faiss_index import FaissAssetIndex, faiss_available
from pipeline.retrieval.query import build_retrieval_query
from pipeline.retrieval.ranking import rank_candidates
from pipeline.retrieval.reuse import detect_reuse_risk
from pipeline.retrieval.sources import LocalCorpusSource, PexelsSource, list_production_sources
from pipeline.retrieval.common import (
    HEURISTIC_NON_SEMANTIC,
    SCHEMA_RETRIEVAL,
    STATUS_NO_SUITABLE,
    STATUS_RETRIEVAL_AVAILABLE,
    STATUS_RETRIEVAL_UNAVAILABLE,
    strip_secrets,
    unavailable,
)

logger = logging.getLogger(__name__)


def retrieve_for_beat(
    beat: Any,
    *,
    index_root: Path | str,
    local_corpus: Path | str | None = None,
    pexels_api_key: str = "",
    scene_intent: Optional[Mapping[str, Any]] = None,
    visual_contract: Optional[Mapping[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    prior_assets: Optional[Sequence[Mapping[str, Any]]] = None,
    allow_hash_embedder: bool = False,
    top_k: int = 8,
    min_candidate_score: float = 0.25,
) -> dict[str, Any]:
    """
    Full retrieval path. Never publishes/approves/repairs.
    CLIP missing → RETRIEVAL_UNAVAILABLE for semantic index (source search may still run).
    """
    query = build_retrieval_query(beat, scene_intent=scene_intent, visual_contract=visual_contract)
    sources_meta = list_production_sources()
    evidence: dict[str, Any] = {
        "schema": SCHEMA_RETRIEVAL,
        "query": query,
        "sources": sources_meta,
        "retrieved_at": time.time(),
        "customer_id": customer_id,
        "channel_id": channel_id,
        "publishes": False,
        "approves": False,
        "repairs": False,
        "publishability_pass": False,
        "replaces_continuity_tracker": False,
        "semantic_final_authority": False,
        "unknown_as_pass": False,
        "creates_final_gate": False,
        "build03_conflict": False,
    }

    media = str(query.get("preferred_media_type") or "image")
    raw_candidates: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []

    if local_corpus:
        loc = LocalCorpusSource(local_corpus, customer_id=customer_id, channel_id=channel_id)
        rep = loc.search(query["query_text"], media_type=media, limit=top_k)
        source_reports.append(strip_secrets({k: v for k, v in rep.items() if k != "candidates"}))
        raw_candidates.extend(rep.get("candidates") or [])

    if pexels_api_key:
        px = PexelsSource(pexels_api_key)
        rep = px.search(query["query_text"], media_type=media, limit=top_k)
        source_reports.append(strip_secrets({k: v for k, v in rep.items() if k != "candidates"}))
        raw_candidates.extend(rep.get("candidates") or [])

    evidence["source_reports"] = source_reports

    backend, backend_meta = resolve_embedding_backend(
        prefer="clip",
        allow_hash_fallback=allow_hash_embedder,
    )
    evidence["embedding"] = strip_secrets(backend_meta)
    faiss_probe = faiss_available()
    evidence["faiss"] = faiss_probe

    index_hits: list[dict[str, Any]] = []
    index_status = STATUS_RETRIEVAL_UNAVAILABLE
    if backend is None:
        evidence["index_status"] = STATUS_RETRIEVAL_UNAVAILABLE
        evidence["index_reason"] = backend_meta.get("reason") or "clip_unavailable"
    elif not faiss_probe.get("available"):
        evidence["index_status"] = STATUS_RETRIEVAL_UNAVAILABLE
        evidence["index_reason"] = "faiss_unavailable"
    else:
        # Namespace isolates CLIP vs hash indexes (never mixed even if dim matches)
        ns_root = namespaced_index_root(index_root, backend)
        idx = FaissAssetIndex(
            ns_root,
            embedding_model=backend.model_id,
            embedding_version=backend.version,
            dim=backend.dim,
            customer_id=customer_id,
            channel_id=channel_id,
        )
        evidence["index_namespace"] = str(ns_root.name)
        evidence["index_root_resolved"] = str(ns_root)
        loaded = idx.load()
        if loaded.get("status") == "FAIL":
            evidence["index_status"] = STATUS_RETRIEVAL_UNAVAILABLE
            evidence["index_reason"] = loaded.get("reason") or "index_corrupt"
            evidence["index_load"] = loaded
            # Do not silent-success
        else:
            # Index local candidates with paths
            for c in raw_candidates:
                asset = c.get("asset") or {}
                lp = asset.get("local_path") or ""
                if not lp or not Path(lp).is_file():
                    continue
                try:
                    if asset.get("media_type") == "image":
                        vec = backend.embed_image(lp)
                    else:
                        vec = backend.embed_text(
                            str(asset.get("caption") or asset.get("title") or query["query_text"])
                        )
                    meta = dict(asset)
                    meta["embedding_model"] = backend.model_id
                    meta["embedding_version"] = backend.version
                    meta["embedding_kind"] = backend.kind
                    idx.add_vector(vec, meta, persist=False)
                except Exception as exc:
                    logger.debug("index skip %s: %s", lp, exc)
            idx.persist()
            qvec = backend.embed_text(query["query_text"])
            searched = idx.search(qvec, top_k=top_k)
            if searched.get("status") == "FAIL":
                evidence["index_status"] = STATUS_RETRIEVAL_UNAVAILABLE
                evidence["index_reason"] = searched.get("reason")
            else:
                index_status = STATUS_RETRIEVAL_AVAILABLE
                evidence["index_status"] = index_status
                for h in searched.get("hits") or []:
                    score_key = (
                        "heuristic_score"
                        if backend.kind == HEURISTIC_NON_SEMANTIC
                        else "semantic_score"
                    )
                    hit_row = {
                        "asset": h.get("asset"),
                        score_key: h.get("semantic_score"),
                        "semantic_kind": backend.kind,
                        "claims_semantic_truth": False,
                    }
                    # Preserve legacy key for ranking only when CLIP
                    if backend.kind != HEURISTIC_NON_SEMANTIC:
                        hit_row["semantic_score"] = h.get("semantic_score")
                    else:
                        hit_row["semantic_score"] = None
                        hit_row["heuristic_non_semantic"] = True
                    index_hits.append(hit_row)

    # Merge index hits + raw source candidates (dedupe by content_hash)
    merged: dict[str, dict[str, Any]] = {}
    for c in index_hits + raw_candidates:
        asset = dict(c.get("asset") or {})
        key = str(asset.get("content_hash") or asset.get("asset_id") or "")
        if not key:
            continue
        if key not in merged or float(c.get("semantic_score") or 0) > float(
            merged[key].get("semantic_score") or 0
        ):
            merged[key] = c

    ranked = rank_candidates(
        query=query,
        candidates=list(merged.values()),
        prior_asset_ids=[str(a.get("asset_id") or "") for a in (prior_assets or [])],
        allow_continuity_reuse=True,
    )
    evidence["candidates"] = ranked

    suitable = [r for r in ranked if float(r.get("candidate_score") or 0) >= min_candidate_score]
    # Media-type preference filter
    mode = str(query.get("visual_mode") or "IMAGE").upper()
    if mode == "VIDEO":
        preferred = [r for r in suitable if (r.get("asset") or {}).get("media_type") == "video"]
    else:
        preferred = [r for r in suitable if (r.get("asset") or {}).get("media_type") == "image"]
        if mode == "IMAGE_WITH_MOTION" and preferred:
            for r in preferred:
                r["motion_path"] = "existing_amp_image_with_motion"
                r["note"] = "image_candidate_plus_existing_motion_path"

    selected = preferred[0] if preferred else (suitable[0] if suitable else None)
    if selected is None:
        if not raw_candidates and backend is None and not pexels_api_key and not local_corpus:
            out = unavailable(reason="no_sources_and_clip_unavailable", detail="fallback_to_amp_generation")
            out["query"] = query
            out["fallback_generation_allowed"] = True
            out["retrieval_status"] = STATUS_RETRIEVAL_UNAVAILABLE
            return out
        evidence["status"] = STATUS_NO_SUITABLE
        evidence["retrieval_status"] = STATUS_NO_SUITABLE
        evidence["selected"] = None
        evidence["fallback_generation_allowed"] = True
        evidence["reason"] = "no_suitable_asset_after_ranking"
        return evidence

    reuse = detect_reuse_risk(
        candidate_asset_id=str((selected.get("asset") or {}).get("asset_id") or ""),
        candidate_content_hash=str((selected.get("asset") or {}).get("content_hash") or ""),
        used_in_job=list(prior_assets or []),
        beat_id=str(query.get("beat_id") or ""),
        scene_id=str(query.get("scene_id") or ""),
        continuity_reuse_allowed=True,
    )
    evidence["reuse"] = reuse
    evidence["selected"] = selected
    evidence["status"] = STATUS_RETRIEVAL_AVAILABLE
    evidence["retrieval_status"] = STATUS_RETRIEVAL_AVAILABLE
    evidence["fallback_generation_allowed"] = False
    evidence["accepts_real_footage_without_semantic"] = False
    evidence["note"] = "candidate_only_semantic_coverage_still_required"
    return evidence


def index_local_assets(
    corpus_root: Path | str,
    index_root: Path | str,
    *,
    customer_id: str = "",
    channel_id: str = "",
    allow_hash_embedder: bool = False,
) -> dict[str, Any]:
    """Build/rebuild FAISS index from local corpus."""
    backend, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=allow_hash_embedder)
    if backend is None:
        return unavailable(reason="EMBEDDING_BACKEND_UNAVAILABLE", detail=str(meta), tool="faiss_index_build")
    if not faiss_available().get("available"):
        return unavailable(reason="faiss_unavailable", tool="faiss_index_build")

    src = LocalCorpusSource(corpus_root, customer_id=customer_id, channel_id=channel_id)
    found = src.search("", media_type="image", limit=500)
    # also videos
    found_v = src.search("", media_type="video", limit=500)
    assets = list(found.get("candidates") or []) + list(found_v.get("candidates") or [])

    ns_root = namespaced_index_root(index_root, backend)
    idx = FaissAssetIndex(
        ns_root,
        embedding_model=backend.model_id,
        embedding_version=backend.version,
        dim=backend.dim,
        customer_id=customer_id,
        channel_id=channel_id,
    )
    idx.load()
    added = 0
    skipped = 0
    for c in assets:
        asset = c.get("asset") or {}
        lp = asset.get("local_path")
        if not lp or not Path(lp).is_file():
            continue
        try:
            if asset.get("media_type") == "image":
                vec = backend.embed_image(lp)
            else:
                vec = backend.embed_text(str(asset.get("caption") or Path(lp).stem))
            asset = dict(asset)
            asset["embedding_model"] = backend.model_id
            asset["embedding_version"] = backend.version
            res = idx.add_vector(vec, asset, persist=False)
            if res.get("duplicate"):
                skipped += 1
            elif res.get("added"):
                added += 1
        except Exception as exc:
            logger.debug("skip asset: %s", exc)
    persisted = idx.persist()
    return {
        "status": persisted.get("status"),
        "added": added,
        "duplicates_skipped": skipped,
        "embedding": meta,
        "index": persisted,
        "rebuild_supported": True,
    }
