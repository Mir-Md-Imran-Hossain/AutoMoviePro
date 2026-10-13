"""C03 — Customer onboarding + dashboard projection (orchestration only).

Reads existing authorities; does NOT own auth, entitlement, readiness, jobs, or configuration.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app import db as store

logger = logging.getLogger(__name__)

# Onboarding states
NOT_STARTED = "NOT_STARTED"
IN_PROGRESS = "IN_PROGRESS"
READY = "READY"
COMPLETED = "COMPLETED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

# Checklist item states
ITEM_COMPLETE = "COMPLETE"
ITEM_INCOMPLETE = "INCOMPLETE"
ITEM_UNKNOWN = "UNKNOWN"
ITEM_BLOCKED = "BLOCKED"
ITEM_NOT_CONFIGURED = "NOT_CONFIGURED"


def _now() -> str:
    return datetime.now().isoformat()


def ensure_onboarding_table() -> None:
    with store.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_onboarding (
              login_id TEXT PRIMARY KEY,
              started_at TEXT,
              completed_at TEXT,
              updated_at TEXT,
              meta_json TEXT
            )
            """
        )


def get_onboarding_record(login_id: str) -> Optional[Dict[str, Any]]:
    ensure_onboarding_table()
    lid = (login_id or "").strip()
    if not lid:
        return None
    with store.db() as conn:
        row = conn.execute(
            "SELECT login_id, started_at, completed_at, updated_at, meta_json FROM customer_onboarding WHERE login_id=?",
            (lid,),
        ).fetchone()
    if not row:
        return None
    meta: Dict[str, Any] = {}
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}
    return {
        "login_id": row["login_id"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "updated_at": row["updated_at"],
        "meta": meta,
    }


def upsert_onboarding_record(
    login_id: str,
    *,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    clear_completed: bool = False,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_onboarding_table()
    lid = (login_id or "").strip()
    if not lid:
        raise ValueError("login_id_required")
    existing = get_onboarding_record(lid) or {}
    st = started_at if started_at is not None else existing.get("started_at")
    if clear_completed:
        ct = None
    elif completed_at is not None:
        ct = completed_at
    else:
        ct = existing.get("completed_at")
    merged_meta = dict(existing.get("meta") or {})
    if meta:
        merged_meta.update(meta)
    updated = _now()
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO customer_onboarding (login_id, started_at, completed_at, updated_at, meta_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(login_id) DO UPDATE SET
              started_at=excluded.started_at,
              completed_at=excluded.completed_at,
              updated_at=excluded.updated_at,
              meta_json=excluded.meta_json
            """,
            (lid, st, ct, updated, json.dumps(merged_meta)),
        )
    return get_onboarding_record(lid) or {}


def assert_customer_scope(requested_login_id: Optional[str], session_login_id: str) -> Optional[str]:
    """Reject cross-customer identifier attempts. Returns error code or None."""
    req = (requested_login_id or "").strip()
    if not req:
        return None
    if req != (session_login_id or "").strip():
        return "customer_scope_denied"
    return None


def _item(
    *,
    id: str,
    label: str,
    source: str,
    state: str,
    blocking: bool,
    message: str,
    resume_tab: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "authoritative_source": source,
        "state": state,
        "blocking": bool(blocking),
        "message": message,
        "resume_tab": resume_tab,
    }


def build_checklist(
    *,
    identity: Dict[str, Any],
    foundation: Optional[Dict[str, Any]],
    access: Optional[Dict[str, Any]],
    channels: List[Dict[str, Any]],
    api_readiness: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Truthful checklist from existing authorities only (no C04 config writes)."""
    f = foundation or {}
    items: List[Dict[str, Any]] = []

    acct = str(identity.get("account_state") or "UNKNOWN")
    if acct == "ACTIVE":
        items.append(
            _item(
                id="account.active",
                label="Account",
                source="customer_auth.evaluate_session.account_state",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Account is active.",
            )
        )
    elif acct == "DISABLED":
        items.append(
            _item(
                id="account.active",
                label="Account",
                source="customer_auth.evaluate_session.account_state",
                state=ITEM_BLOCKED,
                blocking=True,
                message="This account is currently disabled.",
            )
        )
    elif acct == "PENDING":
        items.append(
            _item(
                id="account.active",
                label="Account",
                source="customer_auth.evaluate_session.account_state",
                state=ITEM_INCOMPLETE,
                blocking=True,
                message="Account is pending approval.",
            )
        )
    else:
        items.append(
            _item(
                id="account.active",
                label="Account",
                source="customer_auth.evaluate_session.account_state",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Account state is unknown.",
            )
        )

    ent = str(identity.get("entitlement_state") or "UNKNOWN")
    prod_access = bool(identity.get("production_access"))
    if prod_access and ent == "ACTIVE":
        items.append(
            _item(
                id="access.entitlement",
                label="Production access",
                source="customer_auth.evaluate_session / can_customer_produce",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Entitlement allows production access.",
            )
        )
    elif ent in ("EXPIRED", "SUSPENDED", "NO_ENTITLEMENT") or identity.get("auth_state") == "ENTITLEMENT_REQUIRED":
        items.append(
            _item(
                id="access.entitlement",
                label="Production access",
                source="customer_auth.evaluate_session",
                state=ITEM_BLOCKED if ent in ("EXPIRED", "SUSPENDED") else ITEM_INCOMPLETE,
                blocking=True,
                message="Production access is not currently available for this account.",
            )
        )
    elif ent == "UNKNOWN" or identity.get("auth_state") == "AUTH_ERROR":
        items.append(
            _item(
                id="access.entitlement",
                label="Production access",
                source="customer_auth.evaluate_session",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Entitlement state could not be verified.",
            )
        )
    else:
        items.append(
            _item(
                id="access.entitlement",
                label="Production access",
                source="customer_auth.evaluate_session",
                state=ITEM_INCOMPLETE,
                blocking=True,
                message="Production access is not currently available for this account.",
            )
        )

    try:
        from app.customer_tiers import validate_license_for_customer

        tier_info = validate_license_for_customer(identity)
        t_label = tier_info["display_name_en"]
        items.append(
            _item(
                id="tier.validated",
                label="Product License Tier",
                source="customer_tiers.validate_license_for_customer",
                state=ITEM_COMPLETE if tier_info["valid"] else ITEM_INCOMPLETE,
                blocking=False,
                message=f"Licensed Tier: {t_label} (৳{tier_info['price_bdt']})",
                resume_tab="account",
            )
        )
    except Exception:
        pass

    app_st = str(f.get("application") or "UNKNOWN")
    if app_st == "READY":
        items.append(
            _item(
                id="application.ready",
                label="Application",
                source="customer_foundation.application",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Application plane is READY.",
            )
        )
    elif app_st in ("FAILED", "DEGRADED"):
        items.append(
            _item(
                id="application.ready",
                label="Application",
                source="customer_foundation.application",
                state=ITEM_BLOCKED if app_st == "FAILED" else ITEM_INCOMPLETE,
                blocking=True,
                message=f"Application plane is {app_st}.",
            )
        )
    else:
        items.append(
            _item(
                id="application.ready",
                label="Application",
                source="customer_foundation.application",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Application readiness is unknown.",
            )
        )

    media_st = str(f.get("media") or "UNKNOWN")
    if media_st == "AVAILABLE":
        items.append(
            _item(
                id="media.available",
                label="Media tools",
                source="customer_foundation.media",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Media tools are available.",
            )
        )
    elif media_st == "UNAVAILABLE":
        items.append(
            _item(
                id="media.available",
                label="Media tools",
                source="customer_foundation.media",
                state=ITEM_BLOCKED,
                blocking=True,
                message="Media tools are unavailable.",
            )
        )
    else:
        items.append(
            _item(
                id="media.available",
                label="Media tools",
                source="customer_foundation.media",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Media tool status is unknown.",
            )
        )

    prod_st = str(f.get("production") or "UNKNOWN")
    if prod_st == "READY":
        items.append(
            _item(
                id="production.ready",
                label="Production prerequisites",
                source="customer_foundation.production",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Production prerequisites are READY.",
            )
        )
    elif prod_st == "BLOCKED":
        items.append(
            _item(
                id="production.ready",
                label="Production prerequisites",
                source="customer_foundation.production",
                state=ITEM_BLOCKED,
                blocking=True,
                message="Production prerequisites are BLOCKED.",
            )
        )
    else:
        items.append(
            _item(
                id="production.ready",
                label="Production prerequisites",
                source="customer_foundation.production",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Production prerequisites are UNKNOWN.",
            )
        )

    if channels:
        ch = channels[0]
        name = ch.get("youtube_name") or ch.get("facebook_name") or ch.get("niche") or f"#{ch.get('id')}"
        items.append(
            _item(
                id="channel.configured",
                label="Channel configuration",
                source="db.list_channels / /api/channels",
                state=ITEM_COMPLETE,
                blocking=True,
                message=f"Channel configured: {name}",
                resume_tab="channel",
            )
        )
        if ch.get("youtube_oauth_connected"):
            ch_title = ch.get("youtube_channel_title") or ch.get("youtube_name") or "Connected Channel"
            items.append(
                _item(
                    id="youtube_oauth.connected",
                    label="YouTube 1-Click OAuth",
                    source="publishers.youtube_oauth_service",
                    state=ITEM_COMPLETE,
                    blocking=False,
                    message=f"1-Click YouTube Connected: {ch_title}",
                    resume_tab="channel",
                )
            )
    else:
        items.append(
            _item(
                id="channel.configured",
                label="Channel configuration",
                source="db.list_channels / /api/channels",
                state=ITEM_NOT_CONFIGURED,
                blocking=True,
                message="Channel setup required. Open Channel setup to configure.",
                resume_tab="channel",
            )
        )

    try:
        from pipeline.lang_entitlement import channel_languages

        langs = channel_languages(channels[0]) if channels else []
    except Exception:
        langs = None
    if langs is None:
        items.append(
            _item(
                id="language.configured",
                label="Language configuration",
                source="pipeline.lang_entitlement.channel_languages",
                state=ITEM_UNKNOWN,
                blocking=False,
                message="Language configuration could not be verified.",
                resume_tab="channel",
            )
        )
    elif langs:
        items.append(
            _item(
                id="language.configured",
                label="Language configuration",
                source="pipeline.lang_entitlement.channel_languages",
                state=ITEM_COMPLETE,
                blocking=False,
                message=f"Languages configured: {', '.join(langs)}",
                resume_tab="channel",
            )
        )
    else:
        items.append(
            _item(
                id="language.configured",
                label="Language configuration",
                source="pipeline.lang_entitlement.channel_languages",
                state=ITEM_NOT_CONFIGURED,
                blocking=False,
                message="Languages not configured.",
                resume_tab="channel",
            )
        )

    if api_readiness is None and not channels:
        items.append(
            _item(
                id="provider.configured",
                label="Provider / API configuration",
                source="pipeline.channel_api_slots.evaluate_readiness",
                state=ITEM_NOT_CONFIGURED,
                blocking=True,
                message="Provider APIs not configured.",
                resume_tab="channel",
            )
        )
    elif api_readiness is None:
        items.append(
            _item(
                id="provider.configured",
                label="Provider / API configuration",
                source="pipeline.channel_api_slots.evaluate_readiness",
                state=ITEM_UNKNOWN,
                blocking=True,
                message="Provider readiness is unknown.",
                resume_tab="channel",
            )
        )
    elif api_readiness.get("active"):
        items.append(
            _item(
                id="provider.configured",
                label="Provider / API configuration",
                source="pipeline.channel_api_slots.evaluate_readiness",
                state=ITEM_COMPLETE,
                blocking=True,
                message="Required provider APIs are active.",
                resume_tab="channel",
            )
        )
    else:
        items.append(
            _item(
                id="provider.configured",
                label="Provider / API configuration",
                source="pipeline.channel_api_slots.evaluate_readiness",
                state=ITEM_NOT_CONFIGURED,
                blocking=True,
                message=str(api_readiness.get("message") or "Provider APIs not configured."),
                resume_tab="channel",
            )
        )

    return items


def derive_onboarding_state(
    *,
    identity: Dict[str, Any],
    checklist: List[Dict[str, Any]],
    record: Optional[Dict[str, Any]],
) -> str:
    auth = str(identity.get("auth_state") or "")
    if auth in ("UNAUTHENTICATED", "SESSION_EXPIRED"):
        return UNKNOWN
    if auth in ("ACCOUNT_DISABLED",):
        return BLOCKED
    if auth in ("AUTH_ERROR",):
        return UNKNOWN

    mandatory = [i for i in checklist if i.get("blocking")]
    if any(i.get("state") == ITEM_UNKNOWN for i in mandatory):
        return UNKNOWN
    if any(i.get("state") == ITEM_BLOCKED for i in mandatory):
        return BLOCKED

    incomplete = {ITEM_INCOMPLETE, ITEM_NOT_CONFIGURED}
    all_complete = all(i.get("state") == ITEM_COMPLETE for i in mandatory)
    started = bool(record and record.get("started_at"))
    completed = bool(record and record.get("completed_at"))

    if all_complete:
        if completed:
            return COMPLETED
        return READY

    if auth == "ENTITLEMENT_REQUIRED":
        return BLOCKED

    if any(i.get("state") in incomplete for i in mandatory):
        if started or any(i.get("state") == ITEM_COMPLETE for i in mandatory):
            return IN_PROGRESS
        return NOT_STARTED
    return NOT_STARTED


def startup_route_for(state: str, *, logged_in: bool) -> str:
    if not logged_in:
        return "login"
    if state == NOT_STARTED:
        return "onboarding"
    if state == IN_PROGRESS:
        return "onboarding_resume"
    if state == COMPLETED:
        return "workspace"
    return "dashboard"


def job_summary_from_parts(
    active_jobs: List[Dict[str, Any]], recent_jobs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    ready_review = sum(1 for j in (recent_jobs or []) if j.get("state") == "READY_FOR_REVIEW")
    failed = sum(1 for j in (recent_jobs or []) if j.get("state") == "FAILED")
    latest = None
    if active_jobs:
        latest = active_jobs[0]
    elif recent_jobs:
        latest = recent_jobs[0]
    return {
        "active_count": len(active_jobs or []),
        "recent_count": len(recent_jobs or []),
        "ready_for_review_count": ready_review,
        "failed_count": failed,
        "latest_state": (latest or {}).get("state"),
        "latest_stage": (latest or {}).get("stage") or (latest or {}).get("detail"),
        "latest_job_id": (latest or {}).get("job_id"),
        "active_jobs": active_jobs[:10],
        "recent_jobs": (recent_jobs or [])[:10],
        "note": "counts derived from customer job projection only — not fabricated",
    }


def blocking_issues_from(
    checklist: List[Dict[str, Any]],
    access: Optional[Dict[str, Any]],
    foundation: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if access:
        allowed = access.get("allowed")
        prod = access.get("production_allowed")
        if allowed is False or prod is False:
            issues.append(
                {
                    "id": "c02_access",
                    "message": str(access.get("message") or "Production access is not available."),
                }
            )
    for i in checklist:
        if i.get("blocking") and i.get("state") in (
            ITEM_BLOCKED,
            ITEM_UNKNOWN,
            ITEM_INCOMPLETE,
            ITEM_NOT_CONFIGURED,
        ):
            issues.append({"id": str(i["id"]), "message": str(i.get("message") or i["id"])})
    seen = set()
    out: List[Dict[str, str]] = []
    for x in issues:
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        out.append(x)
    return out


def build_dashboard(
    *,
    identity: Dict[str, Any],
    access: Dict[str, Any],
    foundation: Dict[str, Any],
    channels: List[Dict[str, Any]],
    api_readiness: Optional[Dict[str, Any]],
    active_jobs: List[Dict[str, Any]],
    recent_jobs: List[Dict[str, Any]],
    release: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Thin read-only dashboard projection."""
    login_id = str(identity.get("login_id") or "")
    record = get_onboarding_record(login_id) if login_id else None
    checklist = build_checklist(
        identity=identity,
        foundation=foundation,
        access=access,
        channels=channels,
        api_readiness=api_readiness,
    )
    state = derive_onboarding_state(identity=identity, checklist=checklist, record=record)
    logged_in = bool(identity.get("logged_in"))
    route = startup_route_for(state, logged_in=logged_in)

    access_out = {
        "production_allowed": bool(
            access.get("allowed") if "allowed" in access else access.get("production_allowed")
        ),
        "block_reason": access.get("block_reason"),
        "message": access.get("message"),
        "message_key": access.get("message_key"),
    }

    onboarding = {
        "state": state,
        "started_at": (record or {}).get("started_at"),
        "completed_at": (record or {}).get("completed_at"),
        "login_id": login_id or None,
        "can_start": state == NOT_STARTED and logged_in,
        "can_resume": state in (IN_PROGRESS, BLOCKED, UNKNOWN, READY) and logged_in,
        "can_complete": state == READY and logged_in,
        "resume_hint": next(
            (
                i.get("resume_tab")
                for i in checklist
                if i.get("blocking") and i.get("state") != ITEM_COMPLETE and i.get("resume_tab")
            ),
            "channel",
        ),
        "message": {
            NOT_STARTED: "Setup has not started yet.",
            IN_PROGRESS: "Setup is in progress. Resume where you left off.",
            READY: "Required setup checks are complete. You can finish onboarding.",
            COMPLETED: "Onboarding is complete.",
            BLOCKED: "Setup is blocked. Resolve the issues below.",
            UNKNOWN: "Some setup requirements could not be verified.",
        }.get(state, "Setup status unavailable."),
    }

    readiness = {
        "application": foundation.get("application"),
        "media": foundation.get("media"),
        "production": foundation.get("production"),
        "job": (foundation.get("active_job") or {}).get("state")
        or ((active_jobs[0].get("state") if active_jobs else None)),
        "generate_allowed": foundation.get("generate_allowed"),
        "generate_block_reasons": list(foundation.get("generate_block_reasons") or []),
        "note": foundation.get("note"),
    }

    return {
        "ok": True,
        "identity": identity,
        "access": access_out,
        "onboarding": onboarding,
        "checklist": checklist,
        "readiness": readiness,
        "jobs": job_summary_from_parts(active_jobs, recent_jobs),
        "blocking_issues": blocking_issues_from(checklist, access_out, foundation),
        "startup_route": route,
        "workspace_href": "#workspace",
        "release": release,
        "note": "C03 dashboard aggregates authorities only — does not own configuration or jobs",
    }


def start_onboarding(login_id: str) -> Dict[str, Any]:
    rec = upsert_onboarding_record(login_id, started_at=_now(), clear_completed=True)
    return {"ok": True, "record": rec}


def complete_onboarding(login_id: str, *, state: str) -> Dict[str, Any]:
    if state != READY:
        return {
            "ok": False,
            "error": "onboarding_not_ready",
            "message": "Onboarding can only be completed when all mandatory checks are READY.",
        }
    rec = upsert_onboarding_record(login_id, completed_at=_now())
    if not rec.get("started_at"):
        rec = upsert_onboarding_record(login_id, started_at=_now(), completed_at=rec.get("completed_at"))
    return {"ok": True, "record": rec}
