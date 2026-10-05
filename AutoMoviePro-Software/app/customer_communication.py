"""C09 — Customer Communication & Help (projection only).

Notifications and Help derive from existing monitor/lifecycle/publish/schedule
authorities. They do NOT own production state and never mutate jobs/publish/schedule.

Read-state persistence only. Dedup via stable notification_id (event identity).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR
from app.customer_job import get_job, job_owned_by_channels, list_customer_jobs, sanitize_customer_error

CONTRACT_VERSION = "C09.1"
SUPPORTED_LOCALES = ("en", "bn", "hi", "ur", "ta", "ml")
FALLBACK_LOCALE = "en"

# Categories mapped from actual existing states/events — unavailable ones marked
NOTIFICATION_CATEGORIES = (
    "PRODUCTION_STARTED",
    "PRODUCTION_COMPLETED",
    "VERIFICATION_REQUIRED",
    "REPAIR_REQUIRED",
    "PREVIEW_READY",
    "APPROVAL_REQUIRED",
    "APPROVAL_REJECTED",
    "PUBLISH_STARTED",
    "UPLOAD_ACCEPTED",
    "REMOTE_PROCESSING",
    "PUBLISHED",
    "SCHEDULE_CREATED",
    "SCHEDULE_DUE",
    "SCHEDULE_MISSED",
    "RECONCILIATION_REQUIRED",
    "PRODUCTION_FAILED",
    "RECOVERY_REQUIRED",
)

# Message catalog — deterministic; no external translation API
_MESSAGE_CATALOG: Dict[str, Dict[str, str]] = {
    "en": {
        "PRODUCTION_STARTED": "Production started",
        "PRODUCTION_COMPLETED": "Production finished (not published)",
        "VERIFICATION_REQUIRED": "Verification in progress",
        "REPAIR_REQUIRED": "Repair required",
        "PREVIEW_READY": "Preview ready",
        "APPROVAL_REQUIRED": "Approval required — does not publish",
        "APPROVAL_REJECTED": "Revision rejected — does not regenerate",
        "PUBLISH_STARTED": "Publishing started",
        "UPLOAD_ACCEPTED": "Upload accepted — not published yet",
        "REMOTE_PROCESSING": "Remote processing — not published yet",
        "PUBLISHED": "Published",
        "SCHEDULE_CREATED": "Publish schedule created",
        "SCHEDULE_DUE": "Scheduled publish is due",
        "SCHEDULE_MISSED": "Schedule missed — action required",
        "RECONCILIATION_REQUIRED": "Reconciliation required — do not assume success",
        "PRODUCTION_FAILED": "Production failed",
        "RECOVERY_REQUIRED": "Recovery required",
        "help_fallback": "I can explain your current production state. Ask about approval, publish, schedule, or recovery.",
        "help_unknown": "UNKNOWN — I cannot confirm that from current authoritative state.",
        "unavailable": "This notification category is not emitted by the current authority.",
    },
    "bn": {
        "PRODUCTION_STARTED": "প্রোডাকশন শুরু হয়েছে",
        "PRODUCTION_COMPLETED": "প্রোডাকশন শেষ (প্রকাশিত নয়)",
        "VERIFICATION_REQUIRED": "যাচাই চলছে",
        "REPAIR_REQUIRED": "মেরামত প্রয়োজন",
        "PREVIEW_READY": "প্রিভিউ প্রস্তুত",
        "APPROVAL_REQUIRED": "অনুমোদন প্রয়োজন — প্রকাশ করে না",
        "APPROVAL_REJECTED": "প্রত্যাখ্যান — পুনরায় তৈরি করে না",
        "PUBLISH_STARTED": "প্রকাশনা শুরু",
        "UPLOAD_ACCEPTED": "আপলোড গৃহীত — এখনও প্রকাশিত নয়",
        "REMOTE_PROCESSING": "রিমোট প্রসেসিং — এখনও প্রকাশিত নয়",
        "PUBLISHED": "প্রকাশিত",
        "SCHEDULE_CREATED": "শিডিউল তৈরি",
        "SCHEDULE_DUE": "শিডিউল সময় হয়েছে",
        "SCHEDULE_MISSED": "শিডিউল মিস — পদক্ষেপ প্রয়োজন",
        "RECONCILIATION_REQUIRED": "সমন্বয় প্রয়োজন",
        "PRODUCTION_FAILED": "প্রোডাকশন ব্যর্থ",
        "RECOVERY_REQUIRED": "রিকভারি প্রয়োজন",
        "help_fallback": "বর্তমান স্টেট ব্যাখ্যা করতে পারি।",
        "help_unknown": "UNKNOWN — নিশ্চিত করা যায়নি।",
        "unavailable": "এই ইভেন্ট বর্তমান সিস্টেমে নেই।",
    },
}

# Fill missing locales from English fallback structure
for _loc in SUPPORTED_LOCALES:
    if _loc not in _MESSAGE_CATALOG:
        _MESSAGE_CATALOG[_loc] = dict(_MESSAGE_CATALOG["en"])

DEEP_LINKS = {
    "APPROVAL_REQUIRED": {"target": "approval", "hash": "#ws-approval", "label": "Open Preview/Approval"},
    "APPROVAL_REJECTED": {"target": "approval", "hash": "#ws-approval", "label": "Open Approval"},
    "REPAIR_REQUIRED": {"target": "monitor", "hash": "#ws-monitor", "label": "Open Production Monitor"},
    "PREVIEW_READY": {"target": "preview", "hash": "#ws-preview", "label": "Open Preview"},
    "RECONCILIATION_REQUIRED": {"target": "publishing", "hash": "#ws-publishing", "label": "Open Publishing"},
    "UPLOAD_ACCEPTED": {"target": "publishing", "hash": "#ws-publishing", "label": "Refresh publish status"},
    "REMOTE_PROCESSING": {"target": "publishing", "hash": "#ws-publishing", "label": "Refresh publish status"},
    "SCHEDULE_MISSED": {"target": "schedule", "hash": "#ws-publishing-schedule", "label": "Open Scheduling"},
    "SCHEDULE_DUE": {"target": "schedule", "hash": "#ws-publishing-schedule", "label": "Open Scheduling"},
    "SCHEDULE_CREATED": {"target": "schedule", "hash": "#ws-publishing-schedule", "label": "Open Scheduling"},
    "RECOVERY_REQUIRED": {"target": "monitor", "hash": "#ws-monitor", "label": "Open Production Monitor"},
    "PRODUCTION_FAILED": {"target": "monitor", "hash": "#ws-monitor", "label": "Open Production Monitor"},
    "PUBLISHED": {"target": "publishing", "hash": "#ws-publishing", "label": "Open Publishing"},
    "VERIFICATION_REQUIRED": {"target": "monitor", "hash": "#ws-monitor", "label": "Open Monitor"},
    "PRODUCTION_STARTED": {"target": "monitor", "hash": "#ws-monitor", "label": "Open Monitor"},
    "PRODUCTION_COMPLETED": {"target": "preview", "hash": "#ws-preview", "label": "Open Preview"},
    "PUBLISH_STARTED": {"target": "publishing", "hash": "#ws-publishing", "label": "Open Publishing"},
}

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat()


def _safe_login(login_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (login_id or "anon").strip())[:80] or "anon"


def notifications_dir(login_id: str) -> Path:
    p = Path(DATA_DIR) / "customer_notifications" / _safe_login(login_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_state_path(login_id: str) -> Path:
    return notifications_dir(login_id) / "READ_STATE.json"


def load_read_state(login_id: str) -> Dict[str, Any]:
    path = _read_state_path(login_id)
    if not path.is_file():
        return {"contract": CONTRACT_VERSION, "owner_login_id": login_id, "read": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"contract": CONTRACT_VERSION, "owner_login_id": login_id, "read": {}}
    if str(data.get("owner_login_id") or "") != str(login_id):
        return {"contract": CONTRACT_VERSION, "owner_login_id": login_id, "read": {}}
    data.setdefault("read", {})
    return data


def save_read_state(login_id: str, data: Dict[str, Any]) -> None:
    data["owner_login_id"] = login_id
    data["updated_at"] = _now()
    path = _read_state_path(login_id)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def normalize_locale(locale: Optional[str]) -> str:
    loc = str(locale or FALLBACK_LOCALE).strip().lower()[:8]
    if loc in SUPPORTED_LOCALES:
        return loc
    # unknown → safe fallback
    return FALLBACK_LOCALE


def message_for(category: str, locale: Optional[str] = None) -> str:
    loc = normalize_locale(locale)
    catalog = _MESSAGE_CATALOG.get(loc) or _MESSAGE_CATALOG[FALLBACK_LOCALE]
    return catalog.get(category) or _MESSAGE_CATALOG[FALLBACK_LOCALE].get(category) or category


def scrub_notification(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(x in lk for x in ("token", "secret", "password", "api_key", "authorization")):
                out[k] = "[redacted]"
            else:
                out[k] = scrub_notification(v)
        return out
    if isinstance(obj, list):
        return [scrub_notification(x) for x in obj]
    if isinstance(obj, str):
        return sanitize_customer_error(obj, 400)
    return obj


def _notification_id(*, login_id: str, job_id: int, category: str, source_ref: str) -> str:
    from pipeline.idempotency.fingerprint import hash_text
    from pipeline.idempotency.normalize import canonical_json

    return hash_text(
        canonical_json(
            {
                "login_id": login_id,
                "job_id": int(job_id),
                "category": category,
                "source_ref": source_ref,
            }
        )
    )[:24]


def _map_event_to_category(ev: Dict[str, Any]) -> Optional[str]:
    t = str(ev.get("type") or ev.get("event") or "").upper()
    mapping = {
        "JOB_STARTED": "PRODUCTION_STARTED",
        "JOB_CLAIMED": "PRODUCTION_STARTED",
        "JOB_COMPLETED": "PRODUCTION_COMPLETED",
        "JOB_PREVIEW_READY": "PREVIEW_READY",
        "JOB_APPROVAL_PENDING": "APPROVAL_REQUIRED",
        "JOB_APPROVED": None,  # informational; approval required already covered
        "JOB_REJECTED": "APPROVAL_REJECTED",
        "JOB_FAILED": "PRODUCTION_FAILED",
        "JOB_INTERRUPTED": "RECOVERY_REQUIRED",
        "JOB_RECOVERED": "RECOVERY_REQUIRED",
        "JOB_VERIFYING": "VERIFICATION_REQUIRED",
        "PUBLISH_STARTED": "PUBLISH_STARTED",
        "PUBLISH_UPLOAD_ACCEPTED": "UPLOAD_ACCEPTED",
        "PUBLISH_REMOTE_PROCESSING": "REMOTE_PROCESSING",
        "PUBLISH_COMPLETED": "PUBLISHED",
        "PUBLISH_RECONCILIATION_REQUIRED": "RECONCILIATION_REQUIRED",
        "PUBLISH_FAILED": "PRODUCTION_FAILED",
        "SCHEDULE_CREATED": "SCHEDULE_CREATED",
        "SCHEDULE_DUE": "SCHEDULE_DUE",
        "SCHEDULE_MISSED": "SCHEDULE_MISSED",
        "SCHEDULE_RECONCILIATION_REQUIRED": "RECONCILIATION_REQUIRED",
    }
    return mapping.get(t)


def _map_monitor_to_category(monitor_state: str, row: Dict[str, Any]) -> Optional[str]:
    ms = str(monitor_state or "").upper()
    pstat = str(row.get("publish_status") or "").upper()
    if pstat == "RECONCILIATION_REQUIRED":
        return "RECONCILIATION_REQUIRED"
    if pstat == "REMOTE_PROCESSING":
        return "REMOTE_PROCESSING"
    if pstat == "UPLOAD_ACCEPTED":
        return "UPLOAD_ACCEPTED"
    if pstat == "PUBLISHED":
        return "PUBLISHED"
    if ms in ("APPROVAL_PENDING", "PREVIEW_READY"):
        return "APPROVAL_REQUIRED" if ms == "APPROVAL_PENDING" else "PREVIEW_READY"
    if ms == "VERIFYING":
        return "VERIFICATION_REQUIRED"
    if ms in ("FAILED", "TERMINAL_FAILED", "ACTION_REQUIRED"):
        return "PRODUCTION_FAILED" if ms != "ACTION_REQUIRED" else "RECOVERY_REQUIRED"
    if ms == "INTERRUPTED":
        return "RECOVERY_REQUIRED"
    if ms == "RUNNING":
        return "PRODUCTION_STARTED"
    if ms in ("PUBLISH_RECONCILIATION_REQUIRED",):
        return "RECONCILIATION_REQUIRED"
    if ms == "PUBLISH_REMOTE_PROCESSING":
        return "REMOTE_PROCESSING"
    if ms == "PUBLISH_UPLOAD_ACCEPTED":
        return "UPLOAD_ACCEPTED"
    if ms == "PUBLISHED":
        return "PUBLISHED"
    # Repair: customer_state REPAIRING
    if str(row.get("customer_state") or "").upper() == "REPAIRING":
        return "REPAIR_REQUIRED"
    return None


def _action_required(category: str) -> bool:
    return category in (
        "APPROVAL_REQUIRED",
        "REPAIR_REQUIRED",
        "RECONCILIATION_REQUIRED",
        "SCHEDULE_MISSED",
        "RECOVERY_REQUIRED",
        "PRODUCTION_FAILED",
        "APPROVAL_REJECTED",
    )


def _severity_label(category: str) -> str:
    if category in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "SCHEDULED", "SCHEDULE_CREATED", "SCHEDULE_DUE"):
        return "attention"
    if _action_required(category):
        return "action_required"
    if category in ("PRODUCTION_FAILED",):
        return "error"
    if category in ("PUBLISHED", "PRODUCTION_COMPLETED", "PREVIEW_READY"):
        return "info"
    return "info"


def project_notifications(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    locale: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Deterministic projection from lifecycle + monitor — no second event engine."""
    from app.customer_production_monitor import (
        infer_monitor_state,
        is_live_lab_active,
        load_lifecycle_events,
    )

    loc = normalize_locale(locale)
    # Live Lab must not masquerade as customer production notifications
    if is_live_lab_active():
        lab_note = "live_lab_active — customer notifications suppressed for lab boundary"
    else:
        lab_note = None

    read_state = load_read_state(login_id)
    read_map = dict(read_state.get("read") or {})
    items: List[Dict[str, Any]] = []
    seen_ids = set()

    jobs = list_customer_jobs(40, channel_ids=list(channel_ids))
    for jview in jobs:
        jid = int(jview.get("job_id") or 0)
        if not jid:
            continue
        row = get_job(jid)
        if not row or not job_owned_by_channels(row, list(channel_ids)):
            continue
        requested = str(row.get("requested_by") or "").strip()
        if requested and requested != str(login_id).strip():
            continue

        # Prefer lifecycle events (authoritative event source)
        events = load_lifecycle_events(row, limit=40)
        for ev in events:
            cat = _map_event_to_category(ev)
            if not cat:
                continue
            source_ref = f"{ev.get('type') or ev.get('event')}|{ev.get('at') or ''}|{jid}"
            nid = _notification_id(login_id=login_id, job_id=jid, category=cat, source_ref=source_ref)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            is_read = bool(read_map.get(nid))
            items.append(
                scrub_notification(
                    {
                        "notification_id": nid,
                        "login_id": login_id,
                        "category": cat,
                        "severity": _severity_label(cat),
                        "title_key": cat,
                        "message": message_for(cat, loc),
                        "locale": loc,
                        "read_state": "READ" if is_read else "UNREAD",
                        "action_required": _action_required(cat) and not is_read,
                        "job_id": jid,
                        "revision_id": None,
                        "publication_id": row.get("publish_provider_video_id"),
                        "schedule_id": None,
                        "created_at": ev.get("at") or row.get("updated_at") or row.get("created_at"),
                        "source_event_ref": source_ref,
                        "source_authority": "lifecycle_audit_json",
                        "deep_link": DEEP_LINKS.get(cat),
                        "mutates_production": False,
                    }
                )
            )

        # Supplement from monitor/publish state if not already covered by latest category
        if not lab_note:
            mon_state = infer_monitor_state(row)
            cat2 = _map_monitor_to_category(mon_state, row)
            if cat2:
                source_ref = f"monitor:{mon_state}|publish:{row.get('publish_status')}|{jid}"
                nid = _notification_id(login_id=login_id, job_id=jid, category=cat2, source_ref=source_ref)
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    is_read = bool(read_map.get(nid))
                    items.append(
                        scrub_notification(
                            {
                                "notification_id": nid,
                                "login_id": login_id,
                                "category": cat2,
                                "severity": _severity_label(cat2),
                                "title_key": cat2,
                                "message": message_for(cat2, loc),
                                "locale": loc,
                                "read_state": "READ" if is_read else "UNREAD",
                                "action_required": _action_required(cat2) and not is_read,
                                "job_id": jid,
                                "revision_id": None,
                                "publication_id": row.get("publish_provider_video_id"),
                                "schedule_id": None,
                                "created_at": row.get("updated_at") or row.get("created_at"),
                                "source_event_ref": source_ref,
                                "source_authority": "customer_production_monitor",
                                "deep_link": DEEP_LINKS.get(cat2),
                                "mutates_production": False,
                            }
                        )
                    )

    # Schedule-derived (owned schedules only)
    try:
        from app.customer_publish_schedule import list_schedules_for_customer

        sch = list_schedules_for_customer(login_id, channel_ids=channel_ids)
        for s in sch.get("schedules") or []:
            st = str(s.get("status") or "")
            cat = None
            if st == "MISSED":
                cat = "SCHEDULE_MISSED"
            elif st == "SCHEDULED":
                cat = "SCHEDULE_CREATED"
            elif st == "DUE":
                cat = "SCHEDULE_DUE"
            if not cat:
                continue
            jid = int(s.get("job_id") or 0)
            source_ref = f"schedule:{s.get('schedule_id')}|{st}"
            nid = _notification_id(login_id=login_id, job_id=jid or 0, category=cat, source_ref=source_ref)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            is_read = bool(read_map.get(nid))
            items.append(
                scrub_notification(
                    {
                        "notification_id": nid,
                        "login_id": login_id,
                        "category": cat,
                        "severity": _severity_label(cat),
                        "title_key": cat,
                        "message": message_for(cat, loc),
                        "locale": loc,
                        "read_state": "READ" if is_read else "UNREAD",
                        "action_required": _action_required(cat) and not is_read,
                        "job_id": jid or None,
                        "schedule_id": s.get("schedule_id"),
                        "created_at": s.get("updated_at") or s.get("created_at"),
                        "source_event_ref": source_ref,
                        "source_authority": "customer_publish_schedule",
                        "deep_link": DEEP_LINKS.get(cat),
                        "mutates_production": False,
                    }
                )
            )
    except Exception:
        pass

    # Sort newest first; stable dedupe already by nid
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    items = items[: int(limit)]
    unread = sum(1 for i in items if i.get("read_state") == "UNREAD")
    action_n = sum(1 for i in items if i.get("action_required"))

    return scrub_notification(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "notifications": items,
            "unread_count": unread,
            "action_required_count": action_n,
            "locale": loc,
            "lab_boundary_note": lab_note,
            "is_projection": True,
            "mutates_production": False,
            "paid_api_calls": 0,
            "external_provider_calls": 0,
            "note": (
                "Notification is a projection of existing events/state. "
                "REMOTE_PROCESSING≠PUBLISHED; SCHEDULED≠PUBLISHED; UNKNOWN≠Completed."
            ),
        }
    )


