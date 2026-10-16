from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api_client import LicenseClient
from app.config import ASSETS_DIR, OUTPUT_DIR, UI_DIR, settings
from app import db as store
from app.scheduler_service import SchedulerService

app = FastAPI(title="AutoMovie Pro")

# Cross-Origin Resource Sharing (CORS) for Mobile Solver / PWA Wi-Fi interconnect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
scheduler = SchedulerService()

if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if OUTPUT_DIR.exists():
    app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    try:
        from app.customer_auth import ensure_session_columns

        ensure_session_columns()
    except Exception:
        pass
    try:
        from app.customer_onboarding import ensure_onboarding_table

        ensure_onboarding_table()
    except Exception:
        pass
    try:
        from app.customer_config import ensure_channel_owner_column

        ensure_channel_owner_column()
    except Exception:
        pass
    try:
        from app.customer_job import ensure_job_columns
        from app.customer_job_automation import ensure_automation_columns, recover_after_restart

        ensure_job_columns()
        ensure_automation_columns()
        try:
            from app.customer_publish import ensure_publish_columns

            ensure_publish_columns()
        except Exception:
            pass
        # C06-G: requeue stale leases; legacy in-flight → INTERRUPTED (never silent COMPLETED)
        recover_after_restart()
        try:
            from app.customer_publish_schedule import recover_schedules_after_restart

            recover_schedules_after_restart()
        except Exception:
            pass
    except Exception:
        try:
            from app.customer_job import ensure_job_columns, reconcile_interrupted_jobs

            ensure_job_columns()
            reconcile_interrupted_jobs(live_active=False)
        except Exception:
            pass
    try:
        from app.release_identity import get_release_identity

        ident = get_release_identity(include_media=False)
        import logging

        logging.getLogger(__name__).info(
            "AutoMovie Pro starting release=%s build=%s",
            ident.get("release_version"),
            ident.get("build_id"),
        )
    except Exception:
        pass
    try:
        from pipeline.api_keys import seed_channel_from_env

        seed_channel_from_env()
    except Exception:
        pass
    # Customer tools: Playwright / Camoufox / Edge-TTS / FFmpeg (first-run sync, else async)
    try:
        from app.bootstrap_runtime import maybe_run_on_startup

        maybe_run_on_startup()
    except Exception:
        pass
    scheduler.start()
    try:
        from app.storage.google_drive_sync import get_vault_sync
        get_vault_sync().start_scheduler()
    except Exception:
        pass


@app.on_event("shutdown")
def _shutdown() -> None:
    scheduler.stop()
    try:
        from app.storage.google_drive_sync import get_vault_sync
        get_vault_sync().stop_scheduler()
    except Exception:
        pass


def _require_session() -> Optional[Dict[str, Any]]:
    """C02: authenticated shell session (expired sessions cleared)."""
    from app.customer_auth import require_authenticated_session

    return require_authenticated_session()


def _require_production_access(channel: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """C02: server-side production authorization composed with C01 readiness."""
    from app.customer_auth import can_customer_produce

    return can_customer_produce(channel=channel)


def _require_video_studio_access() -> tuple[bool, Optional[JSONResponse]]:
    """Enforce strict video studio tier access (video_studio, dev, enterprise).
    ৳1,999 (profile_page) and ৳2,999 (fb_business) are strictly blocked with 403.
    """
    session = _require_session()
    if not session:
        return False, JSONResponse(
            status_code=401,
            content={"ok": False, "error": "login_required", "message": "অনুগ্রহ করে লগইন করুন।"},
        )
    customer = session.get("customer") or {}
    plan = customer.get("tier") or customer.get("plan") or session.get("plan")
    from app.customer_tiers import can_produce_video_studio, TIER_UPGRADE_MESSAGE_VIDEO_STUDIO

    if not can_produce_video_studio(plan):
        return False, JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "tier_upgrade_required",
                "message": TIER_UPGRADE_MESSAGE_VIDEO_STUDIO,
                "required_tier": "video_studio",
                "current_tier": str(plan),
                "upgrade_url": "https://automoviepro.com/#pricing",
            },
        )
    return True, None


def _session_login_id() -> str:
    from app.customer_config import resolve_session_login_id

    return resolve_session_login_id()


def _owned_channels_or_empty() -> list:
    from app.customer_config import list_owned_channels

    lid = _session_login_id()
    return list_owned_channels(lid) if lid else []


