"""Retrieval → frame sampling → observation → coverage lineage."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.frame_evidence.coverage import beat_frame_coverage
from pipeline.observation.frame_evidence.observe import observe_frames
from pipeline.observation.frame_evidence.temporal import compare_temporal_frames
from pipeline.observation.frame_sampling import sample_frames
from pipeline.retrieval.common import (
    STATUS_RETRIEVAL_UNAVAILABLE,
    strip_secrets,
)
from pipeline.generation_payload import assert_customer_scoped_asset_reuse


def bridge_retrieval_to_frame_observation(
    *,
    retrieval_evidence: Mapping[str, Any],
    beat: Mapping[str, Any] | Any,
    work_dir: Path | str,
    google_api_keys: Optional[Sequence[str]] = None,
    allow_heuristic_fixture: bool = False,
    fixture_caption: str = "",
    requester_customer_id: str = "",
    requester_channel_id: str = "",
    visual_contract: Optional[Mapping[str, Any]] = None,
    continuity_constraints: Optional[Mapping[str, Any]] = None,
    clip_similarity: Optional[float] = None,
) -> dict[str, Any]:
    """
    Traceable lineage: retrieval candidate → frames → observation → beat coverage.
    Fail-closed customer/channel isolation.
    """
    vr = dict(retrieval_evidence or {})
    inner = dict(vr.get("visual_retrieval") or vr)
    selected = dict(inner.get("selected") or {})
    asset = dict(selected.get("asset") or selected)

    asset_customer = str(asset.get("customer_id") or inner.get("customer_id") or "")
    asset_channel = str(asset.get("channel_id") or inner.get("channel_id") or "")
    iso = assert_customer_scoped_asset_reuse(
        requester_customer_id=requester_customer_id or str(inner.get("customer_id") or ""),
        asset_customer_id=asset_customer or (requester_customer_id or str(inner.get("customer_id") or "")),
        requester_channel_id=requester_channel_id or str(inner.get("channel_id") or ""),
        asset_channel_id=asset_channel or (requester_channel_id or str(inner.get("channel_id") or "")),
    )
    if iso.get("blocked"):
        return strip_secrets(
            {
                "status": "FAIL",
                "reason": "customer_isolation_blocked",
                "isolation": iso,
                "frames": [],
                "observations": [],
                "unknown_as_pass": False,
                "clip_similarity_is_not_visual_truth": True,
            }
        )

    local_path = str(asset.get("local_path") or "")
    if not local_path or not Path(local_path).exists():
        # URL-only candidate cannot be frame-observed without download
        return strip_secrets(
            {
                "status": "UNKNOWN",
                "reason": "asset_local_path_missing",
                "retrieval_status": inner.get("retrieval_status") or inner.get("status"),
                "provenance": {
                    "source": asset.get("source"),
                    "source_url": asset.get("source_url"),
                    "license_usage": asset.get("license_usage"),
                    "retrieved_at": asset.get("retrieved_at") or inner.get("retrieved_at"),
                    "content_hash": asset.get("content_hash"),
                },
                "frames": [],
                "observations": [],
                "fallback_generation_allowed": True,
                "unknown_as_pass": False,
                "clip_similarity": clip_similarity,
                "clip_similarity_is_not_visual_truth": True,
            }
        )

    if hasattr(beat, "to_dict"):
        beat_d = beat.to_dict()
    else:
        beat_d = dict(beat or {})

    expected = {
        "subject": (beat_d.get("character_state") or {}).get("identity") or "",
        "entities": [
            (e.get("label") if isinstance(e, dict) else getattr(e, "label", str(e)))
            for e in (beat_d.get("required_entities") or [])
        ],
        "relationships": [
            " ".join(
                str(x)
                for x in (
                    (r.get("subject"), r.get("relation"), r.get("object"))
                    if isinstance(r, dict)
                    else (r,)
                )
                if x
            )
            for r in (beat_d.get("relationships") or [])
        ],
        "location": (beat_d.get("location_state") or {}).get("location") or "",
        "environment": (beat_d.get("environment_state") or {}).get("environment") or "",
        "camera": beat_d.get("camera_intent") or "",
        "lighting": beat_d.get("lighting_intent") or "",
        "action": (beat_d.get("character_state") or {}).get("action") or "",
    }

    sampled = sample_frames(
        local_path,
        out_dir=Path(work_dir) / "frame_samples",
        asset_id=str(asset.get("asset_id") or ""),
        scene_id=str(beat_d.get("scene_id") or ""),
        beat_id=str(beat_d.get("beat_id") or ""),
        customer_id=requester_customer_id or asset_customer,
        channel_id=requester_channel_id or asset_channel,
        beat_windows=[{"start_sec": 0.0, "end_sec": float(beat_d.get("duration_sec") or 0.0)}]
        if beat_d.get("duration_sec")
        else None,
    )

    if not sampled.get("frames"):
        return strip_secrets(
            {
                "status": sampled.get("status") or STATUS_RETRIEVAL_UNAVAILABLE,
                "reason": sampled.get("reason") or "sampling_failed",
                "sampling": sampled,
                "observations": [],
                "unknown_as_pass": False,
                "provenance": {
                    "source": asset.get("source"),
                    "source_url": asset.get("source_url"),
                    "license_usage": asset.get("license_usage"),
                    "retrieved_at": asset.get("retrieved_at") or inner.get("retrieved_at"),
                    "content_hash": asset.get("content_hash") or sampled.get("content_hash"),
                },
            }
        )

    observations = observe_frames(
        sampled["frames"],
        expected=expected,
        google_api_keys=google_api_keys,
        allow_heuristic_fixture=allow_heuristic_fixture,
        fixture_caption=fixture_caption
        or str(asset.get("caption") or asset.get("title") or ""),
    )
    temporal = compare_temporal_frames(
        observations,
        visual_contract=visual_contract or {"location": expected["location"], "relationships": expected["relationships"]},
        continuity_constraints=continuity_constraints,
    )
    coverage = beat_frame_coverage(beat_d, observations)

    # CLIP similarity optional evidence only
    clip_block = None
    if clip_similarity is not None:
        clip_block = {
            "similarity": float(clip_similarity),
            "is_visual_truth": False,
            "provider_verified": False,
            "note": "CLIP_similarity_not_semantic_PASS",
        }
    else:
        # Probe Phase 6B CLIP honesty
        try:
            from pipeline.retrieval.embedding import resolve_embedding_backend

            _be, meta = resolve_embedding_backend(prefer="clip", allow_hash_fallback=False)
            clip_block = {
                "backend": meta,
                "is_visual_truth": False,
                "hash_embedder_reported_as_clip": False,
            }
            if meta.get("kind") == "HEURISTIC":
                clip_block["hash_embedder_reported_as_clip"] = False
                clip_block["note"] = "hash_not_clip"
            if meta.get("status") == STATUS_RETRIEVAL_UNAVAILABLE:
                clip_block["status"] = STATUS_RETRIEVAL_UNAVAILABLE
        except Exception as exc:
            clip_block = {"status": STATUS_RETRIEVAL_UNAVAILABLE, "detail": str(exc)[:120]}

    return strip_secrets(
        {
            "status": "OK",
            "lineage": [
                "retrieval_candidate",
                "asset_identity",
                "sampled_frames",
                "frame_observation",
                "temporal_evidence",
                "beat_coverage",
            ],
            "provenance": {
                "source": asset.get("source"),
                "source_url": asset.get("source_url"),
                "license_usage": asset.get("license_usage"),
                "retrieved_at": asset.get("retrieved_at") or inner.get("retrieved_at"),
                "content_hash": asset.get("content_hash") or sampled.get("content_hash"),
            },
            "sampling": sampled,
            "observations": observations,
            "temporal": temporal,
            "coverage": coverage,
            "clip": clip_block,
            "clip_similarity_is_not_visual_truth": True,
            "unknown_as_pass": False,
            "creates_semantic_gate": False,
            "isolation": iso,
            "paid_api_calls": 0 if not google_api_keys else "caller_supplied_keys",
        }
    )
