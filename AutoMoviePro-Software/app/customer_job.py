"""C01-A — Customer-facing production job adapter (view model over store.jobs).

Authority:
  - Persistence: app.db jobs table (extended columns; soft migration)
  - Live phases: pipeline.live_activity
  - Pipeline outcomes: upload_status from generate_video / publishability
  - Idempotency: existing BUILD-03 / product_registry / live already_running

Does NOT create a second job engine, quality engine, or idempotency layer.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app import db as store

logger = logging.getLogger(__name__)

# Customer-facing semantic states (C01-A + C01-B)
CUSTOMER_STATES = (
    "DRAFT",
    "QUEUED",
    "STARTING",
    "PREPARING",
    "GENERATING",
    "VALIDATING",
    "REPAIRING",
    "RENDERING",
    "PREPARING_REVIEW",
    "READY_FOR_REVIEW",
    "FAILED",
    "INTERRUPTED",
    "RECOVERING",
    "CANCELLED",
    "COMPLETED",
)

# Monotonic ordinal for stale-response protection (higher = later / terminal)
STATE_ORDINAL: Dict[str, int] = {
    "DRAFT": 0,
    "QUEUED": 10,
    "STARTING": 20,
    "PREPARING": 20,
    "RECOVERING": 25,
    "GENERATING": 30,
    "VALIDATING": 40,
    "REPAIRING": 45,
    "RENDERING": 50,
    "PREPARING_REVIEW": 55,
    "READY_FOR_REVIEW": 90,
    "COMPLETED": 95,
    "FAILED": 100,
    "INTERRUPTED": 100,
    "CANCELLED": 100,
}

TERMINAL_CUSTOMER_STATES = frozenset(
    {"READY_FOR_REVIEW", "FAILED", "INTERRUPTED", "CANCELLED", "COMPLETED"}
)

# Fields allowed in customer projection (C01-B security boundary)
CUSTOMER_VIEW_FIELDS = frozenset(
    {
        "job_id",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "failed_at",
        "requested_by",
        "request_type",
        "channel_id",
        "state",
        "state_ordinal",
        "revision",
        "stage",
        "stage_label",
        "production_stage",
        "progress_percent",
        "duration_sec",
        "error_class",
        "error_summary",
        "recoverable",
        "retry_supported",
        "next_action",
        "artifact_available",
        "artifact_path",
        "package_path",
        "title",
        "upload_status",
        "quality",
        "result_planes",
        "verification",
        "trace_id",
        "live_correlation_id",
        "publishable",
        "terminal",
        "approval_state",
        "approval",
        "lang_code",
        "production_plan_id",
        "production_plan_revision",
        "script_revision",
        "generation_fingerprint",
        "execution_phase",
    }
)

# Internal upload_status values used for in-flight customer jobs (not uploadable)
IN_FLIGHT_UPLOAD_STATUSES = frozenset({"queued", "running", "preparing", "generating", "validating", "repairing", "rendering"})

# Terminal upload statuses that are NOT ready for customer review upload path
FAILED_UPLOAD_STATUSES = frozenset(
    {"failed", "quality_blocked", "missing_file", "interrupted", "cancelled"}
)

PHASE_TO_CUSTOMER_STATE: Dict[str, str] = {
    "idle": "DRAFT",
    "starting": "STARTING",
    "generate": "GENERATING",
    "generate_short": "GENERATING",
    "generate_long": "GENERATING",
    "director": "GENERATING",
    "humanize": "GENERATING",
    "scenes": "GENERATING",
    "scene": "GENERATING",
    "tts": "GENERATING",
    "visual": "GENERATING",
    "localize": "VALIDATING",
    "compose": "RENDERING",
    "package": "PREPARING_REVIEW",
    "upload_check": "PREPARING_REVIEW",
    "done": "READY_FOR_REVIEW",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
}

PHASE_TO_PRODUCTION_STAGE: Dict[str, str] = {
    "starting": "Preparing",
    "generate": "Preparing",
    "director": "Intelligence",
    "humanize": "Script",
    "scenes": "Scene Planning",
    "scene": "Scene Planning",
    "tts": "Audio Generation",
    "visual": "Visual Generation",
    "localize": "Validation",
    "compose": "Rendering",
    "package": "Final Verification",
    "upload_check": "Final Verification",
    "done": "Ready for Review",
    "failed": "Failed",
}

UPLOAD_STATUS_TO_CUSTOMER: Dict[str, str] = {
    "queued": "QUEUED",
    "preparing": "STARTING",
    "running": "GENERATING",
    "generating": "GENERATING",
    "validating": "VALIDATING",
    "repairing": "REPAIRING",
    "rendering": "RENDERING",
    "generated": "VALIDATING",  # produced artifacts; not yet ready_to_upload
    "ready_to_upload": "READY_FOR_REVIEW",
    "dry_run_uploaded": "COMPLETED",
    "uploaded": "COMPLETED",
    "failed": "FAILED",
    "quality_blocked": "FAILED",
    "missing_file": "FAILED",
    "interrupted": "INTERRUPTED",
    "cancelled": "CANCELLED",
}

STAGE_LABELS: Dict[str, str] = {
    "QUEUED": "Queued for generation",
    "STARTING": "Starting…",
    "PREPARING": "Preparing…",
    "GENERATING": "Generating…",
    "VALIDATING": "Validating quality…",
    "REPAIRING": "Repairing…",
    "RENDERING": "Rendering…",
    "PREPARING_REVIEW": "Preparing review package…",
    "READY_FOR_REVIEW": "Ready for review",
    "FAILED": "Failed",
    "INTERRUPTED": "Interrupted — recovery required",
    "RECOVERING": "Recovering…",
    "CANCELLED": "Cancelled",
    "COMPLETED": "Completed",
    "DRAFT": "Draft",
}


def ensure_job_columns() -> None:
    """Soft-migrate jobs table for C01-A customer metadata."""
    with store.db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = [
            ("customer_state", "TEXT"),
            ("customer_stage", "TEXT"),
            ("trace_id", "TEXT"),
            ("error_class", "TEXT"),
            ("updated_at", "TEXT"),
            ("live_correlation_id", "TEXT"),
            ("quality_summary", "TEXT"),
            ("recoverable", "INTEGER DEFAULT 0"),
            ("requested_by", "TEXT"),
            ("customer_approval", "TEXT"),
            ("customer_approval_at", "TEXT"),
            # C06-D immutable plan snapshot refs (extend existing job — no second engine)
            ("production_plan_id", "TEXT"),
            ("production_plan_revision", "TEXT"),
            ("script_revision", "TEXT"),
            ("generation_fingerprint", "TEXT"),
            ("plan_snapshot_json", "TEXT"),
        ]
        for name, typ in migrations:
            if name not in cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")


def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        return dict(row) if row else None


def classify_error(message: str) -> str:
    """Map exception/error text → customer error class (no secrets)."""
    raw = str(message or "").strip()
    low = raw.lower()
    if not raw:
        return "unknown_unclassified"
    if "cancelled_by_user" in low or "cancelled" == low:
        return "cancelled"
    if any(x in low for x in ("channel_not_found", "missing_", "validation", "invalid_")):
        return "validation_failure"
    if any(x in low for x in ("app_inactive", "api_readiness", "login_required", "config")):
        return "configuration_failure"
    if any(x in low for x in ("quota", "rate_limit", "429")):
        return "provider_failure"
    if any(x in low for x in ("provider", "openrouter", "agnes", "timeout", "connection", "network")):
        return "provider_failure"
    if "publishability_blocked" in low or "quality_blocked" in low or "creative_quality" in low:
        return "quality_rejection"
    if any(x in low for x in ("artifact", "multimodal", "audio_quality", "localization")):
        return "quality_rejection"
    if any(x in low for x in ("render", "ffmpeg", "ffprobe", "compose", "mux")):
        return "rendering_failure"
    if any(x in low for x in ("interrupted", "restart", "infrastructure", "disk", "database")):
        return "infrastructure_failure"
    if "generation" in low or "generate" in low:
        return "generation_failure"
    return "unknown_unclassified"


def sanitize_customer_error(message: str, limit: int = 240) -> str:
    """Concise customer-facing error — strip key-like tokens."""
    s = " ".join(str(message or "").replace("\r", " ").split())
    s = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", s)
    s = re.sub(r"\bAIza[0-9A-Za-z\-_]{10,}\b", "[redacted]", s)
    s = re.sub(r"\bsk-[0-9A-Za-z]{10,}\b", "[redacted]", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _now() -> str:
    return datetime.now().isoformat()


def create_generation_job(
    *,
    channel_id: int,
    video_type: str,
    requested_by: str = "",
    title_hint: str = "",
    production_plan_id: str = "",
    production_plan_revision: str = "",
    script_revision: str = "",
    generation_fingerprint: str = "",
    plan_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist authoritative customer job BEFORE pipeline execution."""
    ensure_job_columns()
    video_type = "long" if video_type == "long" else "short"
    trace_id = uuid.uuid4().hex
    title = title_hint or f"{video_type} generation (in progress)"
    job_id = store.add_job(
        {
            "channel_id": int(channel_id),
            "video_type": video_type,
            "title": title,
            "description": "",
            "tags": "",
            "local_path": "",
            "platform": "local",
            "upload_status": "queued",
            "error": None,
            "lang_code": "en",
        }
    )
    snap_json = None
    if plan_snapshot is not None:
        snap_json = json.dumps(plan_snapshot, ensure_ascii=False, default=str)
    store.update_job(
        int(job_id),
        customer_state="QUEUED",
        customer_stage="QUEUED",
        trace_id=trace_id,
        error_class=None,
        updated_at=_now(),
        live_correlation_id=None,
        quality_summary=None,
        recoverable=0,
        requested_by=(requested_by or "customer")[:120],
        production_plan_id=(production_plan_id or "")[:160] or None,
        production_plan_revision=(production_plan_revision or "")[:128] or None,
        script_revision=(script_revision or "")[:128] or None,
        generation_fingerprint=(generation_fingerprint or "")[:128] or None,
        plan_snapshot_json=snap_json,
    )
    row = get_job(int(job_id))
    assert row is not None
    return row


