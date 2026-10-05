"""Duplicate / reuse risk evidence — does not replace BUILD-03."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def detect_reuse_risk(
    *,
    candidate_asset_id: str,
    candidate_content_hash: str,
    used_in_job: Sequence[Mapping[str, Any]],
    beat_id: str = "",
    scene_id: str = "",
    continuity_reuse_allowed: bool = True,
) -> dict[str, Any]:
    """
    Identical asset reuse in same scene/beat → evidence.
    Valid continuity reuse is NOT automatic failure.
    """
    issues: list[str] = []
    same_hash = []
    same_id = []
    for u in used_in_job or []:
        if candidate_content_hash and str(u.get("content_hash") or "") == candidate_content_hash:
            same_hash.append(u)
        if candidate_asset_id and str(u.get("asset_id") or "") == candidate_asset_id:
            same_id.append(u)

    identical = bool(same_hash or same_id)
    same_scene = [
        u
        for u in (same_hash + same_id)
        if scene_id and str(u.get("scene_id") or "") == str(scene_id)
    ]
    same_beat = [
        u
        for u in (same_hash + same_id)
        if beat_id and str(u.get("beat_id") or "") == str(beat_id)
    ]

    if same_beat:
        issues.append("identical_asset_same_beat")
    elif same_scene:
        issues.append("identical_asset_same_scene")
    elif identical and continuity_reuse_allowed:
        issues.append("identical_asset_continuity_reuse_ok")
    elif identical:
        issues.append("identical_asset_reuse_risk")

    failure = bool(same_beat)  # only same-beat identical is hard evidence fail hint
    return {
        "identical_reuse_detected": identical,
        "same_scene_reuse": bool(same_scene),
        "same_beat_reuse": bool(same_beat),
        "continuity_reuse_allowed": continuity_reuse_allowed,
        "automatic_failure": failure,
        "issues": issues,
        "build03_authority_unchanged": True,
        "note": "evidence_only_not_idempotency_authority",
    }
