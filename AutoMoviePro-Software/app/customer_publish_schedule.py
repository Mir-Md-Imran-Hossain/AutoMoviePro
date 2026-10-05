"""C07-SCHED — Customer Publishing Scheduling (intent/timing compose only).

Owns WHEN a publication becomes due. Does NOT upload media.
Delegates execution to C07-PUB ``publish_customer_job``.
Uses existing SchedulerService tick + BUILD-03 idempotency.

Missed policy: overdue beyond MISSED_GRACE_SEC → MISSED (no silent catch-up publish).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.config import DATA_DIR
from app.customer_job import get_job, job_owned_by_channels
from app.customer_job_automation import append_lifecycle_event
from app.customer_preview_approval import compute_revision_id
from app.customer_publish import (
    scrub_secrets,
    validate_publish_gates,
)

CONTRACT_VERSION = "C07-SCHED.1"
SCHEDULE_STAGE = "c07_customer_publish_schedule"
SCHEDULE_CONTRACT = "c07-sched-1.0.0"
MISSED_GRACE_SEC = 6 * 3600  # overdue beyond grace → MISSED, never silent catch-up

SCHEDULE_STATES = (
    "NOT_SCHEDULED",
    "SCHEDULE_VALIDATING",
    "SCHEDULED",
    "DUE",
    "CLAIMED",
    "PUBLISHING",
    "UPLOADED",
    "REMOTE_PROCESSING",
    "PUBLISHED",
    "SCHEDULE_VALIDATION_FAILED",
    "PUBLISH_FAILED",
    "RECONCILIATION_REQUIRED",
    "CANCELLED",
    "MISSED",
    "SUPERSEDED",
)

SCHEDULE_EVENTS = (
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

_LOCK = threading.RLock()
_CLOCK: Optional[Callable[[], datetime]] = None  # injectable for deterministic tests


def set_clock(fn: Optional[Callable[[], datetime]]) -> None:
    """Inject aware UTC clock for tests. None restores system UTC."""
    global _CLOCK
    _CLOCK = fn


def now_utc() -> datetime:
    if _CLOCK is not None:
        dt = _CLOCK()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return now_utc().isoformat()


def schedules_root() -> Path:
    p = Path(DATA_DIR) / "customer_publish_schedules"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    return schedules_root() / "INDEX.json"


def _schedule_path(schedule_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", schedule_id)[:80]
    return schedules_root() / f"{safe}.json"


def _load_index() -> Dict[str, Any]:
    path = _index_path()
    if not path.is_file():
        return {"contract": CONTRACT_VERSION, "ids": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"contract": CONTRACT_VERSION, "ids": []}


def _save_index(data: Dict[str, Any]) -> None:
    path = _index_path()
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_schedule(schedule_id: str) -> Optional[Dict[str, Any]]:
    path = _schedule_path(schedule_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_schedule(rec: Dict[str, Any]) -> Path:
    rec["updated_at"] = _now_iso()
    path = _schedule_path(str(rec["schedule_id"]))
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(scrub_secrets(rec), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    with _LOCK:
        idx = _load_index()
        sid = str(rec["schedule_id"])
        ids = list(idx.get("ids") or [])
        if sid not in ids:
            ids.append(sid)
        idx["ids"] = ids
        idx["updated_at"] = _now_iso()
        _save_index(idx)
    return path


def list_all_schedules() -> List[Dict[str, Any]]:
    out = []
    for sid in list(_load_index().get("ids") or []):
        rec = load_schedule(str(sid))
        if rec:
            out.append(rec)
    return out


def normalize_local_datetime(
    *,
    local_datetime: str,
    tz_name: str,
) -> Dict[str, Any]:
    """Canonical timezone conversion — reject ambiguous/nonexistent local times."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = str(tz_name or "").strip()
    if not name:
        return {"ok": False, "error": "timezone_required", "error_code": "VALIDATION_FAILURE"}
    try:
        zi = ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError, Exception):
        return {"ok": False, "error": "invalid_timezone", "error_code": "VALIDATION_FAILURE", "timezone": name}

    raw = str(local_datetime or "").strip()
    if not raw:
        return {"ok": False, "error": "local_datetime_required", "error_code": "VALIDATION_FAILURE"}

    # Accept "YYYY-MM-DD HH:MM" or "YYYY-MM-DDTHH:MM[:SS]"
    candidates = [raw, raw.replace(" ", "T")]
    parsed_naive = None
    for c in candidates:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed_naive = datetime.strptime(c.replace("Z", ""), fmt)
                break
            except ValueError:
                continue
        if parsed_naive:
            break
    if parsed_naive is None:
        return {"ok": False, "error": "invalid_local_datetime", "error_code": "VALIDATION_FAILURE"}

    # Detect nonexistent first (DST spring-forward gap) via round-trip
    try:
        dt0 = parsed_naive.replace(tzinfo=zi, fold=0)
        utc0 = dt0.astimezone(timezone.utc)
        back = utc0.astimezone(zi)
        if (back.year, back.month, back.day, back.hour, back.minute) != (
            parsed_naive.year,
            parsed_naive.month,
            parsed_naive.day,
            parsed_naive.hour,
            parsed_naive.minute,
        ):
            return {
                "ok": False,
                "error": "nonexistent_local_time",
                "error_code": "VALIDATION_FAILURE",
                "policy": "reject_dst_gap",
                "note": "Nonexistent DST gap times must not silently convert",
            }
        dt1 = parsed_naive.replace(tzinfo=zi, fold=1)
        utc1 = dt1.astimezone(timezone.utc)
        # Ambiguous if fold=0 and fold=1 produce different UTC instants
        if utc0 != utc1:
            return {
                "ok": False,
                "error": "ambiguous_local_time",
                "error_code": "VALIDATION_FAILURE",
                "policy": "reject_ambiguous_dst_fold",
                "note": "Ambiguous local times must not silently convert",
            }
        utc = utc0
    except Exception as exc:
        return {
            "ok": False,
            "error": "timezone_convert_failed",
            "error_code": "VALIDATION_FAILURE",
            "detail": str(exc)[:120],
        }

    return {
        "ok": True,
        "timezone": name,
        "local_datetime": parsed_naive.strftime("%Y-%m-%dT%H:%M:%S"),
        "scheduled_at_utc": utc.isoformat(),
        "scheduled_at_utc_epoch": utc.timestamp(),
    }


