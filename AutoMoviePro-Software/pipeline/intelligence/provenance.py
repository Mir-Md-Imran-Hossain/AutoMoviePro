"""Provenance and invalidation (BUILD-04G-H)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pipeline.intelligence.cache_registry import bump_channel_version, bump_prompt_version, bump_research_scope


def record_topic_provenance(
    work_dir: Path,
    *,
    topic_id: str,
    discovery: dict[str, Any],
    ranking: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> Path:
    work_dir = Path(work_dir)
    entry = {
        "topic_id": topic_id,
        "discovery": discovery,
        "ranking": ranking or {},
        "research": research or {},
        "research_fingerprint": (research or {}).get("fingerprint"),
        "recorded_at": time.time(),
        "revision": discovery.get("revision_id", "r001"),
    }
    p = work_dir / "intelligence" / "provenance" / f"{topic_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def invalidate_ranking_on_channel_change(work_dir: Path, *, channel_id: int, reason: str = "channel_profile_changed") -> dict[str, Any]:
    ver = bump_channel_version(channel_id, reason=reason)
    return {"invalidated": True, "reason": reason, "channel_version": ver}


def invalidate_topic_cache_on_prompt_change(work_dir: Path, *, prompt_version: str) -> dict[str, Any]:
    ver = bump_prompt_version("topic_generation", version=prompt_version)
    return {"invalidated": True, "scope": "topic_generation", "prompt_version": prompt_version, "version": ver}


def invalidate_research_on_scope_change(scope_key: str) -> dict[str, Any]:
    ver = bump_research_scope(scope_key)
    return {"invalidated": True, "scope": scope_key, "version": ver}
