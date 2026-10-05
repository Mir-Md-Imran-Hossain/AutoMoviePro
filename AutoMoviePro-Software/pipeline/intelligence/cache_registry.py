"""Cache invalidation registry (BUILD-04G-H)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

REGISTRY_PATH = DATA_DIR / "intelligence" / "cache_registry.json"


def _load() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"channels": {}, "prompts": {}, "research_scopes": {}}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"channels": {}, "prompts": {}, "research_scopes": {}}


def _save(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def bump_channel_version(channel_id: int, *, reason: str = "") -> int:
    data = _load()
    ch = data.setdefault("channels", {})
    key = str(channel_id)
    ver = int(ch.get(key, {}).get("version") or 0) + 1
    ch[key] = {"version": ver, "reason": reason, "timestamp": time.time()}
    _save(data)
    return ver


def bump_prompt_version(scope: str, *, version: str) -> int:
    data = _load()
    pr = data.setdefault("prompts", {})
    ver = int(pr.get(scope, {}).get("version") or 0) + 1
    pr[scope] = {"version": ver, "prompt_version": version, "timestamp": time.time()}
    _save(data)
    return ver


def bump_research_scope(scope_key: str) -> int:
    data = _load()
    rs = data.setdefault("research_scopes", {})
    ver = int(rs.get(scope_key, {}).get("version") or 0) + 1
    rs[scope_key] = {"version": ver, "timestamp": time.time()}
    _save(data)
    return ver


def get_channel_version(channel_id: int) -> int:
    data = _load()
    return int((data.get("channels") or {}).get(str(channel_id), {}).get("version") or 0)


def get_prompt_version(scope: str) -> int:
    data = _load()
    return int((data.get("prompts") or {}).get(scope, {}).get("version") or 0)


def is_ranking_stale(channel_id: int, cached_version: int) -> bool:
    return cached_version < get_channel_version(channel_id)


def ranking_cache_key(channel_id: int, fmt: str) -> str:
    return f"rank-{channel_id}-{fmt}-v{get_channel_version(channel_id)}"