def set_live_correlation(job_id: int, live_id: str) -> None:
    ensure_job_columns()
    store.update_job(int(job_id), live_correlation_id=str(live_id or ""), updated_at=_now())


def update_customer_progress(
    job_id: int,
    *,
    customer_state: str,
    stage: Optional[str] = None,
    upload_status: Optional[str] = None,
    detail: str = "",
) -> None:
    ensure_job_columns()
    state = str(customer_state or "").upper()
    if state not in CUSTOMER_STATES:
        state = "GENERATING"
    fields: Dict[str, Any] = {
        "customer_state": state,
        "customer_stage": stage or state,
        "updated_at": _now(),
    }
    if upload_status is not None:
        fields["upload_status"] = upload_status
    if detail and state in ("GENERATING", "PREPARING", "VALIDATING", "RENDERING", "REPAIRING"):
        # Keep title stable; put detail in description only if still placeholder
        row = get_job(int(job_id))
        if row and "(in progress)" in str(row.get("title") or ""):
            fields["description"] = sanitize_customer_error(detail, 160)
    store.update_job(int(job_id), **fields)


def mark_failed(job_id: int, error: Any, *, recoverable: bool = True) -> None:
    ensure_job_columns()
    msg = sanitize_customer_error(str(error))
    err_class = classify_error(str(error))
    if err_class == "cancelled":
        state = "CANCELLED"
        upload = "cancelled"
    elif "interrupted" in str(error).lower():
        state = "INTERRUPTED"
        upload = "interrupted"
    else:
        state = "FAILED"
        upload = "failed"
    store.update_job(
        int(job_id),
        upload_status=upload,
        error=msg,
        error_class=err_class,
        customer_state=state,
        customer_stage=state,
        recoverable=1 if recoverable and state in ("FAILED", "INTERRUPTED") else 0,
        updated_at=_now(),
    )