def compute_schedule_fingerprint(
    *,
    login_id: str,
    job_id: int,
    revision_id: str,
    channel_id: int,
    provider: str,
    scheduled_at_utc: str,
) -> str:
    from pipeline.idempotency.fingerprint import compute_fingerprint

    return compute_fingerprint(
        job_id=str(job_id),
        stage=SCHEDULE_STAGE,
        entity_id=f"ch{int(channel_id)}:{revision_id}:sched",
        contract_version=SCHEDULE_CONTRACT,
        provider=str(provider or "mock"),
        inputs={
            "login_id": login_id,
            "revision_id": revision_id,
            "channel_id": int(channel_id),
            "scheduled_at_utc": scheduled_at_utc,
            # no tokens
        },
    )


def compute_execution_fingerprint(schedule_id: str, scheduled_at_utc: str) -> str:
    from pipeline.idempotency.fingerprint import compute_fingerprint

    return compute_fingerprint(
        job_id=str(schedule_id),
        stage=f"{SCHEDULE_STAGE}_exec",
        entity_id=schedule_id,
        contract_version=SCHEDULE_CONTRACT,
        inputs={"scheduled_at_utc": scheduled_at_utc, "kind": "execute"},
    )


def _idem_store():
    from pipeline.idempotency.store import IdempotencyStore

    return IdempotencyStore(schedules_root() / "idempotency")


def _emit_job_event(job_id: int, event: str, **extra: Any) -> None:
    try:
        append_lifecycle_event(
            int(job_id),
            scrub_secrets({"event": event, "type": event, "at": _now_iso(), **extra}),
        )
    except Exception:
        pass


