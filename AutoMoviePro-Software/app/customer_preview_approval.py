"""C06-F — Customer Preview, Approval & Revision History (compose only).

Extends existing customer_job / customer_workspace — does NOT create
second job, generation, quality, publishability, or idempotency engines.

Approval ≠ publishing ≠ verification ≠ quality PASS.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR
from app.customer_job import (
    get_job,
    job_owned_by_channels,
    map_customer_state,
    sanitize_customer_error,
    to_customer_view,
)

CONTRACT_VERSION = "C06-F.1"
APPROVAL_STATES = ("PENDING", "APPROVED", "REJECTED")
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat()


def _safe_login(login_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (login_id or "anon").strip())[:80] or "anon"


def history_path(login_id: str, job_id: int) -> Path:
    return DATA_DIR / "customer_approval_history" / _safe_login(login_id) / f"job{int(job_id)}.json"


def load_history(login_id: str, job_id: int) -> Optional[Dict[str, Any]]:
    path = history_path(login_id, job_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(data.get("owner_login_id") or "") != str(login_id):
        return None
    if int(data.get("job_id") or 0) != int(job_id):
        return None
    return data


def save_history(data: Dict[str, Any]) -> Path:
    login_id = str(data.get("owner_login_id") or "")
    job_id = int(data.get("job_id") or 0)
    path = history_path(login_id, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    return path


def compute_revision_id(row: Dict[str, Any]) -> str:
    """Stable revision identity for a job artifact generation — not a second revision engine."""
    from pipeline.idempotency.fingerprint import hash_text
    from pipeline.idempotency.normalize import canonical_json

    payload = {
        "job_id": row.get("id"),
        "generation_fingerprint": row.get("generation_fingerprint"),
        "production_plan_id": row.get("production_plan_id"),
        "production_plan_revision": row.get("production_plan_revision"),
        "script_revision": row.get("script_revision"),
        "local_path": row.get("local_path"),
        "upload_status": row.get("upload_status"),
        "trace_id": row.get("trace_id"),
    }
    return hash_text(canonical_json(payload))[:32]


def _quality_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("quality_summary")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return {}


def _artifact_meta(path: Optional[str]) -> Dict[str, Any]:
    out = {
        "artifact_available": False,
        "duration_sec": None,
        "resolution": None,
        "path": None,
    }
    if not path:
        return out
    p = Path(str(path))
    out["path"] = str(p) if p.name else None
    if not p.is_file():
        return out
    out["artifact_available"] = True
    try:
        out["size_bytes"] = p.stat().st_size
    except Exception:
        out["size_bytes"] = None
    # Best-effort ffprobe — UNKNOWN if unavailable
    try:
        from pipeline.compose import ffprobe_duration, probe_media_tool_capability

        cap = probe_media_tool_capability()
        if cap.get("FFPROBE_AVAILABLE"):
            dur = ffprobe_duration(p)
            out["duration_sec"] = dur
        else:
            out["duration_sec"] = None
            out["duration_status"] = "UNKNOWN"
    except Exception:
        out["duration_status"] = "UNKNOWN"
    return out


def project_customer_preview(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Evidence-backed preview projection — never secrets, never false PASS."""
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, channel_ids):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    view = to_customer_view(row)
    quality = _quality_dict(row)
    planes = view.get("result_planes") or {}
    revision_id = compute_revision_id(row)
    art = _artifact_meta(row.get("local_path") or view.get("artifact_path"))

    verification = "UNKNOWN"
    if quality.get("artifact_verification"):
        verification = str(quality.get("artifact_verification")).upper()
    elif quality.get("verified") is True:
        verification = "VERIFIED"
    elif quality.get("verified") is False:
        verification = str(quality.get("artifact_verification") or "UNKNOWN").upper()

    # Prefer explicit quality publishable flag when present (evidence over upload_status alone)
    if "publishable" in quality:
        publishable = bool(quality.get("publishable"))
    else:
        publishable = bool(view.get("publishable") or planes.get("publishable"))
    ready_to_upload = str(row.get("upload_status") or "") == "ready_to_upload"
    generated = bool(planes.get("generated") or art["artifact_available"] or quality.get("generated"))

    approval_raw = str(row.get("customer_approval") or "").strip().upper()
    if approval_raw in ("APPROVED", "REJECTED"):
        approval_status = approval_raw
    elif ready_to_upload or map_customer_state(row) == "READY_FOR_REVIEW":
        approval_status = "PENDING"
    else:
        approval_status = "PENDING" if generated else "NOT_READY"

    hist = load_history(login_id, int(job_id))
    exec_mode = None
    if isinstance(quality, dict):
        exec_mode = quality.get("execution_mode")
        if quality.get("mock_is_not_real_media"):
            exec_mode = exec_mode or "MOCK_DETERMINISTIC"
        if quality.get("deterministic_fixtures"):
            exec_mode = exec_mode or "CUSTOMER_APPROVED_PLAN"

    if quality.get("verified") is True and publishable:
        quality_status = "PASS"
    elif quality.get("verified") is False:
        quality_status = "FAIL"
    else:
        quality_status = "UNKNOWN"

    return {
        "ok": True,
        "contract": CONTRACT_VERSION,
        "job_id": int(job_id),
        "plan_id": row.get("production_plan_id"),
        "plan_revision": row.get("production_plan_revision"),
        "revision_id": revision_id,
        "artifact_identity": {
            "local_path": art.get("path"),
            "generation_fingerprint": row.get("generation_fingerprint"),
            "trace_id": row.get("trace_id"),
        },
        "artifact_available": art["artifact_available"],
        "duration_sec": art.get("duration_sec"),
        "resolution": art.get("resolution"),  # may be None/UNKNOWN
        "language": row.get("lang_code"),
        "generation_mode": (quality.get("planes") or {}).get("modes")
        or quality.get("generation_modes")
        or row.get("video_type"),
        "verification_status": verification,
        "quality_status": quality_status,
        "publishability_status": "PUBLISHABLE" if publishable else "NOT_PUBLISHABLE",
        "ready_to_upload": ready_to_upload,
        "approval_status": approval_status if approval_status in APPROVAL_STATES or approval_status == "NOT_READY" else "PENDING",
        "current_revision": revision_id,
        "job_state": view.get("state"),
        "planes": {
            "generated": generated,
            "verified": bool(quality.get("verified") or planes.get("technically_verified")),
            "publishable": publishable,
            "ready_to_upload": ready_to_upload,
            "approved": approval_raw == "APPROVED",
            "published": False,
            "note": "PREVIEW available != VERIFIED != PUBLISHABLE != APPROVED != PUBLISHED",
        },
        "execution_mode": exec_mode,
        "mock_is_not_real_media": bool(quality.get("mock_is_not_real_media")),
        "deterministic_fixtures": bool(quality.get("deterministic_fixtures")),
        "history_count": len((hist or {}).get("entries") or []),
        "provenance": {
            "contract": CONTRACT_VERSION,
            "excludes_credentials": True,
            "publishes": False,
            "source": "customer_job + quality_summary + approval history",
        },
        "note": "File existence is never semantic PASS. UNKNOWN remains UNKNOWN.",
    }


