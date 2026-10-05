"""Generation idempotency — same generation_key must not call provider twice.

H3 DEF-H3-005: This is a *nested helper* under BUILD-03 runtimes
(visual/audio/script/render/subtitle). It is NOT a second idempotency authority.
Canonical claim/reuse remains IdempotentExecutor + IdempotencyStore.
Callers must continue to go through BUILD-03 bridges; do not write GenerationCache
independently of the executor claim path.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.idempotency.fs_lock import exclusive_path_lock

PIPELINE_VERSION = "marathon-v0"


def make_generation_key(
    *,
    scene_id: int,
    claim_id: str = "",
    narration: str = "",
    visual_prompt: str = "",
    provider: str = "",
    model: str = "",
    pipeline_version: str = PIPELINE_VERSION,
    size: str = "",
) -> str:
    raw = "|".join(
        [
            str(int(scene_id)),
            (claim_id or "").strip(),
            (narration or "").strip(),
            (visual_prompt or "").strip()[:500],
            (provider or "").strip().lower(),
            (model or "").strip().lower(),
            (pipeline_version or PIPELINE_VERSION).strip(),
            (size or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class GenerationCache:
    """Filesystem-backed idempotency for scene artifacts (legacy nested cache)."""

    def __init__(self, work_dir: Path):
        self.work = Path(work_dir)
        self.path = self.work / "GENERATION_CACHE.json"
        self._data: Dict[str, Any] = {"entries": {}, "create_count": 0, "reuse_count": 0}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._data.setdefault("entries", {})
        self._data.setdefault("create_count", 0)
        self._data.setdefault("reuse_count", 0)

    def _save(self) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def lookup(self, key: str) -> Optional[Dict[str, Any]]:
        with exclusive_path_lock(self.path):
            self._load()
            ent = (self._data.get("entries") or {}).get(key)
            if not isinstance(ent, dict):
                return None
            art = Path(str(ent.get("artifact") or ""))
            if art.is_file() and art.stat().st_size > 1000:
                return ent
            return None

    def request_create(
        self,
        key: str,
        *,
        artifact: Optional[Path] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Idempotent create request.
        Returns {action: 'reuse'|'create', artifact?, create_count, reuse_count}
        """
        with exclusive_path_lock(self.path):
            self._load()
            ent = (self._data.get("entries") or {}).get(key)
            if isinstance(ent, dict):
                art = Path(str(ent.get("artifact") or ""))
                if art.is_file() and art.stat().st_size > 1000:
                    self._data["reuse_count"] = int(self._data.get("reuse_count") or 0) + 1
                    self._save()
                    return {
                        "action": "reuse",
                        "artifact": ent.get("artifact"),
                        "create_count": int(self._data.get("create_count") or 0),
                        "reuse_count": int(self._data.get("reuse_count") or 0),
                        "key": key,
                    }
            self._data.setdefault("entries", {})[key] = {
                "status": "pending",
                "artifact": str(artifact or ""),
                "meta": dict(meta or {}),
            }
            self._data["create_count"] = int(self._data.get("create_count") or 0) + 1
            self._save()
            return {
                "action": "create",
                "artifact": str(artifact or ""),
                "create_count": int(self._data.get("create_count") or 0),
                "reuse_count": int(self._data.get("reuse_count") or 0),
                "key": key,
            }

    def commit(self, key: str, artifact: Path, *, meta: Optional[Dict[str, Any]] = None) -> None:
        with exclusive_path_lock(self.path):
            self._load()
            art = Path(artifact)
            self._data.setdefault("entries", {})[key] = {
                "status": "ready",
                "artifact": str(art),
                "meta": dict(meta or {}),
            }
            self._save()

    def stats(self) -> Dict[str, int]:
        with exclusive_path_lock(self.path):
            self._load()
            return {
                "create_count": int(self._data.get("create_count") or 0),
                "reuse_count": int(self._data.get("reuse_count") or 0),
            }