def create_schedule(
    login_id: str,
    *,
    job_id: int,
    channel_ids: Sequence[int],
    local_datetime: str,
    timezone_name: str,
    channel_id: Optional[int] = None,
    revision_id: Optional[str] = None,
    provider: str = "mock",
    identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SCHEDULE PUBLISH — validates gates, persists SCHEDULED. No provider upload."""
    with _LOCK:
        _emit_job_event(int(job_id), "SCHEDULE_VALIDATION_STARTED")
        gate = validate_publish_gates(
            login_id,
            int(job_id),
            channel_ids=channel_ids,
            channel_id=channel_id,
            revision_id=revision_id,
            provider=provider,
            identity=identity,
        )
        if not gate.get("admitted"):
            _emit_job_event(
                int(job_id),
                "SCHEDULE_VALIDATION_FAILED",
                blockers=gate.get("blockers"),
            )
            return scrub_secrets(
                {
                    "ok": False,
                    "admitted": False,
                    "schedule_status": "SCHEDULE_VALIDATION_FAILED",
                    "error": gate.get("error") or "schedule_validation_failed",
                    "error_code": gate.get("error_code") or "VALIDATION_FAILURE",
                    "blockers": gate.get("blockers"),
                    "provider_called": False,
                }
            )

        # Provider capability: mock always; youtube requires config unless mock path
        from publishers.customer_publish_provider import get_publish_provider

        prov = get_publish_provider(provider, allow_live=False)
        # Scheduling capability: C07-SCHED supports scheduling intent for mock/youtube_mock;
        # live provider "scheduledPrivacy" is NOT_SUPPORTED (we schedule locally, not via YT schedule API)
        capability = {
            "local_schedule": True,
            "provider_native_schedule": "NOT_SUPPORTED",
            "note": "Local ScheduledPublish only — no browser / native YT schedule API in this phase",
        }

        tz = normalize_local_datetime(local_datetime=local_datetime, tz_name=timezone_name)
        if not tz.get("ok"):
            _emit_job_event(int(job_id), "SCHEDULE_VALIDATION_FAILED", error=tz.get("error"))
            return scrub_secrets(
                {
                    "ok": False,
                    "schedule_status": "SCHEDULE_VALIDATION_FAILED",
                    "error": tz.get("error"),
                    "error_code": tz.get("error_code") or "VALIDATION_FAILURE",
                    "provider_called": False,
                    **{k: v for k, v in tz.items() if k not in ("ok",)},
                }
            )

        utc_epoch = float(tz["scheduled_at_utc_epoch"])
        if utc_epoch <= now_utc().timestamp():
            _emit_job_event(int(job_id), "SCHEDULE_VALIDATION_FAILED", error="past_schedule")
            return scrub_secrets(
                {
                    "ok": False,
                    "schedule_status": "SCHEDULE_VALIDATION_FAILED",
                    "error": "past_schedule",
                    "error_code": "VALIDATION_FAILURE",
                    "provider_called": False,
                    "note": "Schedule time must be in the future",
                }
            )

        rev = gate["revision_id"]
        ch_id = int(gate["channel_id"])
        fp = compute_schedule_fingerprint(
            login_id=login_id,
            job_id=int(job_id),
            revision_id=rev,
            channel_id=ch_id,
            provider=provider,
            scheduled_at_utc=tz["scheduled_at_utc"],
        )

        from pipeline.idempotency.states import IdempotencyState
        from pipeline.idempotency.store import IdempotencyRecord

        store_i = _idem_store()
        # Reuse if identical schedule already SUCCEEDED creation
        existing = store_i.get(fp)
        if existing and existing.request_state == IdempotencyState.SUCCEEDED and existing.result_reference:
            prev = load_schedule(existing.result_reference)
            if prev and prev.get("status") in ("SCHEDULED", "DUE", "CLAIMED", "PUBLISHING", "UPLOADED", "REMOTE_PROCESSING", "PUBLISHED"):
                return scrub_secrets(
                    {
                        "ok": True,
                        "reused": True,
                        "schedule": scrub_secrets(prev),
                        "provider_called": False,
                        "note": "BUILD-03 identical schedule fingerprint — reuse",
                    }
                )
            # CANCELLED / SUPERSEDED / MISSED / FAILED → allow new schedule under new claim below
            # Clear succeeded so atomic_claim can proceed: put NOT_STARTED-like by deleting via overwrite
            if prev and prev.get("status") in ("CANCELLED", "SUPERSEDED", "MISSED", "PUBLISH_FAILED", "SCHEDULE_VALIDATION_FAILED"):
                from pipeline.idempotency.states import IdempotencyState as IS

                existing.request_state = IS.FAILED_FINAL
                existing.metadata["superseded_inactive"] = True
                store_i.put(existing)
                # New fingerprint variant to allow fresh schedule after cancel
                fp = compute_schedule_fingerprint(
                    login_id=login_id,
                    job_id=int(job_id),
                    revision_id=rev,
                    channel_id=ch_id,
                    provider=provider,
                    scheduled_at_utc=tz["scheduled_at_utc"] + f"|after:{prev.get('schedule_id')}",
                )

        record = IdempotencyRecord(
            fingerprint=fp,
            job_id=str(job_id),
            stage=SCHEDULE_STAGE,
            entity_id=f"ch{ch_id}:{rev}",
            provider=str(provider),
            max_attempts=3,
            metadata={"login_id": login_id},
        )
        claimed, ex = store_i.atomic_claim(record, worker_id=f"sched:{login_id}")
        if not claimed:
            if ex and ex.request_state == IdempotencyState.SUCCEEDED and ex.result_reference:
                prev = load_schedule(ex.result_reference)
                if prev and prev.get("status") in (
                    "SCHEDULED",
                    "DUE",
                    "CLAIMED",
                    "PUBLISHING",
                    "UPLOADED",
                    "REMOTE_PROCESSING",
                    "PUBLISHED",
                ):
                    return scrub_secrets(
                        {
                            "ok": True,
                            "reused": True,
                            "schedule": scrub_secrets(prev) if prev else None,
                            "provider_called": False,
                        }
                    )
            return scrub_secrets(
                {
                    "ok": False if not (ex and ex.request_state == IdempotencyState.IN_PROGRESS) else True,
                    "error": "schedule_claim_blocked",
                    "error_code": "IDEMPOTENCY",
                    "in_progress": bool(ex and ex.request_state == IdempotencyState.IN_PROGRESS),
                    "reused": bool(ex and ex.request_state == IdempotencyState.IN_PROGRESS),
                    "provider_called": False,
                    "note": "Concurrent duplicate schedule — one claim",
                }
            )
        schedule_id = "sch_" + uuid.uuid4().hex[:16]
        row = get_job(int(job_id)) or {}
        rec = {
            "contract": CONTRACT_VERSION,
            "kind": "ScheduledPublish",
            "schedule_id": schedule_id,
            "login_id": login_id,
            "job_id": int(job_id),
            "revision_id": rev,
            "approved_revision": rev,
            "channel_id": ch_id,
            "provider": provider,
            "language": gate.get("language"),
            "artifact_path": gate.get("artifact_path"),
            "publish_intent_ref": {
                "stage": "c07_customer_publish",
                "job_id": int(job_id),
                "revision_id": rev,
            },
            "local_datetime": tz["local_datetime"],
            "timezone": tz["timezone"],
            "scheduled_at_utc": tz["scheduled_at_utc"],
            "status": "SCHEDULED",
            "cancellation_state": "NONE",
            "execution_ref": None,
            "fingerprint": fp,
            "supersedes": None,
            "superseded_by": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "mock": True,
            "capability": capability,
            "generation_fingerprint": row.get("generation_fingerprint"),
            "missed_grace_sec": MISSED_GRACE_SEC,
            "provider_name": getattr(prov, "name", provider),
        }
        save_schedule(rec)
        # Mark creation SUCCEEDED with schedule id
        rec_i = store_i.get(fp)
        if rec_i:
            from pipeline.idempotency.states import IdempotencyState as IS
            import time

            rec_i.request_state = IS.SUCCEEDED
            rec_i.result_reference = schedule_id
            rec_i.completed_at = time.time()
            store_i.put(rec_i)

        _emit_job_event(int(job_id), "SCHEDULE_CREATED", schedule_id=schedule_id, scheduled_at_utc=tz["scheduled_at_utc"])
        return scrub_secrets(
            {
                "ok": True,
                "reused": False,
                "schedule": scrub_secrets(rec),
                "provider_called": False,
                "note": "Schedule created — no provider upload",
            }
        )


def cancel_schedule(
    login_id: str,
    schedule_id: str,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Cancel before execution. Idempotent. Never fake-cancel active publish."""
    with _LOCK:
        rec = load_schedule(schedule_id)
        if not rec:
            return {"ok": False, "error": "schedule_not_found", "error_code": "not_found"}
        if str(rec.get("login_id")) != str(login_id):
            return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}
        if int(rec.get("channel_id") or 0) not in {int(x) for x in channel_ids}:
            return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}

        st = str(rec.get("status") or "")
        if st == "CANCELLED":
            return scrub_secrets({"ok": True, "reused": True, "schedule": rec, "note": "Already cancelled"})
        if st in ("PUBLISHED",):
            return scrub_secrets(
                {
                    "ok": False,
                    "error": "cannot_cancel_published",
                    "error_code": "INVALID_STATE",
                    "schedule": rec,
                    "note": "PUBLISHED cannot become CANCELLED without provider reversal",
                }
            )
        if st in ("CLAIMED", "PUBLISHING", "UPLOADED", "REMOTE_PROCESSING"):
            return scrub_secrets(
                {
                    "ok": False,
                    "error": "execution_already_started",
                    "error_code": "INVALID_STATE",
                    "schedule": rec,
                    "status": st,
                    "note": "Cannot fake-cancel active execution — truthful state retained",
                }
            )
        if st not in ("SCHEDULED", "DUE", "MISSED", "SCHEDULE_VALIDATION_FAILED"):
            return scrub_secrets(
                {
                    "ok": False,
                    "error": "not_cancellable",
                    "error_code": "INVALID_STATE",
                    "schedule": rec,
                }
            )

        rec["status"] = "CANCELLED"
        rec["cancellation_state"] = "CANCELLED"
        save_schedule(rec)
        _emit_job_event(int(rec["job_id"]), "SCHEDULE_CANCELLED", schedule_id=schedule_id)
        return scrub_secrets({"ok": True, "schedule": rec, "provider_called": False})