def list_revision_history(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, channel_ids):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    hist = load_history(login_id, int(job_id)) or {
        "owner_login_id": login_id,
        "job_id": int(job_id),
        "entries": [],
    }
    current_rev = compute_revision_id(row)
    entries = list(hist.get("entries") or [])
    # Ensure current generation revision appears even without approval yet
    if not any(e.get("revision_id") == current_rev for e in entries):
        entries.append(
            {
                "revision_id": current_rev,
                "kind": "generation",
                "approval_status": str(row.get("customer_approval") or "PENDING").upper()
                if row.get("customer_approval")
                else "PENDING",
                "artifact_identity": row.get("local_path"),
                "generation_fingerprint": row.get("generation_fingerprint"),
                "created_at": row.get("created_at") or row.get("updated_at"),
                "current": True,
            }
        )
    else:
        for e in entries:
            e["current"] = e.get("revision_id") == current_rev

    # Sort: oldest first for history, rejected retained
    entries_sorted = sorted(entries, key=lambda e: str(e.get("created_at") or e.get("timestamp") or ""))
    return {
        "ok": True,
        "contract": CONTRACT_VERSION,
        "job_id": int(job_id),
        "current_revision": current_rev,
        "entries": entries_sorted,
        "note": "Rejected revisions remain visible; newer revisions do not erase history",
    }