def mark_from_pipeline_result(job_id: int, result: Optional[Dict[str, Any]]) -> None:
    """Map generate_video result → customer terminal state (C01-A stops at review readiness)."""
    ensure_job_columns()
    result = result or {}
    upload_status = str(result.get("upload_status") or "").strip()
    quality = {
        "upload_status": upload_status,
        "publishable": upload_status == "ready_to_upload",
        "local_path": result.get("local_path") or result.get("final_path"),
        "package_path": result.get("package_path"),
        "title": result.get("title"),
    }
    if upload_status == "ready_to_upload":
        customer_state = "READY_FOR_REVIEW"
    elif upload_status in FAILED_UPLOAD_STATUSES:
        customer_state = "FAILED"
    elif upload_status == "generated":
        # Generated without ready_to_upload must NOT be treated as ready
        customer_state = "FAILED"
        quality["publishable"] = False
        quality["note"] = "generated_but_not_ready_to_upload"
    else:
        customer_state = "FAILED"
        quality["note"] = "unknown_terminal_upload_status"
        quality["publishable"] = False

    fields: Dict[str, Any] = {
        "customer_state": customer_state,
        "customer_stage": customer_state,
        "quality_summary": json.dumps(quality, ensure_ascii=False, default=str),
        "updated_at": _now(),
        "recoverable": 1 if customer_state == "FAILED" else 0,
    }
    if result.get("title"):
        fields["title"] = result.get("title")
    if result.get("description") is not None:
        fields["description"] = result.get("description")
    if result.get("local_path") or result.get("final_path"):
        fields["local_path"] = result.get("local_path") or result.get("final_path")
    if upload_status:
        fields["upload_status"] = upload_status
    if customer_state == "FAILED" and not result.get("error"):
        fields["error"] = sanitize_customer_error(
            quality.get("note") or f"terminal_status:{upload_status or 'unknown'}"
        )
        fields["error_class"] = classify_error(fields["error"])
    store.update_job(int(job_id), **fields)