def reschedule(
    login_id: str,
    schedule_id: str,
    *,
    channel_ids: Sequence[int],
    local_datetime: str,
    timezone_name: str,
    identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reschedule only before execution — supersede old, create new (one future execution)."""
    with _LOCK:
        rec = load_schedule(schedule_id)
        if not rec:
            return {"ok": False, "error": "schedule_not_found"}
        if str(rec.get("login_id")) != str(login_id):
            return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}
        if int(rec.get("channel_id") or 0) not in {int(x) for x in channel_ids}:
            return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}
        st = str(rec.get("status") or "")
        if st not in ("SCHEDULED", "DUE", "MISSED"):
            return scrub_secrets(
                {
                    "ok": False,
                    "error": "cannot_reschedule",
                    "error_code": "INVALID_STATE",
                    "status": st,
                    "note": "Reschedule only before execution starts",
                }
            )

        created = create_schedule(
            login_id,
            job_id=int(rec["job_id"]),
            channel_ids=channel_ids,
            local_datetime=local_datetime,
            timezone_name=timezone_name,
            channel_id=int(rec["channel_id"]),
            revision_id=str(rec.get("revision_id")),
            provider=str(rec.get("provider") or "mock"),
            identity=identity,
        )
        if not created.get("ok"):
            return created
        new_sch = created.get("schedule") or {}
        new_id = new_sch.get("schedule_id")
        rec["status"] = "SUPERSEDED"
        rec["superseded_by"] = new_id
        save_schedule(rec)
        if new_id:
            fresh = load_schedule(new_id)
            if fresh:
                fresh["supersedes"] = schedule_id
                save_schedule(fresh)
                created["schedule"] = scrub_secrets(fresh)
        _emit_job_event(int(rec["job_id"]), "SCHEDULE_UPDATED", old=schedule_id, new=new_id)
        return scrub_secrets(
            {
                "ok": True,
                "schedule": created.get("schedule"),
                "superseded": scrub_secrets(rec),
                "provider_called": False,
                "note": "Old schedule SUPERSEDED — only new schedule can execute",
            }
        )


def _revision_still_valid(rec: Dict[str, Any]) -> Dict[str, Any]:
    row = get_job(int(rec["job_id"]))
    if not row:
        return {"ok": False, "error": "job_missing"}
    current = compute_revision_id(row)
    if str(rec.get("revision_id")) != current:
        return {"ok": False, "error": "revision_changed", "current": current, "frozen": rec.get("revision_id")}
    if str(row.get("customer_approval") or "").upper() != "APPROVED":
        return {"ok": False, "error": "no_longer_approved"}
    if str(row.get("upload_status") or "") not in ("ready_to_upload", "dry_run_uploaded", "uploaded"):
        # ready_to_upload required unless already publishing path advanced
        if str(row.get("upload_status") or "") != "ready_to_upload":
            return {"ok": False, "error": "ready_to_upload_lost"}
    path = str(rec.get("artifact_path") or row.get("local_path") or "")
    import os

    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "artifact_missing"}
    if str(row.get("local_path") or "") != str(rec.get("artifact_path") or row.get("local_path") or ""):
        # frozen artifact must match
        if rec.get("artifact_path") and str(row.get("local_path")) != str(rec.get("artifact_path")):
            return {"ok": False, "error": "artifact_mismatch"}
    return {"ok": True, "row": row}


def mark_missed_schedules(*, now: Optional[datetime] = None) -> List[str]:
    """Overdue beyond grace → MISSED (never auto-publish)."""
    n = now or now_utc()
    marked = []
    with _LOCK:
        for rec in list_all_schedules():
            if str(rec.get("status")) != "SCHEDULED":
                continue
            try:
                due = datetime.fromisoformat(str(rec["scheduled_at_utc"]))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            age = (n - due).total_seconds()
            if age > float(rec.get("missed_grace_sec") or MISSED_GRACE_SEC):
                rec["status"] = "MISSED"
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_MISSED", schedule_id=rec["schedule_id"])
                marked.append(rec["schedule_id"])
    return marked


def process_due_schedules(
    *,
    worker_id: str = "apscheduler:publish_schedule",
    now: Optional[datetime] = None,
    max_one: bool = True,
    allow_live_provider: bool = False,
) -> Dict[str, Any]:
    """Called from SchedulerService — claim due schedule and hand off to C07-PUB.

    Never uploads directly. Never executes SUPERSEDED/CANCELLED/PUBLISHED/MISSED.
    """
    n = now or now_utc()
    mark_missed_schedules(now=n)
    executed = []
    skipped = []

    with _LOCK:
        candidates = []
        for rec in list_all_schedules():
            if str(rec.get("status")) != "SCHEDULED":
                continue
            if rec.get("superseded_by") or str(rec.get("status")) == "SUPERSEDED":
                continue
            try:
                due = datetime.fromisoformat(str(rec["scheduled_at_utc"]))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if due > n:
                continue
            age = (n - due).total_seconds()
            if age > float(rec.get("missed_grace_sec") or MISSED_GRACE_SEC):
                continue  # already MISSED by mark_missed
            candidates.append(rec)

        candidates.sort(key=lambda r: str(r.get("scheduled_at_utc") or ""))

        from pipeline.idempotency.states import IdempotencyState
        from pipeline.idempotency.store import IdempotencyRecord

        store_i = _idem_store()

        for rec in candidates:
            sid = str(rec["schedule_id"])
            efp = compute_execution_fingerprint(sid, str(rec["scheduled_at_utc"]))
            erec = IdempotencyRecord(
                fingerprint=efp,
                job_id=str(rec["job_id"]),
                stage=f"{SCHEDULE_STAGE}_exec",
                entity_id=sid,
                provider=str(rec.get("provider") or "mock"),
                max_attempts=3,
                metadata={"worker_id": worker_id},
            )
            claimed, existing = store_i.atomic_claim(erec, worker_id=worker_id)
            if not claimed:
                skipped.append({"schedule_id": sid, "reason": "claim_blocked", "state": getattr(existing, "request_state", None)})
                continue

            # Mark DUE then CLAIMED
            rec["status"] = "DUE"
            save_schedule(rec)
            _emit_job_event(int(rec["job_id"]), "SCHEDULE_DUE", schedule_id=sid)
            rec["status"] = "CLAIMED"
            rec["execution_ref"] = {"worker_id": worker_id, "claimed_at": _now_iso(), "fingerprint": efp}
            save_schedule(rec)
            _emit_job_event(int(rec["job_id"]), "SCHEDULE_CLAIMED", schedule_id=sid)

            # Revision immutability fail-closed
            valid = _revision_still_valid(rec)
            if not valid.get("ok"):
                rec["status"] = "PUBLISH_FAILED"
                rec["error"] = valid.get("error")
                save_schedule(rec)
                _emit_job_event(
                    int(rec["job_id"]),
                    "SCHEDULE_HANDOFF_FAILED",
                    schedule_id=sid,
                    error=valid.get("error"),
                )
                _mark_exec_failed(store_i, efp, retryable=False)
                executed.append({"schedule_id": sid, "ok": False, "error": valid.get("error")})
                if max_one:
                    break
                continue

            _emit_job_event(int(rec["job_id"]), "SCHEDULE_HANDOFF_STARTED", schedule_id=sid)
            rec["status"] = "PUBLISHING"
            save_schedule(rec)
            _emit_job_event(int(rec["job_id"]), "SCHEDULE_EXECUTION_STARTED", schedule_id=sid)

            # HANDOFF → C07-PUB only (no direct provider upload)
            from app.customer_publish import publish_customer_job

            identity = {
                "login_id": rec["login_id"],
                "authenticated": True,
                "auth_state": "AUTHENTICATED",
                "production_access": True,
                "entitlement_state": "ACTIVE",
                "account_state": "ACTIVE",
            }
            try:
                result = publish_customer_job(
                    str(rec["login_id"]),
                    int(rec["job_id"]),
                    channel_ids=[int(rec["channel_id"])],
                    channel_id=int(rec["channel_id"]),
                    revision_id=str(rec.get("revision_id")),
                    provider=str(rec.get("provider") or "mock"),
                    scenario="happy_path",
                    allow_live_provider=bool(allow_live_provider),
                    identity=identity,
                )
            except Exception as exc:
                rec["status"] = "PUBLISH_FAILED"
                rec["error"] = str(exc)[:200]
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_EXECUTION_FAILED", schedule_id=sid)
                _mark_exec_failed(store_i, efp, retryable=True)
                executed.append({"schedule_id": sid, "ok": False, "error": "handoff_exception"})
                if max_one:
                    break
                continue

            rstate = str((result.get("result") or {}).get("state") or "")
            if result.get("result", {}).get("reconciliation_required") or rstate == "RECONCILIATION_REQUIRED":
                rec["status"] = "RECONCILIATION_REQUIRED"
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_RECONCILIATION_REQUIRED", schedule_id=sid)
                _mark_exec_unknown(store_i, efp)
            elif rstate == "UPLOAD_ACCEPTED":
                rec["status"] = "UPLOADED"
                rec["publish_result"] = scrub_secrets(result.get("result"))
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_EXECUTION_COMPLETED", schedule_id=sid, publish_state=rstate)
                # Execution claim stays in-progress until published via refresh — mark succeeded for trigger
                _mark_exec_succeeded(store_i, efp, sid)
            elif rstate == "PUBLISHED":
                rec["status"] = "PUBLISHED"
                rec["publish_result"] = scrub_secrets(result.get("result"))
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_EXECUTION_COMPLETED", schedule_id=sid, publish_state="PUBLISHED")
                _mark_exec_succeeded(store_i, efp, sid)
            elif not result.get("ok"):
                rec["status"] = "PUBLISH_FAILED"
                rec["publish_result"] = scrub_secrets(result.get("result"))
                save_schedule(rec)
                _emit_job_event(int(rec["job_id"]), "SCHEDULE_EXECUTION_FAILED", schedule_id=sid)
                _mark_exec_failed(store_i, efp, retryable=bool(result.get("retryable")))
            else:
                rec["status"] = "UPLOADED"
                rec["publish_result"] = scrub_secrets(result.get("result"))
                save_schedule(rec)
                _mark_exec_succeeded(store_i, efp, sid)

            executed.append(
                {
                    "schedule_id": sid,
                    "ok": bool(result.get("ok")),
                    "publish_state": rstate,
                    "provider_called_by": "c07_pub",
                    "scheduler_uploaded": False,
                }
            )
            if max_one:
                break

    return scrub_secrets(
        {
            "ok": True,
            "executed": executed,
            "skipped": skipped,
            "count": len(executed),
            "scheduler_direct_upload": False,
            "note": "Scheduler timing only — publish delegated to C07-PUB",
            "mock": True,
            "now": n.isoformat(),
        }
    )


def _mark_exec_succeeded(store_i, fp: str, ref: str) -> None:
    from pipeline.idempotency.states import IdempotencyState
    import time

    rec = store_i.get(fp)
    if not rec:
        return
    rec.request_state = IdempotencyState.SUCCEEDED
    rec.result_reference = ref
    rec.completed_at = time.time()
    store_i.put(rec)


def _mark_exec_failed(store_i, fp: str, *, retryable: bool) -> None:
    from pipeline.idempotency.states import IdempotencyState

    rec = store_i.get(fp)
    if not rec:
        return
    rec.request_state = (
        IdempotencyState.FAILED_RETRYABLE if retryable else IdempotencyState.FAILED_FINAL
    )
    store_i.put(rec)


def _mark_exec_unknown(store_i, fp: str) -> None:
    from pipeline.idempotency.states import IdempotencyState

    rec = store_i.get(fp)
    if not rec:
        return
    rec.request_state = IdempotencyState.UNKNOWN
    rec.metadata["safe_to_retry"] = False
    store_i.put(rec)


def refresh_schedule(
    login_id: str,
    schedule_id: str,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Refresh schedule + optional C07-PUB observe when upload accepted."""
    rec = load_schedule(schedule_id)
    if not rec:
        return {"ok": False, "error": "schedule_not_found"}
    if str(rec.get("login_id")) != str(login_id):
        return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}
    if int(rec.get("channel_id") or 0) not in {int(x) for x in channel_ids}:
        return {"ok": False, "error": "schedule_access_denied", "error_code": "OWNERSHIP_FAILURE"}

    st = str(rec.get("status") or "")
    pub = None
    if st in ("UPLOADED", "REMOTE_PROCESSING", "RECONCILIATION_REQUIRED", "PUBLISHING"):
        from app.customer_publish import refresh_publish_status

        pub = refresh_publish_status(
            login_id,
            int(rec["job_id"]),
            channel_ids=channel_ids,
            scenario="published_immediate",
        )
        rstate = str((pub.get("result") or {}).get("state") or "")
        if rstate == "PUBLISHED":
            rec["status"] = "PUBLISHED"
        elif rstate == "REMOTE_PROCESSING":
            rec["status"] = "REMOTE_PROCESSING"
        elif rstate == "RECONCILIATION_REQUIRED":
            rec["status"] = "RECONCILIATION_REQUIRED"
        elif rstate == "FAILED":
            rec["status"] = "PUBLISH_FAILED"
        rec["publish_result"] = scrub_secrets(pub.get("result"))
        save_schedule(rec)

    return scrub_secrets({"ok": True, "schedule": rec, "publish_refresh": pub})


