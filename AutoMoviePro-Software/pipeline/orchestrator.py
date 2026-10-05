"""Central orchestrator priorities P0–P5 (protocol §92)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR

PRIORITIES = {
    "P0": 0,  # active user generation
    "P1": 1,  # scheduled production
    "P2": 2,  # upload
    "P3": 3,  # comments/messages
    "P4": 4,  # pre-generation
    "P5": 5,  # health checks
}

QUEUE_PATH = Path(DATA_DIR) / "orchestrator_queue.json"


def _load() -> List[Dict[str, Any]]:
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return list(data.get("jobs") or [])
    except Exception:
        return []


def _save(jobs: List[Dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(
        json.dumps({"updated_at": time.time(), "jobs": jobs}, indent=2),
        encoding="utf-8",
    )


def enqueue(
    kind: str,
    *,
    priority: str = "P1",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pr = priority if priority in PRIORITIES else "P5"
    job = {
        "id": str(uuid.uuid4())[:12],
        "kind": kind,
        "priority": pr,
        "priority_rank": PRIORITIES[pr],
        "payload": dict(payload or {}),
        "state": "QUEUED",
        "created_at": time.time(),
    }
    try:
        from pipeline.contract_wiring.orchestrator_bridge import enrich_queue_payload

        job["payload"] = enrich_queue_payload(job["payload"])
    except Exception:
        pass
    try:
        from pipeline.idempotency.bridge import enrich_payload_with_idempotency

        job["payload"] = enrich_payload_with_idempotency(job["payload"])
    except Exception:
        pass
    jobs = _load()
    jobs.append(job)
    jobs.sort(key=lambda j: (int(j.get("priority_rank") or 99), float(j.get("created_at") or 0)))
    _save(jobs)
    return job


def next_job() -> Optional[Dict[str, Any]]:
    jobs = _load()
    for j in jobs:
        if j.get("state") == "QUEUED":
            j["state"] = "RUNNING"
            _save(jobs)
            return j
    return None


def complete(job_id: str, *, ok: bool = True) -> None:
    jobs = _load()
    for j in jobs:
        if j.get("id") == job_id:
            j["state"] = "DONE" if ok else "FAILED"
    _save([j for j in jobs if j.get("state") in ("QUEUED", "RUNNING")] + [
        j for j in jobs if j.get("state") not in ("QUEUED", "RUNNING")
    ][:200])


def snapshot() -> Dict[str, Any]:
    jobs = _load()
    return {
        "queued": sum(1 for j in jobs if j.get("state") == "QUEUED"),
        "running": sum(1 for j in jobs if j.get("state") == "RUNNING"),
        "top": jobs[:5],
    }
