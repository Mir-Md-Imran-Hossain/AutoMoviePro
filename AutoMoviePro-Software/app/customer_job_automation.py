"""C06-G — Customer Job Queue, Scheduler & Recovery (compose / orchestration only).

Extends existing customer_job + generation_guard + C06-D orchestrator.
Does NOT create a second generation/quality/idempotency/repair/publish engine.
Paid APIs for deterministic path: 0.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import DATA_DIR
from app.customer_job import (
    create_generation_job,
    get_job,
    job_owned_by_channels,
    mark_failed,
    mark_from_pipeline_result,
    sanitize_customer_error,
    to_customer_view,
    update_customer_progress,
)

CONTRACT_VERSION = "C06-G.1"
MAX_ATTEMPTS = 3
LEASE_SECONDS = 120
DEFAULT_BACKOFF_SEC = (5, 15, 45)

# Map conceptual C06-G states ↔ existing customer_state where possible
LIFECYCLE_ALIASES = {
    "CREATED": "QUEUED",
    "READY": "QUEUED",
    "QUEUED": "QUEUED",
    "RUNNING": "GENERATING",
    "VERIFYING": "VALIDATING",
    "PREVIEW_READY": "READY_FOR_REVIEW",
    "APPROVAL_PENDING": "READY_FOR_REVIEW",
    "APPROVED": "READY_FOR_REVIEW",  # approval is separate plane
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
    "RETRY_WAITING": "QUEUED",
    "TERMINAL_FAILED": "FAILED",
    "INTERRUPTED": "INTERRUPTED",
    "CANCELLED": "CANCELLED",
}

FAILURE_CATEGORIES = (
    "TRANSIENT",
    "TIMEOUT",
    "PROVIDER_TEMPORARY",
    "RESOURCE_TEMPORARY",
    "CONFIGURATION",
    "CONTRACT",
    "CUSTOMER_ACTION_REQUIRED",
    "QUALITY_FAILURE",
    "OWNERSHIP_FAILURE",
    "ENTITLEMENT_FAILURE",
    "STALE_PLAN",
    "INTEGRITY_FAILURE",
    "UNKNOWN",
)

RETRY_ELIGIBLE = frozenset(
    {"TRANSIENT", "TIMEOUT", "PROVIDER_TEMPORARY", "RESOURCE_TEMPORARY"}
)
NEVER_RETRY = frozenset(
    {
        "CONFIGURATION",
        "CONTRACT",
        "CUSTOMER_ACTION_REQUIRED",
        "QUALITY_FAILURE",
        "OWNERSHIP_FAILURE",
        "ENTITLEMENT_FAILURE",
        "STALE_PLAN",
        "INTEGRITY_FAILURE",
        "UNKNOWN",
    }
)

_CLAIM_LOCK = threading.Lock()
_TICK_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat()


def _now_dt() -> datetime:
    return datetime.now()


def ensure_automation_columns() -> None:
    """Soft-migrate jobs for C06-G queue/claim/retry — extend existing table."""
    from app import db as store
    from app.customer_job import ensure_job_columns

    ensure_job_columns()
    with store.db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = [
            ("queue_status", "TEXT"),  # none|queued|claimed|running|done|cancelled
            ("queue_enqueued_at", "TEXT"),
            ("claim_token", "TEXT"),
            ("claimed_at", "TEXT"),
            ("claimed_by", "TEXT"),
            ("lease_expires_at", "TEXT"),
            ("attempt_count", "INTEGER DEFAULT 0"),
            ("max_attempts", "INTEGER DEFAULT 3"),
            ("failure_category", "TEXT"),
            ("cancel_requested", "INTEGER DEFAULT 0"),
            ("next_retry_at", "TEXT"),
            ("worker_id", "TEXT"),
            ("lifecycle_audit_json", "TEXT"),
            ("queue_fingerprint", "TEXT"),  # prevent duplicate enqueue for same executable revision
        ]
        for name, typ in migrations:
            if name not in cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")


def append_lifecycle_event(job_id: int, event: Dict[str, Any]) -> None:
    ensure_automation_columns()
    from app import db as store

    row = get_job(int(job_id)) or {}
    raw = row.get("lifecycle_audit_json")
    try:
        data = json.loads(raw) if raw else {"events": []}
    except Exception:
        data = {"events": []}
    events = list(data.get("events") or [])
    evt = {**event, "at": _now()}
    # never persist secrets
    blob = json.dumps(evt, ensure_ascii=False, default=str).lower()
    if any(x in blob for x in ("api_key", "sk-", "password=", "authorization:")):
        evt = {**evt, "redacted": True, "detail": "[redacted]"}
    events.append(evt)
    data["events"] = events[-200:]
    store.update_job(int(job_id), lifecycle_audit_json=json.dumps(data, ensure_ascii=False), updated_at=_now())
    # C10: observation fan-out only when a marathon session is bound to this job.
    try:
        from app.customer_marathon_observability import on_lifecycle_event

        on_lifecycle_event(int(job_id), evt)
    except Exception:
        pass


def classify_failure(error: str, *, error_code: str = "") -> str:
    """C06-G failure classification — extends customer_job.classify_error semantics."""
    from app.customer_job import classify_error

    low = f"{error} {error_code}".lower()
    code = str(error_code or "").lower()
    if "ownership" in low or code == "ownership_violation":
        return "OWNERSHIP_FAILURE"
    if "entitlement" in low or "account" in low and "inactive" in low:
        return "ENTITLEMENT_FAILURE"
    if "stale_plan" in low or code == "stale_plan" or "plan_revision" in low:
        return "STALE_PLAN"
    if "integrity" in low or "publish_side_effect" in low:
        return "INTEGRITY_FAILURE"
    if any(x in low for x in ("quality", "publishability", "artifact_verif", "creative_quality")):
        return "QUALITY_FAILURE"
    if any(x in low for x in ("config", "missing_", "validation", "not_ready", "readiness")):
        return "CONFIGURATION"
    if "contract" in low or "mandatory" in low:
        return "CONTRACT"
    if "customer_action" in low or "approval" in low and "required" in low:
        return "CUSTOMER_ACTION_REQUIRED"
    if "timeout" in low or code == "timeout":
        return "TIMEOUT"
    if any(x in low for x in ("429", "rate_limit", "temporarily", "provider_temp")):
        return "PROVIDER_TEMPORARY"
    if any(x in low for x in ("disk", "memory", "resource", "busy", "generation_busy")):
        return "RESOURCE_TEMPORARY"
    if any(x in low for x in ("network", "connection", "transient", "retry")):
        return "TRANSIENT"
    mapped = classify_error(error)
    if mapped in ("provider_failure",):
        return "PROVIDER_TEMPORARY"
    if mapped in ("quality_rejection", "rendering_failure"):
        return "QUALITY_FAILURE"
    if mapped in ("configuration_failure", "validation_failure"):
        return "CONFIGURATION"
    if mapped in ("infrastructure_failure",):
        return "TRANSIENT"
    return "UNKNOWN"


def retry_eligible(category: str, attempt_count: int, max_attempts: int = MAX_ATTEMPTS) -> bool:
    if category in NEVER_RETRY:
        return False
    if category not in RETRY_ELIGIBLE:
        return False
    return int(attempt_count) < int(max_attempts)


def backoff_seconds(attempt_count: int) -> int:
    idx = max(0, min(int(attempt_count), len(DEFAULT_BACKOFF_SEC) - 1))
    return int(DEFAULT_BACKOFF_SEC[idx])


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", ""))
    except Exception:
        return None


def find_duplicate_queued(
    *,
    login_id: str,
    channel_id: int,
    queue_fingerprint: str,
) -> Optional[Dict[str, Any]]:
    """Prevent duplicate queue entries for same executable job revision."""
    ensure_automation_columns()
    from app import db as store

    with store.db() as conn:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE channel_id=? AND requested_by=? AND queue_fingerprint=?
              AND queue_status IN ('queued','claimed','running')
              AND IFNULL(cancel_requested,0)=0
            ORDER BY id DESC LIMIT 1
            """,
            (int(channel_id), str(login_id), str(queue_fingerprint)),
        ).fetchone()
        return dict(row) if row else None