def sync_from_live_phase(job_id: int, phase: str, detail: str = "") -> None:
    """Best-effort progress sync from live_activity phases — no fabricated %."""
    phase_l = str(phase or "").strip().lower()
    if phase_l in ("done", "failed", "cancelled"):
        return  # terminal handled by finish/mark_*
    state = PHASE_TO_CUSTOMER_STATE.get(phase_l, "GENERATING")
    upload_map = {
        "STARTING": "preparing",
        "PREPARING": "preparing",
        "GENERATING": "generating",
        "VALIDATING": "validating",
        "REPAIRING": "repairing",
        "RENDERING": "rendering",
        "PREPARING_REVIEW": "rendering",
        "QUEUED": "queued",
    }
    update_customer_progress(
        int(job_id),
        customer_state=state,
        stage=state,
        upload_status=upload_map.get(state),
        detail=detail,
    )


def map_customer_state(
    row: Dict[str, Any],
    *,
    live: Optional[Dict[str, Any]] = None,
) -> str:
    """Derive customer state from DB + optional live snapshot. Never invent success."""
    stored = str(row.get("customer_state") or "").upper()
    upload = str(row.get("upload_status") or "").strip().lower()

    # Live active for this job wins for in-flight display
    if live and live.get("active"):
        live_db = str(live.get("db_job_id") or "")
        live_corr = str(live.get("job_id") or "")
        row_corr = str(row.get("live_correlation_id") or "")
        if live_db and str(row.get("id")) == str(live_db):
            phase = str(live.get("phase") or "").lower()
            return PHASE_TO_CUSTOMER_STATE.get(phase, "GENERATING")
        if row_corr and live_corr and row_corr == live_corr:
            phase = str(live.get("phase") or "").lower()
            return PHASE_TO_CUSTOMER_STATE.get(phase, "GENERATING")

    if upload == "interrupted":
        return "INTERRUPTED"
    if upload in ("failed", "quality_blocked", "missing_file"):
        return "FAILED"
    if upload == "cancelled":
        return "CANCELLED"
    if upload == "ready_to_upload":
        return "READY_FOR_REVIEW"

    # Normalize C01-A PREPARING → still valid
    if stored == "PREPARING":
        stored = "STARTING"
    if stored in CUSTOMER_STATES:
        return stored

    mapped = UPLOAD_STATUS_TO_CUSTOMER.get(upload)
    if mapped:
        return mapped
    return "FAILED"  # unknown ≠ success


def state_ordinal(state: str) -> int:
    return int(STATE_ORDINAL.get(str(state or "").upper(), 0))


def build_revision(updated_at: str, state: str, upload_status: str) -> str:
    return f"{updated_at or ''}|{state or ''}|{upload_status or ''}"