def list_schedules_for_customer(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    job_id: Optional[int] = None,
) -> Dict[str, Any]:
    owned = {int(x) for x in channel_ids}
    items = []
    for rec in list_all_schedules():
        if str(rec.get("login_id")) != str(login_id):
            continue
        if int(rec.get("channel_id") or 0) not in owned:
            continue
        if job_id is not None and int(rec.get("job_id") or 0) != int(job_id):
            continue
        items.append(scrub_secrets(rec))
    items.sort(key=lambda r: str(r.get("scheduled_at_utc") or ""), reverse=True)
    return {"ok": True, "schedules": items, "contract": CONTRACT_VERSION, "secrets_excluded": True}


def project_schedule_panel(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    job_id: Optional[int] = None,
) -> Dict[str, Any]:
    listed = list_schedules_for_customer(login_id, channel_ids=channel_ids, job_id=job_id)
    schedules = listed.get("schedules") or []
    active = next((s for s in schedules if s.get("status") in ("SCHEDULED", "DUE", "CLAIMED", "PUBLISHING", "UPLOADED", "REMOTE_PROCESSING")), None)
    return scrub_secrets(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "schedules": schedules,
            "active": active,
            "actions": {
                "SCHEDULE": True,
                "RESCHEDULE": bool(active and active.get("status") in ("SCHEDULED", "DUE", "MISSED")),
                "CANCEL_SCHEDULE": bool(active and active.get("status") in ("SCHEDULED", "DUE", "MISSED")),
                "REFRESH": bool(active),
            },
            "missed_policy": {
                "grace_sec": MISSED_GRACE_SEC,
                "behavior": "MISSED_REQUIRES_ACTION",
                "auto_catch_up_publish": False,
            },
            "scheduling_implemented": True,
            "scheduler_direct_upload": False,
            "secrets_excluded": True,
        }
    )


