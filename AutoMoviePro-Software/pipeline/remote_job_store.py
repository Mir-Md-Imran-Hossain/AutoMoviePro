"""Persist remote provider job IDs for recovery (protocol §38)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def store_path(work_dir: Path) -> Path:
    return Path(work_dir) / "REMOTE_JOBS.json"


def load_jobs(work_dir: Path) -> Dict[str, Any]:
    p = store_path(work_dir)
    if not p.exists():
        return {"jobs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": {}}


def save_remote_job(
    work_dir: Path,
    *,
    generation_key: str,
    remote_job_id: str,
    provider: str = "agnes",
    scene_id: int = 0,
    status: str = "submitted",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = load_jobs(work_dir)
    jobs = data.setdefault("jobs", {})
    row = {
        "remote_job_id": remote_job_id,
        "provider": provider,
        "scene_id": scene_id,
        "generation_key": generation_key,
        "status": status,
        "updated_at": time.time(),
        "meta": dict(meta or {}),
    }
    jobs[generation_key] = row
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    store_path(work_dir).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return row


def get_remote_job(work_dir: Path, generation_key: str) -> Optional[Dict[str, Any]]:
    jobs = load_jobs(work_dir).get("jobs") or {}
    row = jobs.get(generation_key)
    return dict(row) if isinstance(row, dict) else None


def list_open_jobs(work_dir: Path) -> List[Dict[str, Any]]:
    jobs = load_jobs(work_dir).get("jobs") or {}
    return [dict(v) for v in jobs.values() if str(v.get("status") or "") not in ("done", "failed", "cancelled")]