def is_newer_projection(incoming: Dict[str, Any], current: Optional[Dict[str, Any]]) -> bool:
    """Stale-response guard: True if incoming should replace current."""
    if not current:
        return True
    iu = str(incoming.get("updated_at") or "")
    cu = str(current.get("updated_at") or "")
    if iu and cu:
        if iu > cu:
            return True
        if iu < cu:
            return False
    return state_ordinal(str(incoming.get("state") or "")) >= state_ordinal(str(current.get("state") or ""))


def is_terminal_state(state: str) -> bool:
    return str(state or "").upper() in TERMINAL_CUSTOMER_STATES


def next_action_for(state: str, *, recoverable: bool, error_class: Optional[str] = None) -> Optional[str]:
    st = str(state or "").upper()
    if st in ("FAILED", "INTERRUPTED") and recoverable:
        return "Start a new Generate after fixing the cause (no silent auto-resume)."
    if st == "CANCELLED":
        return "Start a new Generate if you still need a video."
    if st == "READY_FOR_REVIEW":
        return "Review the result. Publishing is not part of this workspace stage."
    if error_class == "configuration_failure":
        return "Fix channel API / media readiness, then Generate again."
    return None


def to_customer_view(
    row: Dict[str, Any],
    *,
    live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Adapter: DB job (+ live) → customer job contract (projection only)."""
    ensure_job_columns()
    state = map_customer_state(row, live=live)
    if state == "PREPARING":
        state = "STARTING"
    upload = str(row.get("upload_status") or "")
    quality_raw = row.get("quality_summary")
    quality: Any = None
    if quality_raw:
        try:
            quality = json.loads(quality_raw) if isinstance(quality_raw, str) else quality_raw
        except Exception:
            quality = {"raw": sanitize_customer_error(str(quality_raw), 120)}

    publishable = False
    if isinstance(quality, dict) and "publishable" in quality:
        publishable = bool(quality.get("publishable"))
    elif upload == "ready_to_upload" and state == "READY_FOR_REVIEW":
        publishable = True

    path_exists = bool(str(row.get("local_path") or "").strip())
    # Honest planes — file existence ≠ verified
    planes = {
        "generated": path_exists or upload in ("generated", "ready_to_upload", "dry_run_uploaded", "uploaded"),
        "file_exists": path_exists,
        "technically_verified": publishable,  # gates passed (publishability)
        "quality_verified": publishable,
        "render_verified": publishable,  # RI is AND'd into publishability in production
        "ready_for_review": state == "READY_FOR_REVIEW" and publishable,
        "approved": False,
        "published": upload in ("uploaded", "dry_run_uploaded"),
        # C01-A aliases retained
        "technically_valid": publishable,
        "quality_validated": publishable,
        "rendered": path_exists,
    }

    verification = {
        "artifact_available": path_exists,
        "artifact_verified": publishable,
        "publishable": publishable,
        "note": (
            "Publishability/Artifact Verification/Rendering Integrity remain authoritative; "
            "file existence alone is never PASS"
        ),
    }

    created = row.get("created_at") or ""
    updated = row.get("updated_at") or created
    started_at = created
    completed_at = None
    failed_at = None
    if state == "READY_FOR_REVIEW" or state == "COMPLETED":
        completed_at = updated
    if state in ("FAILED", "INTERRUPTED", "CANCELLED"):
        failed_at = updated

    duration_sec = None
    try:
        if live and live.get("active") and str(live.get("db_job_id") or "") == str(row.get("id")):
            duration_sec = live.get("elapsed_sec")
        elif created and updated and created != updated:
            from datetime import datetime as dt

            duration_sec = round(
                (dt.fromisoformat(str(updated)) - dt.fromisoformat(str(created))).total_seconds(),
                1,
            )
    except Exception:
        duration_sec = None

    err = sanitize_customer_error(row.get("error") or "")
    err_class = row.get("error_class") or (classify_error(err) if err else None)
    if state in ("FAILED", "INTERRUPTED") and not err:
        err = "Job failed or was interrupted"
        err_class = err_class or "unknown_unclassified"

    production_stage = STAGE_LABELS.get(state, state)
    stage_label = production_stage
    if live and live.get("active") and str(live.get("db_job_id") or "") == str(row.get("id")):
        phase = str(live.get("phase") or "").lower()
        production_stage = PHASE_TO_PRODUCTION_STAGE.get(phase, production_stage)
        detail = str(live.get("detail") or "").strip()
        stage_label = detail or production_stage

    recoverable = bool(row.get("recoverable")) if state in ("FAILED", "INTERRUPTED") else False
    # No same-job retry engine — recoverable means new Generate only
    retry_supported = False

    approval_state = str(row.get("customer_approval") or "").strip().upper() or None
    if approval_state not in ("APPROVED", "REJECTED", "READY_FOR_REVIEW", "NOT_READY"):
        approval_state = None
    approval_obj = None
    if approval_state:
        approval_obj = {
            "state": approval_state,
            "updated_at": row.get("customer_approval_at"),
            "publishes": False,
        }

    raw = {
        "job_id": int(row["id"]),
        "created_at": created,
        "updated_at": updated,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "requested_by": row.get("requested_by") or "customer",
        "request_type": row.get("video_type") or "short",
        "channel_id": row.get("channel_id"),
        "lang_code": row.get("lang_code"),
        "state": state,
        "state_ordinal": state_ordinal(state),
        "revision": build_revision(str(updated), state, upload),
        "stage": row.get("customer_stage") or state,
        "stage_label": stage_label,
        "production_stage": production_stage,
        "progress_percent": None,
        "duration_sec": duration_sec,
        "error_class": err_class,
        "error_summary": err or None,
        "recoverable": recoverable,
        "retry_supported": retry_supported,
        "next_action": next_action_for(state, recoverable=recoverable, error_class=err_class),
        "artifact_available": path_exists,
        "artifact_path": row.get("local_path") or None,
        "package_path": row.get("package_path") or None,
        "title": row.get("title"),
        "upload_status": upload,
        "quality": quality if isinstance(quality, dict) else None,
        "result_planes": planes,
        "verification": verification,
        "trace_id": row.get("trace_id"),
        "live_correlation_id": row.get("live_correlation_id"),
        "publishable": publishable,
        "terminal": is_terminal_state(state),
        "approval_state": approval_state,
        "approval": approval_obj,
        "production_plan_id": row.get("production_plan_id"),
        "production_plan_revision": row.get("production_plan_revision"),
        "script_revision": row.get("script_revision"),
        "generation_fingerprint": row.get("generation_fingerprint"),
        "execution_phase": row.get("customer_stage") or state,
    }
    return {k: v for k, v in raw.items() if k in CUSTOMER_VIEW_FIELDS}


def list_customer_jobs(
    limit: int = 100,
    *,
    live: Optional[Dict[str, Any]] = None,
    channel_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """List jobs as customer views. When channel_ids is set, filter to those channels only."""
    ensure_job_columns()
    rows = store.list_jobs(limit)
    if channel_ids is not None:
        allowed = {int(x) for x in channel_ids}
        rows = [r for r in rows if int(r.get("channel_id") or 0) in allowed]
    return [to_customer_view(r, live=live) for r in rows]


def job_owned_by_channels(row: Optional[Dict[str, Any]], channel_ids: List[int]) -> bool:
    if not row:
        return False
    allowed = {int(x) for x in channel_ids}
    return int(row.get("channel_id") or 0) in allowed


def set_customer_approval(job_id: int, decision: str) -> Dict[str, Any]:
    """Customer workflow approval only — never marks uploaded/published."""
    ensure_job_columns()
    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "job_not_found"}
    state = map_customer_state(row)
    if state != "READY_FOR_REVIEW":
        return {
            "ok": False,
            "error": "not_ready_for_approval",
            "error_code": "approval_not_ready",
            "state": state,
        }
    upload = str(row.get("upload_status") or "")
    if upload != "ready_to_upload":
        return {
            "ok": False,
            "error": "not_publishable_for_review",
            "error_code": "approval_not_ready",
        }
    dec = str(decision or "").strip().lower()
    if dec in ("reject", "rejected"):
        approval = "REJECTED"
        store.update_job(
            int(job_id),
            customer_approval=approval,
            customer_approval_at=_now(),
            updated_at=_now(),
        )
        return {
            "ok": True,
            "job_id": int(job_id),
            "approval_state": approval,
            "publishes": False,
            "note": "Customer workflow approval only — does not publish/upload/schedule",
            "job": to_customer_view(get_job(int(job_id)) or row),
        }
    if dec not in ("approve", "approved"):
        return {"ok": False, "error": "invalid_decision", "error_code": "validation_failure"}
    # Gate A: APPROVED cannot bypass duration reconciliation
    try:
        from pathlib import Path

        from pipeline.duration_budget import (
            load_duration_reconciliation,
            reconcile_rendered_duration,
            resolve_duration_contract,
        )

        local_path = str(row.get("local_path") or "").strip()
        work_dir = Path(local_path).parent if local_path else None
        recon = load_duration_reconciliation(work_dir) if work_dir else None
        if recon is None and local_path and Path(local_path).is_file():
            try:
                from pipeline.compose import ffprobe_duration

                actual = ffprobe_duration(Path(local_path))
            except Exception:
                actual = None
            vt = str(row.get("video_type") or "short")
            recon = reconcile_rendered_duration(
                actual_duration_sec=actual,
                contract=resolve_duration_contract(vt),
            )
        if recon is None:
            return {
                "ok": False,
                "error": "duration_reconciliation_missing",
                "error_code": "duration_blocked",
                "duration_status": "ABSENT",
            }
        dur_st = str(recon.get("status") or "UNKNOWN").upper()
        if dur_st != "PASS" or not recon.get("allows_approved"):
            return {
                "ok": False,
                "error": "duration_reconciliation_blocked",
                "error_code": "duration_blocked",
                "duration_status": dur_st,
                "blocks": recon.get("blocks") or [],
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"duration_approval_gate_error:{type(exc).__name__}",
            "error_code": "duration_blocked",
        }
    approval = "APPROVED"
    store.update_job(
        int(job_id),
        customer_approval=approval,
        customer_approval_at=_now(),
        updated_at=_now(),
        # Explicitly do NOT change upload_status to uploaded
    )
    return {
        "ok": True,
        "job_id": int(job_id),
        "approval_state": approval,
        "publishes": False,
        "note": "Customer workflow approval only — does not publish/upload/schedule",
        "job": to_customer_view(get_job(int(job_id)) or row),
    }


def partition_jobs(
    jobs: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Split into active vs recent (terminal/history) for workspace."""
    active: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    for j in jobs:
        if j.get("terminal") or is_terminal_state(str(j.get("state") or "")):
            recent.append(j)
        else:
            active.append(j)
    return {"active_jobs": active, "recent_jobs": recent}


def find_active_db_job_id() -> Optional[int]:
    ensure_job_columns()
    with store.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM jobs
            WHERE upload_status IN ('queued','preparing','running','generating','validating','repairing','rendering')
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        return int(row["id"]) if row else None


def reconcile_interrupted_jobs(*, live_active: bool = False) -> int:
    """On startup: in-flight jobs without a live worker become FAILED (no auto-resume duplication)."""
    ensure_job_columns()
    if live_active:
        return 0
    changed = 0
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM jobs
            WHERE upload_status IN ('queued','preparing','running','generating','validating','repairing','rendering')
            """
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
    for jid in ids:
        mark_failed(
            jid,
            "interrupted_by_restart:job was in-flight when the application stopped",
            recoverable=True,
        )
        # mark_failed sets upload_status failed; also stamp interrupted class already via classify
        store.update_job(jid, upload_status="interrupted", updated_at=_now())
        changed += 1
    if changed:
        logger.info("C01-A reconciled %s interrupted in-flight job(s)", changed)
    return changed


def apply_existing_job_update(
    job_id: int,
    *,
    title: str,
    description: str,
    tags: str,
    local_path: str,
) -> None:
    """Used by generate_video when existing_job_id is provided (instead of add_job)."""
    ensure_job_columns()
    store.update_job(
        int(job_id),
        title=title,
        description=description,
        tags=tags,
        local_path=local_path,
        platform="local",
        upload_status="generated",
        error=None,
        error_class=None,
        updated_at=_now(),
        customer_state="VALIDATING",
        customer_stage="VALIDATING",
    )