def recover_schedules_after_restart() -> Dict[str, Any]:
    """Restart: future stay SCHEDULED; stale CLAIMED without handoff → reconcile; never promote UNKNOWN→PUBLISHED."""
    n = now_utc()
    mark_missed_schedules(now=n)
    fixed = []
    with _LOCK:
        for rec in list_all_schedules():
            st = str(rec.get("status") or "")
            if st == "CLAIMED":
                # Claimed but no publish result — leave for re-tick only if execution idempotency allows
                # Do not mark PUBLISHED
                fixed.append({"schedule_id": rec["schedule_id"], "status": st, "note": "awaiting_tick_or_recon"})
            if st == "PUBLISHED":
                fixed.append({"schedule_id": rec["schedule_id"], "status": "PUBLISHED", "note": "never_reexecute"})
    return {"ok": True, "recovered": fixed, "publishes": False}


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat, label in (
        (r"(?m)^\s*class\s+SchedulerService\b", "SchedulerService"),
        (r"(?m)^\s*def\s+generate_video\s*\(", "generate_video"),
        (r"(?m)^\s*def\s+evaluate_publishability\s*\(", "evaluate_publishability"),
        (r"(?m)^\s*class\s+IdempotencyStore\b", "IdempotencyStore"),
        (r"(?m)^\s*def\s+compute_fingerprint\s*\(", "compute_fingerprint"),
        (r"customer_scheduler\.py", "customer_scheduler"),
        (r"publishing_scheduler\.py", "publishing_scheduler"),
        (r"schedule_idempotency\.py", "schedule_idempotency"),
    ):
        if _re.search(pat, source):
            bad.append(label)
    return bad