def mark_notification_read(
    login_id: str,
    notification_id: str,
    *,
    channel_ids: Sequence[int],
) -> Dict[str, Any]:
    """Mark read only — never changes production state."""
    with _LOCK:
        proj = project_notifications(login_id, channel_ids=channel_ids, limit=200)
        found = None
        for n in proj.get("notifications") or []:
            if str(n.get("notification_id")) == str(notification_id):
                found = n
                break
        if not found:
            return {
                "ok": False,
                "error": "notification_not_found_or_denied",
                "error_code": "OWNERSHIP_FAILURE",
            }
        if str(found.get("login_id")) != str(login_id):
            return {"ok": False, "error": "access_denied", "error_code": "OWNERSHIP_FAILURE"}

        state = load_read_state(login_id)
        state.setdefault("read", {})[str(notification_id)] = {"at": _now(), "read": True}
        save_read_state(login_id, state)
        return {
            "ok": True,
            "notification_id": notification_id,
            "read_state": "READ",
            "mutates_production": False,
            "note": "Read state only — production unchanged",
        }


def help_context(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    job_id: Optional[int] = None,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic help context from authoritative monitor/publish planes."""
    from app.customer_production_certification import project_journey, project_result_planes
    from app.customer_production_monitor import project_production_monitor

    loc = normalize_locale(locale)
    journey = project_journey(
        login_id,
        channel_ids=channel_ids,
        job_id=job_id,
        identity={
            "login_id": login_id,
            "authenticated": True,
            "auth_state": "AUTHENTICATED",
            "production_access": True,
            "entitlement_state": "ACTIVE",
            "account_state": "ACTIVE",
        },
    )
    mon = None
    planes = {}
    if job_id:
        mon = project_production_monitor(login_id, int(job_id), channel_ids=channel_ids)
        if not mon.get("ok"):
            code = mon.get("error_code") or "OWNERSHIP_FAILURE"
            if str(code).lower() in ("ownership_violation", "ownership_failure"):
                code = "OWNERSHIP_FAILURE"
            return scrub_notification(
                {
                    "ok": False,
                    "error": mon.get("error") or "access_denied",
                    "error_code": code,
                }
            )
        row = get_job(int(job_id))
        planes = project_result_planes(row)

    state = (mon or {}).get("monitor_state") or "UNKNOWN"
    recommended = (mon or {}).get("state_contract", {}).get("action") or "None"
    deep = None
    if planes.get("APPROVED") and not planes.get("PUBLISHED"):
        deep = DEEP_LINKS.get("PUBLISH_STARTED") or DEEP_LINKS["UPLOAD_ACCEPTED"]
    elif state in ("APPROVAL_PENDING", "PREVIEW_READY"):
        deep = DEEP_LINKS["APPROVAL_REQUIRED"]
    elif state in ("INTERRUPTED", "ACTION_REQUIRED", "FAILED"):
        deep = DEEP_LINKS["RECOVERY_REQUIRED"]
    elif planes.get("REMOTE_PROCESSING") or planes.get("UPLOAD_ACCEPTED"):
        deep = DEEP_LINKS["REMOTE_PROCESSING"]

    return scrub_notification(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "current_state": state,
            "planes": planes,
            "authoritative_source": "customer_production_monitor + customer_publish fields",
            "recommended_action": recommended,
            "deep_link": deep,
            "locale": loc,
            "journey_stages": [s.get("stage") for s in (journey.get("stages") or [])],
            "can_mutate_production": False,
            "note": "Help explains state; it does not execute generation/publish/schedule.",
            "paid_api_calls": 0,
        }
    )


def help_query(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    query: str,
    job_id: Optional[int] = None,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic state-based help — no generative hallucination."""
    loc = normalize_locale(locale)
    q = str(query or "").strip().lower()
    ctx = help_context(login_id, channel_ids=channel_ids, job_id=job_id, locale=loc)
    if not ctx.get("ok"):
        return ctx

    planes = ctx.get("planes") or {}
    state = str(ctx.get("current_state") or "UNKNOWN")

    answer = None
    classification = "DETERMINISTIC"
    confidence = "HIGH"

    if any(x in q for x in ("publish", "upload", "প্রকাশ")):
        if planes.get("PUBLISHED"):
            answer = message_for("PUBLISHED", loc)
        elif planes.get("REMOTE_PROCESSING"):
            answer = message_for("REMOTE_PROCESSING", loc)
        elif planes.get("UPLOAD_ACCEPTED"):
            answer = message_for("UPLOAD_ACCEPTED", loc)
        elif planes.get("APPROVED") and planes.get("READY_TO_UPLOAD"):
            answer = "Approved and ready to upload — use Publishing panel. Approval alone does not publish."
        elif not planes.get("APPROVED"):
            answer = message_for("APPROVAL_REQUIRED", loc)
        else:
            answer = message_for("help_unknown", loc)
            classification = "UNKNOWN"
            confidence = "LOW"
    elif any(x in q for x in ("approv", "preview", "অনুমোদন")):
        if planes.get("APPROVED"):
            answer = "Revision is APPROVED — not published."
        else:
            row = get_job(int(job_id)) if job_id else None
            if row and str(row.get("customer_approval") or "").upper() == "REJECTED":
                answer = message_for("APPROVAL_REJECTED", loc)
            else:
                answer = message_for("APPROVAL_REQUIRED", loc)
    elif any(x in q for x in ("schedule", "শিডিউল")):
        try:
            from app.customer_publish_schedule import project_schedule_panel

            panel = project_schedule_panel(login_id, channel_ids=channel_ids, job_id=job_id)
            active = panel.get("active") or {}
            st = str(active.get("status") or "NOT_SCHEDULED")
            if st == "MISSED":
                answer = message_for("SCHEDULE_MISSED", loc)
            elif st in ("SCHEDULED", "DUE"):
                answer = f"{message_for('SCHEDULE_CREATED' if st == 'SCHEDULED' else 'SCHEDULE_DUE', loc)} SCHEDULED ≠ PUBLISHED."
            else:
                answer = "Use Publishing Schedule panel. Scheduling does not upload by itself. SCHEDULED ≠ PUBLISHED."
        except Exception:
            answer = "Use Publishing Schedule panel. Scheduling does not upload by itself. SCHEDULED ≠ PUBLISHED."
    elif any(x in q for x in ("fail", "error", "recover", "ব্যর্থ")):
        if state in ("FAILED", "TERMINAL_FAILED", "ACTION_REQUIRED", "INTERRUPTED"):
            answer = message_for("RECOVERY_REQUIRED" if state != "FAILED" else "PRODUCTION_FAILED", loc)
        else:
            answer = f"Current monitor state is {state}. No failure indicated."
    elif any(x in q for x in ("reconcil",)):
        answer = message_for("RECONCILIATION_REQUIRED", loc)
    else:
        answer = message_for("help_fallback", loc)
        classification = "FALLBACK"
        confidence = "MEDIUM"

    # Never claim published for non-published planes
    if planes.get("REMOTE_PROCESSING") or planes.get("UPLOAD_ACCEPTED"):
        if "published" in (answer or "").lower() and not planes.get("PUBLISHED"):
            if "not published" not in (answer or "").lower():
                answer = message_for("REMOTE_PROCESSING", loc)

    return scrub_notification(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "kind": "CustomerHelpResponse",
            "answer": answer,
            "current_state": state,
            "planes": planes,
            "authoritative_source": ctx.get("authoritative_source"),
            "recommended_action": ctx.get("recommended_action"),
            "deep_link": ctx.get("deep_link"),
            "support_classification": classification,
            "confidence": confidence,
            "locale": loc,
            "can_mutate_production": False,
            "paid_api_calls": 0,
            "external_provider_calls": 0,
        }
    )


def category_availability() -> Dict[str, str]:
    """Document which categories are projected from real authorities."""
    return {c: "AVAILABLE" for c in NOTIFICATION_CATEGORIES}


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat, label in (
        (r"(?m)^\s*class\s+SchedulerService\b", "SchedulerService"),
        (r"(?m)^\s*def\s+generate_video\s*\(", "generate_video"),
        (r"(?m)^\s*def\s+evaluate_publishability\s*\(", "evaluate_publishability"),
        (r"(?m)^\s*class\s+IdempotencyStore\b", "IdempotencyStore"),
        (r"(?m)^\s*class\s+EventEngine\b", "EventEngine"),
        (r"(?m)^\s*class\s+NotificationEngine\b", "NotificationEngine"),
        (r"(?m)^\s*def\s+append_lifecycle_event\s*\(", "append_lifecycle_event"),
    ):
        if _re.search(pat, source):
            bad.append(label)
    return bad
