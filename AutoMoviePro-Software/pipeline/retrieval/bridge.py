"""Bridge retrieval evidence into C05-S / materialization — no authority replacement."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from pipeline.retrieval.retrieve import retrieve_for_beat


def attach_retrieval_evidence(
    beat: Any,
    *,
    index_root: str,
    local_corpus: str | None = None,
    pexels_api_key: str = "",
    scene_intent: Optional[Mapping[str, Any]] = None,
    visual_contract: Optional[Mapping[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    prior_assets: Optional[Sequence[Mapping[str, Any]]] = None,
    allow_hash_embedder: bool = False,
) -> dict[str, Any]:
    """
    DialogueVisualBeat/DirectedVisualBeat → retrieval evidence.
    Feeds existing SceneIntent / ContinuityTracker / C05-MR — does not replace them.
    """
    ev = retrieve_for_beat(
        beat,
        index_root=index_root,
        local_corpus=local_corpus,
        pexels_api_key=pexels_api_key,
        scene_intent=scene_intent,
        visual_contract=visual_contract,
        customer_id=customer_id,
        channel_id=channel_id,
        prior_assets=prior_assets,
        allow_hash_embedder=allow_hash_embedder,
    )
    return {
        "visual_retrieval": ev,
        "flow": [
            "DirectedVisualBeat",
            "VisualContract",
            "RetrievalQuery",
            "CandidateSearch",
            "CandidateRanking",
            "ExistingSceneIntent",
            "ExistingContinuityTracker",
            "ExistingC05MR",
            "GenerationOrComposition",
        ],
        "creates_final_gate": False,
        "does_not_replace": [
            "SceneIntent",
            "ContinuityTracker",
            "C05-S DirectedVisualBeat",
            "C05-MR materialization",
            "BUILD-03 idempotency",
            "semantic_coverage",
        ],
        "unknown_as_pass": False,
    }


def apply_retrieval_to_materialization_unit(
    unit: Mapping[str, Any],
    retrieval_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach selected candidate hint onto a C05-MR unit without approving publishability."""
    row = dict(unit or {})
    vr = dict(retrieval_evidence or {})
    inner = dict(vr.get("visual_retrieval") or vr)
    selected = inner.get("selected")
    row["retrieval_status"] = inner.get("retrieval_status") or inner.get("status")
    row["retrieval_fallback_generation_allowed"] = bool(inner.get("fallback_generation_allowed"))
    if selected and (selected.get("asset") or {}).get("asset_id"):
        asset = selected["asset"]
        if not row.get("asset_id"):
            row["asset_id"] = asset.get("asset_id")
        row["retrieval_candidate"] = {
            "asset_id": asset.get("asset_id"),
            "source": asset.get("source"),
            "source_url": asset.get("source_url"),
            "local_path": asset.get("local_path"),
            "media_type": asset.get("media_type"),
            "content_hash": asset.get("content_hash"),
            "candidate_score": selected.get("candidate_score"),
            "scores": {
                "semantic": selected.get("semantic_score"),
                "entity": selected.get("entity_score"),
                "relationship": selected.get("relationship_score"),
                "location": selected.get("location_score"),
                "technical": selected.get("technical_score"),
                "continuity": selected.get("continuity_score"),
            },
            "score_mark": selected.get("score_mark"),
        }
        row["prefer_real_footage"] = True
        row["skip_ai_generation_if_semantic_ok"] = True
    else:
        row["prefer_real_footage"] = False
        row["skip_ai_generation_if_semantic_ok"] = False
    row["retrieval_does_not_grant_publishability"] = True
    return row
