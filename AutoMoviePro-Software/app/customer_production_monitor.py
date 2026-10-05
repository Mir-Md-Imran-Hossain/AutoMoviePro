"""C06-H — Customer Production Monitoring & Control (projection / compose only).

Extends C06-G automation + C06-F planes + customer_job — no second engines.
No fake progress %. No publishing. Paid APIs = 0 for tests.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

CONTRACT_VERSION = "C06-H.1"

# Observability contract: MONITOR_STATE → source → label → action
STATE_CONTRACT: Dict[str, Dict[str, str]] = {
    "DRAFT": {"source": "customer_state|absence", "label": "Draft", "action": "Configure channel / plan"},
    "READY": {"source": "plan READY_FOR_GENERATION", "label": "Ready", "action": "Start Generate"},
    "QUEUED": {"source": "queue_status=queued", "label": "Queued", "action": "Wait for worker"},
    "WAITING": {"source": "next_retry_at|generation_busy", "label": "Waiting", "action": "Wait"},
    "RUNNING": {"source": "queue_status=running|GENERATING", "label": "Running", "action": "Wait"},
    "VERIFYING": {"source": "VALIDATING|upload validating", "label": "Verifying", "action": "Wait"},
    "PREVIEW_READY": {"source": "READY_FOR_REVIEW+artifact", "label": "Preview ready", "action": "Open preview"},
    "APPROVAL_PENDING": {"source": "READY_FOR_REVIEW+no approval", "label": "Approval pending", "action": "Approve or reject"},
    "APPROVED": {"source": "customer_approval=APPROVED", "label": "Approved", "action": "Publish when ready (C07-PUB)"},
    "PUBLISH_UPLOAD_ACCEPTED": {
        "source": "publish_status=UPLOAD_ACCEPTED",
        "label": "Upload accepted",
        "action": "Refresh status — not published yet",
    },
    "PUBLISH_REMOTE_PROCESSING": {
        "source": "publish_status=REMOTE_PROCESSING",
        "label": "Remote processing",
        "action": "Refresh status",
    },
    "PUBLISH_RECONCILIATION_REQUIRED": {
        "source": "publish_status=RECONCILIATION_REQUIRED",
        "label": "Reconciliation required",
        "action": "Do not blind re-upload",
    },
    "PUBLISHED": {"source": "publish_status=PUBLISHED", "label": "Published", "action": "None"},
    "COMPLETED": {"source": "customer_state=COMPLETED|uploaded", "label": "Completed", "action": "None"},
    "FAILED": {"source": "customer_state=FAILED", "label": "Failed", "action": "See failure category"},
    "RETRY_WAITING": {"source": "queue_status=queued+next_retry_at", "label": "Retry waiting", "action": "Wait for retry"},
    "CANCELLATION_REQUESTED": {"source": "cancel_requested=1+running", "label": "Cancellation requested", "action": "Wait for safe reconcile"},
    "CANCELLED": {"source": "CANCELLED|queue cancelled", "label": "Cancelled", "action": "Start new Generate if needed"},
    "INTERRUPTED": {"source": "INTERRUPTED|upload interrupted", "label": "Interrupted", "action": "Recovery queued or restart"},
    "TERMINAL_FAILED": {"source": "FAILED+non-recoverable", "label": "Terminal failure", "action": "Fix config / new job"},
    "ACTION_REQUIRED": {"source": "failure_category CUSTOMER_ACTION|CONFIGURATION", "label": "Action required", "action": "Resolve blocker"},
}

LIFECYCLE_EVENT_TYPES = (
    "JOB_CREATED",
    "JOB_READY",
    "JOB_QUEUED",
    "JOB_CLAIMED",
    "JOB_STARTED",
    "JOB_STAGE_CHANGED",
    "JOB_VERIFYING",
    "JOB_PREVIEW_READY",
    "JOB_APPROVAL_PENDING",
    "JOB_APPROVED",
    "JOB_REJECTED",
    "JOB_RETRY_WAITING",
    "JOB_RETRY_STARTED",
    "JOB_FAILED",
    "JOB_INTERRUPTED",
    "JOB_RECOVERED",
    "JOB_CANCELLATION_REQUESTED",
    "JOB_CANCELLED",
    "JOB_COMPLETED",
    # C07-PUB (same lifecycle_audit_json authority — not a second event store)
    "PUBLISH_REQUESTED",
    "PUBLISH_VALIDATION_FAILED",
    "PUBLISH_AUTH_REQUIRED",
    "PUBLISH_STARTED",
    "PUBLISH_UPLOAD_ACCEPTED",
    "PUBLISH_REMOTE_PROCESSING",
    "PUBLISH_REMOTE_SUCCEEDED",
    "PUBLISH_REMOTE_FAILED",
    "PUBLISH_RECONCILIATION_REQUIRED",
    "PUBLISH_FAILED",
    "PUBLISH_COMPLETED",
    # C07-SCHED
    "SCHEDULE_VALIDATION_STARTED",
    "SCHEDULE_VALIDATION_FAILED",
    "SCHEDULE_CREATED",
    "SCHEDULE_UPDATED",
    "SCHEDULE_CANCELLED",
    "SCHEDULE_DUE",
    "SCHEDULE_CLAIMED",
    "SCHEDULE_HANDOFF_STARTED",
    "SCHEDULE_HANDOFF_FAILED",
    "SCHEDULE_EXECUTION_STARTED",
    "SCHEDULE_EXECUTION_COMPLETED",
    "SCHEDULE_EXECUTION_FAILED",
    "SCHEDULE_MISSED",
    "SCHEDULE_RECONCILIATION_REQUIRED",
)

# Map legacy short event names → canonical C06-H types
_EVENT_NORMALIZE = {
    "enqueued": "JOB_QUEUED",
    "claimed": "JOB_CLAIMED",
    "execution_start": "JOB_STARTED",
    "execution_complete": "JOB_COMPLETED",
    "execution_failed": "JOB_FAILED",
    "retry_scheduled": "JOB_RETRY_WAITING",
    "terminal_failed": "JOB_FAILED",
    "cancel_requested": "JOB_CANCELLATION_REQUESTED",
    "cancelled": "JOB_CANCELLED",
    "cancelled_after_run": "JOB_CANCELLED",
    "interrupted_restart": "JOB_INTERRUPTED",
    "requeued_after_restart": "JOB_RECOVERED",
    "requeue_guard_busy": "JOB_QUEUED",
}

ENTRY_POINT_CLASSIFICATION = {
    "workspace_generate_queue": {
        "class": "CANONICAL",
        "path": "POST /api/workspace/generate queue=true → submit → tick → execute",
    },
    "workspace_generate_sync": {
        "class": "LEGACY_COMPAT",
        "path": "POST /api/workspace/generate default → start_customer_generation",
        "note": "Preserved for C06-D tests; UI prefers queue",
    },
    "api_generate_live": {
        "class": "LEGACY_COMPAT",
        "path": "POST /api/generate → run_in_background → generate_video",
    },
    "customer_queue_tick": {
        "class": "CANONICAL",
        "path": "SchedulerService.customer_queue_tick_job → scheduler_tick",
    },
    "idle_pregen": {
        "class": "LEGACY_COMPAT",
        "path": "idle_pregenerate → generate_video",
        "note": "Not customer production; generation_guard; blocked when live_lab_active",
    },
    "timed_fallback": {
        "class": "LEGACY_COMPAT",
        "path": "timed_upload fallback generate_video",
        "note": "Not customer production; generation_guard; blocked when live_lab_active",
    },
    "live_lab": {
        "class": "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        "also": "INTERNAL_LAB",
        "path": "pipeline/live_lab → generate_video (no generation_guard)",
        "note": "Must not masquerade as customer production; queue tick skips when active",
    },
}


def normalize_lifecycle_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    ev = dict(raw or {})
    name = str(ev.get("event") or ev.get("type") or "")
    canon = _EVENT_NORMALIZE.get(name, name if name in LIFECYCLE_EVENT_TYPES else name)
    ev["type"] = canon
    ev["event"] = canon
    return ev


def load_lifecycle_events(row: Optional[Dict[str, Any]], *, limit: int = 50) -> List[Dict[str, Any]]:
    if not row:
        return []
    raw = row.get("lifecycle_audit_json")
    try:
        data = json.loads(raw) if raw else {"events": []}
    except Exception:
        data = {"events": []}
    events = [normalize_lifecycle_event(e) for e in (data.get("events") or [])]
    return events[-int(limit) :]


def infer_execution_path(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "UNKNOWN"
    if row.get("queue_status") or row.get("queue_enqueued_at") or row.get("claim_token"):
        return "CANONICAL_QUEUE"
    if row.get("live_correlation_id"):
        return "LEGACY_COMPAT_LIVE"
    return "LEGACY_COMPAT_SYNC"


def infer_monitor_state(row: Optional[Dict[str, Any]]) -> str:
    """Truthful monitor state from persisted evidence only."""
    if not row:
        return "DRAFT"
    cancel_req = bool(int(row.get("cancel_requested") or 0))
    qstat = str(row.get("queue_status") or "")
    cust = str(row.get("customer_state") or "").upper()
    upload = str(row.get("upload_status") or "")
    approval = str(row.get("customer_approval") or "").upper()
    recoverable = bool(int(row.get("recoverable") or 0))
    fail_cat = str(row.get("failure_category") or "")

    if cust == "CANCELLED" or qstat == "cancelled" or upload == "cancelled":
        return "CANCELLED"
    if cancel_req and qstat in ("claimed", "running") and cust not in ("CANCELLED",):
        return "CANCELLATION_REQUESTED"
    # C07-PUB publication plane (distinct from APPROVED / ready_to_upload)
    pstat = str(row.get("publish_status") or "").upper()
    if pstat == "PUBLISHED":
        return "PUBLISHED"
    if pstat == "RECONCILIATION_REQUIRED":
        return "PUBLISH_RECONCILIATION_REQUIRED"
    if pstat == "REMOTE_PROCESSING":
        return "PUBLISH_REMOTE_PROCESSING"
    if pstat == "UPLOAD_ACCEPTED":
        return "PUBLISH_UPLOAD_ACCEPTED"
    if approval == "APPROVED":
        return "APPROVED"
    if cust == "INTERRUPTED" or upload == "interrupted":
        return "INTERRUPTED"
    if cust == "FAILED" or upload in ("failed", "quality_blocked"):
        if fail_cat in ("CONFIGURATION", "CUSTOMER_ACTION_REQUIRED", "CONTRACT", "STALE_PLAN"):
            return "ACTION_REQUIRED"
        if not recoverable and fail_cat:
            return "TERMINAL_FAILED"
        return "FAILED"
    if qstat == "queued" and row.get("next_retry_at"):
        return "RETRY_WAITING"
    if qstat == "queued":
        return "QUEUED"
    if qstat == "claimed":
        return "WAITING"
    if qstat == "running" or cust in ("GENERATING", "STARTING", "PREPARING", "REPAIRING", "RENDERING"):
        if cust in ("VALIDATING",) or upload == "validating":
            return "VERIFYING"
        return "RUNNING"
    if cust == "VALIDATING" or upload in ("validating", "generated"):
        return "VERIFYING"
    if cust == "READY_FOR_REVIEW" or upload == "ready_to_upload":
        if approval in ("", "PENDING") or not approval:
            # artifact check deferred to caller for PREVIEW_READY vs APPROVAL_PENDING
            return "APPROVAL_PENDING"
        if approval == "REJECTED":
            return "FAILED"
    if cust == "COMPLETED" or upload in ("uploaded", "dry_run_uploaded"):
        return "COMPLETED"
    if cust == "QUEUED":
        return "QUEUED"
    if cust == "DRAFT":
        return "DRAFT"
    return cust or "DRAFT"


def qualitative_progress(monitor_state: str) -> str:
    """Never invent percentage — qualitative stage only."""
    return {
        "QUEUED": "QUEUED",
        "WAITING": "WAITING",
        "RUNNING": "RUNNING",
        "VERIFYING": "VERIFYING",
        "RETRY_WAITING": "RETRY_WAITING",
        "CANCELLATION_REQUESTED": "CANCELLATION_REQUESTED",
        "PREVIEW_READY": "PREVIEW_READY",
        "APPROVAL_PENDING": "APPROVAL_PENDING",
        "APPROVED": "APPROVED",
        "COMPLETED": "COMPLETED",
        "FAILED": "FAILED",
        "ACTION_REQUIRED": "ACTION_REQUIRED",
        "INTERRUPTED": "INTERRUPTED",
        "CANCELLED": "CANCELLED",
        "TERMINAL_FAILED": "TERMINAL_FAILED",
    }.get(monitor_state, "UNKNOWN")


def is_live_lab_active() -> bool:
    try:
        from app import db as store

        return store.get_meta("live_lab_active") == "1"
    except Exception:
        return False


def classify_live_lab() -> Dict[str, Any]:
    return {
        **ENTRY_POINT_CLASSIFICATION["live_lab"],
        "active": is_live_lab_active(),
        "customer_production_allowed": False,
        "uses_generation_guard": False,
    }


def attention_signals(row: Optional[Dict[str, Any]], *, monitor_state: str) -> List[Dict[str, str]]:
    """Thin workspace notification projection — not a messaging platform."""
    signals: List[Dict[str, str]] = []
    if not row:
        return signals
    contract = STATE_CONTRACT.get(monitor_state) or {}
    if monitor_state in ("RUNNING", "VERIFYING", "QUEUED", "WAITING", "RETRY_WAITING"):
        signals.append({"kind": "job_waiting" if monitor_state != "RUNNING" else "job_started", "message": contract.get("label", monitor_state)})
    if monitor_state == "APPROVAL_PENDING":
        signals.append({"kind": "approval_required", "message": "Review and approve (does not publish)"})
    if monitor_state in ("FAILED", "TERMINAL_FAILED", "ACTION_REQUIRED"):
        signals.append(
            {
                "kind": "action_required" if monitor_state == "ACTION_REQUIRED" else "job_failed",
                "message": str(row.get("error") or row.get("failure_category") or "Failure"),
            }
        )
    if monitor_state == "CANCELLED":
        signals.append({"kind": "cancellation_completed", "message": "Job cancelled"})
    if monitor_state == "CANCELLATION_REQUESTED":
        signals.append({"kind": "cancellation_requested", "message": "Cancellation requested — awaiting safe reconcile"})
    if monitor_state == "INTERRUPTED":
        signals.append({"kind": "recovery_occurred", "message": "Interrupted — recovery may requeue"})
    if monitor_state in ("APPROVED", "COMPLETED", "PREVIEW_READY"):
        signals.append({"kind": "job_completed", "message": contract.get("label", monitor_state)})
    return signals


def project_production_monitor(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Full C06-H monitor projection — ownership fail-closed."""
    from app.customer_job import get_job, job_owned_by_channels, map_customer_state, to_customer_view
    from app.customer_job_automation import project_job_automation
    from app.generation_guard import metrics_snapshot, owner as guard_owner

    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    view = to_customer_view(row)
    auto = project_job_automation(row)
    monitor_state = infer_monitor_state(row)
    if monitor_state == "APPROVAL_PENDING" and view.get("artifact_available"):
        # Prefer PREVIEW_READY when artifact exists and approval still pending
        monitor_state = "PREVIEW_READY" if not row.get("customer_approval") else monitor_state
        if not row.get("customer_approval"):
            # dual: preview ready implies approval pending for action
            pass
    # If preview ready + no decision → expose both via approval_status
    if monitor_state == "PREVIEW_READY":
        action_state = "APPROVAL_PENDING"
    else:
        action_state = monitor_state

    events = load_lifecycle_events(row)
    path = infer_execution_path(row)
    progress = qualitative_progress(monitor_state)
    contract = STATE_CONTRACT.get(monitor_state) or STATE_CONTRACT["DRAFT"]
    lab = classify_live_lab()
    metrics = metrics_snapshot()

    # Verification honesty — never invent PASS
    verification = "UNKNOWN"
    qs = row.get("quality_summary")
    if isinstance(qs, str):
        try:
            qs = json.loads(qs)
        except Exception:
            qs = {}
    qs = qs if isinstance(qs, dict) else {}
    if qs.get("artifact_verification"):
        verification = str(qs.get("artifact_verification")).upper()
    elif qs.get("verified") is True:
        verification = "VERIFIED"
    elif qs.get("verified") is False:
        verification = "FAIL"

    publishable = str(row.get("upload_status") or "") == "ready_to_upload"
    approval = str(row.get("customer_approval") or "").upper() or (
        "PENDING" if publishable else "NOT_READY"
    )

    recovery_status = None
    if monitor_state == "INTERRUPTED":
        recovery_status = "INTERRUPTED_NEEDS_RECOVERY"
    elif monitor_state == "RETRY_WAITING":
        recovery_status = "RETRY_SCHEDULED"
    elif any(e.get("type") == "JOB_RECOVERED" for e in events[-5:]):
        recovery_status = "RECOVERED_REQUEUED"

    return {
        "ok": True,
        "contract": CONTRACT_VERSION,
        "job_id": int(job_id),
        "monitor_state": monitor_state,
        "action_state": action_state,
        "customer_state": map_customer_state(row),
        "queue_status": row.get("queue_status"),
        "stage": row.get("customer_stage") or map_customer_state(row),
        "queued_at": row.get("queue_enqueued_at"),
        "started_at": row.get("claimed_at") or row.get("created_at"),
        "updated_at": row.get("updated_at") or row.get("created_at"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "retry_count": max(0, int(row.get("attempt_count") or 0) - 1),
        "max_attempts": int(row.get("max_attempts") or 3),
        "next_retry_at": row.get("next_retry_at"),
        "verification_status": verification,
        "preview_available": bool(view.get("artifact_available")),
        "approval_status": approval if approval in ("APPROVED", "REJECTED", "PENDING", "NOT_READY") else "PENDING",
        "failure_category": row.get("failure_category"),
        "failure_reason": view.get("error_summary") or row.get("error"),
        "cancellation_status": (
            "CANCELLED"
            if monitor_state == "CANCELLED"
            else ("CANCELLATION_REQUESTED" if monitor_state == "CANCELLATION_REQUESTED" else "NONE")
        ),
        "recovery_status": recovery_status,
        "progress": progress,
        "progress_percent": None,
        "progress_note": "UNKNOWN or qualitative stage only — never fabricated %",
        "execution_path": path,
        "execution_path_class": (
            "CANONICAL" if path == "CANONICAL_QUEUE" else "LEGACY_COMPAT"
        ),
        "lifecycle_events": events,
        "attention": attention_signals(row, monitor_state=monitor_state),
        "state_contract": contract,
        "planes": {
            "generated": auto.get("planes", {}).get("generated"),
            "verified": verification == "VERIFIED",
            "publishable": publishable,
            "approved": approval == "APPROVED",
            "upload_accepted": str(row.get("publish_status") or "")
            in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED"),
            "remote_processing": str(row.get("publish_status") or "") == "REMOTE_PROCESSING",
            "published": str(row.get("publish_status") or "") == "PUBLISHED",
            "note": (
                "RUNNING!=VERIFYING; FAILED!=ACTION_REQUIRED; APPROVAL_PENDING!=APPROVED; "
                "APPROVED!=READY_TO_UPLOAD!=UPLOAD_ACCEPTED!=REMOTE_PROCESSING!=PUBLISHED"
            ),
        },
        "publishing": {
            "status": row.get("publish_status") or "NOT_STARTED",
            "provider": row.get("publish_provider"),
            "provider_video_id": row.get("publish_provider_video_id"),
            "provider_url": row.get("publish_provider_url"),
            "mock": bool(int(row.get("publish_mock") or 0)) if row.get("publish_status") else None,
        },
        "guard": {
            "busy": metrics.get("busy"),
            "owner": guard_owner(),
            "max_active_generation": 1,
        },
        "live_lab": lab,
        "automation": auto,
        "job": view,
        "publishes": False,
        "social_calls": False,
        "secrets_excluded": True,
    }


def project_recent_activity(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    limit: int = 20,
) -> Dict[str, Any]:
    from app.customer_job import list_customer_jobs

    jobs = list_customer_jobs(limit, channel_ids=list(channel_ids))
    items = []
    for j in jobs:
        jid = int(j.get("job_id") or 0)
        if not jid:
            continue
        mon = project_production_monitor(login_id, jid, channel_ids=channel_ids)
        if not mon.get("ok"):
            continue
        items.append(
            {
                "job_id": jid,
                "monitor_state": mon.get("monitor_state"),
                "attention": mon.get("attention"),
                "updated_at": mon.get("updated_at"),
                "execution_path": mon.get("execution_path"),
            }
        )
    return {"ok": True, "items": items, "publishes": False}


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat in (
        r"(?m)^\s*def\s+generate_video\s*\(",
        r"(?m)^\s*class\s+SchedulerService\b",
        r"(?m)^\s*def\s+try_acquire\s*\(",
        r"(?m)^\s*def\s+compute_fingerprint\s*\(",
        r"(?m)^\s*class\s+NotificationPlatform\b",
    ):
        if _re.search(pat, source):
            bad.append(pat)
    return bad
