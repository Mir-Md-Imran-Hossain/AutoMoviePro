"""
Persistent small-error notebook — accumulate low-level faults so admins see root causes.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _fingerprint(subsystem: str, fault_code: str, message: str, scene_idx: Optional[int] = None) -> str:
    norm = re.sub(r"\d+", "#", (message or "").strip().lower())[:240]
    raw = f"{subsystem}|{fault_code}|{scene_idx}|{norm}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]


def note_error(
    *,
    subsystem: str,
    fault_code: str,
    message: str,
    severity: str = "warn",
    job_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    scene_idx: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> int:
    """Record or bump a recurring small error. Returns note id."""
    try:
        from app import db as store

        fp = _fingerprint(subsystem, fault_code, message, scene_idx)
        return store.upsert_error_note(
            fingerprint=fp,
            subsystem=subsystem,
            fault_code=fault_code,
            message=(message or "")[:800],
            severity=severity or "warn",
            job_id=job_id,
            channel_id=channel_id,
            scene_idx=scene_idx,
            context=context or {},
        )
    except Exception as exc:
        logger.debug("error notebook write failed: %s", exc)
        return 0


def note_exception(
    *,
    subsystem: str,
    exc: BaseException,
    fault_code: str = "exception",
    severity: str = "error",
    job_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    scene_idx: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> int:
    return note_error(
        subsystem=subsystem,
        fault_code=fault_code,
        message=f"{type(exc).__name__}: {exc}",
        severity=severity,
        job_id=job_id,
        channel_id=channel_id,
        scene_idx=scene_idx,
        context=context,
    )


def summarize_open_notes(limit: int = 40) -> Dict[str, Any]:
    from app import db as store

    rows = store.list_error_notes(status="open", limit=limit)
    by_sub: Dict[str, int] = {}
    for r in rows:
        sub = str(r.get("subsystem") or "unknown")
        by_sub[sub] = by_sub.get(sub, 0) + int(r.get("count") or 1)
    return {
        "ok": True,
        "open_count": len(rows),
        "by_subsystem": by_sub,
        "notes": rows,
    }