def record_customer_approval(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
    decision: str,
    revision_id: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """PENDING→APPROVED/REJECTED. Does NOT publish/upload/schedule/regenerate.

    Job field write reuses existing ``set_customer_approval`` (no second approval DB writer).
    """
    from app.customer_job import set_customer_approval

    with _LOCK:
        row = get_job(int(job_id))
        if not row:
            return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
        if not job_owned_by_channels(row, channel_ids):
            return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
        requested = str(row.get("requested_by") or "").strip()
        if requested and requested != str(login_id).strip():
            return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

        current_rev = compute_revision_id(row)
        if revision_id and str(revision_id).strip() and str(revision_id).strip() != current_rev:
            return {
                "ok": False,
                "error": "stale_revision",
                "error_code": "stale_revision",
                "current_revision": current_rev,
                "requested_revision": revision_id,
            }

        path = row.get("local_path") or ""
        if not path or not os.path.isfile(str(path)):
            return {
                "ok": False,
                "error": "artifact_missing",
                "error_code": "artifact_missing",
            }

        dec = str(decision or "").strip().lower()
        if dec in ("approve", "approved"):
            approval = "APPROVED"
        elif dec in ("reject", "rejected"):
            approval = "REJECTED"
        else:
            return {"ok": False, "error": "invalid_decision", "error_code": "validation_failure"}

        reason_struct = None
        if approval == "REJECTED" and rejection_reason:
            reason = sanitize_customer_error(str(rejection_reason), 240)
            reason_struct = {
                "text": reason,
                "repair_hint": "targeted_repair_deferred",
                "authority_ref": "BUILD-04F",
                "auto_regenerate": False,
            }

        hist = load_history(login_id, int(job_id)) or {
            "contract": CONTRACT_VERSION,
            "owner_login_id": login_id,
            "job_id": int(job_id),
            "entries": [],
        }
        existing = str(row.get("customer_approval") or "").upper()
        if existing == approval:
            for e in reversed(hist.get("entries") or []):
                if e.get("revision_id") == current_rev and e.get("approval_status") == approval:
                    return {
                        "ok": True,
                        "reused": True,
                        "job_id": int(job_id),
                        "revision_id": current_rev,
                        "approval_status": approval,
                        "approval_state": approval,
                        "publishes": False,
                        "regenerates": False,
                        "schedules": False,
                        "uploads": False,
                        "note": "Duplicate approval — deterministic reuse",
                        "job": to_customer_view(row),
                    }

        prev_upload = str(row.get("upload_status") or "")
        # Existing C06-A writer — READY_FOR_REVIEW + ready_to_upload gates live there
        written = set_customer_approval(int(job_id), decision)
        if not written.get("ok"):
            return written

        after = get_job(int(job_id)) or row
        if str(after.get("upload_status") or "") != prev_upload:
            # Must never flip to uploaded/scheduled via approval
            if str(after.get("upload_status") or "") in ("uploaded", "dry_run_uploaded", "scheduled"):
                from app import db as store

                store.update_job(int(job_id), upload_status=prev_upload)
                return {"ok": False, "error": "publish_side_effect_blocked", "error_code": "integrity_failure"}

        entry = {
            "entry_id": uuid.uuid4().hex[:16],
            "kind": "approval",
            "revision_id": current_rev,
            "approval_status": approval,
            "login_id": login_id,
            "timestamp": _now(),
            "created_at": _now(),
            "artifact_identity": path,
            "generation_fingerprint": row.get("generation_fingerprint"),
            "plan_id": row.get("production_plan_id"),
            "plan_revision": row.get("production_plan_revision"),
            "rejection_reason": reason_struct,
            "publishes": False,
            "regenerates": False,
            "current": True,
        }
        for e in hist.get("entries") or []:
            e["current"] = False
        hist.setdefault("entries", []).append(entry)
        save_history(hist)

        return {
            "ok": True,
            "reused": False,
            "job_id": int(job_id),
            "revision_id": current_rev,
            "approval_status": approval,
            "approval_state": approval,
            "publishes": False,
            "regenerates": False,
            "schedules": False,
            "uploads": False,
            "rejection_reason": reason_struct,
            "note": "Customer approval only — does not publish/upload/schedule/regenerate",
            "job": to_customer_view(after),
        }


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat in (
        r"(?m)^\s*def\s+generate_video\s*\(",
        r"(?m)^\s*def\s+compute_fingerprint\s*\(",
        r"(?m)^\s*def\s+evaluate_publishability\s*\(",
        r"(?m)^\s*class\s+ContinuityTracker\b",
        r"(?m)^\s*def\s+materialize_visual_beats\s*\(",
    ):
        if _re.search(pat, source):
            bad.append(pat)
    return bad