def enqueue_existing_job(
    job_id: int,
    *,
    login_id: str,
    channel_ids: Sequence[int],
    queue_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """Place an existing customer job onto the persistent queue."""
    ensure_automation_columns()
    from app import db as store

    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    requested = str(row.get("requested_by") or "").strip()
    if requested and requested != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    approval = str(row.get("customer_approval") or "").upper()
    if approval == "APPROVED":
        return {
            "ok": False,
            "error": "already_approved",
            "error_code": "approval_blocks_enqueue",
            "note": "APPROVED is not a new generation request",
        }
    # Rejected must not auto-requeue
    if approval == "REJECTED" and not queue_fingerprint:
        return {
            "ok": False,
            "error": "rejected_no_auto_requeue",
            "error_code": "rejection_blocks_enqueue",
        }

    qstat = str(row.get("queue_status") or "")
    if qstat in ("queued", "claimed", "running"):
        return {
            "ok": True,
            "reused": True,
            "job_id": int(job_id),
            "queue_status": qstat,
            "note": "Already on queue — duplicate enqueue prevented",
        }
    if str(row.get("upload_status") or "") in ("ready_to_upload", "uploaded", "dry_run_uploaded"):
        if str(row.get("customer_state") or "") in ("READY_FOR_REVIEW", "COMPLETED"):
            return {
                "ok": False,
                "error": "terminal_or_ready",
                "error_code": "terminal_blocks_enqueue",
            }

    fp = queue_fingerprint or row.get("generation_fingerprint") or row.get("queue_fingerprint")
    if fp:
        dup = find_duplicate_queued(
            login_id=login_id, channel_id=int(row.get("channel_id") or 0), queue_fingerprint=str(fp)
        )
        if dup and int(dup["id"]) != int(job_id):
            return {
                "ok": True,
                "reused": True,
                "job_id": int(dup["id"]),
                "queue_status": dup.get("queue_status"),
                "note": "Duplicate executable revision — reuse existing queue entry",
            }

    store.update_job(
        int(job_id),
        queue_status="queued",
        queue_enqueued_at=_now(),
        claim_token=None,
        claimed_at=None,
        claimed_by=None,
        lease_expires_at=None,
        worker_id=None,
        queue_fingerprint=str(fp) if fp else None,
        max_attempts=int(row.get("max_attempts") or MAX_ATTEMPTS),
        attempt_count=int(row.get("attempt_count") or 0),
        customer_state="QUEUED",
        customer_stage="QUEUED",
        upload_status="queued",
        updated_at=_now(),
        cancel_requested=0,
    )
    append_lifecycle_event(
        int(job_id),
        {
            "event": "enqueued",
            "login_id": login_id,
            "queue_fingerprint": fp,
            "publishes": False,
        },
    )
    return {
        "ok": True,
        "reused": False,
        "job_id": int(job_id),
        "queue_status": "queued",
        "publishes": False,
    }


def submit_customer_generation(
    login_id: str,
    channel: Dict[str, Any],
    *,
    video_type: str = "short",
    execution_mode: Optional[str] = None,
    use_mock: Optional[bool] = None,
    deterministic_fixtures: bool = True,
    force_rebuild: bool = False,
    process_now: bool = False,
) -> Dict[str, Any]:
    """Admit + create job + enqueue. Optionally run one scheduler tick (orchestration only)."""
    ensure_automation_columns()
    from app.customer_generation_orchestrator import (
        admit_generation,
        compute_generation_job_fingerprint,
        find_reusable_job,
    )
    from app.customer_plan_adapter import resolve_execution_mode

    mode = resolve_execution_mode(execution_mode=execution_mode, use_mock=use_mock)
    admission = admit_generation(login_id, channel)
    if not admission.get("ok"):
        return {**admission, "queued": False, "started": False, "execution_mode": mode}

    plan = admission["plan"]
    snapshot = admission["snapshot"]
    if str(snapshot.get("production_plan_revision")) != str(plan.get("fingerprint") or plan.get("script_revision")):
        return {
            "ok": False,
            "error": "plan_revision_mismatch",
            "error_code": "stale_plan",
            "failure_category": "STALE_PLAN",
            "queued": False,
            "started": False,
        }

    fingerprint = compute_generation_job_fingerprint(snapshot, plan, video_type=video_type)
    if not force_rebuild:
        reused = find_reusable_job(login_id, int(channel.get("id") or 0), fingerprint)
        if reused:
            return {
                "ok": True,
                "reused": True,
                "queued": False,
                "started": False,
                "job_id": reused["job"]["id"],
                "fingerprint": fingerprint,
                "execution_mode": mode,
                "message": "Equivalent generation fingerprint — REUSE (BUILD-03)",
                "publishes": False,
            }

    dup = find_duplicate_queued(
        login_id=login_id,
        channel_id=int(channel.get("id") or 0),
        queue_fingerprint=fingerprint,
    )
    if dup:
        return {
            "ok": True,
            "reused": True,
            "queued": True,
            "started": False,
            "job_id": int(dup["id"]),
            "queue_status": dup.get("queue_status"),
            "fingerprint": fingerprint,
            "execution_mode": mode,
            "note": "Duplicate enqueue prevented",
            "publishes": False,
        }

    row = create_generation_job(
        channel_id=int(channel.get("id") or 0),
        video_type=video_type,
        requested_by=login_id,
        title_hint=f"{video_type} queued plan {snapshot.get('production_plan_id')}",
        production_plan_id=str(snapshot.get("production_plan_id") or ""),
        production_plan_revision=str(snapshot.get("production_plan_revision") or ""),
        script_revision=str(snapshot.get("script_revision") or ""),
        generation_fingerprint=fingerprint,
        plan_snapshot={
            **snapshot,
            "_c06g": {
                "execution_mode": mode,
                "deterministic_fixtures": deterministic_fixtures,
                "video_type": video_type,
            },
        },
    )
    job_id = int(row["id"])
    enq = enqueue_existing_job(
        job_id,
        login_id=login_id,
        channel_ids=[int(channel.get("id") or 0)],
        queue_fingerprint=fingerprint,
    )
    out = {
        "ok": True,
        "queued": True,
        "started": False,
        "job_id": job_id,
        "fingerprint": fingerprint,
        "execution_mode": mode,
        "queue_status": "queued",
        "publishes": False,
        "social_calls": False,
        "paid_api_calls": 0,
        "note": "Enqueued — scheduler/worker will claim under generation_guard (max=1)",
        **{k: enq[k] for k in ("reused",) if k in enq},
    }
    if process_now:
        tick = scheduler_tick(worker_id="inline")
        out["tick"] = tick
        out["started"] = bool(tick.get("executed"))
    return out


def claim_next_job(
    *,
    worker_id: str,
    channel_ids: Optional[Sequence[int]] = None,
) -> Optional[Dict[str, Any]]:
    """Atomic worker claim — one active lease per job; concurrent workers cannot double-claim."""
    ensure_automation_columns()
    from app import db as store

    token = uuid.uuid4().hex
    lease_until = (_now_dt() + timedelta(seconds=LEASE_SECONDS)).isoformat()
    wid = str(worker_id or "worker")[:80]

    with _CLAIM_LOCK:
        with store.db() as conn:
            # Recover expired leases first (same transaction window)
            now = _now()
            conn.execute(
                """
                UPDATE jobs SET queue_status='queued', claim_token=NULL, claimed_at=NULL,
                  claimed_by=NULL, lease_expires_at=NULL, worker_id=NULL, updated_at=?
                WHERE queue_status IN ('claimed','running')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
                  AND IFNULL(cancel_requested,0)=0
                """,
                (now, now),
            )
            q = """
                SELECT id FROM jobs
                WHERE queue_status='queued'
                  AND IFNULL(cancel_requested,0)=0
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                  AND upload_status NOT IN ('ready_to_upload','uploaded','dry_run_uploaded','cancelled')
                  AND IFNULL(customer_approval,'') != 'APPROVED'
            """
            params: List[Any] = [now]
            if channel_ids:
                placeholders = ",".join("?" for _ in channel_ids)
                q += f" AND channel_id IN ({placeholders})"
                params.extend(int(x) for x in channel_ids)
            q += " ORDER BY queue_enqueued_at ASC, id ASC LIMIT 1"
            row = conn.execute(q, params).fetchone()
            if not row:
                return None
            jid = int(row["id"])
            cur = conn.execute(
                """
                UPDATE jobs SET queue_status='claimed', claim_token=?, claimed_at=?,
                  claimed_by=?, lease_expires_at=?, worker_id=?, updated_at=?,
                  customer_state='STARTING', customer_stage='STARTING', upload_status='preparing'
                WHERE id=? AND queue_status='queued' AND IFNULL(cancel_requested,0)=0
                """,
                (token, now, wid, lease_until, wid, now, jid),
            )
            if cur.rowcount != 1:
                return None
        claimed = get_job(jid)
        if not claimed or claimed.get("claim_token") != token:
            return None
        append_lifecycle_event(
            jid,
            {"event": "claimed", "worker_id": wid, "claim_token": token[:8], "lease_expires_at": lease_until},
        )
        return claimed


def release_claim(job_id: int, *, claim_token: str, final_status: str = "done") -> None:
    ensure_automation_columns()
    from app import db as store

    row = get_job(int(job_id))
    if not row or str(row.get("claim_token") or "") != str(claim_token):
        return
    store.update_job(
        int(job_id),
        queue_status=final_status,
        claim_token=None,
        lease_expires_at=None,
        updated_at=_now(),
    )


def request_cancel(
    login_id: str,
    job_id: int,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    ensure_automation_columns()
    from app import db as store

    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found", "error_code": "not_found"}
    if not job_owned_by_channels(row, list(channel_ids)):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    if str(row.get("requested_by") or "").strip() and str(row.get("requested_by")).strip() != str(login_id).strip():
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}

    qstat = str(row.get("queue_status") or "")
    cust = str(row.get("customer_state") or "")
    # Idempotent: already cancelled
    if cust == "CANCELLED" or qstat == "cancelled" or str(row.get("upload_status") or "") == "cancelled":
        return {
            "ok": True,
            "reused": True,
            "job_id": int(job_id),
            "state": "CANCELLED",
            "publishes": False,
            "note": "Duplicate cancel — deterministic reuse",
        }
    # Idempotent: already requested while running
    if int(row.get("cancel_requested") or 0) and qstat in ("claimed", "running"):
        return {
            "ok": True,
            "reused": True,
            "job_id": int(job_id),
            "state": "CANCELLATION_REQUESTED",
            "immediate": False,
            "publishes": False,
            "note": "Cancellation already requested",
        }

    if qstat in ("done",) or cust in ("COMPLETED", "READY_FOR_REVIEW"):
        return {"ok": False, "error": "not_cancellable", "error_code": "cancel_not_allowed"}

    if qstat in ("queued", "claimed") or not row.get("claim_token"):
        # Safe cancel before/at claim
        store.update_job(
            int(job_id),
            cancel_requested=1,
            queue_status="cancelled",
            customer_state="CANCELLED",
            customer_stage="CANCELLED",
            upload_status="cancelled",
            claim_token=None,
            updated_at=_now(),
        )
        append_lifecycle_event(
            int(job_id),
            {"event": "JOB_CANCELLED", "login_id": login_id, "mode": "immediate"},
        )
        return {
            "ok": True,
            "job_id": int(job_id),
            "state": "CANCELLED",
            "immediate": True,
            "publishes": False,
            "retry_eligible": False,
        }

    # Running — request only; do not fake kill or COMPLETED
    store.update_job(int(job_id), cancel_requested=1, updated_at=_now())
    append_lifecycle_event(
        int(job_id),
        {
            "event": "JOB_CANCELLATION_REQUESTED",
            "login_id": login_id,
            "mode": "CANCELLATION_REQUESTED",
            "note": "Never silent COMPLETED",
        },
    )
    return {
        "ok": True,
        "job_id": int(job_id),
        "state": "CANCELLATION_REQUESTED",
        "immediate": False,
        "publishes": False,
        "note": "Cancel requested — reconcile when safe; not faked as success kill",
    }


def execute_claimed_job(
    row: Dict[str, Any],
    *,
    channel: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run existing C06-D/E mock/handoff for a claimed job — no second generate_video engine."""
    ensure_automation_columns()
    from pathlib import Path
    from app import db as store
    from app.customer_generation_orchestrator import (
        _safe_login,
        _set_phase,
        run_mock_execution,
        save_execution_record,
    )
    from app.customer_plan_adapter import (
        EXECUTION_MODE_APPROVED,
        EXECUTION_MODE_MOCK,
        build_director_plan_from_production_plan,
        build_immutable_execution_snapshot,
        run_deterministic_canonical_handoff,
        write_director_plan,
        write_execution_snapshot,
    )
    from app.customer_production_plan import load_production_plan
    from app.generation_guard import release as generation_release
    from app.generation_guard import try_acquire as generation_try_acquire

    job_id = int(row["id"])
    login_id = str(row.get("requested_by") or "")
    claim_token = str(row.get("claim_token") or "")
    if int(row.get("cancel_requested") or 0):
        store.update_job(
            job_id,
            queue_status="cancelled",
            customer_state="CANCELLED",
            upload_status="cancelled",
            claim_token=None,
            updated_at=_now(),
        )
        return {"ok": True, "cancelled": True, "job_id": job_id, "publishes": False}

    # generation_guard remains max=1 authority
    if not generation_try_acquire("customer"):
        # Release claim back to queue for later
        store.update_job(
            job_id,
            queue_status="queued",
            claim_token=None,
            claimed_at=None,
            claimed_by=None,
            lease_expires_at=None,
            worker_id=None,
            updated_at=_now(),
            upload_status="queued",
            customer_state="QUEUED",
        )
        append_lifecycle_event(job_id, {"event": "requeue_guard_busy"})
        return {"ok": False, "error": "generation_busy", "error_code": "generation_busy", "requeued": True}

    attempt = int(row.get("attempt_count") or 0) + 1
    store.update_job(
        job_id,
        queue_status="running",
        attempt_count=attempt,
        customer_state="GENERATING",
        customer_stage="GENERATING",
        upload_status="generating",
        updated_at=_now(),
    )
    append_lifecycle_event(
        job_id,
        {
            "event": "execution_start",
            "attempt": attempt,
            "plan_id": row.get("production_plan_id"),
            "plan_revision": row.get("production_plan_revision"),
        },
    )

    try:
        snap_raw = row.get("plan_snapshot_json")
        snapshot = json.loads(snap_raw) if snap_raw else {}
        meta = snapshot.get("_c06g") or {}
        mode = str(meta.get("execution_mode") or EXECUTION_MODE_MOCK)
        fixtures = bool(meta.get("deterministic_fixtures", True))
        video_type = str(row.get("video_type") or meta.get("video_type") or "short")

        plan = load_production_plan(login_id, int(row.get("channel_id") or 0))
        if not plan:
            raise RuntimeError("stale_plan:production plan missing")
        # Immutable snapshot identity must match plan fingerprint when present
        if row.get("production_plan_revision") and str(plan.get("fingerprint") or plan.get("script_revision")) != str(
            row.get("production_plan_revision")
        ):
            # Prefer job snapshot revision — block if live plan drifted without matching snapshot
            if str(snapshot.get("production_plan_revision") or "") != str(row.get("production_plan_revision")):
                raise RuntimeError("stale_plan:snapshot/plan mismatch")

        # Prefer immutable snapshot fields for execution identity
        exec_plan = dict(plan)
        if snapshot:
            for k in ("production_plan_id", "fingerprint", "script_revision", "language", "scenes", "status"):
                if snapshot.get(k) is not None and k != "status":
                    # do not overwrite scene content from mutable plan if snapshot has scenes
                    pass
            if snapshot.get("scenes"):
                exec_plan = {**plan, **{k: snapshot[k] for k in snapshot if k != "_c06g"}}

        fingerprint = str(row.get("generation_fingerprint") or "")
        wd = DATA_DIR / "customer_generation_work" / _safe_login(login_id) / f"job{job_id}"
        wd.mkdir(parents=True, exist_ok=True)

        exec_snap = build_immutable_execution_snapshot(
            plan=exec_plan if isinstance(exec_plan, dict) else plan,
            job_id=job_id,
            login_id=login_id,
            channel_id=int(row.get("channel_id") or 0),
            execution_mode=mode,
            generation_fingerprint=fingerprint,
        )
        write_execution_snapshot(wd, exec_snap)
        save_execution_record(
            login_id,
            job_id,
            {
                "contract": CONTRACT_VERSION,
                "owner_login_id": login_id,
                "job_id": job_id,
                "phase": "RUNNING",
                "attempt": attempt,
                "execution_mode": mode,
                "fingerprint": fingerprint,
                "publishes": False,
            },
        )

        if mode == EXECUTION_MODE_MOCK or mode == "MOCK_DETERMINISTIC":
            result = run_mock_execution(
                login_id=login_id,
                job_id=job_id,
                plan=plan,
                snapshot=snapshot or exec_snap,
                fingerprint=fingerprint,
                work_dir=wd,
            )
        elif fixtures:
            director = build_director_plan_from_production_plan(
                plan,
                execution_mode=EXECUTION_MODE_APPROVED,
                login_id=login_id,
                channel_id=int(row.get("channel_id") or 0),
                job_id=job_id,
            )
            write_director_plan(wd, director)
            _set_phase(job_id, "PREPARING", "C06-G queued CUSTOMER_APPROVED_PLAN fixtures")
            result = run_deterministic_canonical_handoff(
                plan=plan,
                login_id=login_id,
                channel_id=int(row.get("channel_id") or 0),
                job_id=job_id,
                work_dir=wd,
                generation_fingerprint=fingerprint,
            )
            if result.get("ok"):
                planes = result.get("planes") or {}
                publishable = bool((result.get("publishability") or {}).get("publishable"))
                ready = bool(planes.get("ready_to_upload")) and publishable
                store.update_job(
                    job_id,
                    upload_status="ready_to_upload" if ready else "generated",
                    customer_state="READY_FOR_REVIEW" if ready else "VALIDATING",
                    customer_stage="READY_FOR_REVIEW" if ready else "GENERATED",
                    local_path=str(result.get("local_path") or result.get("artifact_path") or ""),
                    updated_at=_now(),
                    error=None if ready else "duration_reconciliation_blocked_fixture",
                )
                mark_from_pipeline_result(
                    job_id,
                    {
                        "upload_status": "ready_to_upload" if ready else "generated",
                        "local_path": result.get("local_path") or result.get("artifact_path"),
                        "title": result.get("title") or "queued generation",
                    },
                )
            else:
                raise RuntimeError(result.get("error") or "handoff_failed")
        else:
            # Opt-in industrial custom pipeline (AMP_CUSTOM_PIPELINE=1 or meta.pipeline_engine=custom)
            from app.custom_pipeline_bridge import (
                custom_pipeline_enabled,
                run_custom_pipeline_for_customer_job,
            )

            if custom_pipeline_enabled(job_meta=meta):
                niche = str(
                    meta.get("niche")
                    or snapshot.get("topic")
                    or (plan or {}).get("topic")
                    or row.get("title")
                    or "customer topic"
                )
                langs = meta.get("languages") or snapshot.get("languages")
                if isinstance(langs, str):
                    langs = [x.strip() for x in langs.split(",") if x.strip()]
                result = run_custom_pipeline_for_customer_job(
                    niche=niche,
                    video_type=video_type,
                    work_dir=wd,
                    languages=langs if isinstance(langs, list) else None,
                    audience=str(meta.get("audience") or "সাধারণ দর্শক"),
                )
                mark_from_pipeline_result(job_id, result)
            else:
                # Live unpaid path still goes through existing generate_video — not a second engine
                from pipeline.video_pipeline import generate_video

                # Hydrate full channel from DB so languages_json / entitlement / API slots
                # reach generate_video (stub {id, owner} would force en-only / ABSENT localize).
                cid = int(row.get("channel_id") or 0)
                ch = dict(channel or {})
                if cid:
                    fresh = store.get_channel(cid) or {}
                    if fresh:
                        ch = {**fresh, **ch}
                    ch.setdefault("id", cid)
                if login_id:
                    ch.setdefault("owner_login_id", login_id)
                if not ch.get("id"):
                    ch = {"id": cid or row.get("channel_id"), "owner_login_id": login_id}
                director = build_director_plan_from_production_plan(
                    plan,
                    execution_mode=EXECUTION_MODE_APPROVED,
                    login_id=login_id,
                    channel_id=int(row.get("channel_id") or 0),
                    job_id=job_id,
                )
                write_director_plan(wd, director)
                result = generate_video(
                    ch,
                    video_type,
                    existing_job_id=job_id,
                    work_dir=str(wd),
                )
                final_media = (
                    (result or {}).get("local_path")
                    or (result or {}).get("final_path")
                    or (wd / "final.mp4")
                )
                from app.customer_generation_orchestrator import is_mock_or_invalid_media_artifact

                is_mock_art, reason = is_mock_or_invalid_media_artifact(final_media)
                if is_mock_art:
                    mark_failed(job_id, f"live_generation_rejected_invalid_or_mock_media:{reason}", recoverable=False)
                else:
                    mark_from_pipeline_result(job_id, result)

        # Cancel request during run
        after = get_job(job_id) or {}
        if int(after.get("cancel_requested") or 0) and str(after.get("upload_status")) != "ready_to_upload":
            store.update_job(
                job_id,
                queue_status="cancelled",
                customer_state="CANCELLED",
                upload_status="cancelled",
                claim_token=None,
                updated_at=_now(),
            )
            append_lifecycle_event(job_id, {"event": "cancelled_after_run"})
            return {"ok": True, "cancelled": True, "job_id": job_id, "publishes": False}

        release_claim(job_id, claim_token=claim_token, final_status="done")
        append_lifecycle_event(
            job_id,
            {
                "event": "execution_complete",
                "attempt": attempt,
                "verification_honest": True,
                "publishes": False,
                "note": "GENERATED!=VERIFIED!=PUBLISHABLE!=APPROVED!=PUBLISHED",
            },
        )
        return {
            "ok": True,
            "job_id": job_id,
            "attempt": attempt,
            "publishes": False,
            "social_calls": False,
            "paid_api_calls": 0,
            "result": result if isinstance(result, dict) else {"ok": True},
        }
    except Exception as exc:
        category = classify_failure(str(exc))
        store.update_job(job_id, failure_category=category, updated_at=_now())
        append_lifecycle_event(
            job_id,
            {"event": "execution_failed", "attempt": attempt, "failure_category": category, "error": sanitize_customer_error(str(exc))},
        )
        max_a = int(row.get("max_attempts") or MAX_ATTEMPTS)
        if retry_eligible(category, attempt, max_a):
            delay = backoff_seconds(attempt)
            nxt = (_now_dt() + timedelta(seconds=delay)).isoformat()
            store.update_job(
                job_id,
                queue_status="queued",
                claim_token=None,
                claimed_at=None,
                claimed_by=None,
                lease_expires_at=None,
                worker_id=None,
                next_retry_at=nxt,
                customer_state="QUEUED",
                customer_stage="QUEUED",
                upload_status="queued",
                recoverable=1,
                error=sanitize_customer_error(str(exc)),
                updated_at=_now(),
            )
            append_lifecycle_event(
                job_id,
                {"event": "retry_scheduled", "failure_category": category, "next_retry_at": nxt, "attempt": attempt},
            )
            return {
                "ok": False,
                "retry_scheduled": True,
                "failure_category": category,
                "error": sanitize_customer_error(str(exc)),
                "job_id": job_id,
                "attempt": attempt,
                "publishes": False,
            }
        # Terminal — quality never blindly regenerates
        mark_failed(job_id, sanitize_customer_error(str(exc)), recoverable=False)
        store.update_job(
            job_id,
            queue_status="done",
            claim_token=None,
            failure_category=category,
            customer_state="FAILED",
            updated_at=_now(),
        )
        append_lifecycle_event(
            job_id,
            {
                "event": "terminal_failed",
                "failure_category": category,
                "note": "QUALITY_FAILURE and UNKNOWN do not blind-retry",
            },
        )
        return {
            "ok": False,
            "terminal": True,
            "failure_category": category,
            "error": sanitize_customer_error(str(exc)),
            "job_id": job_id,
            "publishes": False,
        }
    finally:
        generation_release("customer")


def scheduler_tick(*, worker_id: str = "c06g-scheduler", channel_ids: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Orchestration only: claim one eligible job if generation_guard free, then execute."""
    from app.generation_guard import is_busy
    from app.customer_production_monitor import is_live_lab_active

    with _TICK_LOCK:
        if is_live_lab_active():
            return {
                "ok": True,
                "skipped": True,
                "reason": "live_lab_active",
                "lab_boundary": "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
                "executed": False,
                "publishes": False,
            }
        if is_busy():
            return {
                "ok": True,
                "skipped": True,
                "reason": "generation_guard_busy",
                "max_active_generation": 1,
                "executed": False,
                "publishes": False,
            }
        claimed = claim_next_job(worker_id=worker_id, channel_ids=channel_ids)
        if not claimed:
            return {"ok": True, "skipped": True, "reason": "queue_empty", "executed": False}
        result = execute_claimed_job(claimed)
        return {
            "ok": True,
            "skipped": False,
            "executed": True,
            "job_id": int(claimed["id"]),
            "result": result,
            "publishes": False,
            "trs_replanned": False,
            "note": "Scheduler orchestration only — no content generation by scheduler itself",
        }


def recover_after_restart(*, lease_grace: bool = True) -> Dict[str, Any]:
    """Restart recovery: expired/stale claims → requeue; never silent COMPLETED."""
    ensure_automation_columns()
    from app import db as store

    now = _now()
    requeued = 0
    interrupted = 0
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT id, queue_status, lease_expires_at, upload_status, customer_state, claim_token
            FROM jobs
            WHERE queue_status IN ('claimed','running')
               OR upload_status IN ('preparing','running','generating','validating','repairing','rendering')
            """
        ).fetchall()
        for r in rows:
            jid = int(r["id"])
            qstat = str(r["queue_status"] or "")
            lease = str(r["lease_expires_at"] or "")
            stale = False
            if qstat in ("claimed", "running"):
                if not lease or lease < now:
                    stale = True
            elif str(r["upload_status"] or "") in (
                "preparing",
                "running",
                "generating",
                "validating",
                "repairing",
                "rendering",
            ):
                # In-flight without queue claim after crash
                stale = True
            if not stale:
                continue
            # Requeue if was on automation queue; else mark interrupted (legacy path)
            if qstat in ("claimed", "running", "queued") or r["claim_token"]:
                conn.execute(
                    """
                    UPDATE jobs SET queue_status='queued', claim_token=NULL, claimed_at=NULL,
                      claimed_by=NULL, lease_expires_at=NULL, worker_id=NULL,
                      upload_status='queued', customer_state='QUEUED', customer_stage='QUEUED',
                      updated_at=?
                    WHERE id=? AND IFNULL(cancel_requested,0)=0
                      AND IFNULL(customer_approval,'') NOT IN ('APPROVED')
                      AND upload_status NOT IN ('ready_to_upload','uploaded','dry_run_uploaded')
                    """,
                    (now, jid),
                )
                requeued += 1
            else:
                pass
    # Legacy in-flight without queue_status: keep existing interrupt semantics
    from app.customer_job import reconcile_interrupted_jobs

    # Only interrupt rows still in-flight that are not queued for retry
    with store.db() as conn:
        legacy = conn.execute(
            """
            SELECT id FROM jobs
            WHERE upload_status IN ('preparing','running','generating','validating','repairing','rendering')
              AND IFNULL(queue_status,'') NOT IN ('queued','claimed','running')
            """
        ).fetchall()
        legacy_ids = [int(x["id"]) for x in legacy]
    for jid in legacy_ids:
        mark_failed(
            jid,
            "interrupted_by_restart:job was in-flight when the application stopped",
            recoverable=True,
        )
        store.update_job(jid, upload_status="interrupted", updated_at=_now())
        interrupted += 1
        append_lifecycle_event(jid, {"event": "interrupted_restart", "note": "never silent COMPLETED"})

    for jid in []:  # placeholder kept for clarity
        pass

    # Annotate requeued
    with store.db() as conn:
        qrows = conn.execute(
            "SELECT id FROM jobs WHERE queue_status='queued' AND updated_at=? LIMIT 500",
            (now,),
        ).fetchall()
    for r in qrows:
        append_lifecycle_event(int(r["id"]), {"event": "requeued_after_restart"})

    return {
        "ok": True,
        "requeued": requeued,
        "interrupted_legacy": interrupted,
        "silent_completed": 0,
        "note": "Interrupted jobs never become COMPLETED",
    }


def list_queue(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    limit: int = 50,
) -> Dict[str, Any]:
    ensure_automation_columns()
    from app import db as store

    owned = [int(x) for x in channel_ids]
    if not owned:
        return {"ok": True, "jobs": [], "note": "no owned channels"}
    placeholders = ",".join("?" for _ in owned)
    with store.db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM jobs
            WHERE channel_id IN ({placeholders})
              AND requested_by=?
              AND queue_status IN ('queued','claimed','running')
            ORDER BY queue_enqueued_at ASC, id ASC
            LIMIT ?
            """,
            [*owned, str(login_id), int(limit)],
        ).fetchall()
    jobs = []
    for i, r in enumerate(rows):
        d = dict(r)
        view = to_customer_view(d)
        jobs.append(
            {
                **view,
                "queue_position": i + 1,
                "queue_status": d.get("queue_status"),
                "attempt_count": d.get("attempt_count") or 0,
                "failure_category": d.get("failure_category"),
                "lease_expires_at": d.get("lease_expires_at"),
                "next_retry_at": d.get("next_retry_at"),
            }
        )
    return {"ok": True, "jobs": jobs, "count": len(jobs), "publishes": False}


def project_job_automation(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {"available": False}
    approval = str(row.get("customer_approval") or "").upper() or "PENDING"
    if not row.get("customer_approval") and str(row.get("upload_status")) == "ready_to_upload":
        approval = "PENDING"
    return {
        "queue_status": row.get("queue_status"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "max_attempts": int(row.get("max_attempts") or MAX_ATTEMPTS),
        "failure_category": row.get("failure_category"),
        "claimed_by": row.get("claimed_by"),
        "lease_expires_at": row.get("lease_expires_at"),
        "next_retry_at": row.get("next_retry_at"),
        "cancel_requested": bool(int(row.get("cancel_requested") or 0)),
        "approval_status": approval if approval in ("APPROVED", "REJECTED", "PENDING") else "PENDING",
        "planes": {
            "generated": str(row.get("upload_status") or "") in ("generated", "ready_to_upload"),
            "verified": False,  # never invent
            "publishable": str(row.get("upload_status") or "") == "ready_to_upload",
            "approved": approval == "APPROVED",
            "published": False,
            "note": "GENERATED!=VERIFIED!=PUBLISHABLE!=APPROVED!=PUBLISHED",
        },
        "publishes": False,
    }


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat in (
        r"(?m)^\s*def\s+generate_video\s*\(",
        r"(?m)^\s*def\s+compute_fingerprint\s*\(",
        r"(?m)^\s*def\s+evaluate_publishability\s*\(",
        r"(?m)^\s*class\s+SchedulerService\b",
        r"(?m)^\s*def\s+try_acquire\s*\(",
    ):
        if _re.search(pat, source):
            bad.append(pat)
    return bad