@app.get("/")
def index() -> HTMLResponse:
    html = (UI_DIR.parent / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Process liveness — does NOT mean media tools or publishability."""
    from app.release_identity import RELEASE_VERSION

    return {
        "ok": True,
        "health": "ALIVE",
        "release_version": RELEASE_VERSION,
        "note": "liveness only; see /api/media-capability and /api/operational-readiness",
    }


@app.get("/api/media-capability")
def media_capability() -> Dict[str, Any]:
    """Independent FFmpeg/ffprobe capability (extends compose probe)."""
    from pipeline.compose import media_tool_versions, probe_media_tool_capability

    cap = probe_media_tool_capability()
    vers = media_tool_versions()
    return {
        "ok": True,
        "ffmpeg_available": bool(cap.get("FFMPEG_AVAILABLE")),
        "ffprobe_available": bool(cap.get("FFPROBE_AVAILABLE")),
        "ffmpeg_source": cap.get("ffmpeg_source"),
        "ffprobe_source": cap.get("ffprobe_source"),
        "ffmpeg_version": vers.get("ffmpeg_version"),
        "ffprobe_version": vers.get("ffprobe_version"),
        "method": cap.get("method"),
        "note": "media capability ≠ artifact publishability",
    }


@app.get("/api/operational-readiness")
def operational_readiness() -> Dict[str, Any]:
    """Operational prerequisites for media work — NOT publishability."""
    from app.config import validate_production_operational
    from app.release_identity import get_release_identity

    report = validate_production_operational()
    report["release"] = get_release_identity(include_media=False)
    return report


@app.get("/api/diagnostics/run")
@app.post("/api/diagnostics/run")
def api_diagnostics_run() -> Dict[str, Any]:
    """1-Click Automated Customer Self-Diagnostics (Sector 6).
    Checks: Internet, AI Keys, Hardware/FFmpeg, Disk Space, Browser Sessions.
    """
    from app.diagnostics import run_full_diagnostics

    return run_full_diagnostics()


@app.get("/api/subscription/google-paid-status")
def google_paid_status() -> Dict[str, Any]:
    from pipeline.dedicated_api_registry import (
        google_paid_unlocked_slot_count,
        is_google_paid_unlocked,
        list_paid_google_keys,
    )
    from app.db import list_google_pro_orders

    keys = list_paid_google_keys()
    unlocked_count = google_paid_unlocked_slot_count()
    orders = list_google_pro_orders()

    plans = [
        {
            "id": "1_month",
            "name": "মাসিক প্ল্যান (৩০ দিন)",
            "duration_months": 1,
            "price": 120,
            "currency": "৳",
            "features": [
                "Nano Banana & Veo-3 API",
                "রোবোটিকলেস প্রিমিয়াম TTS",
                "১৫০ জিবি গুগল ক্লাউড ড্রাইভ",
                "১ মাস ভ্যালিডিটি",
            ],
            "popular": False,
        },
        {
            "id": "12_month",
            "name": "বাৎসরিক প্ল্যান (১২ মাস)",
            "duration_months": 12,
            "price": 999,
            "currency": "৳",
            "features": [
                "Nano Banana & Veo-3 API",
                "রোবোটিকলেস প্রিমিয়াম TTS",
                "১৫০ জিবি গুগল ক্লাউড ড্রাইভ",
                "১২ মাস নিরবচ্ছিন্ন ভ্যালিডিটি",
                "স্পেশাল ডিসকাউন্ট সেভিংস",
            ],
            "popular": True,
        },
        {
            "id": "18_month",
            "name": "স্পেশাল প্ল্যান (১৮ মাস)",
            "duration_months": 18,
            "price": 1299,
            "currency": "৳",
            "features": [
                "Nano Banana & Veo-3 API",
                "রোবোটিকলেস প্রিমিয়াম TTS",
                "১৫০ জিবি গুগল ক্লাউড ড্রাইভ",
                "১৮ মাস সম্পূর্ণ লাইসেন্স মেয়াদ",
                "ভিআইপি প্রায়োরিটি সাপোর্ট",
            ],
            "popular": False,
        },
    ]

    return {
        "ok": True,
        "unlocked": unlocked_count > 0,
        "unlocked_slots": unlocked_count,
        "total_slots": 3,
        "key_count": len(keys),
        "has_active_key": len(keys) > 0,
        "plans": plans,
        "orders": orders,
    }


@app.post("/api/subscription/order-google-paid")
async def order_google_paid(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    from app.db import create_google_pro_order

    order = create_google_pro_order(body)
    return {
        "ok": True,
        "order": order,
        "message": (
            "আপনার Google AI Pro অ্যাকাউন্ট অর্ডারটি সফলভাবে জমা হয়েছে। "
            "অ্যাডমিন অ্যাকাউন্ট কানেক্ট করে অর্ডার এক্সেপ্ট করলেই সফটওয়্যারে ১টি নতুন এপিআই স্লট আনলক হয়ে যাবে।"
        ),
    }


@app.post("/api/subscription/approve-google-paid")
async def approve_google_paid(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    order_id = str(body.get("order_id") or "").strip()
    from app.db import approve_google_pro_order
    from pipeline.dedicated_api_registry import (
        google_paid_unlocked_slot_count,
        unlock_google_paid,
    )

    if order_id:
        approve_google_pro_order(order_id)
    unlock_google_paid("ADMIN-APPROVE", slots_to_add=1)
    new_slots = google_paid_unlocked_slot_count()
    return {
        "ok": True,
        "unlocked_slots": new_slots,
        "message": f"অর্ডার সফলভাবে এক্সেপ্ট করা হয়েছে! নতুন এপিআই স্লট আনলকড: {new_slots}/৩",
    }


@app.post("/api/subscription/activate-google-paid")
async def activate_google_paid(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str(body.get("code") or "").strip()
    from pipeline.dedicated_api_registry import (
        google_paid_unlocked_slot_count,
        unlock_google_paid,
    )

    ok, msg = unlock_google_paid(code, slots_to_add=1)
    return {
        "ok": ok,
        "message": msg,
        "unlocked_slots": google_paid_unlocked_slot_count(),
    }



@app.get("/api/status")
def status() -> Dict[str, Any]:
    from app.customer_auth import evaluate_session, ensure_session_columns

    ensure_session_columns()
    identity = evaluate_session()
    session = store.get_session() if identity.get("logged_in") else None
    # If session expired, evaluate_session already reflects it; clear happens in require path
    readiness = {
        "active": False,
        "inactive": True,
        "missing": [],
        "message_key": "login_required",
        "message": "Please log in",
        "details": {},
    }
    if session:
        from pipeline.channel_api_slots import evaluate_readiness

        channels = _owned_channels_or_empty()
        if channels:
            best = None
            for ch in channels:
                r = evaluate_readiness(channel=ch)
                if best is None or (r["active"] and not best["active"]):
                    best = r
                if r["active"]:
                    best = r
                    break
            readiness = best or evaluate_readiness(channel=channels[0])
        else:
            readiness = evaluate_readiness(channel={})
            readiness["message_key"] = "app_inactive_no_channel"
            readiness["message"] = "Application inactive — set up a channel and add required APIs first"
            readiness["active"] = False
            readiness["inactive"] = True
    from app.config import validate_production_operational
    from app.customer_foundation import build_foundation_snapshot
    from app.release_identity import get_release_identity
    from pipeline.compose import probe_media_tool_capability

    release = get_release_identity(include_media=False)
    media_cap = probe_media_tool_capability()
    operational = validate_production_operational()
    foundation = build_foundation_snapshot(
        app_started=True,
        media_cap=media_cap,
        operational=operational,
        api_readiness=readiness if session else None,
    )
    pub_customer = None
    if session:
        c = session.get("customer") or {}
        pub_customer = {
            "id": c.get("id"),
            "name": c.get("name"),
            "login_id": c.get("login_id") or session.get("login_id"),
            "status": c.get("status"),
            "plan": c.get("plan"),
        }
    return {
        "ok": True,
        "logged_in": bool(identity.get("logged_in")),
        "identity": identity,
        "customer": pub_customer,
        "api_base_url": (session or {}).get("api_base_url") or settings.api_base_url,
        "dry_run_publish": settings.dry_run_publish,
        "channels": len(_owned_channels_or_empty()) if session else 0,
        "jobs": len(store.list_jobs(20)) if session else 0,
        "channel_setup_done": len(_owned_channels_or_empty()) > 0 if session else False,
        "app_active": bool(readiness.get("active")) if session else False,
        "api_readiness": readiness,
        "release": release,
        "media_ready": None,
        "foundation": foundation,
        "note": "ok/app_active do not imply media tools; use /api/media-capability and foundation",
    }


@app.get("/api/auth/identity")
def auth_identity() -> Dict[str, Any]:
    """C02: safe authentication / account / entitlement projection."""
    from app.customer_auth import evaluate_session, ensure_session_columns

    ensure_session_columns()
    return {"ok": True, "identity": evaluate_session()}


@app.get("/api/auth/access")
def auth_access() -> Dict[str, Any]:
    """C02: production access decision (auth ∧ entitlement ∧ C01 readiness)."""
    from app.customer_auth import can_customer_produce

    decision = can_customer_produce()
    return {"ok": True, **decision}


@app.get("/api/dashboard")
def dashboard(customer_id: str = "", login_id: str = "") -> Dict[str, Any]:
    """C03: thin read-only onboarding + dashboard projection (no owned job/config state).

    METHOD GET /api/dashboard
    AUTH require_authenticated_session
    AUTHORIZATION customer-scoped (rejects forged login_id/customer_id)
    INPUT optional login_id|customer_id (must match session or empty)
    OUTPUT identity, access, onboarding, checklist, readiness, jobs summary
    DATA SOURCE customer_auth + customer_foundation + customer_job + channels + api_readiness
    SIDE EFFECTS none
    """
    session = _require_session()
    if not session:
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}

    from app.config import validate_production_operational
    from app.customer_auth import can_customer_produce, evaluate_session
    from app.customer_foundation import build_foundation_snapshot
    from app.customer_job import list_customer_jobs, partition_jobs
    from app.customer_onboarding import assert_customer_scope, build_dashboard, ensure_onboarding_table
    from app.release_identity import get_release_identity
    from pipeline.channel_api_slots import evaluate_readiness
    from pipeline.compose import probe_media_tool_capability
    from pipeline.live_activity import snapshot

    ensure_onboarding_table()
    identity = evaluate_session()
    session_login = str(identity.get("login_id") or session.get("login_id") or "")
    scope_err = assert_customer_scope(login_id or customer_id, session_login)
    if scope_err:
        return {
            "ok": False,
            "error": scope_err,
            "message": "Requested customer identifier does not match the signed-in account.",
            "identity": identity,
        }

    from app.legal.consent_manager import ConsentManager
    cm = ConsentManager()
    is_local_dev = (
        session.get("auth_mode") == "local_dev"
        or str(session.get("token") or "").startswith("local-")
        or identity.get("auth_mode") == "local_dev"
    )
    if is_local_dev and session_login and not cm.has_user_consented(session_login):
        cm.record_consent(session_login, ip_address="127.0.0.1")

    if not cm.has_user_consented(session_login):
        return {
            "ok": False,
            "error": "legal_consent_required",
            "consent_required": True,
            "message": "সফটওয়্যার ব্যবহারের পূর্বে আইনি নিয়মাবলী ও টার্মস ডিসক্লেইমারে সম্মতি প্রদান বাধ্যতামূলক।",
            "terms": cm.get_terms("bn"),
            "identity": identity,
        }

    live = snapshot()
    channels = _owned_channels_or_empty()
    owned_ids = [int(c["id"]) for c in channels if c.get("id") is not None]
    jobs = list_customer_jobs(50, live=live, channel_ids=owned_ids)
    parts = partition_jobs(jobs)
    api_readiness = evaluate_readiness(channel=channels[0] if channels else {})
    foundation_snap = build_foundation_snapshot(
        app_started=True,
        media_cap=probe_media_tool_capability(),
        operational=validate_production_operational(),
        api_readiness=api_readiness,
        active_job=(parts["active_jobs"][0] if parts["active_jobs"] else None),
    )
    access = can_customer_produce(channel=channels[0] if channels else {}, foundation=foundation_snap)
    dash = build_dashboard(
        identity=identity,
        access=access,
        foundation=foundation_snap,
        channels=channels,
        api_readiness=api_readiness,
        active_jobs=parts["active_jobs"],
        recent_jobs=parts["recent_jobs"],
        release=get_release_identity(include_media=False),
    )
    from app.customer_config import configuration_summary

    dash["configuration"] = configuration_summary(session_login)
    return dash


@app.get("/api/onboarding")
def onboarding_status(login_id: str = "") -> Dict[str, Any]:
    """C03: onboarding projection only (subset of dashboard)."""
    session = _require_session()
    if not session:
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    dash = dashboard(login_id=login_id)
    if not dash.get("ok"):
        return dash
    return {
        "ok": True,
        "onboarding": dash.get("onboarding"),
        "checklist": dash.get("checklist"),
        "startup_route": dash.get("startup_route"),
        "blocking_issues": dash.get("blocking_issues"),
        "identity": dash.get("identity"),
        "access": dash.get("access"),
    }


@app.post("/api/onboarding/start")
def onboarding_start(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """C03: mark onboarding started for the signed-in customer only."""
    session = _require_session()
    if not session:
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_onboarding import assert_customer_scope, start_onboarding

    identity = evaluate_session()
    session_login = str(identity.get("login_id") or session.get("login_id") or "")
    req = str((payload or {}).get("login_id") or "")
    if assert_customer_scope(req, session_login):
        return {"ok": False, "error": "customer_scope_denied"}
    if not session_login:
        return {"ok": False, "error": "login_id_missing"}
    return start_onboarding(session_login)


@app.post("/api/onboarding/complete")
def onboarding_complete(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """C03: mark onboarding completed only when mandatory checks are READY."""
    session = _require_session()
    if not session:
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_onboarding import assert_customer_scope, complete_onboarding

    identity = evaluate_session()
    session_login = str(identity.get("login_id") or session.get("login_id") or "")
    req = str((payload or {}).get("login_id") or "")
    if assert_customer_scope(req, session_login):
        return {"ok": False, "error": "customer_scope_denied"}
    dash = dashboard()
    if not dash.get("ok"):
        return dash
    state = str((dash.get("onboarding") or {}).get("state") or "")
    result = complete_onboarding(session_login, state=state)
    if not result.get("ok"):
        return result
    refreshed = dashboard()
    return {"ok": True, "onboarding": refreshed.get("onboarding"), "startup_route": refreshed.get("startup_route")}


@app.get("/api/foundation")
def foundation() -> Dict[str, Any]:
    """C01-A: truthful application / media / production / active-job planes."""
    from app.config import validate_production_operational
    from app.customer_foundation import build_foundation_snapshot
    from app.customer_job import get_job, to_customer_view
    from pipeline.compose import probe_media_tool_capability
    from pipeline.live_activity import snapshot

    session = store.get_session()
    api_readiness = None
    if session:
        from pipeline.channel_api_slots import evaluate_readiness

        channels = _owned_channels_or_empty()
        api_readiness = evaluate_readiness(channel=channels[0] if channels else {})

    live = snapshot()
    active_job = None
    db_jid = live.get("db_job_id")
    if db_jid:
        row = get_job(int(db_jid))
        if row:
            active_job = to_customer_view(row, live=live)

    snap = build_foundation_snapshot(
        app_started=True,
        media_cap=probe_media_tool_capability(),
        operational=validate_production_operational(),
        api_readiness=api_readiness,
        active_job=active_job,
    )
    return {"ok": True, "foundation": snap, "activity": {
        "active": bool(live.get("active")),
        "phase": live.get("phase"),
        "db_job_id": live.get("db_job_id"),
        "live_job_id": live.get("job_id"),
        "detail": live.get("detail"),
        "elapsed_sec": live.get("elapsed_sec"),
        "error": live.get("error") or None,
    }}


@app.get("/api/workspace")
def workspace(job_id: int = 0) -> Dict[str, Any]:
    """C01-B + C06-A: thin aggregation of foundation + jobs + workflow projection (no owned state)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.config import validate_production_operational
    from app.customer_auth import can_customer_produce, evaluate_session
    from app.customer_foundation import build_foundation_snapshot
    from app.customer_job import (
        get_job,
        job_owned_by_channels,
        list_customer_jobs,
        partition_jobs,
        to_customer_view,
    )
    from app.customer_workspace import build_workspace_projection
    from app.generation_guard import is_busy as generation_is_busy
    from app.generation_guard import metrics_snapshot as generation_metrics
    from pipeline.compose import probe_media_tool_capability
    from pipeline.channel_api_slots import evaluate_readiness
    from pipeline.live_activity import snapshot

    live = snapshot()
    login_id = _session_login_id()
    channels = _owned_channels_or_empty()
    owned_ids = [int(c["id"]) for c in channels if c.get("id") is not None]
    jobs = list_customer_jobs(50, live=live, channel_ids=owned_ids)
    parts = partition_jobs(jobs)
    api_readiness = evaluate_readiness(channel=channels[0] if channels else {})
    foundation = build_foundation_snapshot(
        app_started=True,
        media_cap=probe_media_tool_capability(),
        operational=validate_production_operational(),
        api_readiness=api_readiness,
        active_job=(parts["active_jobs"][0] if parts["active_jobs"] else None),
    )
    access_raw = can_customer_produce(
        channel=channels[0] if channels else {},
        foundation=foundation,
    )
    access = {
        "production_allowed": bool(access_raw.get("allowed")),
        "allowed": bool(access_raw.get("allowed")),
        "block_reason": access_raw.get("block_reason"),
        "message": access_raw.get("message"),
        "message_key": access_raw.get("message_key"),
    }
    selected = None
    selected_forbidden = False
    if job_id:
        row = get_job(int(job_id))
        if row and not job_owned_by_channels(row, owned_ids):
            selected_forbidden = True
            selected = None
        elif row:
            selected = to_customer_view(row, live=live)
    elif parts["active_jobs"]:
        selected = parts["active_jobs"][0]
    elif parts["recent_jobs"]:
        selected = parts["recent_jobs"][0]

    channel = channels[0] if channels else None
    if selected and selected.get("channel_id"):
        for c in channels:
            if int(c.get("id") or 0) == int(selected.get("channel_id") or 0):
                channel = c
                break

    projection = build_workspace_projection(
        login_id=login_id,
        channel=channel,
        job=selected,
        live=live,
        foundation=foundation,
        access=access,
    )

    trs_workflow = None
    if channel and channel.get("id") is not None:
        from app.customer_trs_workflow import load_workflow, project_trs_workflow

        trs_workflow = project_trs_workflow(load_workflow(login_id, int(channel["id"])))

    out: Dict[str, Any] = {
        "ok": True,
        "identity": evaluate_session(),
        "access": access,
        "foundation": foundation,
        "active_jobs": parts["active_jobs"],
        "recent_jobs": parts["recent_jobs"][:30],
        "selected_job": selected,
        "generation_busy": generation_is_busy(),
        "activity": {
            "active": bool(live.get("active")),
            "phase": live.get("phase"),
            "db_job_id": live.get("db_job_id"),
            "detail": live.get("detail"),
            "elapsed_sec": live.get("elapsed_sec"),
            "scene": live.get("scene"),
            "scene_total": live.get("scene_total"),
            "error": live.get("error") or None,
        },
        "project": projection["project"],
        "workflow": projection["workflow"],
        "production_summary": projection["production_summary"],
        "quality_panel": projection["quality_panel"],
        "preview": projection["preview"],
        "approval": projection["approval"],
        "revision_history": projection.get("revision_history"),
        "automation": projection.get("automation"),
        "production_monitor": projection.get("production_monitor"),
        "action": projection["action"],
        "trs_workflow": trs_workflow,
        "production_plan": None,
        "execution": None,
        "note": "workspace aggregates authorities only — does not own job lifecycle",
        "guard_metrics": generation_metrics(),
    }
    if channel and channel.get("id") is not None:
        from app.customer_production_plan import load_production_plan, project_production_plan

        out["production_plan"] = project_production_plan(
            load_production_plan(login_id, int(channel["id"]))
        )
        try:
            from app.customer_generation_orchestrator import project_execution_status
            from app.customer_job import list_customer_jobs

            jobs = list_customer_jobs(5, channel_ids=[int(channel["id"])])
            exec_proj = None
            for j in jobs:
                if j.get("production_plan_id") or j.get("generation_fingerprint"):
                    exec_proj = project_execution_status(login_id, int(j["job_id"]))
                    break
            out["execution"] = exec_proj
        except Exception:
            out["execution"] = None
    if selected_forbidden:
        out["ok"] = False
        out["error"] = "job_access_denied"
        out["error_code"] = "ownership_violation"
        out["selected_job"] = None
    return out


@app.get("/api/workspace/preview")
def workspace_preview(job_id: int = 0) -> Dict[str, Any]:
    """C06-F: evidence-backed preview projection (ownership-bound)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "validation_failure"}
    from app.customer_preview_approval import project_customer_preview

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_customer_preview(_session_login_id(), int(job_id), channel_ids=owned_ids)


@app.get("/api/workspace/revision-history")
def workspace_revision_history(job_id: int = 0) -> Dict[str, Any]:
    """C06-F: non-destructive revision / approval history."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "validation_failure"}
    from app.customer_preview_approval import list_revision_history

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return list_revision_history(_session_login_id(), int(job_id), channel_ids=owned_ids)


@app.post("/api/workspace/approval")
def workspace_approval(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-A/F: customer review approval boundary — does NOT publish.

    Job field write remains set_customer_approval (via record_customer_approval).
    """
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_job import get_job, job_owned_by_channels, set_customer_approval
    from app.customer_preview_approval import record_customer_approval

    job_id = int(payload.get("job_id") or 0)
    decision = str(payload.get("decision") or payload.get("approval") or "")
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "validation_failure"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    row = get_job(job_id)
    if not row or not job_owned_by_channels(row, owned_ids):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    # Identity from session only — ignore client-supplied login_id
    _ = set_customer_approval  # C06-A contract: symbol retained; invoked inside record path
    return record_customer_approval(
        _session_login_id(),
        job_id,
        channel_ids=owned_ids,
        decision=decision,
        revision_id=payload.get("revision_id"),
        rejection_reason=payload.get("rejection_reason") or payload.get("reason"),
    )


def _owned_channel_or_err(channel_id: int):
    from app.customer_config import require_owned_channel

    return require_owned_channel(int(channel_id), _session_login_id())


@app.post("/api/workspace/topic")
def workspace_topic(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-B: manual topic or select suggested/reserved — BUILD-04G duplicate check."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_trs_workflow import select_topic, set_manual_topic

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    action = str(payload.get("action") or "manual").lower()
    if action in ("manual", "set"):
        return set_manual_topic(
            _session_login_id(),
            channel_id,
            str(payload.get("topic_text") or payload.get("topic") or ""),
            niche=str(channel.get("niche") or ""),
        )
    return select_topic(
        _session_login_id(),
        channel,
        topic_id=str(payload.get("topic_id") or ""),
        topic_text=str(payload.get("topic_text") or payload.get("topic") or ""),
        source=str(payload.get("source") or "SUGGESTED"),
        niche=str(channel.get("niche") or ""),
    )


@app.post("/api/workspace/topics/suggest")
def workspace_topics_suggest(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-B: BUILD-04G discovery suggestions (local — not external live web)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_trs_workflow import suggest_topics

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    return suggest_topics(
        _session_login_id(),
        channel,
        video_type="long" if payload.get("video_type") == "long" else "short",
        count=int(payload.get("count") or 6),
    )


def _resolve_workspace_mock_flag(payload: Dict[str, Any], endpoint_name: str = "workspace") -> bool:
    """Resolve mock vs live execution mode for workspace production endpoints (C-01).

    In production endpoints, Live Mode (use_mock=False) is the standard default.
    Mock Mode is activated only when:
    1. The caller explicitly specifies `use_mock=True` (or False to force live).
    2. The caller specifies `mode` or `execution_mode` as 'mock' / 'mock_deterministic'.
    3. An explicit environment variable `AUTOMOVIE_WORKSPACE_MOCK=1` or `AUTOMOVIE_MOCK_ALL=1` is set.
    """
    raw_mock = payload.get("use_mock")
    if raw_mock is not None:
        return bool(raw_mock)

    raw_mode = str(payload.get("mode") or payload.get("execution_mode") or "").strip().lower()
    if raw_mode in ("mock", "mock_deterministic"):
        return True
    if raw_mode in ("live", "production", "real"):
        return False

    env_mock = os.environ.get("AUTOMOVIE_WORKSPACE_MOCK") or os.environ.get("AUTOMOVIE_MOCK_ALL") or ""
    if env_mock.strip().lower() in ("1", "true", "yes", "on"):
        return True

    # Default for production endpoints is LIVE execution (use_mock=False)
    return False


@app.post("/api/workspace/research")
def workspace_research(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-B: BUILD-04G research — honest LOCAL_FACTPACK capability (Live by default)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_trs_workflow import run_research

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    use_mock = _resolve_workspace_mock_flag(payload, endpoint_name="research")
    res = run_research(_session_login_id(), channel, use_mock=use_mock)
    if isinstance(res, dict):
        res["execution_mode"] = "MOCK" if use_mock else "LIVE"
        res["use_mock"] = use_mock
    return res


@app.post("/api/workspace/script")
def workspace_script(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-B: generate ScriptPlan via existing script authority + BUILD-04F quality (Live by default)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_trs_workflow import generate_script
    from pipeline.duration_budget import resolve_duration_contract

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    use_mock = _resolve_workspace_mock_flag(payload, endpoint_name="script")
    video_type = "long" if payload.get("video_type") == "long" else "short"
    if payload.get("max_seconds") is not None:
        max_seconds = int(payload.get("max_seconds"))
    else:
        max_seconds = int(resolve_duration_contract(video_type)["target_seconds"])
    res = generate_script(
        _session_login_id(),
        channel,
        video_type=video_type,
        max_seconds=max_seconds,
        use_mock=use_mock,
        tone=str(payload.get("tone") or ""),
        audience=str(payload.get("audience") or ""),
        instructions=str(payload.get("instructions") or ""),
    )
    if isinstance(res, dict):
        res["execution_mode"] = "MOCK" if use_mock else "LIVE"
        res["use_mock"] = use_mock
    return res


@app.post("/api/workspace/script/approval")
def workspace_script_approval(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-B: approve/reject script — APPROVED_SCRIPT ≠ generated/published."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_trs_workflow import approve_script

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    return approve_script(
        _session_login_id(),
        channel_id,
        decision=str(payload.get("decision") or payload.get("approval") or ""),
    )


@app.get("/api/workspace/production-plan")
def workspace_production_plan_get(channel_id: int = 0) -> Dict[str, Any]:
    """C06-C: read customer production plan projection (no media)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_production_plan import load_production_plan, project_production_plan

    channel, err = _owned_channel_or_err(int(channel_id))
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    plan = load_production_plan(_session_login_id(), int(channel_id))
    return {"ok": True, "production_plan": project_production_plan(plan)}


@app.post("/api/workspace/production-plan")
def workspace_production_plan_build(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-C: build/rebuild Production Plan from APPROVED_SCRIPT — no media generation."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_production_plan import build_production_plan

    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    return build_production_plan(
        _session_login_id(),
        channel,
        force_rebuild=bool(payload.get("force_rebuild") or payload.get("refresh")),
    )


@app.get("/api/workspace/execution")
def workspace_execution_get(channel_id: int = 0, job_id: int = 0) -> Dict[str, Any]:
    """C06-D: truthful generation execution projection (no publishing)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    from app.customer_generation_orchestrator import assert_job_owner, project_execution_status
    from app.customer_job import list_customer_jobs

    login_id = _session_login_id()
    owned_ids = [int(channel["id"])]
    if job_id:
        own = assert_job_owner(login_id, int(job_id), owned_ids)
        if own:
            return own
        return project_execution_status(login_id, int(job_id))
    jobs = list_customer_jobs(10, channel_ids=owned_ids)
    if not jobs:
        return {"ok": True, "execution": {"status": "NOT_STARTED", "note": "No generation jobs"}}
    return project_execution_status(login_id, int(jobs[0]["job_id"]))


@app.post("/api/workspace/generate")
def workspace_generate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C06-D/G: Generate from READY_FOR_GENERATION plan.

    Default remains synchronous C06-D start_customer_generation (compat).
    Pass queue=true for C06-G enqueue + optional process_now tick.
    """
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    channel_id = int(payload.get("channel_id") or 0)
    channel, err = _owned_channel_or_err(channel_id)
    if err:
        return {**err, "error_code": err.get("error") or "ownership_violation"}
    video_type = "long" if payload.get("video_type") == "long" else "short"
    execution_mode = payload.get("execution_mode")
    use_mock = payload.get("use_mock")
    if execution_mode is None and use_mock is None:
        execution_mode = "MOCK_DETERMINISTIC"
    deterministic_fixtures = True if payload.get("deterministic_fixtures") is None else bool(payload.get("deterministic_fixtures"))
    ch = {**channel, "owner_login_id": channel.get("owner_login_id") or _session_login_id()}

    if payload.get("queue") or payload.get("async_queue"):
        from app.customer_job_automation import submit_customer_generation

        return submit_customer_generation(
            _session_login_id(),
            ch,
            video_type=video_type,
            use_mock=use_mock if use_mock is not None else None,
            execution_mode=execution_mode,
            deterministic_fixtures=deterministic_fixtures,
            force_rebuild=bool(payload.get("force_rebuild")),
            process_now=bool(payload.get("process_now", True)),
        )

    from app.customer_generation_orchestrator import start_customer_generation

    return start_customer_generation(
        _session_login_id(),
        ch,
        video_type=video_type,
        use_mock=use_mock if use_mock is not None else None,
        execution_mode=execution_mode,
        deterministic_fixtures=deterministic_fixtures,
        force_rebuild=bool(payload.get("force_rebuild")),
    )


@app.get("/api/workspace/monitor")
def workspace_monitor(job_id: int = 0) -> Dict[str, Any]:
    """C06-H: truthful production monitor projection."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "validation_failure"}
    from app.customer_production_monitor import project_production_monitor

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_production_monitor(_session_login_id(), int(job_id), channel_ids=owned_ids)


@app.get("/api/workspace/activity-feed")
def workspace_activity_feed() -> Dict[str, Any]:
    """C06-H: thin attention/activity projection (not external messaging)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_production_monitor import project_recent_activity

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_recent_activity(_session_login_id(), channel_ids=owned_ids)


@app.get("/api/workspace/notifications")
def workspace_notifications(locale: str = "en") -> Dict[str, Any]:
    """C09: customer notification projection (not a second event engine)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_communication import project_notifications

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_notifications(_session_login_id(), channel_ids=owned_ids, locale=locale)


@app.post("/api/workspace/notifications/{notification_id}/read")
def workspace_notification_read(notification_id: str) -> Dict[str, Any]:
    """C09: mark notification read — never mutates production."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_communication import mark_notification_read

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return mark_notification_read(_session_login_id(), notification_id, channel_ids=owned_ids)


@app.get("/api/workspace/help/context")
def workspace_help_context(job_id: int = 0, locale: str = "en") -> Dict[str, Any]:
    """C09: contextual help from authoritative state."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_communication import help_context

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return help_context(
        _session_login_id(),
        channel_ids=owned_ids,
        job_id=int(job_id) if job_id else None,
        locale=locale,
    )


@app.post("/api/workspace/help/query")
def workspace_help_query(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C09: deterministic help query — no production mutations."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_communication import help_query

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return help_query(
        _session_login_id(),
        channel_ids=owned_ids,
        query=str(payload.get("query") or payload.get("q") or ""),
        job_id=int(payload["job_id"]) if payload.get("job_id") else None,
        locale=str(payload.get("locale") or "en"),
    )


@app.get("/api/workspace/entry-points")
def workspace_entry_points() -> Dict[str, Any]:
    """C06-H: classify generation entry points (canonical vs legacy vs lab)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_production_monitor import ENTRY_POINT_CLASSIFICATION, classify_live_lab

    return {
        "ok": True,
        "entry_points": ENTRY_POINT_CLASSIFICATION,
        "live_lab": classify_live_lab(),
        "publishes": False,
    }


@app.get("/api/workspace/certification")
def workspace_certification(job_id: int = 0) -> Dict[str, Any]:
    """C08: thin journey projection over existing authorities (not a second engine)."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_auth import evaluate_session
    from app.customer_production_certification import project_journey

    channels = _owned_channels_or_empty()
    owned_ids = [int(c["id"]) for c in channels if c.get("id") is not None]
    ch = channels[0] if channels else {}
    return project_journey(
        _session_login_id(),
        channel_ids=owned_ids,
        job_id=int(job_id) if job_id else None,
        channel=ch,
        identity=evaluate_session(),
    )


@app.get("/api/workspace/queue")
def workspace_queue() -> Dict[str, Any]:
    """C06-G: customer-owned queue projection."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    from app.customer_job_automation import list_queue

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return list_queue(_session_login_id(), channel_ids=owned_ids)


@app.post("/api/workspace/queue/tick")
def workspace_queue_tick() -> Dict[str, Any]:
    """C06-G: deterministic scheduler tick (orchestration only; tests / local)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_job_automation import scheduler_tick

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return scheduler_tick(worker_id=f"session:{_session_login_id()}", channel_ids=owned_ids or None)


@app.post("/api/workspace/job/{job_id}/cancel")
def workspace_job_cancel(job_id: int) -> Dict[str, Any]:
    """C06-G: explicit cancellation — never silently retries cancelled jobs."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_job_automation import request_cancel

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return request_cancel(_session_login_id(), int(job_id), channel_ids=owned_ids)


@app.get("/api/workspace/publishing")
def workspace_publishing(job_id: int = 0) -> Dict[str, Any]:
    """C07-PUB: publishing projection over existing job state."""
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {"ok": False, "error": "login_required", "identity": evaluate_session()}
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "validation_failure"}
    from app.customer_publish import project_publishing

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_publishing(_session_login_id(), int(job_id), channel_ids=owned_ids)


@app.post("/api/workspace/publishing/validate")
def workspace_publishing_validate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C07-PUB: fail-closed admit gates — no provider call."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_publish import validate_publish_gates

    job_id = int(payload.get("job_id") or 0)
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "VALIDATION_FAILURE"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return validate_publish_gates(
        _session_login_id(),
        job_id,
        channel_ids=owned_ids,
        channel_id=int(payload["channel_id"]) if payload.get("channel_id") else None,
        revision_id=payload.get("revision_id"),
        provider=str(payload.get("provider") or "mock"),
        identity=evaluate_session(),
    )


@app.post("/api/workspace/publishing/publish")
def workspace_publishing_publish(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C07-PUB: explicit publish — approval alone never publishes."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_publish import publish_customer_job

    job_id = int(payload.get("job_id") or 0)
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "VALIDATION_FAILURE"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    # Live provider only when explicitly requested AND not the default product path
    allow_live = bool(payload.get("allow_live_provider")) and str(payload.get("provider") or "").lower() in (
        "youtube",
        "yt",
    )
    return publish_customer_job(
        _session_login_id(),
        job_id,
        channel_ids=owned_ids,
        channel_id=int(payload["channel_id"]) if payload.get("channel_id") else None,
        revision_id=payload.get("revision_id"),
        provider=str(payload.get("provider") or "mock"),
        scenario=str(payload.get("scenario") or "happy_path"),
        allow_live_provider=allow_live,
        identity=evaluate_session(),
        publish_at=payload.get("publish_at"),
    )


@app.post("/api/workspace/publishing/refresh")
def workspace_publishing_refresh(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C07-PUB: observe remote processing — upload success ≠ published."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_publish import refresh_publish_status

    job_id = int(payload.get("job_id") or 0)
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "VALIDATION_FAILURE"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return refresh_publish_status(
        _session_login_id(),
        job_id,
        channel_ids=owned_ids,
        provider=payload.get("provider"),
        scenario=str(payload.get("scenario") or "happy_path"),
    )


@app.get("/api/workspace/publishing/schedules")
def workspace_publishing_schedules(job_id: int = 0) -> Dict[str, Any]:
    """C07-SCHED: list customer publish schedules."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_publish_schedule import project_schedule_panel

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return project_schedule_panel(
        _session_login_id(),
        channel_ids=owned_ids,
        job_id=int(job_id) if job_id else None,
    )


@app.post("/api/workspace/publishing/schedule")
def workspace_publishing_schedule_create(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """C07-SCHED: create ScheduledPublish — no provider upload."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_publish_schedule import create_schedule

    job_id = int(payload.get("job_id") or 0)
    if not job_id:
        return {"ok": False, "error": "job_id_required", "error_code": "VALIDATION_FAILURE"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return create_schedule(
        _session_login_id(),
        job_id=job_id,
        channel_ids=owned_ids,
        local_datetime=str(payload.get("local_datetime") or payload.get("scheduled_local") or ""),
        timezone_name=str(payload.get("timezone") or payload.get("tz") or "UTC"),
        channel_id=int(payload["channel_id"]) if payload.get("channel_id") else None,
        revision_id=payload.get("revision_id"),
        provider=str(payload.get("provider") or "mock"),
        identity=evaluate_session(),
    )


@app.post("/api/workspace/publishing/schedule/{schedule_id}/cancel")
def workspace_publishing_schedule_cancel(schedule_id: str) -> Dict[str, Any]:
    """C07-SCHED: cancel before execution."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_publish_schedule import cancel_schedule

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return cancel_schedule(_session_login_id(), schedule_id, channel_ids=owned_ids)


@app.post("/api/workspace/publishing/schedule/{schedule_id}/reschedule")
def workspace_publishing_schedule_reschedule(
    schedule_id: str, payload: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """C07-SCHED: supersede + create new schedule (one future execution)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_auth import evaluate_session
    from app.customer_publish_schedule import reschedule

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return reschedule(
        _session_login_id(),
        schedule_id,
        channel_ids=owned_ids,
        local_datetime=str(payload.get("local_datetime") or ""),
        timezone_name=str(payload.get("timezone") or "UTC"),
        identity=evaluate_session(),
    )


@app.post("/api/workspace/publishing/schedule/{schedule_id}/refresh")
def workspace_publishing_schedule_refresh(schedule_id: str) -> Dict[str, Any]:
    """C07-SCHED: refresh schedule + publish observation."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_publish_schedule import refresh_schedule

    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return refresh_schedule(_session_login_id(), schedule_id, channel_ids=owned_ids)


@app.post("/api/login")
def login(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    login_id = str(payload.get("login_id") or "").strip()
    password = str(payload.get("password") or "")
    api_base = str(payload.get("api_base_url") or settings.api_base_url).rstrip("/")
    from app.customer_auth import authenticate

    result = authenticate(login_id, password, api_base)
    if not result.get("ok"):
        code = 401
        if result.get("error") == "missing_credentials":
            code = 400
        if result.get("auth_state") == "ACCOUNT_DISABLED":
            code = 403
        return JSONResponse(
            {
                "ok": False,
                "error": result.get("error") or "login_failed",
                "auth_state": result.get("auth_state"),
                "identity": result.get("identity"),
                "message": result.get("message"),
                "message_key": result.get("message_key"),
                "hint": result.get("hint"),
            },
            status_code=code,
        )

    # Language unlock sync (existing behavior) — uses safe customer fields only
    customer = result.get("customer") or {}
    unlocked = [str(c).strip().lower() for c in (customer.get("unlocked") or []) if str(c).strip()]
    if unlocked:
        try:
            from pipeline.lang_entitlement import parse_languages, serialize_languages

            channels = _owned_channels_or_empty()
            if channels:
                ch = channels[0]
                merged = parse_languages(list(parse_languages(ch.get("languages_json"))) + unlocked)
                if merged != parse_languages(ch.get("languages_json")):
                    ch["languages_json"] = serialize_languages(merged)
                    store.upsert_channel(ch, int(ch["id"]))
        except Exception:
            pass

    return JSONResponse(
        {
            "ok": True,
            "customer": customer,
            "mode": result.get("mode"),
            "identity": result.get("identity"),
            "warning": result.get("warning"),
        }
    )


@app.get("/api/auth/device-info")
def get_device_info() -> Dict[str, Any]:
    from app.auth.hardware_id import get_hardware_fingerprint

    return {"ok": True, "hardware_id": get_hardware_fingerprint()}


@app.post("/api/auth/request-otp")
def request_otp_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    target = str(
        payload.get("login_id")
        or payload.get("email")
        or payload.get("identifier")
        or payload.get("phone")
        or payload.get("whatsapp")
        or payload.get("telegram")
        or ""
    ).strip()
    api_base = str(payload.get("api_base_url") or settings.api_base_url).rstrip("/")
    if not target:
        return JSONResponse({"ok": False, "error": "missing_target", "message": "হোয়াটসঅ্যাপ/টেলিগ্রাম নম্বর, ইউজার আইডি বা ইমেইল প্রদান করুন।"}, status_code=400)
    from app.customer_auth import request_password_otp

    res = request_password_otp(target, api_base)
    status_code = 200 if res.get("ok") else 400
    return JSONResponse(res, status_code=status_code)


@app.post("/api/auth/reset-password")
def reset_password_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    target = str(
        payload.get("login_id")
        or payload.get("email")
        or payload.get("identifier")
        or payload.get("phone")
        or payload.get("whatsapp")
        or payload.get("telegram")
        or ""
    ).strip()
    otp = str(payload.get("otp") or "").strip()
    new_password = str(payload.get("new_password") or "")
    api_base = str(payload.get("api_base_url") or settings.api_base_url).rstrip("/")
    if not target or not otp or not new_password:
        return JSONResponse({"ok": False, "error": "missing_fields", "message": "সকল প্রয়োজনীয় তথ্য পূরণ করুন।"}, status_code=400)
    from app.customer_auth import reset_password

    res = reset_password(target, otp, new_password, api_base)
    status_code = 200 if res.get("ok") else 400
    return JSONResponse(res, status_code=status_code)


@app.post("/api/support/ticket")
def submit_support_ticket(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    import time
    import requests

    ticket_type = str(payload.get("type") or payload.get("reason") or "Bug Report").strip()
    message = str(payload.get("message") or "").strip()
    contact = str(payload.get("contact") or payload.get("whatsapp") or payload.get("email") or "").strip()
    screenshot_note = str(payload.get("screenshot_note") or "").strip()

    if not message:
        return JSONResponse({"ok": False, "message": "অনুগ্রহ করে বিস্তারিত বিবরণ প্রদান করুন।"}, status_code=400)

    ticket_id = f"AMP-TK{int(time.time()) % 100000:05d}"
    api_base = str(payload.get("api_base_url") or settings.api_base_url).rstrip("/")
    try:
        r = requests.post(f"{api_base}/api/agent-escalate.php", json={
            "reason": ticket_type,
            "message": message,
            "contact": contact,
            "screenshot_note": screenshot_note
        }, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("ticket_id"):
                ticket_id = data.get("ticket_id")
    except Exception:
        pass

    return JSONResponse({
        "ok": True,
        "ticket_id": ticket_id,
        "message": f"আপনার রিপোর্ট/পরামর্শ সফলভাবে জমা হয়েছে। ট্র্যাকিং টিকিট আইডি: {ticket_id}। ইনশাআল্লাহ, সর্বোচ্চ ৭২ ঘণ্টার মধ্যে আমাদের ইঞ্জিনিয়ার টিম এটি খতিয়ে দেখে সরাসরি আপনার হোয়াটসঅ্যাপ/ইমেইলে সমাধান বা প্রয়োজনীয় আপডেট প্রদান করবে।"
    })


@app.post("/api/feedback/review")
def submit_feedback_review(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    import requests

    name = str(payload.get("name") or "AutoMovie Pro User").strip()
    try:
        rating = int(payload.get("rating") or 5)
    except Exception:
        rating = 5
    review_text = str(payload.get("review_text") or payload.get("message") or "").strip()
    platform = str(payload.get("platform") or "Desktop App").strip()

    if not review_text:
        return JSONResponse({"ok": False, "message": "অনুগ্রহ করে আপনার মূল্যবান মতামত লিখুন।"}, status_code=400)

    api_base = str(payload.get("api_base_url") or settings.api_base_url).rstrip("/")
    try:
        requests.post(f"{api_base}/api/reviews.php", json={
            "name": name,
            "rating": rating,
            "review_text": review_text,
            "platform": platform
        }, timeout=8)
    except Exception:
        pass

    return JSONResponse({
        "ok": True,
        "message": "আপনার মূল্যবান মতামত ও রেটিংয়ের জন্য আন্তরিক ধন্যবাদ! এটি আমাদের সেবাকে আরও উন্নত করতে সহায়তা করবে।"
    })


@app.post("/api/logout")
def logout() -> Dict[str, Any]:
    from app.customer_auth import logout as auth_logout

    return auth_logout()



# --- Step 2: Channel, Page, Language & Brand Setup Routes ---
@app.get("/api/setup/overview")
def get_setup_overview() -> Dict[str, Any]:
    from app.setup.channel_setup import (
        LANGUAGE_CATALOG,
        PACKAGE_ADDON_PRICE,
        PACKAGE_BASE_PRICE,
        PACKAGE_FULL_PRICE,
        PRICING_PACKAGES,
        SUPPORTED_NICHES,
        SetupManager,
    )

    manager = SetupManager()
    return {
        "ok": True,
        "config": manager.get_profile(),
        "catalog": LANGUAGE_CATALOG,
        "niches": SUPPORTED_NICHES,
        "pricing": {
            "base_2999": PACKAGE_BASE_PRICE,
            "addon_999": PACKAGE_ADDON_PRICE,
            "full_4999": PACKAGE_FULL_PRICE,
            "packages": PRICING_PACKAGES,
        },
        "active_channels_count": manager.get_active_channels_count(),
    }


@app.post("/api/setup/user-profile")
def update_setup_user_profile(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    from app.setup.channel_setup import SetupManager

    manager = SetupManager()
    updated = manager.update_user_profile(
        user_name=payload.get("user_name"),
        mobile_number=payload.get("mobile_number"),
        channel_niche=payload.get("channel_niche"),
    )
    return {"ok": True, "config": updated}


@app.post("/api/setup/package-tier")
def update_setup_package_tier(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    tier = str(payload.get("package_tier") or "base_2999")
    optional_lang = str(payload.get("selected_optional_lang") or "bn")
    from app.setup.channel_setup import SetupManager

    manager = SetupManager()
    updated = manager.set_package_tier(tier, optional_lang)
    return {"ok": True, "config": updated}


@app.post("/api/setup/unlock-language")
def unlock_language_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    lang = str(payload.get("lang_code") or "").strip()
    from app.setup.channel_setup import SetupManager

    manager = SetupManager()
    try:
        updated = manager.unlock_additional_language(lang)
        return JSONResponse({"ok": True, "config": updated})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.post("/api/setup/language-profile")
def update_language_profile_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    lang = str(payload.get("lang_code") or "").strip()
    if not lang:
        return JSONResponse({"ok": False, "error": "missing_lang_code"}, status_code=400)
    from app.setup.channel_setup import SetupManager

    manager = SetupManager()
    try:
        updated = manager.update_language_profile(
            lang,
            youtube=payload.get("youtube"),
            facebook=payload.get("facebook"),
            tiktok=payload.get("tiktok"),
            schedule=payload.get("schedule"),
            branding=payload.get("branding"),
            youtube_channel_name=payload.get("youtube_channel_name"),
            youtube_channel_id=payload.get("youtube_channel_id"),
            facebook_page_name=payload.get("facebook_page_name"),
            facebook_page_id=payload.get("facebook_page_id"),
            tiktok_account_name=payload.get("tiktok_account_name"),
            tiktok_id=payload.get("tiktok_id"),
            cookie_file=payload.get("cookie_file"),
            official_api_enabled=payload.get("official_api_enabled"),
            official_api_key=payload.get("official_api_key"),
            short_schedule=payload.get("short_schedule"),
            long_schedule=payload.get("long_schedule"),
            logo_path=payload.get("logo_path"),
            intro_video_path=payload.get("intro_video_path"),
        )
        return JSONResponse({"ok": True, "config": updated})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


# --- Step 3: Central API Hub & Failover Matrix Routes ---
@app.get("/api/matrix/summary")
def get_api_matrix_summary() -> Dict[str, Any]:
    from app.api_matrix.api_hub import ApiHub

    hub = ApiHub()
    return {"ok": True, "summary": hub.get_summary()}


@app.post("/api/matrix/keys")
def update_api_matrix_keys(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    from app.api_matrix.api_hub import ApiHub

    hub = ApiHub()
    summary = hub.update_keys(
        grok_primary_key=payload.get("grok_primary_key"),
        grok_fallback_key=payload.get("grok_fallback_key"),
        google_media_key=payload.get("google_media_key"),
        google_tts_keys=payload.get("google_tts_keys"),
        openrouter_key=payload.get("openrouter_key"),
        agnes_key=payload.get("agnes_key"),
        pexels_key=payload.get("pexels_key"),
        pollinations_key=payload.get("pollinations_key"),
    )
    return {"ok": True, "summary": summary}


@app.post("/api/matrix/validate")
def validate_api_matrix_readiness(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    unlocked = payload.get("unlocked_languages")
    if not isinstance(unlocked, list):
        from app.setup.channel_setup import SetupManager
        unlocked = SetupManager().get_profile().get("unlocked_languages", ["en", "bn"])
    from app.api_matrix.api_hub import ApiHub

    hub = ApiHub()
    report = hub.validate_readiness_for_languages(unlocked)
    return {"ok": True, "report": report}


# --- Step 4: Anti-Duplicate Topic Research & Segregated Storage Routes ---
@app.get("/api/topics")
def list_topics_route(video_format: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    from pipeline.anti_duplicate_topic import AntiDuplicateTopicEngine

    engine = AntiDuplicateTopicEngine()
    items = engine.list_topics(video_format=video_format, limit=limit)
    return {"ok": True, "topics": items}


@app.post("/api/topics/add")
def add_topic_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    title = str(payload.get("title") or "").strip()
    niche = str(payload.get("niche") or "General").strip()
    video_format = str(payload.get("video_format") or "short").strip()
    if not title:
        return JSONResponse({"ok": False, "error": "missing_title"}, status_code=400)
    from pipeline.anti_duplicate_topic import AntiDuplicateTopicEngine

    engine = AntiDuplicateTopicEngine()
    res = engine.add_topic(
        title=title,
        niche=niche,
        video_format=video_format,
        seo_keywords=payload.get("seo_keywords"),
        hook_angle=payload.get("hook_angle") or "",
        why_trending=payload.get("why_trending") or "",
        estimated_duration_sec=payload.get("estimated_duration_sec"),
    )
    status_code = 200 if res.get("ok") else 409
    return JSONResponse(res, status_code=status_code)


@app.post("/api/topics/mark-used")
def mark_topic_used_route(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    topic_id = str(payload.get("topic_id") or "").strip()
    from pipeline.anti_duplicate_topic import AntiDuplicateTopicEngine

    engine = AntiDuplicateTopicEngine()
    success = engine.mark_topic_used(topic_id)
    return {"ok": success}


# --- Step 5: Scriptwriting & Local Agent Inspection Routes ---
@app.post("/api/script/generate")
def generate_script_route(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    topic_title = str(payload.get("topic_title") or "").strip()
    niche = str(payload.get("niche") or "General").strip()
    video_format = str(payload.get("video_format") or "short").strip()
    language = str(payload.get("language") or "bn").strip()
    from dataclasses import asdict
    from pipeline.script_engine import ScriptEngine

    engine = ScriptEngine()
    script = engine.generate_script(
        topic_title=topic_title,
        niche=niche,
        video_format=video_format,
        language=language,
        include_islamic_touch=bool(payload.get("include_islamic_touch", True)),
        include_social_cta=bool(payload.get("include_social_cta", True)),
    )
    return {"ok": True, "script": asdict(script)}


@app.post("/api/script/regenerate-scene")
def regenerate_scene_route(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    script_data = payload.get("script")
    scene_index = int(payload.get("scene_index", 1))
    new_direction = str(payload.get("new_direction") or "")
    if not isinstance(script_data, dict):
        return JSONResponse({"ok": False, "error": "missing_script_data"}, status_code=400)
    from dataclasses import asdict
    from pipeline.script_engine import ProductionScript, ScriptEngine, ScriptScene

    engine = ScriptEngine()
    scenes = [
        ScriptScene(
            scene_index=s.get("scene_index", 1),
            narration=s.get("narration", ""),
            visual_prompt=s.get("visual_prompt", ""),
            estimated_duration_sec=float(s.get("estimated_duration_sec", 5.0)),
            hook_type=s.get("hook_type", "body"),
            passed_agent_qa=s.get("passed_agent_qa", True),
            agent_notes=s.get("agent_notes", ""),
        )
        for s in script_data.get("scenes", [])
    ]
    script = ProductionScript(
        script_id=script_data.get("script_id", "scr_tmp"),
        topic_id=script_data.get("topic_id", "top_tmp"),
        title=script_data.get("title", ""),
        niche=script_data.get("niche", ""),
        video_format=script_data.get("video_format", "short"),
        language=script_data.get("language", "bn"),
        scenes=scenes,
        total_estimated_duration_sec=float(script_data.get("total_estimated_duration_sec", 0.0)),
    )
    updated = engine.regenerate_single_scene(script, scene_index, new_direction)
    return JSONResponse({"ok": True, "script": asdict(updated)})


@app.get("/api/channels")
def channels() -> Dict[str, Any]:
    """C04: list customer-owned channels only (safe projection, no raw secrets)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import (
        configuration_summary,
        list_orphan_channels,
        to_safe_channel_view,
    )

    lid = _session_login_id()
    rows = _owned_channels_or_empty()
    safe = [to_safe_channel_view(r) for r in rows]
    summary = configuration_summary(lid)
    return {
        "ok": True,
        "channels": safe,
        "channel_setup_done": len(rows) > 0,
        "max_channels": 1,
        "configuration": summary,
        "orphan_channels_available": len(list_orphan_channels()),
        "note": "raw API keys never returned; ownership enforced server-side",
    }


@app.get("/api/api-providers")
def api_providers() -> Dict[str, Any]:
    """UI metadata for dedicated per-task API slots (+ language-gated TTS)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.api_guides import dedicated_providers_ui_meta, providers_ui_meta
    from pipeline.channel_api_slots import MAX_SLOTS, MIN_REQUIRED, evaluate_readiness
    from pipeline.lang_entitlement import channel_languages

    channels = _owned_channels_or_empty()
    ch = channels[0] if channels else {}
    unlocked = channel_languages(ch) if ch else ["en"]
    dedicated = dedicated_providers_ui_meta(unlocked=unlocked, channel=ch)
    ready = evaluate_readiness(channel=ch) if ch else {"active": False, "missing": [], "warnings": []}
    return {
        "ok": True,
        "mode": "dedicated",
        "max_slots": MAX_SLOTS,
        "min_required": MIN_REQUIRED,
        "unlocked_languages": unlocked,
        "providers": dedicated,
        "legacy_providers": providers_ui_meta(),
        "readiness": {
            "active": ready.get("active"),
            "missing": ready.get("missing") or [],
            "warnings": ready.get("warnings") or [],
            "message": ready.get("message"),
        },
    }


@app.get("/api/niches")
def niches(q: str = "", lang: str = "") -> Dict[str, Any]:
    """Full Nish.Md catalog for dashboard dropdown (150 niches), localized by lang."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    try:
        from pipeline.nish_catalog import list_niches_for_api, load_niche_catalog

        load_niche_catalog()  # warm / validate parse
        code = (lang or "").strip().lower()[:2] or "en"
        items = list_niches_for_api(lang=code)
        needle = (q or "").strip().lower()
        if needle:
            items = [
                n
                for n in items
                if needle in (n.get("name") or "").lower()
                or needle in (n.get("name_en") or "").lower()
                or needle in (n.get("blurb") or "").lower()
                or needle == str(n["id"])
            ]
        return {"ok": True, "count": len(items), "lang": code, "niches": items}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/channels")
async def create_channel(
    request: Request,
    youtube_name: str = Form(""),
    facebook_name: str = Form(""),
    tiktok_name: str = Form(""),
    niche: str = Form(""),
    niche_id: Optional[str] = Form(None),
    video_special: str = Form(""),
    long_upload_time: str = Form("18:00"),
    short_upload_time: str = Form("12:00"),
    example_script: str = Form(""),
    generation_special: str = Form(""),
    title_desc_special: str = Form(""),
    channel_id: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    intro: Optional[UploadFile] = File(None),
) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}

    from app.customer_config import (
        list_owned_channels,
        require_owned_channel,
        resolve_session_login_id,
        set_channel_owner_on_payload,
    )
    from pipeline.channel_api_slots import (
        MIN_REQUIRED,
        PROVIDER_DEFS,
        channel_provider_keys,
        collect_from_form,
        evaluate_readiness,
        merge_keep_existing,
        min_for_provider,
        serialize_api_keys_json,
        sync_legacy_fields,
    )
    from pipeline.niche_agent import apply_niche_to_channel

    form = await request.form()
    incoming_slots = collect_from_form(form)
    try:
        from pipeline.dedicated_api_registry import (
            collect_dedicated_from_form,
            merge_dedicated_keep,
            channel_dedicated_keys,
            serialize_dedicated_json,
        )

        dedicated_incoming = collect_dedicated_from_form(form)
    except Exception:
        dedicated_incoming = {}
        serialize_dedicated_json = None  # type: ignore
    secondary_lang = str(form.get("secondary_lang") or "").strip()
    login_id = resolve_session_login_id()
    if not login_id:
        return {"ok": False, "error": "login_required"}

    existing_channels = list_owned_channels(login_id)
    cid_int: Optional[int] = None
    if channel_id not in (None, "", "null"):
        try:
            cid_int = int(channel_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            cid_int = None

    # One channel per customer — new create blocked if this customer already owns one
    if cid_int is None and existing_channels:
        return {
            "ok": False,
            "error": "channel_already_setup",
            "hint": "একটি সফটওয়্যারে শুধুমাত্র একবার চ্যানেল সেটআপ করা যায়",
        }

    if cid_int is not None:
        _ch, own_err = require_owned_channel(cid_int, login_id)
        if own_err:
            return own_err

    from pipeline.lang_entitlement import serialize_languages, setup_languages

    nid_int: Optional[int] = None
    if niche_id not in (None, "", "null"):
        try:
            nid_int = int(niche_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            nid_int = None

    logo_path = ""
    intro_path = ""
    chan_dir = ASSETS_DIR / "channels"
    chan_dir.mkdir(parents=True, exist_ok=True)
    if logo is not None and logo.filename:
        dest = chan_dir / f"logo_{youtube_name or niche}_{logo.filename}"
        dest.write_bytes(await logo.read())
        logo_path = str(dest)
    if intro is not None and intro.filename:
        dest = chan_dir / f"intro_{youtube_name or niche}_{intro.filename}"
        dest.write_bytes(await intro.read())
        intro_path = str(dest)

    existing = store.get_channel(cid_int) if cid_int else None
    existing_slots = channel_provider_keys(existing or {})
    slots = merge_keep_existing(incoming_slots, existing_slots)
    legacy = sync_legacy_fields(slots)
    dedicated_json = (existing or {}).get("dedicated_api_keys_json") or "{}"
    try:
        if dedicated_incoming and serialize_dedicated_json:
            dedicated_merged = merge_dedicated_keep(
                dedicated_incoming,
                channel_dedicated_keys(existing or {}),
            )
            dedicated_json = serialize_dedicated_json(dedicated_merged)
    except Exception:
        pass

    # Soft-validate: allow save but mark inactive if under min (dedicated readiness)
    under = []
    try:
        from pipeline.dedicated_api_registry import evaluate_dedicated_readiness

        soft = evaluate_dedicated_readiness(
            channel={**(existing or {}), "dedicated_api_keys_json": dedicated_json, "languages_json": (existing or {}).get("languages_json")},
        )
        under = list(soft.get("missing") or [])
    except Exception:
        for pid, label, required in PROVIDER_DEFS:
            if required and len(slots.get(pid) or []) < min_for_provider(pid, required=True):
                need = min_for_provider(pid, required=True)
                under.append(f"{label} ({len(slots.get(pid) or [])}/{need})")

    # Niche locked after first setup
    session = store.get_session() or {}
    remote_unlocked = [
        str(c).strip().lower()
        for c in ((session.get("customer") or {}).get("unlocked") or [])
        if str(c).strip()
    ]
    if existing:
        niche = existing.get("niche") or niche
        nid_int = existing.get("niche_id") if existing.get("niche_id") is not None else nid_int
        languages_json = existing.get("languages_json") or serialize_languages(["en"])
    else:
        try:
            from pipeline.lang_entitlement import parse_languages

            if len(remote_unlocked) >= 2:
                if secondary_lang:
                    try:
                        base = setup_languages(secondary_lang)
                    except ValueError:
                        base = parse_languages(remote_unlocked)
                    extra = [c for c in remote_unlocked if c not in base]
                    languages_json = serialize_languages(list(base) + extra)
                else:
                    languages_json = serialize_languages(remote_unlocked)
            else:
                languages_json = serialize_languages(setup_languages(secondary_lang))
        except ValueError:
            return {
                "ok": False,
                "error": "secondary_lang_required",
                "hint": "ইংরেজি ডিফল্ট — আরও একটি ভাষা সিলেক্ট করুন (মোট ২টি)",
            }

    from pipeline.lang_destinations import merge_destination_form, serialize_lang_destinations
    from pipeline.lang_entitlement import channel_languages as _ch_langs

    lang_list = _ch_langs({"languages_json": languages_json})
    dest_map = merge_destination_form(
        (existing or {}).get("lang_destinations_json"),
        lang_list,
        lambda k: form.get(k),
    )
    # Seed English destination from top-level names if empty
    en_slot = dest_map.get("en") or {}
    if youtube_name and not en_slot.get("youtube_name"):
        en_slot["youtube_name"] = youtube_name
    if facebook_name and not en_slot.get("facebook_name"):
        en_slot["facebook_name"] = facebook_name
    if tiktok_name and not en_slot.get("tiktok_name"):
        en_slot["tiktok_name"] = tiktok_name
    if en_slot:
        dest_map["en"] = {
            "youtube_name": en_slot.get("youtube_name") or "",
            "facebook_name": en_slot.get("facebook_name") or "",
            "tiktok_name": en_slot.get("tiktok_name") or "",
            "youtube_session": en_slot.get("youtube_session") or (existing or {}).get("youtube_session") or "",
            "facebook_session": en_slot.get("facebook_session") or (existing or {}).get("facebook_session") or "",
            "tiktok_session": en_slot.get("tiktok_session") or (existing or {}).get("tiktok_session") or "",
        }

    payload = {
        "youtube_name": youtube_name or (existing or {}).get("youtube_name"),
        "facebook_name": facebook_name or (existing or {}).get("facebook_name"),
        "tiktok_name": tiktok_name or (existing or {}).get("tiktok_name"),
        "niche": niche,
        "niche_id": nid_int,
        "video_special": video_special if video_special != "" else (existing or {}).get("video_special"),
        "long_upload_time": long_upload_time or (existing or {}).get("long_upload_time") or "18:00",
        "short_upload_time": short_upload_time or (existing or {}).get("short_upload_time") or "12:00",
        "example_script": example_script if example_script != "" else (existing or {}).get("example_script"),
        "generation_special": generation_special if generation_special != "" else (existing or {}).get("generation_special"),
        "title_desc_special": title_desc_special if title_desc_special != "" else (existing or {}).get("title_desc_special"),
        "logo_path": logo_path or (existing or {}).get("logo_path"),
        "intro_path": intro_path or (existing or {}).get("intro_path"),
        "api_keys_json": serialize_api_keys_json(slots),
        "dedicated_api_keys_json": dedicated_json,
        "google_api_1": legacy["google_api_1"] or (existing or {}).get("google_api_1"),
        "google_api_2": legacy["google_api_2"] or (existing or {}).get("google_api_2"),
        "agnes_api": legacy["agnes_api"] or (existing or {}).get("agnes_api"),
        "pexels_api": legacy["pexels_api"] or (existing or {}).get("pexels_api"),
        "pollinations_api": legacy["pollinations_api"] or (existing or {}).get("pollinations_api"),
        "languages_json": languages_json,
        "lang_destinations_json": serialize_lang_destinations(dest_map),
        "youtube_session": (existing or {}).get("youtube_session"),
        "facebook_session": (existing or {}).get("facebook_session"),
        "tiktok_session": (existing or {}).get("tiktok_session"),
        "reels_per_day": int(form.get("reels_per_day") or (existing or {}).get("reels_per_day") or 2),
        "reel_schedule_times": str(form.get("reel_schedule_times") or (existing or {}).get("reel_schedule_times") or '["11:00", "16:00", "20:30"]').strip(),
        "reel_topics": str(form.get("reel_topics") or (existing or {}).get("reel_topics") or "").strip(),
        "reel_strategy_json": str(form.get("reel_strategy_json") or (existing or {}).get("reel_strategy_json") or "{}").strip(),
        "enabled": 1,
    }
    payload = set_channel_owner_on_payload(payload, login_id)
    # Auto-fill niche name + empty specials from Nish.Md (user text wins if provided)
    payload = apply_niche_to_channel(payload, overwrite_empty_only=True)
    if not (payload.get("niche") or "").strip():
        return {"ok": False, "error": "niche_required"}
    cid = store.upsert_channel(payload, cid_int)
    ready = evaluate_readiness(channel=store.get_channel(cid) or payload)
    from app.customer_config import to_safe_channel_view

    safe_ch = to_safe_channel_view(store.get_channel(cid) or payload)
    return {
        "ok": True,
        "channel_id": cid,
        "niche": payload.get("niche"),
        "niche_id": payload.get("niche_id"),
        "languages": json_loads_safe(payload.get("languages_json")),
        "app_active": ready["active"],
        "api_readiness": ready,
        "channel": safe_ch,
        "warning": (
            None
            if ready["active"]
            else "চ্যানেল সেভ হয়েছে কিন্তু অ্যাপ ইনঅ্যাকটিভ — প্রয়োজনীয় প্রোভাইডারে কমপক্ষে ২টি API দিন: "
            + ", ".join(under)
        ),
    }


def json_loads_safe(raw: Any) -> Any:
    import json as _json

    if isinstance(raw, (list, dict)):
        return raw
    try:
        return _json.loads(raw or "[]")
    except Exception:
        return []


@app.get("/api/reels/schedule")
def get_reels_schedule(channel_id: Optional[int] = None) -> Dict[str, Any]:
    """Exposes reel daily limits, schedule slots, and topic pool for a channel."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    channels = _owned_channels_or_empty()
    if not channels:
        channels = store.list_channels()
    if not channels:
        return {"ok": False, "error": "no_channels_found"}
    cid = int(channel_id) if channel_id else int(channels[0]["id"])
    settings_dict = store.get_channel_reel_settings(cid)

    from publishers.omni_reel_publisher import OmniReelPublisher
    pub = OmniReelPublisher(channel_id=cid)
    today_posts = pub.get_today_reels_published()
    can_pub, reason = pub.can_publish_reel_today()
    due_slot = pub.get_due_schedule_slot()

    return {
        "ok": True,
        "channel_id": cid,
        "settings": settings_dict,
        "status": {
            "published_today": len(today_posts),
            "limit": settings_dict.get("reels_per_day", 2),
            "can_publish_today": can_pub,
            "quota_reason": reason,
            "due_slot": due_slot,
            "today_posts": today_posts
        }
    }


@app.post("/api/reels/schedule")
def update_reels_schedule(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Updates daily limits, schedule slots, and topics for video reels."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    channels = _owned_channels_or_empty()
    if not channels:
        channels = store.list_channels()
    if not channels:
        return {"ok": False, "error": "no_channels_found"}
    cid = int(payload.get("channel_id") or channels[0]["id"])
    _ch, err = _owned_channel_or_err(cid)
    if err and err.get("error") != "channel_unowned":
        return err

    reels_per_day = payload.get("reels_per_day")
    schedule_slots = payload.get("schedule_slots")
    topics_pool = payload.get("topics_pool")
    strategy_json = payload.get("reel_strategy_json")

    success = store.update_channel_reel_settings(
        cid,
        reels_per_day=int(reels_per_day) if reels_per_day is not None else None,
        schedule_slots=schedule_slots if isinstance(schedule_slots, list) else None,
        topics_pool=topics_pool if isinstance(topics_pool, list) else None,
        strategy_json=str(strategy_json) if strategy_json else None
    )
    return {
        "ok": success,
        "channel_id": cid,
        "settings": store.get_channel_reel_settings(cid)
    }


@app.get("/api/config/summary")
def config_summary() -> Dict[str, Any]:
    """C04: customer-owned configuration readiness projection."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import CLASSIFICATION, configuration_summary

    return {"ok": True, "configuration": configuration_summary(_session_login_id()), "classification": CLASSIFICATION}


@app.post("/api/channels/{channel_id}/claim")
def claim_channel(channel_id: int) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import claim_orphan_channel, to_safe_channel_view

    res = claim_orphan_channel(int(channel_id), _session_login_id())
    if not res.get("ok"):
        return res
    ch = store.get_channel(int(channel_id))
    return {**res, "channel": to_safe_channel_view(ch) if ch else None}


@app.post("/api/channels/{channel_id}/activate")
def activate_channel(channel_id: int) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import set_channel_enabled, to_safe_channel_view

    res = set_channel_enabled(int(channel_id), _session_login_id(), True)
    if not res.get("ok"):
        return res
    ch = store.get_channel(int(channel_id))
    return {**res, "channel": to_safe_channel_view(ch) if ch else None}


@app.post("/api/channels/{channel_id}/deactivate")
def deactivate_channel(channel_id: int) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import set_channel_enabled, to_safe_channel_view

    res = set_channel_enabled(int(channel_id), _session_login_id(), False)
    if not res.get("ok"):
        return res
    ch = store.get_channel(int(channel_id))
    return {**res, "channel": to_safe_channel_view(ch) if ch else None}


@app.post("/api/channels/{channel_id}/languages")
def set_languages(channel_id: int, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import assert_no_forged_identity, set_channel_languages, to_safe_channel_view

    lid = _session_login_id()
    forged = assert_no_forged_identity(payload, lid)
    if forged:
        return {"ok": False, "error": forged}
    session = store.get_session() or {}
    remote_unlocked = [
        str(c).strip().lower()
        for c in ((session.get("customer") or {}).get("unlocked") or [])
        if str(c).strip()
    ]
    langs = payload.get("languages") or payload.get("lang_codes") or []
    if not isinstance(langs, list):
        return {"ok": False, "error": "languages_required"}
    res = set_channel_languages(
        int(channel_id),
        lid,
        langs,
        entitled_unlocked=remote_unlocked,
        allow_setup_pair=bool(payload.get("allow_setup_pair")),
    )
    if not res.get("ok"):
        return res
    ch = store.get_channel(int(channel_id))
    return {**res, "channel": to_safe_channel_view(ch) if ch else None}


@app.post("/api/channels/{channel_id}/providers")
async def save_channel_providers(channel_id: int, request: Request) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import save_owned_provider_slots
    from pipeline.channel_api_slots import collect_from_form

    form = await request.form()
    return save_owned_provider_slots(int(channel_id), _session_login_id(), collect_from_form(form))


@app.post("/api/channels/{channel_id}/providers/{provider_id}/clear")
def clear_channel_provider(channel_id: int, provider_id: str) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import clear_owned_provider

    return clear_owned_provider(int(channel_id), _session_login_id(), provider_id)


@app.get("/api/languages")
def languages_status() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.lang_entitlement import (
        DEFAULT_LANGUAGE_PRICE,
        MAX_LANGUAGES,
        catalog,
        channel_languages,
        secondary_options,
    )
    from pipeline.lang_config import SOURCE_LANG

    channels = _owned_channels_or_empty()
    ch = channels[0] if channels else None
    unlocked = channel_languages(ch) if ch else [SOURCE_LANG]
    pending = [
        r for r in store.list_language_requests(40)
        if r.get("status") == "pending"
    ]
    price = store.get_meta("language_addon_price", DEFAULT_LANGUAGE_PRICE)
    return {
        "ok": True,
        "max": MAX_LANGUAGES,
        "setup_count": 2,
        "price": price,
        "catalog": catalog(),
        "secondary_options": secondary_options(),
        "unlocked": unlocked,
        "unlocked_names": [
            next((c["name"] for c in catalog() if c["code"] == code), code)
            for code in unlocked
        ],
        "pending": pending,
        "available_to_buy": [
            c for c in secondary_options()
            if c["code"] not in unlocked
            and not any(p.get("lang_code") == c["code"] for p in pending)
        ],
        "channel_id": ch.get("id") if ch else None,
        "channel_setup_done": bool(ch),
    }


@app.post("/api/languages/request")
def language_request(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.lang_entitlement import (
        DEFAULT_LANGUAGE_PRICE,
        MAX_LANGUAGES,
        can_request,
        channel_languages,
        catalog,
    )

    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_required", "hint": "আগে চ্যানেল সেটআপ করুন"}
    ch = channels[0]
    unlocked = channel_languages(ch)

    raw_codes = payload.get("lang_codes")
    if raw_codes is None and payload.get("lang_code"):
        raw_codes = [payload.get("lang_code")]
    if not isinstance(raw_codes, list):
        raw_codes = []
    codes: list = []
    for c in raw_codes:
        code = str(c or "").strip().lower()
        if code and code not in codes:
            codes.append(code)
    if not codes:
        return {"ok": False, "error": "lang_required", "hint": "কমপক্ষে একটি ভাষা সিলেক্ট করুন"}

    if len(unlocked) + len(codes) > MAX_LANGUAGES:
        return {
            "ok": False,
            "error": "max_languages_reached",
            "hint": f"সর্বোচ্চ {MAX_LANGUAGES}টি ভাষা — আর {max(0, MAX_LANGUAGES - len(unlocked))}টি যোগ করা যাবে",
        }

    accepted = []
    for lang_code in codes:
        check = can_request(lang_code, unlocked + accepted)
        if not check.get("ok"):
            return {"ok": False, "error": check.get("error"), "lang_code": lang_code}
        if store.pending_language_for(lang_code):
            return {"ok": False, "error": "already_pending", "lang_code": lang_code}
        accepted.append(lang_code)

    unit = float(store.get_meta("language_addon_price", DEFAULT_LANGUAGE_PRICE) or DEFAULT_LANGUAGE_PRICE)
    try:
        unit = float(payload.get("unit_price") or unit)
    except (TypeError, ValueError):
        unit = float(DEFAULT_LANGUAGE_PRICE)
    total_amount = unit * len(accepted)
    payment_ref = str(payload.get("payment_ref") or "").strip()
    payment_note = str(payload.get("payment_note") or "").strip()
    if not payment_ref and not payment_note:
        return {"ok": False, "error": "payment_info_required", "hint": "পেমেন্ট রেফারেন্স বা নোট দিন"}

    remote_ids: list = []
    session = store.get_session() or {}
    api_base = (session.get("api_base_url") or "").rstrip("/")
    token = session.get("token") or ""
    if api_base and api_base.lower() not in {"local", "localhost", "offline", ""} and token:
        try:
            data = LicenseClient(api_base, token).language_request(
                {
                    "lang_codes": accepted,
                    "unit_price": unit,
                    "amount": total_amount,
                    "payment_ref": payment_ref,
                    "payment_note": payment_note,
                }
            )
            if data.get("ok"):
                remote_ids = list(data.get("order_ids") or [])
                if data.get("order_id") and not remote_ids:
                    remote_ids = [int(data["order_id"])]
        except Exception:
            remote_ids = []

    created = []
    for i, lang_code in enumerate(accepted):
        rid = remote_ids[i] if i < len(remote_ids) else None
        req_id = store.add_language_request(
            {
                "channel_id": ch.get("id"),
                "lang_code": lang_code,
                "amount": str(unit),
                "payment_ref": payment_ref,
                "payment_note": payment_note,
                "status": "pending",
                "remote_id": rid,
            }
        )
        name = next((c["name"] for c in catalog() if c["code"] == lang_code), lang_code)
        created.append({"request_id": req_id, "lang_code": lang_code, "lang_name": name, "amount": unit})

    names = ", ".join(x["lang_name"] for x in created)
    return {
        "ok": True,
        "requests": created,
        "count": len(created),
        "unit_price": unit,
        "total_amount": total_amount,
        "status": "pending",
        "message": (
            f"{len(created)}টি ভাষা ({names}) আবেদন জমা — মোট {total_amount:g} BDT "
            f"({unit:g}×{len(created)}) · অ্যাডমিন অ্যাপ্রুভালের অপেক্ষা করুন"
        ),
    }


@app.post("/api/languages/sync")
def language_sync() -> Dict[str, Any]:
    """Pull approved language unlocks from website (and apply locally)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.lang_entitlement import channel_languages, serialize_languages, unlock_language

    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_required"}
    ch = channels[0]
    unlocked = channel_languages(ch)
    session = store.get_session() or {}
    api_base = (session.get("api_base_url") or "").rstrip("/")
    token = session.get("token") or ""
    newly: list = []
    if api_base and api_base.lower() not in {"local", "localhost", "offline", ""} and token:
        try:
            data = LicenseClient(api_base, token).language_status()
            remote_unlocked = list(data.get("unlocked") or []) if data.get("ok") else []
            for code in remote_unlocked:
                if code not in unlocked:
                    try:
                        unlocked = unlock_language(unlocked, code)
                        newly.append(code)
                    except ValueError:
                        pass
            # Mark matching pending local requests approved
            for req in store.list_language_requests(50):
                if req.get("status") == "pending" and req.get("lang_code") in remote_unlocked:
                    store.update_language_request(
                        int(req["id"]),
                        status="approved",
                        approved_at=__import__("datetime").datetime.now().isoformat(),
                    )
        except Exception as exc:
            return {"ok": False, "error": f"sync_failed:{exc}"}

    if newly:
        ch["languages_json"] = serialize_languages(unlocked)
        store.upsert_channel(ch, int(ch["id"]))
    return {"ok": True, "unlocked": unlocked, "newly": newly}


@app.post("/api/languages/local-approve")
def language_local_approve(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Local/dev approve pending language request (AMP_ALLOW_LOCAL_LOGIN only)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from datetime import datetime

    from app.config import api_base_allows_local_login, settings as app_settings
    from pipeline.lang_entitlement import channel_languages, serialize_languages, unlock_language

    if not bool(app_settings.amp_allow_local_login):
        return {"ok": False, "error": "forbidden"}
    session = store.get_session() or {}
    base = session.get("api_base_url") or ""
    if not api_base_allows_local_login(base):
        return {"ok": False, "error": "local_only"}

    req_id = int(payload.get("request_id") or 0)
    req = store.get_language_request(req_id)
    if not req or req.get("status") != "pending":
        return {"ok": False, "error": "not_found"}
    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_required"}
    ch = channels[0]
    try:
        unlocked = unlock_language(channel_languages(ch), str(req["lang_code"]))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    ch["languages_json"] = serialize_languages(unlocked)
    store.upsert_channel(ch, int(ch["id"]))
    store.update_language_request(req_id, status="approved", approved_at=datetime.now().isoformat())
    return {"ok": True, "unlocked": unlocked, "lang_code": req["lang_code"]}


@app.post("/api/channels/{channel_id}/youtube-login")
def youtube_login(channel_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Start Chromium login in background; poll /api/auth-login/status."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import require_owned_channel

    channel, err = require_owned_channel(int(channel_id), _session_login_id())
    if err:
        return err
    from publishers.browser_auth import start_login

    lang_code = str((payload or {}).get("lang_code") or "")
    return start_login(channel_id, "youtube", lang_code=lang_code)


@app.post("/api/channels/{channel_id}/facebook-login")
def facebook_login(channel_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import require_owned_channel

    channel, err = require_owned_channel(int(channel_id), _session_login_id())
    if err:
        return err
    from publishers.browser_auth import start_login

    lang_code = str((payload or {}).get("lang_code") or "")
    return start_login(channel_id, "facebook", lang_code=lang_code)


@app.post("/api/channels/{channel_id}/tiktok-login")
def tiktok_login(channel_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import require_owned_channel

    channel, err = require_owned_channel(int(channel_id), _session_login_id())
    if err:
        return err
    from publishers.browser_auth import start_login

    lang_code = str((payload or {}).get("lang_code") or "")
    return start_login(channel_id, "tiktok", lang_code=lang_code)


@app.get("/api/auth-login/status")
def auth_login_status(job_id: str = "") -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.browser_auth import get_login_status

    if not job_id:
        return {"ok": False, "error": "job_id_required"}
    return get_login_status(job_id)


@app.get("/api/sessions")
def sessions_list(channel_id: int = 0) -> Dict[str, Any]:
    """WhatsApp-like linked session statuses (cookie vault)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.session_vault import list_sessions, session_status
    from publishers.stealth_session import engine_status

    if channel_id:
        ch = store.get_channel(channel_id)
        if not ch:
            return {"ok": False, "error": "not_found"}
        langs = []
        try:
            from pipeline.lang_entitlement import parse_languages

            langs = parse_languages(ch.get("languages_json")) or ["en"]
        except Exception:
            langs = ["en"]
        items = []
        for code in langs:
            items.append(session_status("youtube", channel_id, code))
            items.append(session_status("facebook", channel_id, code))
            items.append(session_status("tiktok", channel_id, code))
        return {"ok": True, "sessions": items, "engines": engine_status()}
    return {"ok": True, "sessions": list_sessions(), "engines": engine_status()}


@app.post("/api/channels/{channel_id}/session-health")
def session_health(channel_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import require_owned_channel

    channel, err = require_owned_channel(int(channel_id), _session_login_id())
    if err:
        return err
    from publishers.session_vault import health_check, paths_for_channel

    platform = "facebook" if str((payload or {}).get("platform") or "") == "facebook" else "youtube"
    lang_code = str((payload or {}).get("lang_code") or "en")
    paths = paths_for_channel(platform, channel, lang_code=lang_code)
    return health_check(
        platform,
        channel_id,
        lang_code,
        legacy_storage=paths.get("storage_state") or "",
    )


@app.post("/api/channels/{channel_id}/session-disconnect")
def session_disconnect(channel_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_config import require_owned_channel

    _, err = require_owned_channel(int(channel_id), _session_login_id())
    if err:
        return err
    from publishers.session_vault import disconnect_session

    platform = "facebook" if str((payload or {}).get("platform") or "") == "facebook" else "youtube"
    lang_code = str((payload or {}).get("lang_code") or "en")
    return {"ok": True, "session": disconnect_session(platform, channel_id, lang_code)}


@app.get("/api/captcha-status")
def captcha_status_api() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.human_browser import captcha_status
    from publishers.stealth_session import engine_status

    st = captcha_status()
    return {"ok": True, "captcha": st, "engines": engine_status()}


@app.post("/api/captcha-open")
def captcha_open_api(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Open the CAPTCHA / challenge URL in the system browser."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.captcha_solver import open_captcha_page

    url = str((payload or {}).get("url") or "")
    return open_captcha_page(url)


@app.post("/api/captcha-unlock")
def captcha_unlock_api(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Admin unlock after solving CAPTCHA (or after auto/DOM clear)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.human_browser import captcha_unlock

    note = str((payload or {}).get("note") or "")
    st = captcha_unlock(note=note)
    # Also clear E2E challenge pause so WorkflowTaskRunner can resume
    try:
        from app import db as store

        store.set_meta("e2e_challenge_resume", "1")
        store.set_meta("e2e_challenge_paused", "0")
    except Exception:
        pass
    return {"ok": True, "captcha": st}


@app.get("/api/bootstrap/status")
def bootstrap_status_api() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.bootstrap_runtime import status

    return status()


@app.post("/api/bootstrap/run")
def bootstrap_run_api(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Re-run customer tool bootstrap (Playwright/Camoufox/FFmpeg/edge-tts)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    import threading

    from app.bootstrap_runtime import ensure_all, status

    force = bool((payload or {}).get("force"))
    st = status()
    if st.get("running"):
        return {"ok": True, "already_running": True, "status": st}

    def _job() -> None:
        ensure_all(force=force)

    threading.Thread(target=_job, name="amp-bootstrap-api", daemon=True).start()
    return {"ok": True, "started": True, "force": force}


@app.get("/api/e2e-ui/status")
def e2e_ui_status() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app import db as store

    return {
        "ok": True,
        "paused": (store.get_meta("e2e_challenge_paused", "") or "") in ("1", "true", "yes"),
        "url": store.get_meta("e2e_challenge_url", "") or "",
        "screenshot": store.get_meta("e2e_challenge_screenshot", "") or "",
        "at": store.get_meta("e2e_challenge_at", "") or "",
        "last_summary": store.get_meta("e2e_ui_last_summary", "") or "",
    }


@app.post("/api/e2e-ui/resume")
def e2e_ui_resume() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app import db as store

    store.set_meta("e2e_challenge_resume", "1")
    store.set_meta("e2e_challenge_paused", "0")
    return {"ok": True, "resumed": True}


@app.post("/api/e2e-ui/run")
def e2e_ui_run(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """
    Launch E2E UI automation (Camoufox/Playwright) in a background thread.
    Body: platform, query, url, tasks, subscribe, like, comment, watch_seconds, headless
    """
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    import json
    import threading

    from app import db as store

    body = payload or {}
    if (store.get_meta("e2e_ui_running", "") or "") in ("1", "true", "yes"):
        return {"ok": False, "error": "e2e_already_running"}

    def _job() -> None:
        store.set_meta("e2e_ui_running", "1")
        try:
            from pipeline.e2e_ui.runner import run_e2e_session

            tasks_raw = body.get("tasks") or ["a", "b", "c"]
            if isinstance(tasks_raw, str):
                tasks = [t.strip() for t in tasks_raw.split(",") if t.strip()]
            else:
                tasks = list(tasks_raw)
            summary = run_e2e_session(
                platform=str(body.get("platform") or "youtube"),
                start_url=str(body.get("url") or ""),
                query=str(body.get("query") or ""),
                subscribe=bool(body.get("subscribe")),
                like=bool(body.get("like")),
                comment=str(body.get("comment") or ""),
                watch_seconds=float(body.get("watch_seconds") or 20),
                headless=bool(body.get("headless")) if "headless" in body else None,
                user_data_dir=str(body.get("profile") or ""),
                tasks=tasks,
            )
            store.set_meta("e2e_ui_last_summary", json.dumps(summary, ensure_ascii=False)[:8000])
        except Exception as exc:
            store.set_meta("e2e_ui_last_summary", json.dumps({"ok": False, "error": str(exc)[:500]}))
        finally:
            store.set_meta("e2e_ui_running", "0")

    threading.Thread(target=_job, name="e2e-ui-run", daemon=True).start()
    return {"ok": True, "started": True}


@app.get("/api/automation-mode")
def automation_mode_get() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.hybrid_mode import mode_status

    return mode_status()


@app.post("/api/automation-mode")
def automation_mode_set(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.hybrid_mode import mode_status, set_automation_mode

    mode = str((payload or {}).get("mode") or "hybrid")
    set_automation_mode(mode)
    return mode_status()


@app.get("/api/drive-accounts")
def drive_accounts_list() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.google_drive_rotation import list_drive_accounts, pick_active_account

    accounts = list_drive_accounts()
    active = pick_active_account()
    return {
        "ok": True,
        "accounts": accounts,
        "active_email": (active or {}).get("email") or "",
        "threshold_gb": 14,
        "hint": "See website /guide.html#google-storage for setup.",
    }


@app.post("/api/drive-accounts")
def drive_accounts_add(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.google_drive_rotation import upsert_drive_account

    p = payload or {}
    try:
        return upsert_drive_account(
            email=str(p.get("email") or ""),
            credentials_json=str(p.get("credentials_json") or p.get("credentials") or ""),
            label=str(p.get("label") or ""),
            folder_id=str(p.get("folder_id") or ""),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@app.post("/api/drive-accounts/{account_id}/refresh")
def drive_accounts_refresh(account_id: int) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.google_drive_rotation import refresh_account_usage

    return refresh_account_usage(account_id)


@app.post("/api/assets/local-sync")
def assets_local_sync() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.asset_archive import try_local_server_sync

    return try_local_server_sync()


@app.post("/api/agent/collect-api")
def agent_collect_api(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Guided browser collection of provider API keys (non-tech Mode B)."""
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.api_collector import start_collect

    provider = str((payload or {}).get("provider") or "missing").strip().lower()
    channel_id = int((payload or {}).get("channel_id") or 0)
    if not channel_id:
        chs = _owned_channels_or_empty()
        channel_id = int(chs[0]["id"]) if chs else 0
    timeout = int((payload or {}).get("timeout_sec") or 300)
    return start_collect(provider, channel_id=channel_id, timeout_sec=timeout)


@app.get("/api/agent/collect-api/status")
def agent_collect_api_status(job_id: str = "") -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.api_collector import get_job

    if not job_id:
        return {"ok": False, "error": "job_id_required"}
    return get_job(job_id)


@app.get("/api/jobs")
def jobs() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_job import list_customer_jobs
    from pipeline.live_activity import snapshot

    live = snapshot()
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    return {"ok": True, "jobs": list_customer_jobs(100, live=live, channel_ids=owned_ids)}


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_job import get_job, job_owned_by_channels, to_customer_view
    from pipeline.live_activity import snapshot

    row = get_job(int(job_id))
    if not row:
        return {"ok": False, "error": "job_not_found"}
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    if not job_owned_by_channels(row, owned_ids):
        return {"ok": False, "error": "job_access_denied", "error_code": "ownership_violation"}
    return {"ok": True, "job": to_customer_view(row, live=snapshot())}


@app.get("/api/error-notes")
def error_notes(status: str = "open", subsystem: str = "") -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.error_notebook import summarize_open_notes

    if status == "open" and not subsystem:
        return summarize_open_notes(80)
    rows = store.list_error_notes(status=status or "open", subsystem=subsystem or "", limit=80)
    return {"ok": True, "notes": rows, "count": len(rows)}


@app.post("/api/error-notes/{note_id}/resolve")
def error_note_resolve(note_id: int, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    store.resolve_error_note(note_id, owner_note=str((payload or {}).get("owner_note") or ""))
    return {"ok": True, "id": note_id}


@app.get("/api/activity")
def activity(since_seq: int = 0) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from app.customer_job import get_job, job_owned_by_channels, to_customer_view
    from pipeline.live_activity import snapshot

    snap = snapshot(since_seq=int(since_seq or 0))
    customer_job = None
    db_jid = snap.get("db_job_id")
    owned_ids = [int(c["id"]) for c in _owned_channels_or_empty() if c.get("id") is not None]
    if db_jid:
        row = get_job(int(db_jid))
        if row and job_owned_by_channels(row, owned_ids):
            customer_job = to_customer_view(row, live=snap)
    return {"ok": True, "activity": snap, "customer_job": customer_job}


@app.post("/api/activity/stop")
def activity_stop() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_activity import request_stop, snapshot

    request_stop()
    return {"ok": True, "activity": snapshot()}


@app.post("/api/agent-chat")
def agent_chat(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.agent_chat import agent_chat_reply
    from pipeline.live_activity import snapshot

    act = snapshot()
    hint = ""
    if act.get("active") or act.get("phase") not in ("", "idle", None):
        hint = (
            f"active={act.get('active')} kind={act.get('kind')} phase={act.get('phase')} "
            f"scene={act.get('scene')}/{act.get('scene_total')} detail={act.get('detail')} "
            f"apis={[a.get('provider') for a in (act.get('apis') or [])[-5:]]}"
        )
    ui_lang = str(payload.get("ui_lang") or "bn")
    image_b64 = str(payload.get("image_base64") or "")
    image_mime = str(payload.get("image_mime") or "image/png")
    user_msg = str(payload.get("message") or "")
    result = agent_chat_reply(
        user_msg,
        history=list(payload.get("history") or []),
        activity_hint=hint,
        ui_lang=ui_lang,
        image_base64=image_b64,
        image_mime=image_mime,
    )
    if result.get("apply_keys"):
        applied = _apply_api_keys_dict(result["apply_keys"])
        result["keys_applied"] = applied
    if result.get("escalate"):
        esc = _escalate_agent_issue(
            message="[redacted]" if result.get("redact_user") else user_msg,
            reason=str(result.get("escalate_reason") or "unsolved"),
            screenshot_note=str(result.get("screenshot_caption") or ""),
            activity_hint=hint,
        )
        result["escalation"] = esc
    return result


def _apply_api_keys_dict(incoming: Dict[str, Any]) -> Dict[str, Any]:
    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_required"}
    ch = channels[0]
    from pipeline.channel_api_slots import (
        channel_provider_keys,
        evaluate_readiness,
        merge_keep_existing,
        serialize_api_keys_json,
        sync_legacy_fields,
    )

    existing = channel_provider_keys(ch)
    slots = merge_keep_existing(incoming or {}, existing)
    legacy = sync_legacy_fields(slots)
    ch["api_keys_json"] = serialize_api_keys_json(slots)
    ch["google_api_1"] = legacy["google_api_1"] or ch.get("google_api_1")
    ch["google_api_2"] = legacy["google_api_2"] or ch.get("google_api_2")
    ch["agnes_api"] = legacy["agnes_api"] or ch.get("agnes_api")
    ch["pexels_api"] = legacy["pexels_api"] or ch.get("pexels_api")
    ch["pollinations_api"] = legacy["pollinations_api"] or ch.get("pollinations_api")
    store.upsert_channel(ch, int(ch["id"]))
    ready = evaluate_readiness(channel=store.get_channel(int(ch["id"])) or ch)
    return {
        "ok": True,
        "counts": {k: len(v or []) for k, v in slots.items() if v},
        "app_active": ready.get("active"),
        "message_key": ready.get("message_key"),
    }


@app.post("/api/settings/api-keys")
async def save_api_keys(request: Request) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_required", "hint": "আগে চ্যানেল সেটআপ করুন"}
    form = await request.form()
    from app.customer_config import save_owned_provider_slots
    from pipeline.channel_api_slots import collect_from_form
    from pipeline.dedicated_api_registry import collect_dedicated_from_form

    ch = channels[0]
    merged = {}
    merged.update(collect_from_form(form))
    merged.update(collect_dedicated_from_form(form))
    return save_owned_provider_slots(int(ch["id"]), _session_login_id(), merged)


@app.get("/api/posts")
def posts(lang: str = "") -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    rows = store.list_posts(100, lang_code=(lang or "").strip())
    return {"ok": True, "posts": rows}


@app.post("/api/posts/{post_id}/stats")
def post_stats(post_id: int, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    store.update_post_stats(
        post_id,
        views=int(payload.get("views") or 0),
        likes=int(payload.get("likes") or 0),
        comments=int(payload.get("comments") or 0),
        shares=int(payload.get("shares") or 0),
        reach=int(payload.get("reach") or 0),
    )
    return {"ok": True}


def _escalate_agent_issue(
    *,
    message: str,
    reason: str,
    screenshot_note: str = "",
    activity_hint: str = "",
) -> Dict[str, Any]:
    session = store.get_session() or {}
    customer = session.get("customer") or {}
    login_id = str(session.get("login_id") or customer.get("login_id") or "")
    remote_ok = False
    remote_id = None
    api_base = (session.get("api_base_url") or "").rstrip("/")
    token = session.get("token") or ""
    if api_base and api_base.lower() not in {"local", "localhost", "offline", ""} and token:
        try:
            data = LicenseClient(api_base, token).escalate(
                {
                    "message": message[:4000],
                    "reason": reason[:2000],
                    "screenshot_note": screenshot_note[:4000],
                    "activity_hint": activity_hint[:2000],
                    "needs_app_update": True,
                }
            )
            remote_ok = bool(data.get("ok"))
            remote_id = data.get("ticket_id")
        except Exception as exc:
            remote_ok = False
            remote_id = str(exc)[:120]
    local_id = store.save_agent_escalation(
        customer_login=login_id,
        message=message,
        reason=reason,
        screenshot_note=screenshot_note,
        activity_hint=activity_hint,
        remote_ok=remote_ok,
    )
    return {"ok": True, "local_id": local_id, "remote_ok": remote_ok, "remote_id": remote_id}


@app.get("/api/live-lab")
def live_lab_status() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import status_payload

    return status_payload()


@app.post("/api/live-lab/names")
def live_lab_names(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import save_connect_names

    body = payload or {}
    return save_connect_names(
        youtube_name=str(body.get("youtube_name") or ""),
        facebook_name=str(body.get("facebook_name") or ""),
        tiktok_name=str(body.get("tiktok_name") or ""),
    )


@app.post("/api/live-lab/connect/{platform}")
def live_lab_connect(platform: str, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    platform = platform.lower()
    if platform not in ("facebook", "tiktok", "youtube"):
        platform = "youtube"
    channels = _owned_channels_or_empty()
    if not channels:
        return {"ok": False, "error": "channel_missing", "hint": "আগে Channel ট্যাবে নিশ সেটআপ করুন"}
    channel = channels[0]
    from publishers.browser_auth import start_login

    lang_code = str((payload or {}).get("lang_code") or "en")
    return start_login(int(channel["id"]), platform, lang_code=lang_code)


@app.post("/api/live-lab/live-publish")
def live_lab_live_publish(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import set_live_publish, status_payload

    enabled = True if payload is None else bool((payload or {}).get("enabled", True))
    set_live_publish(enabled)
    return status_payload()


@app.post("/api/live-lab/start")
def live_lab_start() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import start_cycle_background

    return start_cycle_background()


@app.post("/api/live-lab/comment-check")
def live_lab_comment_check() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import start_comment_check_background

    return start_comment_check_background()


@app.post("/api/live-lab/stop")
def live_lab_stop() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from pipeline.live_lab import stop_lab

    return stop_lab()


@app.post("/api/generate")
def generate(payload: Dict[str, Any] = Body(...)) -> Any:
    """C01-A: create persisted job → existing live worker → generate_video (no false success).

    C02: production requires auth ∧ account ∧ entitlement ∧ C01 readiness.
    Strict tier gating prevents ৳1,999 and ৳2,999 packages from leaking video studio.
    """
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    if not _require_session():
        from app.customer_auth import evaluate_session

        return {
            "ok": False,
            "error": "login_required",
            "error_class": "configuration_failure",
            "identity": evaluate_session(),
        }
    channel_id = int(payload.get("channel_id") or 0)
    video_type = "long" if payload.get("video_type") == "long" else "short"
    from app.customer_config import require_owned_channel

    channel, own_err = require_owned_channel(channel_id, _session_login_id())
    if own_err:
        return {**own_err, "error_class": "validation_failure"}
    if not channel:
        return {"ok": False, "error": "channel_not_found", "error_class": "validation_failure"}

    from app.config import validate_production_operational
    from app.customer_auth import can_customer_produce
    from app.customer_foundation import build_foundation_snapshot
    from app.customer_job import (
        create_generation_job,
        get_job,
        mark_failed,
        set_live_correlation,
        to_customer_view,
        update_customer_progress,
    )
    from pipeline.channel_api_slots import evaluate_readiness
    from pipeline.compose import probe_media_tool_capability
    from pipeline.live_activity import run_in_background, set_phase, note_api, is_cancel_requested, snapshot

    ready = evaluate_readiness(channel=channel)
    foundation = build_foundation_snapshot(
        app_started=True,
        media_cap=probe_media_tool_capability(),
        operational=validate_production_operational(),
        api_readiness=ready,
    )
    access = can_customer_produce(channel=channel, foundation=foundation)
    if not access.get("allowed"):
        if access.get("block_reason") == "tier_upgrade_required":
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "tier_upgrade_required",
                    "message": access.get("message"),
                    "required_tier": "video_studio",
                    "upgrade_url": "https://automoviepro.com/#pricing",
                },
            )
        return {
            "ok": False,
            "error": access.get("block_reason") or "production_access_denied",
            "error_class": "configuration_failure",
            "hint": access.get("message"),
            "message": access.get("message"),
            "message_key": access.get("message_key"),
            "identity": access.get("identity"),
            "foundation": foundation,
            "api_readiness": ready,
            "generate_block_reasons": access.get("generate_block_reasons")
            or foundation.get("generate_block_reasons"),
        }


@app.post("/api/generate/short")
def api_generate_short(payload: Dict[str, Any] = Body(default_factory=dict)) -> Any:
    """Enforces strict tier gating for short video generation."""
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    p = dict(payload or {})
    p["video_type"] = "short"
    if not p.get("channel_id"):
        channels = _owned_channels_or_empty()
        if channels:
            p["channel_id"] = channels[0]["id"]
    return generate(p)


@app.post("/api/generate/long")
def api_generate_long(payload: Dict[str, Any] = Body(default_factory=dict)) -> Any:
    """Enforces strict tier gating for long video generation."""
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    p = dict(payload or {})
    p["video_type"] = "long"
    if not p.get("channel_id"):
        channels = _owned_channels_or_empty()
        if channels:
            p["channel_id"] = channels[0]["id"]
    return generate(p)


@app.post("/api/job/start")
def api_job_start(payload: Dict[str, Any] = Body(default_factory=dict)) -> Any:
    """Enforces strict tier gating for starting video production jobs."""
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    p = dict(payload or {})
    if not p.get("channel_id"):
        channels = _owned_channels_or_empty()
        if channels:
            p["channel_id"] = channels[0]["id"]
    return generate(p)


@app.post("/api/jobs/create")
def api_jobs_create(payload: Dict[str, Any] = Body(default_factory=dict)) -> Any:
    """Enforces strict tier gating for creating video production jobs."""
    allowed, err_resp = _require_video_studio_access()
    if not allowed and err_resp is not None:
        return err_resp
    p = dict(payload or {})
    if not p.get("channel_id"):
        channels = _owned_channels_or_empty()
        if channels:
            p["channel_id"] = channels[0]["id"]
    return generate(p)

    # C06-D: when a production plan exists, it MUST be READY_FOR_GENERATION (fail closed).
    # Legacy path (no plan yet) remains for pre-C06-D compatibility; workspace UI requires plan.
    from app.customer_generation_orchestrator import admit_generation, start_customer_generation
    from app.customer_production_plan import load_production_plan

    login_id = _session_login_id()
    existing_plan = load_production_plan(login_id, channel_id)
    use_mock = bool(payload.get("use_mock"))
    if existing_plan is not None or use_mock or payload.get("require_production_plan"):
        admission = admit_generation(
            login_id,
            {**channel, "owner_login_id": channel.get("owner_login_id") or login_id},
            account_active=True,
            entitlement_active=True,
            capability_available=bool(ready.get("active")),
            foundation_allowed=True,
        )
        if not admission.get("ok"):
            return {
                "ok": False,
                "error": admission.get("error") or "plan_not_ready_for_generation",
                "error_code": admission.get("error_code") or "not_ready",
                "error_class": "validation_failure",
                "status": admission.get("status"),
                "blocks": admission.get("blocks"),
                "hint": "Build and ready a Production Plan before Generate",
            }
        if use_mock:
            # Deterministic C06-D execution boundary (paid APIs = 0)
            return start_customer_generation(
                login_id,
                {**channel, "owner_login_id": channel.get("owner_login_id") or login_id},
                video_type=video_type,
                use_mock=True,
                force_rebuild=bool(payload.get("force_rebuild")),
            )
        plan_snapshot = admission.get("snapshot")
        plan_fp = None
        try:
            from app.customer_generation_orchestrator import compute_generation_job_fingerprint

            plan_fp = compute_generation_job_fingerprint(
                plan_snapshot, admission["plan"], video_type=video_type
            )
        except Exception:
            plan_fp = plan_snapshot.get("production_plan_revision") if plan_snapshot else None
    else:
        plan_snapshot = None
        plan_fp = None

    live_now = snapshot()
    if live_now.get("active"):
        return {
            "ok": False,
            "error": "already_running",
            "error_class": "validation_failure",
            "hint": "A production job is already active — use Live panel to watch or stop it",
            "customer_job": (
                to_customer_view(get_job(int(live_now["db_job_id"])), live=live_now)
                if live_now.get("db_job_id") and get_job(int(live_now["db_job_id"]))
                else None
            ),
        }

    from app.generation_guard import try_acquire as generation_try_acquire
    from app.generation_guard import release as generation_release

    # C01-B: shared generation slot with idle pregen / timed fallback
    if not generation_try_acquire("customer"):
        return {
            "ok": False,
            "error": "generation_busy",
            "error_class": "validation_failure",
            "hint": "Another generation is in progress (idle pregen or live job). Try again shortly.",
        }

    session = store.get_session() or {}
    customer = session.get("customer") or {}
    requested_by = str(customer.get("login_id") or customer.get("name") or "customer")
    ch_name = channel.get("youtube_name") or channel.get("facebook_name") or channel.get("niche") or ""

    row = create_generation_job(
        channel_id=channel_id,
        video_type=video_type,
        requested_by=requested_by,
        title_hint=f"{video_type} generation (in progress)",
        production_plan_id=str((plan_snapshot or {}).get("production_plan_id") or ""),
        production_plan_revision=str((plan_snapshot or {}).get("production_plan_revision") or ""),
        script_revision=str((plan_snapshot or {}).get("script_revision") or ""),
        generation_fingerprint=str(plan_fp or ""),
        plan_snapshot=plan_snapshot,
    )
    db_job_id = int(row["id"])

    def _job():
        update_customer_progress(
            db_job_id,
            customer_state="STARTING",
            stage="STARTING",
            upload_status="preparing",
            detail=f"{video_type} video generation started — {ch_name}",
        )
        set_phase("generate", f"{video_type} video generation started — {ch_name}")
        note_api("pipeline", f"generate_{video_type}", "start")
        if is_cancel_requested():
            raise RuntimeError("cancelled_by_user")
        from pipeline.video_pipeline import generate_video

        result = generate_video(channel, video_type=video_type, existing_job_id=db_job_id)
        if is_cancel_requested():
            raise RuntimeError("cancelled_by_user")
        set_phase("upload_check", "Generation finished — validating readiness")
        note_api("pipeline", f"generate_{video_type}", "ok")
        return result

    try:
        live_id = run_in_background(
            _job,
            kind=video_type,
            channel_id=channel_id,
            channel_name=str(ch_name),
            db_job_id=db_job_id,
            generation_owner="customer",
        )
    except RuntimeError as exc:
        generation_release("customer")
        if str(exc) == "already_running":
            mark_failed(db_job_id, "already_running", recoverable=True)
            return {
                "ok": False,
                "error": "already_running",
                "error_class": "validation_failure",
                "hint": "লাইভ প্যানেল থেকে বন্ধ করুন",
                "job_id": db_job_id,
            }
        mark_failed(db_job_id, exc, recoverable=True)
        return {
            "ok": False,
            "error": "start_failed",
            "error_class": "infrastructure_failure",
            "hint": str(exc)[:200],
            "job_id": db_job_id,
        }
    except Exception as exc:
        generation_release("customer")
        mark_failed(db_job_id, exc, recoverable=True)
        return {
            "ok": False,
            "error": "start_failed",
            "error_class": "infrastructure_failure",
            "hint": str(exc)[:200],
            "job_id": db_job_id,
        }

    set_live_correlation(db_job_id, live_id)
    view = to_customer_view(get_job(db_job_id) or row, live=snapshot())
    return {
        "ok": True,
        "started": True,
        "job_id": db_job_id,
        "live_correlation_id": live_id,
        "video_type": video_type,
        "job": view,
        "message": "Job queued — watch Live / Jobs for actual stage (not complete yet)",
    }


@app.post("/api/run-hidden-once")
def run_hidden_once() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from hidden_engage.worker import run_daily_engagement

    summary = run_daily_engagement()
    return {"ok": True, "summary": summary}


@app.get("/api/trust-browse/log")
def trust_browse_log(limit: int = 200) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from hidden_engage.activity_log import list_today
    from hidden_engage.schedule_plan import plan_summary
    from hidden_engage.trust_browse import is_running
    from publishers.browser_intel import list_recent_glitches

    return {
        "ok": True,
        "running": is_running(),
        "plan": plan_summary(),
        "events": list_today(limit=max(20, min(limit, 500))),
        "glitches": list_recent_glitches(limit=60),
    }


@app.get("/api/browser-glitches")
def browser_glitches(limit: int = 80) -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from publishers.browser_intel import list_recent_glitches

    rows = list_recent_glitches(limit=max(10, min(limit, 200)))
    return {"ok": True, "glitches": rows, "count": len(rows)}


@app.post("/api/trust-browse/run-once")
def trust_browse_run_once() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from hidden_engage.trust_browse import run_trust_session_now

    # Short manual sample so UI can verify without a long wait
    return run_trust_session_now(minutes=5)


@app.post("/api/trust-browse/sync")
def trust_browse_sync() -> Dict[str, Any]:
    if not _require_session():
        return {"ok": False, "error": "login_required"}
    from hidden_engage.activity_log import sync_unsynced_to_website

    return sync_unsynced_to_website()


# ==========================================
# Steps 11-19: SAAS ENHANCED API ENDPOINTS
# ==========================================

@app.post("/api/publisher/publish")
def api_publisher_publish(payload: Dict[str, Any]) -> Dict[str, Any]:
    from pipeline.social_publisher import MultiPlatformAutoPublisher
    pub = MultiPlatformAutoPublisher()
    return pub.publish_video(
        video_path=payload.get("video_path", ""),
        metadata=payload.get("metadata", {}),
        platforms=payload.get("platforms", ["youtube", "facebook", "tiktok"]),
        is_short=payload.get("is_short", True),
        age_restricted=payload.get("age_restricted", False),
        credentials=payload.get("credentials")
    )


@app.get("/api/publisher/history")
def api_publisher_history(limit: int = 50) -> Dict[str, Any]:
    from pipeline.social_publisher import MultiPlatformAutoPublisher
    pub = MultiPlatformAutoPublisher()
    return {"ok": True, "history": pub.get_publication_history(limit=limit)}


@app.post("/api/autoreply/process")
def api_autoreply_process(payload: Dict[str, Any]) -> Dict[str, Any]:
    from pipeline.auto_reply_agent import AutoReplyAgent
    agent = AutoReplyAgent()
    processed = agent.process_incoming_comments(
        platform=payload.get("platform", "youtube"),
        comments=payload.get("comments", []),
        channel_niche=payload.get("channel_niche", "general"),
        language=payload.get("language", "bn")
    )
    return {"ok": True, "processed": processed}


@app.get("/api/autoreply/logs")
def api_autoreply_logs(limit: int = 50) -> Dict[str, Any]:
    from pipeline.auto_reply_agent import AutoReplyAgent
    agent = AutoReplyAgent()
    return {"ok": True, "logs": agent.get_logs(limit=limit)}


@app.post("/api/human-browsing/session")
def api_human_browsing_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    from pipeline.human_browsing_engine import HumanBrowsingEngine
    engine = HumanBrowsingEngine()
    session = engine.simulate_watch_session(
        niche=payload.get("niche", "general"),
        forced_channel_type=payload.get("forced_channel_type"),
        mock_fast_mode=payload.get("fast_mode", False)
    )
    return {"ok": True, "session": session}


@app.get("/api/human-browsing/history")
def api_human_browsing_history(limit: int = 50) -> Dict[str, Any]:
    from pipeline.human_browsing_engine import HumanBrowsingEngine
    engine = HumanBrowsingEngine()
    return {"ok": True, "sessions": engine.get_recent_sessions(limit=limit)}


@app.get("/api/captcha/status/{captcha_id}")
def api_captcha_status(captcha_id: str) -> Dict[str, Any]:
    from pipeline.captcha_handler import CaptchaHandler
    handler = CaptchaHandler()
    status = handler.get_challenge_status(captcha_id)
    return {"ok": True, "status": status}


@app.post("/api/captcha/resolve")
def api_captcha_resolve(payload: Dict[str, Any]) -> Any:
    from pipeline.captcha_handler import CaptchaHandler
    handler = CaptchaHandler()
    cid = payload.get("captcha_id", "")
    solution = payload.get("solution", {})
    resolved = handler.resolve_from_mobile(cid, solution)
    if not resolved:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "INVALID_OR_REJECTED_SOLUTION", "message": "ক্যাপচা সমাধান বৈধ নয় বা বাতিল হয়েছে।"}
        )
    return {"ok": True}


@app.get("/api/announcements/list")
def api_announcements_list(language: str = "bn") -> Dict[str, Any]:
    from app.notification.scrolling_bar import ScrollingNotificationManager
    mgr = ScrollingNotificationManager()
    return {"ok": True, "announcements": mgr.get_announcements(language=language)}


@app.get("/api/voice/briefing")
def api_voice_briefing(user_name: str = "User", language: str = "bn") -> Dict[str, Any]:
    from app.voice.voice_commentary import FuturisticVoiceEngine
    engine = FuturisticVoiceEngine()
    return engine.get_startup_briefing(user_name=user_name, language=language)


@app.get("/api/voice/commentary")
def api_voice_commentary(stage: str, language: str = "bn") -> Dict[str, Any]:
    from app.voice.voice_commentary import FuturisticVoiceEngine
    engine = FuturisticVoiceEngine()
    return engine.get_pipeline_commentary(stage=stage, language=language)


@app.get("/api/voice/settings")
def api_voice_settings() -> Dict[str, Any]:
    from app.voice.voice_commentary import FuturisticVoiceEngine
    engine = FuturisticVoiceEngine()
    return {"ok": True, "settings": engine.get_preferences()}


@app.post("/api/voice/settings")
def api_voice_settings_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.voice.voice_commentary import FuturisticVoiceEngine
    engine = FuturisticVoiceEngine()
    is_muted = payload.get("is_muted")
    volume = payload.get("volume")
    updated = engine.update_settings(is_muted=is_muted, volume=volume)
    return {"ok": True, "settings": updated}


@app.get("/api/helper/tooltip")
def api_helper_tooltip(field_key: str, language: str = "bn") -> Dict[str, Any]:
    from app.agent.inapp_helper import InAppHelperAgent
    helper = InAppHelperAgent()
    return {"ok": True, "tooltip": helper.get_tooltip_info(field_key, language=language)}


@app.post("/api/helper/query")
def api_helper_query(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.agent.inapp_helper import InAppHelperAgent
    helper = InAppHelperAgent()
    query = payload.get("query", "")
    language = payload.get("language", "bn")
    return {"ok": True, "response": helper.handle_user_query(query, language=language)}


@app.post("/api/feedback/submit-ticket")
def api_feedback_ticket(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.feedback.feedback_system import FeedbackSystem
    sys = FeedbackSystem()
    return sys.submit_ticket(
        user_id=payload.get("user_id", "guest"),
        category=payload.get("category", "suggestion"),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        attachment_path=payload.get("attachment_path")
    )


@app.post("/api/feedback/submit-review")
def api_feedback_review(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.feedback.feedback_system import FeedbackSystem
    sys = FeedbackSystem()
    return sys.submit_review(
        user_id=payload.get("user_id", "guest"),
        user_name=payload.get("user_name", "Anonymous"),
        rating=payload.get("rating", 5),
        review_text=payload.get("review_text", "")
    )


@app.get("/api/legal/terms")
def api_legal_terms(language: str = "bn") -> Dict[str, Any]:
    from app.legal.consent_manager import ConsentManager
    cm = ConsentManager()
    return {"ok": True, "terms": cm.get_terms(language=language)}


@app.post("/api/legal/consent")
def api_legal_consent(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.legal.consent_manager import ConsentManager
    cm = ConsentManager()
    user_id = str(payload.get("user_id") or "").strip()
    if not user_id:
        from app.customer_auth import evaluate_session
        sess = evaluate_session()
        user_id = str(sess.get("login_id") or "admin")
    return cm.record_consent(
        user_id=user_id,
        hardware_id=payload.get("hardware_id"),
        ip_address=payload.get("ip_address")
    )


@app.get("/api/mobile/status")

def api_mobile_status() -> Dict[str, Any]:
    from app.mobile_bridge import bridge
    return bridge.get_live_metrics()


@app.get("/api/mobile/captcha")
def api_mobile_captcha() -> Dict[str, Any]:
    from app.mobile_bridge import bridge
    return bridge.get_pending_captcha()


@app.post("/api/mobile/captcha/solve")
def api_mobile_captcha_solve(payload: Dict[str, Any]) -> Any:
    from app.mobile_bridge import bridge
    res = bridge.resolve_captcha_remotely(
        captcha_id=payload.get("captcha_id", ""),
        coordinates=payload.get("coordinates", {})
    )
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/api/mobile/captcha/simulate")
def api_mobile_captcha_simulate(payload: Dict[str, Any]) -> Any:
    from app.config import is_production_runtime
    is_prod = is_production_runtime()
    allow_sim = os.getenv("AMP_ALLOW_CAPTCHA_SIMULATION", "false").lower() in ("true", "1")

    if is_prod and not allow_sim:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "SIMULATION_DISABLED_IN_PRODUCTION",
                "message": "নিরাপত্তা নীতি: প্রোডাকশন মোডে ক্যাপচা সিমুলেশন নিষিদ্ধ। এটি শুধুমাত্র Development ও Test মোডে অনুমোদিত।"
            }
        )

    from app.mobile_bridge import bridge
    sim_payload = dict(payload)
    # Real Mobile Telemetry Integration: bind genuine system telemetry to mobile push payload
    live_telemetry = bridge.get_live_metrics()
    sim_payload["telemetry"] = {
        "connected": live_telemetry.get("connected", True),
        "system_state": live_telemetry.get("system_state", "active"),
        "server_time": live_telemetry.get("server_time"),
        "videos_generated_today": live_telemetry.get("videos_generated_today", 0),
        "videos_published_today": live_telemetry.get("videos_published_today", 0),
        "last_video_title": live_telemetry.get("last_video_title", ""),
        "last_published_url": live_telemetry.get("last_published_url"),
    }
    sim_payload["is_simulation"] = True
    bridge.set_captcha_challenge(sim_payload)
    return {
        "ok": True,
        "simulated": True,
        "telemetry_synced": True,
        "telemetry": sim_payload["telemetry"],
        "message": "ক্যাপচা চ্যালেঞ্জ ও রিয়েল মোবাইল টেলিমেট্রি সফলভাবে ব্রডকাস্ট করা হয়েছে।"
    }


@app.post("/api/mobile/upload/resume")
def api_mobile_upload_resume(payload: Dict[str, Any] = Body(default={})) -> Any:
    from app.mobile_bridge import bridge
    return bridge.resume_upload(payload.get("captcha_id"))


@app.post("/api/admin/killswitch")
def api_admin_killswitch(payload: Dict[str, Any] = Body(default={})) -> Any:
    from app.customer_auth import clear_session
    clear_session()
    return {
        "ok": True,
        "action": "locked",
        "customer_id": payload.get("customer_id"),
        "message": "অ্যাডমিন কমান্ডে পিসি সফটওয়্যার তাৎক্ষণিকভাবে বন্ধ ও সেশন লক করা হয়েছে।"
    }

@app.post("/api/setup/google-pro-key")
def api_setup_google_pro_key(payload: Dict[str, Any] = Body(default={})) -> Any:
    """Save & validate Google AI Pro key for a specific language or globally."""
    lang = (payload.get("lang") or payload.get("language") or "en").strip().lower()
    key = (payload.get("google_pro_key") or payload.get("key") or "").strip()

    from app.setup.channel_setup import channel_manager
    from app.api_matrix.api_hub import get_api_hub

    channel_manager.set_google_pro_key(lang, key)
    hub = get_api_hub()
    hub.set_google_pro_key(lang, key)

    return {
        "ok": True,
        "language": lang,
        "configured": bool(key),
        "message": f"ভাষা '{lang}'-এর জন্য Google AI Pro Key সফলভাবে সংরক্ষিত ও কার্যকর করা হয়েছে।" if key else f"ভাষা '{lang}'-এর Google AI Pro Key অপসারিত হয়েছে।",
    }


@app.get("/api/setup/google-pro-key")
def api_get_google_pro_keys() -> Any:
    """Retrieve configured Google AI Pro keys (masked for safety)."""
    from app.setup.channel_setup import channel_manager
    from app.api_matrix.api_hub import get_api_hub

    hub = get_api_hub()
    profile = channel_manager.get_channel_profile()
    languages = profile.get("profiles_by_language") or profile.get("languages") or {}
    keys_map = {}
    for l_code, l_data in languages.items():
        k = l_data.get("google_pro_key", "")
        keys_map[l_code] = {
            "configured": bool(k),
            "masked": (k[:4] + "..." + k[-4:]) if len(k) > 10 else ("***" if k else ""),
        }
    return {
        "ok": True,
        "keys": keys_map,
        "global_pro_configured": bool(hub.config.google_pro_key),
    }


@app.post("/api/storage/drive-config")
def api_storage_drive_config(payload: Dict[str, Any] = Body(default={})) -> Any:
    """Configure Google Drive 150 GB Cloud Storage Vault."""
    from app.storage.google_drive_sync import get_vault_sync

    sync = get_vault_sync()
    auth_type = payload.get("auth_type", "service_account")
    credentials = payload.get("credentials", "")
    vault_folder_id = payload.get("vault_folder_id", "AutoMoviePro_Vault")
    target_email = payload.get("target_email", "")
    auto_sync = payload.get("auto_sync_enabled", True)

    cfg = sync.save_config(
        auth_type=auth_type,
        credentials=credentials,
        vault_folder_id=vault_folder_id,
        target_email=target_email,
        auto_sync_enabled=auto_sync,
    )
    return {
        "ok": True,
        "config": cfg,
        "message": "Google Drive 150 GB Vault কনফিগারেশন সফলভাবে সংরক্ষিত হয়েছে।",
    }


@app.post("/api/storage/connect")
def api_storage_connect(payload: Dict[str, Any] = Body(default={})) -> Any:
    """Connect Google Drive Vault (150 GB) with credentials/token."""
    from app.storage.google_drive_sync import get_vault_sync

    sync = get_vault_sync()
    creds = payload.get("credentials", "")
    email = payload.get("target_email", "")
    res = sync.connect_drive(credentials=creds, target_email=email)
    return res


@app.post("/api/storage/sync-now")
def api_storage_sync_now() -> Any:
    """Trigger immediate cloud synchronization for today's video production assets."""
    from app.storage.google_drive_sync import get_vault_sync

    sync = get_vault_sync()
    result = sync.sync_now()
    return {
        "ok": True,
        "sync_result": result,
        "message": "Google Drive Vault সিঙ্ক প্রক্রিয়া সফলভাবে সম্পন্ন হয়েছে।",
    }


@app.get("/api/storage/status")
def api_storage_status() -> Any:
    """Check Drive connection, 150 GB quota usage, and today's backup status."""
    from app.storage.google_drive_sync import get_vault_sync

    sync = get_vault_sync()
    return {
        "ok": True,
        "status": sync.get_status(),
    }


# ==============================================================================
# Auto-Reply System Endpoints (YouTube & Facebook)
# ==============================================================================

@app.get("/api/auto-reply/status")
def api_auto_reply_status() -> Any:
    """Returns whether auto-reply is enabled, last scan timestamp, and recent comments replied."""
    from publishers.comment_reply_agent import get_auto_reply_status

    return {
        "ok": True,
        **get_auto_reply_status(),
    }


@app.post("/api/auto-reply/toggle")
def api_auto_reply_toggle(payload: Dict[str, Any] = Body(default={})) -> Any:
    """Enable or disable the background auto-reply system."""
    from publishers.comment_reply_agent import (
        get_auto_reply_status,
        is_auto_reply_enabled,
        set_auto_reply_enabled,
    )

    enabled = payload.get("enabled")
    if enabled is None:
        enabled = not is_auto_reply_enabled()
    set_auto_reply_enabled(bool(enabled))
    return {
        "ok": True,
        "enabled": bool(enabled),
        "message": f"অটো-রিপ্লাই সিস্টেম সফলভাবে {'চালু' if enabled else 'বন্ধ'} করা হয়েছে।",
        **get_auto_reply_status(),
    }


@app.post("/api/auto-reply/trigger")
def api_auto_reply_trigger() -> Any:
    """Instantly triggers a comment & message scan across connected YouTube and Facebook channels."""
    from publishers.comment_reply_agent import get_auto_reply_status, run_comment_reply_pass

    res = run_comment_reply_pass(max_posts=5, max_replies_each=3)
    return {
        "ok": True,
        "result": res,
        "message": f"স্ক্যান সম্পন্ন: {res.get('handled', 0)} টি কন্টেন্টে স্বয়ংক্রিয় রিপ্লাই দেওয়া হয়েছে।",
        **get_auto_reply_status(),
    }


# ==============================================================================
# Video Performance Tracker & Growth Report Endpoints
# ==============================================================================

@app.get("/api/analytics/overview")
def api_analytics_overview() -> Any:
    """Returns aggregate video performance metrics (views, likes, comments)."""
    from pipeline.social_publisher import get_analytics_tracker

    tracker = get_analytics_tracker()
    return {
        "ok": True,
        "analytics": tracker.get_overview(),
    }


@app.get("/api/analytics/growth-advice")
def api_analytics_growth_advice(period: str = "daily") -> Any:
    """Local helping agent daily, weekly, and monthly growth recommendations."""
    from pipeline.social_publisher import get_analytics_tracker

    tracker = get_analytics_tracker()
    advice = tracker.generate_growth_advice(period=period)
    return {
        "ok": True,
        "advice": advice,
    }


@app.post("/api/analytics/refresh")
def api_analytics_refresh() -> Any:
    """Manually refresh live view and like counts for all uploaded videos."""
    from pipeline.social_publisher import get_analytics_tracker

    tracker = get_analytics_tracker()
    updated = tracker.refresh_metrics()
    return {
        "ok": True,
        "message": "ভিডিও পারফরম্যান্স ডাটা সফলভাবে রিফ্রেশ করা হয়েছে।",
        "analytics": updated,
    }


# ==============================================================================
# WhatsApp & Telegram Bulk Marketing Engine Endpoints
# ==============================================================================


@app.post("/api/marketing/import-contacts")
async def api_marketing_import_contacts(request: Request) -> Any:
    """Imports and deduplicates bulk numbers/contacts for WhatsApp or Telegram."""
    from marketing.bulk_marketing_engine import BulkMarketingEngine

    body = await request.json()
    contacts_raw = body.get("contacts", "")
    platform = body.get("platform", "whatsapp")
    niche = body.get("niche", "general")

    engine = BulkMarketingEngine()
    result = engine.import_bulk_numbers(contacts_raw=contacts_raw, platform=platform, niche=niche)
    return result


@app.post("/api/marketing/generate-copy")
async def api_marketing_generate_copy(request: Request) -> Any:
    """Grok-powered persuasive marketing copy generator for product/niche."""
    from marketing.bulk_marketing_engine import BulkMarketingEngine

    body = await request.json()
    niche = body.get("niche", "faceless_youtube")
    platform = body.get("platform", "whatsapp")
    discount = int(body.get("discount_pct", 20))
    language = body.get("language", "bn")

    engine = BulkMarketingEngine()
    copy_text = engine.generate_persuasive_copy(
        niche=niche,
        platform=platform,
        discount_pct=discount,
        language=language
    )
    return {
        "ok": True,
        "copy": copy_text,
        "niche": niche,
        "platform": platform,
        "discount_pct": discount,
    }


@app.post("/api/marketing/broadcast")
async def api_marketing_broadcast(request: Request) -> Any:
    """Dispatches broadcast campaign with anti-ban randomized time gaps."""
    from marketing.bulk_marketing_engine import BulkMarketingEngine

    body = await request.json()
    name = body.get("campaign_name", "Auto Campaign")
    template = body.get("template", "Hello {contact}")
    contacts = body.get("contacts", [])
    platform = body.get("platform", "whatsapp")
    is_live = bool(body.get("is_live", False))

    engine = BulkMarketingEngine()
    res = engine.run_broadcast_simulation(
        campaign_name=name,
        template=template,
        lead_contacts=contacts,
        platform=platform,
        is_live=is_live
    )
    return res


@app.get("/api/marketing/leads")
def api_marketing_leads(status: Optional[str] = None) -> Any:
    """Lists current leads in database."""
    from marketing.bulk_marketing_engine import BulkMarketingEngine

    engine = BulkMarketingEngine()
    leads = engine.get_leads(status=status)
    return {
        "ok": True,
        "leads": leads,
        "total": len(leads),
    }


# =============================================================================
# PRODUCT CATALOG & AD CAMPAIGN ENDPOINTS
# =============================================================================

@app.get("/api/products")
def api_list_products() -> Any:
    """Lists all products registered in the system."""
    from app.product_service import ProductService
    products = ProductService.list_products()
    return {"ok": True, "products": products, "total": len(products)}


@app.post("/api/products")
def api_create_product(payload: Dict[str, Any] = Body(...)) -> Any:
    """Creates a new product with full details."""
    from app.product_service import ProductService
    try:
        created = ProductService.create_product(payload)
        return {"ok": True, "product": created}
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.get("/api/products/ads")
def api_list_product_ads(product_id: Optional[str] = None) -> Any:
    """Lists all product ad campaigns."""
    from app.product_service import ProductService
    ads = ProductService.list_ad_campaigns(product_id=product_id)
    return {"ok": True, "ads": ads, "total": len(ads)}


@app.get("/api/products/{product_id}")
def api_get_product(product_id: str) -> Any:
    """Gets a single product by ID."""
    from app.product_service import ProductService
    product = ProductService.get_product(product_id)
    if not product:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Product not found"})
    return {"ok": True, "product": product}


@app.delete("/api/products/{product_id}")
def api_delete_product(product_id: str) -> Any:
    """Deletes a product by ID."""
    from app.product_service import ProductService
    deleted = ProductService.delete_product(product_id)
    return {"ok": deleted}


@app.post("/api/products/{product_id}/generate-ad")
def api_generate_product_ad(product_id: str, payload: Dict[str, Any] = Body(...)) -> Any:
    """Triggers generation of promotional storyboard, banner, and ad record."""
    session = _require_session()
    customer = session.get("customer") if session else {}
    plan = customer.get("tier") or customer.get("plan") or (session.get("plan") if session else None)
    from app.customer_tiers import can_access_fb_business, TIER_UPGRADE_MESSAGE_FB_BUSINESS
    if not can_access_fb_business(plan):
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "tier_upgrade_required",
                "message": TIER_UPGRADE_MESSAGE_FB_BUSINESS,
                "required_tier": "fb_business",
                "current_tier": str(plan),
                "upgrade_url": "https://automoviepro.com/#pricing",
            },
        )
    from app.product_service import ProductService
    ad_type = payload.get("ad_type", "reel_9_16")
    duration = int(payload.get("duration_seconds", 30))
    talking_points = payload.get("talking_points", "")
    scheduled_at = payload.get("scheduled_at")

    try:
        res = ProductService.create_ad_campaign(
            product_id=product_id,
            ad_type=ad_type,
            duration_seconds=duration,
            talking_points=talking_points,
            scheduled_at=scheduled_at
        )
        return {"ok": True, "campaign": res}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/api/videos/library")
def api_videos_library(folder: str = "all", limit: int = 80) -> Any:
    """Returns all rendered videos from OUTPUT_DIR with metadata and direct stream URLs."""
    from datetime import datetime
    videos = []
    if not OUTPUT_DIR.exists():
        return {"ok": True, "videos": [], "count": 0, "total_disk_mb": 0}

    for f in OUTPUT_DIR.rglob("*.mp4"):
        try:
            rel = f.relative_to(OUTPUT_DIR).as_posix()
            stat = f.stat()
            name_lower = f.name.lower()
            is_short = ("short" in name_lower or "reel" in name_lower or "9_16" in name_lower)
            folder_name = f.parent.name if f.parent != OUTPUT_DIR else "Root"

            if folder == "short" and not is_short:
                continue
            if folder == "long" and is_short:
                continue
            if folder not in ("all", "short", "long") and folder.lower() != folder_name.lower():
                continue

            videos.append({
                "filename": f.name,
                "relative_path": rel,
                "url": f"/output/{rel}",
                "folder": folder_name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "is_short": is_short,
                "type": "Shorts / Reel (9:16)" if is_short else "Long Video (16:9)",
            })
        except Exception:
            continue

    videos.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "ok": True,
        "videos": videos[:limit],
        "count": len(videos),
        "total_disk_mb": round(sum(v["size_mb"] for v in videos), 2)
    }


@app.post("/api/open-folder")
def api_open_folder(payload: Dict[str, Any] = Body(default_factory=dict)) -> Any:
    """Opens Windows explorer or file manager for the output folder."""
    import platform
    import subprocess
    import os

    target = OUTPUT_DIR
    sub = payload.get("folder") or payload.get("path")
    if sub:
        candidate = (OUTPUT_DIR / sub).resolve()
        if candidate.exists():
            target = candidate

    try:
        sys_name = platform.system()
        if sys_name == "Windows":
            os.startfile(str(target))
        elif sys_name == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True, "opened": str(target)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


def main() -> None:

    store.init_db()
    url = f"http://{settings.local_host}:{settings.local_port}/"
    webbrowser.open(url)
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.local_host,
        port=settings.local_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
