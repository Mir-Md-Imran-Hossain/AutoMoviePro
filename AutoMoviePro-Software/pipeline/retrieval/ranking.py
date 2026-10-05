"""Explainable multi-factor candidate ranking — heuristics marked HEURISTIC."""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

from pipeline.retrieval.common import HEURISTIC


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def _coverage(required: Sequence[str], haystack: str) -> float:
    req = [r for r in (required or []) if str(r).strip()]
    if not req:
        return 1.0
    hay = _tokens(haystack)
    hits = 0
    for r in req:
        rt = _tokens(str(r))
        if rt & hay or str(r).lower() in haystack.lower():
            hits += 1
    return hits / max(1, len(req))


def media_type_preference(visual_mode: str, media_type: str) -> float:
    mode = (visual_mode or "IMAGE").upper()
    mt = (media_type or "").lower()
    if mode == "VIDEO":
        return 1.0 if mt == "video" else 0.25
    if mode in ("IMAGE", "IMAGE_WITH_MOTION"):
        return 1.0 if mt == "image" else 0.35
    return 0.5


def technical_score(asset: Mapping[str, Any], *, prefer_landscape: bool = True) -> float:
    w = int(asset.get("width") or 0)
    h = int(asset.get("height") or 0)
    dur = float(asset.get("duration") or 0.0)
    score = 0.4
    if w >= 1280 and h >= 720:
        score += 0.3
    elif w >= 640:
        score += 0.15
    if prefer_landscape and w >= h:
        score += 0.15
    elif not prefer_landscape and h >= w:
        score += 0.15
    if asset.get("media_type") == "video":
        if 2.0 <= dur <= 30.0:
            score += 0.15
        elif dur > 0:
            score += 0.05
    else:
        score += 0.1
    return min(1.0, score)


def source_reliability(source: str) -> float:
    s = (source or "").lower()
    table = {
        "local_licensed": 1.0,
        "local": 0.95,
        "pexels": 0.85,
        "customer_upload": 0.9,
        "unknown": 0.3,
    }
    return table.get(s, 0.5)


def continuity_compatibility(
    *,
    asset: Mapping[str, Any],
    prior_asset_ids: Sequence[str],
    allow_continuity_reuse: bool,
) -> tuple[float, str]:
    aid = str(asset.get("asset_id") or "")
    if not aid or aid not in set(prior_asset_ids or []):
        return 1.0, "no_prior_reuse"
    if allow_continuity_reuse:
        return 0.85, "valid_continuity_reuse_candidate"
    return 0.35, "identical_reuse_risk"


def rank_candidates(
    *,
    query: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    prior_asset_ids: Optional[Sequence[str]] = None,
    allow_continuity_reuse: bool = True,
) -> list[dict[str, Any]]:
    """
    Combine CLIP/semantic similarity with entity/relationship/location/tech/continuity.
    All non-model factors marked HEURISTIC.
    """
    qtext = str(query.get("query_text") or "")
    ranked: list[dict[str, Any]] = []
    for raw in candidates or []:
        c = dict(raw)
        asset = dict(c.get("asset") or c)
        caption = " ".join(
            str(x)
            for x in (
                asset.get("caption"),
                asset.get("title"),
                asset.get("tags"),
                asset.get("source_url"),
                asset.get("local_path"),
                qtext,
            )
            if x
        )
        # Prefer provided semantic_score (CLIP/FAISS); else token overlap HEURISTIC
        if c.get("semantic_score") is not None:
            sem = float(c["semantic_score"])
            sem_kind = str(c.get("semantic_kind") or "CLIP_OR_INDEX")
        else:
            qt = _tokens(qtext)
            ct = _tokens(caption)
            sem = (len(qt & ct) / max(1, len(qt))) if qt else 0.0
            sem_kind = HEURISTIC

        ent = _coverage(list(query.get("entities") or []) + list(query.get("objects") or []), caption)
        rel = _coverage(list(query.get("relationships") or []), caption)
        loc = _coverage([str(query.get("location") or "")], caption) if query.get("location") else 1.0
        tech = technical_score(asset)
        src = source_reliability(str(asset.get("source") or ""))
        cont, cont_note = continuity_compatibility(
            asset=asset,
            prior_asset_ids=list(prior_asset_ids or []),
            allow_continuity_reuse=allow_continuity_reuse,
        )
        media = media_type_preference(str(query.get("visual_mode") or "IMAGE"), str(asset.get("media_type") or ""))

        # Weighted blend — explainable
        candidate_score = (
            0.35 * sem
            + 0.15 * ent
            + 0.10 * rel
            + 0.10 * loc
            + 0.10 * tech
            + 0.10 * media
            + 0.05 * src
            + 0.05 * cont
        )
        ranked.append(
            {
                "asset": asset,
                "candidate_score": round(candidate_score, 6),
                "semantic_score": round(sem, 6),
                "semantic_kind": sem_kind,
                "entity_score": round(ent, 6),
                "relationship_score": round(rel, 6),
                "location_score": round(loc, 6),
                "technical_score": round(tech, 6),
                "media_score": round(media, 6),
                "source_score": round(src, 6),
                "continuity_score": round(cont, 6),
                "continuity_note": cont_note,
                "score_mark": HEURISTIC,
                "explanation": {
                    "weights": {
                        "semantic": 0.35,
                        "entity": 0.15,
                        "relationship": 0.10,
                        "location": 0.10,
                        "technical": 0.10,
                        "media": 0.10,
                        "source": 0.05,
                        "continuity": 0.05,
                    },
                    "mark": HEURISTIC,
                },
            }
        )
    ranked.sort(key=lambda x: x["candidate_score"], reverse=True)
    return ranked
