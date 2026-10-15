"""C02 — Customer authentication, account, entitlement & production access authority.

Single authority for:
  AUTHENTICATION / SESSION / ACCOUNT / ENTITLEMENT / ACCESS DECISION

Composes with (does not replace):
  - app.db session persistence
  - app.api_client.LicenseClient (remote license gateway)
  - app.config local_login_permitted (H2 fail-closed local login)
  - app.customer_foundation readiness (C01)
  - pipeline.lang_entitlement (language packs — separate commercial surface)

NOT a second job/scheduler/quality/readiness engine.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app import db as store
from app.config import local_login_permitted, settings

logger = logging.getLogger(__name__)

# Customer-facing authentication states
UNAUTHENTICATED = "UNAUTHENTICATED"
AUTHENTICATING = "AUTHENTICATING"
AUTHENTICATED = "AUTHENTICATED"
SESSION_EXPIRED = "SESSION_EXPIRED"
ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
AUTH_ERROR = "AUTH_ERROR"

# Account states
ACCOUNT_ACTIVE = "ACTIVE"
ACCOUNT_DISABLED_STATE = "DISABLED"
ACCOUNT_PENDING = "PENDING"
ACCOUNT_UNKNOWN = "UNKNOWN"

# Entitlement states
ENTITLEMENT_NONE = "NO_ENTITLEMENT"
ENTITLEMENT_ACTIVE = "ACTIVE"
ENTITLEMENT_EXPIRED = "EXPIRED"
ENTITLEMENT_SUSPENDED = "SUSPENDED"
ENTITLEMENT_UNKNOWN = "UNKNOWN"

IDENTITY_FIELDS = frozenset(
    {
        "auth_state",
        "account_state",
        "entitlement_state",
        "production_access",
        "production_allowed",
        "block_reason",
        "message_key",
        "message",
        "customer_id",
        "display_name",
        "login_id",
        "plan_label",
        "plan",
        "tier",
        "session_updated_at",
        "session_expires_at",
        "mode",
        "logged_in",
        "release_version",
    }
)

# Default session TTL (hours) when remote does not provide expiry
DEFAULT_SESSION_TTL_HOURS = 168  # 7 days


def _now() -> datetime:
    return datetime.now()


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None


def session_ttl_hours() -> int:
    raw = (getattr(settings, "amp_session_ttl_hours", None) or "").strip() if hasattr(settings, "amp_session_ttl_hours") else ""
    # Also read from env via settings extra — fallback constant
    import os

    env = (os.environ.get("AMP_SESSION_TTL_HOURS") or "").strip()
    try:
        v = int(env or raw or DEFAULT_SESSION_TTL_HOURS)
        return max(1, min(v, 24 * 90))
    except Exception:
        return DEFAULT_SESSION_TTL_HOURS


def ensure_session_columns() -> None:
    """Soft-migrate session table for C02 metadata."""
    with store.db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session (
                token TEXT PRIMARY KEY,
                customer_id TEXT,
                login_id TEXT,
                email TEXT,
                whatsapp TEXT,
                name TEXT,
                tier TEXT,
                plan TEXT,
                created_at TEXT
            )
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(session)").fetchall()}
        for name, typ in (
            ("expires_at", "TEXT"),
            ("account_state", "TEXT"),
            ("entitlement_state", "TEXT"),
            ("auth_mode", "TEXT"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE session ADD COLUMN {name} {typ}")


def sanitize_auth_error(message: str, limit: int = 180) -> str:
    s = " ".join(str(message or "").replace("\r", " ").split())
    s = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", s)
    s = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", s)
    s = re.sub(r"\bsk-[0-9A-Za-z]{8,}\b", "[redacted]", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def map_account_state(customer: Optional[Dict[str, Any]]) -> str:
    c = customer or {}
    raw = str(c.get("status") or c.get("account_status") or c.get("account_state") or "").strip().lower()
    if raw in {"active", "ok", "enabled", "approved"}:
        return ACCOUNT_ACTIVE
    if raw in {"disabled", "blocked", "banned", "inactive", "suspended_account"}:
        return ACCOUNT_DISABLED_STATE
    if raw in {"pending", "pending_approval", "awaiting"}:
        return ACCOUNT_PENDING
    if not raw and c:
        # Local / partial customer without status — UNKNOWN until proven
        if c.get("plan") == "dev" or c.get("mode") == "local_dev":
            return ACCOUNT_ACTIVE
        return ACCOUNT_UNKNOWN
    if not c:
        return ACCOUNT_UNKNOWN
    return ACCOUNT_UNKNOWN


def map_entitlement_state(customer: Optional[Dict[str, Any]], *, auth_mode: str = "") -> str:
    """Minimal entitlement abstraction (replaceable by future website billing)."""
    c = customer or {}
    raw = str(
        c.get("entitlement")
        or c.get("entitlement_status")
        or c.get("subscription_status")
        or c.get("plan_status")
        or ""
    ).strip().lower()
    if raw in {"active", "ok", "paid", "valid", "current"}:
        return ENTITLEMENT_ACTIVE
    if raw in {"expired", "lapsed", "ended"}:
        return ENTITLEMENT_EXPIRED
    if raw in {"suspended", "paused", "hold"}:
        return ENTITLEMENT_SUSPENDED
    if raw in {"none", "missing", "no", "inactive"}:
        return ENTITLEMENT_NONE

    plan = str(c.get("plan") or c.get("plan_name") or "").strip().lower()
    if auth_mode == "local_dev" or plan in {"dev", "local", "developer"}:
        return ENTITLEMENT_ACTIVE
    if plan in {"expired", "lapsed"}:
        return ENTITLEMENT_EXPIRED
    if plan in {"suspended"}:
        return ENTITLEMENT_SUSPENDED
    # Remote login with customer record but no plan/entitlement field → fail-closed unknown
    if auth_mode == "license" and c and not plan and not raw:
        # License login without explicit entitlement: treat ACTIVE if account active (legacy compat)
        # but mark as ACTIVE only when status is active — otherwise NO_ENTITLEMENT
        if map_account_state(c) == ACCOUNT_ACTIVE:
            return ENTITLEMENT_ACTIVE
        return ENTITLEMENT_NONE
    if not c:
        return ENTITLEMENT_UNKNOWN
    if plan:
        return ENTITLEMENT_ACTIVE
    return ENTITLEMENT_NONE


def compute_expires_at(session_updated_at: Optional[str], customer: Optional[Dict[str, Any]] = None) -> str:
    c = customer or {}
    explicit = c.get("session_expires_at") or c.get("expires_at") or c.get("token_expires_at")
    if explicit:
        return str(explicit)
    base = _parse_iso(session_updated_at) or _now()
    return (base + timedelta(hours=session_ttl_hours())).isoformat()


def is_session_expired(session: Optional[Dict[str, Any]]) -> bool:
    if not session:
        return True
    exp = session.get("expires_at")
    if not exp:
        exp = compute_expires_at(session.get("updated_at"), session.get("customer"))
    dt = _parse_iso(str(exp))
    if not dt:
        return False  # cannot parse — do not invent expiry; rely on other checks
    return _now() > dt


def customer_message(auth_state: str) -> Dict[str, str]:
    messages = {
        UNAUTHENTICATED: ("please_sign_in", "Please sign in to continue."),
        AUTHENTICATING: ("authenticating", "Signing in…"),
        AUTHENTICATED: ("signed_in", "Signed in."),
        SESSION_EXPIRED: ("session_expired", "Your session has expired. Please sign in again."),
        ACCOUNT_DISABLED: ("account_disabled", "This account is currently disabled."),
        ENTITLEMENT_REQUIRED: (
            "entitlement_required",
            "Production access is not currently available for this account.",
        ),
        AUTH_ERROR: (
            "auth_error",
            "We couldn't verify your account right now. Please try again.",
        ),
    }
    key, msg = messages.get(auth_state, ("auth_error", "We couldn't verify your account right now. Please try again."))
    return {"message_key": key, "message": msg}


def to_identity_projection(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Allowlisted customer identity projection — never includes tokens/secrets."""
    out = {k: bundle.get(k) for k in IDENTITY_FIELDS if k in bundle}
    # Strip any accidental secret-like values
    for k, v in list(out.items()):
        if isinstance(v, str) and re.search(r"(?i)(token|password|secret|api[_-]?key)\s*[:=]", v):
            out[k] = "[redacted]"
    return out


def evaluate_session(session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Authoritative evaluation of auth/account/entitlement from persisted session."""
    ensure_session_columns()
    session = session if session is not None else store.get_session()
    if not session:
        msg = customer_message(UNAUTHENTICATED)
        return to_identity_projection(
            {
                "auth_state": UNAUTHENTICATED,
                "account_state": ACCOUNT_UNKNOWN,
                "entitlement_state": ENTITLEMENT_UNKNOWN,
                "production_access": False,
                "production_allowed": False,
                "block_reason": "unauthenticated",
                "logged_in": False,
                **msg,
            }
        )

    if is_session_expired(session):
        msg = customer_message(SESSION_EXPIRED)
        return to_identity_projection(
            {
                "auth_state": SESSION_EXPIRED,
                "account_state": map_account_state(session.get("customer")),
                "entitlement_state": map_entitlement_state(
                    session.get("customer"), auth_mode=str(session.get("auth_mode") or "")
                ),
                "production_access": False,
                "production_allowed": False,
                "block_reason": "session_expired",
                "logged_in": False,
                "login_id": session.get("login_id"),
                "session_updated_at": session.get("updated_at"),
                "session_expires_at": session.get("expires_at"),
                **msg,
            }
        )

    customer = session.get("customer") or {}
    auth_mode = str(session.get("auth_mode") or ("local_dev" if str(session.get("token") or "").startswith("local-") else "license"))
    account = str(session.get("account_state") or "") or map_account_state(customer)
    entitlement = str(session.get("entitlement_state") or "") or map_entitlement_state(customer, auth_mode=auth_mode)

    auth_state = AUTHENTICATED
    block_reason = None
    if account == ACCOUNT_DISABLED_STATE:
        auth_state = ACCOUNT_DISABLED
        block_reason = "account_disabled"
    elif account == ACCOUNT_PENDING:
        auth_state = ENTITLEMENT_REQUIRED
        block_reason = "account_pending"
    elif account == ACCOUNT_UNKNOWN:
        auth_state = AUTH_ERROR
        block_reason = "account_unknown"
    elif entitlement in (ENTITLEMENT_NONE, ENTITLEMENT_EXPIRED, ENTITLEMENT_SUSPENDED):
        auth_state = ENTITLEMENT_REQUIRED
        block_reason = f"entitlement_{entitlement.lower()}"
    elif entitlement == ENTITLEMENT_UNKNOWN:
        auth_state = AUTH_ERROR
        block_reason = "entitlement_unknown"

    production_access = (
        account == ACCOUNT_ACTIVE
        and entitlement == ENTITLEMENT_ACTIVE
        and auth_state == AUTHENTICATED
    )
    # Shell access: signed-in session that is not disabled/expired/error
    shell_access = auth_state in (AUTHENTICATED, ENTITLEMENT_REQUIRED)
    msg = customer_message(auth_state)
    try:
        from app.release_identity import RELEASE_VERSION

        rel = RELEASE_VERSION
    except Exception:
        rel = None

    from app.customer_tiers import normalize_tier_id
    raw_tier = customer.get("tier") or customer.get("plan") or customer.get("plan_name")
    resolved_tier = normalize_tier_id(raw_tier) if (raw_tier or auth_mode != "local_dev") else "dev"

    return to_identity_projection(
        {
            "auth_state": auth_state,
            "account_state": account,
            "entitlement_state": entitlement,
            "production_access": production_access,
            "production_allowed": False,  # filled by can_customer_produce with C01
            "block_reason": block_reason,
            "logged_in": bool(shell_access),
            "customer_id": customer.get("id"),
            "display_name": customer.get("name") or customer.get("display_name") or session.get("login_id"),
            "login_id": session.get("login_id") or customer.get("login_id"),
            "plan_label": customer.get("plan") or customer.get("tier") or customer.get("plan_name") or resolved_tier,
            "plan": resolved_tier,
            "tier": resolved_tier,
            "session_updated_at": session.get("updated_at"),
            "session_expires_at": session.get("expires_at")
            or compute_expires_at(session.get("updated_at"), customer),
            "mode": auth_mode,
            "release_version": rel,
            **msg,
        }
    )


def persist_session(
    *,
    login_id: str,
    token: str,
    customer: Dict[str, Any],
    api_base: str,
    auth_mode: str,
) -> None:
    """Save session with C02 metadata. Never logs the token."""
    ensure_session_columns()
    account = map_account_state(customer)
    entitlement = map_entitlement_state(customer, auth_mode=auth_mode)
    updated = _now().isoformat()
    expires = compute_expires_at(updated, customer)
    # Use existing save then update meta columns
    store.save_session(login_id, token, customer, api_base)
    with store.db() as conn:
        conn.execute(
            """
            UPDATE session SET expires_at=?, account_state=?, entitlement_state=?, auth_mode=?
            WHERE id=1
            """,
            (expires, account, entitlement, auth_mode),
        )


def clear_session() -> None:
    store.clear_session()


def authenticate(login_id: str, password: str, api_base: str) -> Dict[str, Any]:
    """Perform login via local H2 path or LicenseClient. Returns safe result dict."""
    login_id = (login_id or "").strip()
    password = password or ""
    api_base = (api_base or settings.api_base_url or "").rstrip("/")
    if not login_id or not password:
        return {
            "ok": False,
            "auth_state": AUTH_ERROR,
            "error": "missing_credentials",
            **customer_message(AUTH_ERROR),
        }

    if local_login_permitted(login_id, password, api_base):
        customer = {
            "id": 1,
            "name": "Local Admin",
            "login_id": login_id,
            "status": "active",
            "tier": "dev",
            "plan": "dev",
            "entitlement": "active",
        }
        persist_session(
            login_id=login_id,
            token="local-dev-token",
            customer=customer,
            api_base=api_base or "local",
            auth_mode="local_dev",
        )
        settings.api_base_url = api_base or "local"
        identity = evaluate_session()
        return {"ok": True, "mode": "local_dev", "identity": identity, "customer": _public_customer(customer)}

    from app.api_client import LicenseClient
    from app.auth.hardware_id import get_hardware_fingerprint

    current_hwid = get_hardware_fingerprint()
    client = LicenseClient(api_base)
    try:
        data = client.login(login_id, password, hwid=current_hwid)
    except Exception as exc:
        raw_err = str(exc)
        logger.info("license login failed for login_id=%s err=%s", login_id, sanitize_auth_error(raw_err))
        err_code = "login_failed"
        custom_msg = "লগইন ব্যর্থ হয়েছে। অনুগ্রহ করে ইউজার আইডি ও পাসওয়ার্ড সঠিক দিন।"
        if "device_locked_to_another_pc" in raw_err:
            err_code = "device_locked"
            custom_msg = "এই অ্যাকাউন্টটি অন্য একটি নির্দিষ্ট পিসিতে আবদ্ধ (Locked)। একই সাথে একাধিক পিসিতে ব্যবহার করা সম্পূর্ণ নিষিদ্ধ।"
        elif "account_blocked" in raw_err or "account_disabled" in raw_err:
            err_code = "account_disabled"
            custom_msg = "আপনার অ্যাকাউন্টটি অ্যাডমিন প্যানেল থেকে ডিঅ্যাক্টিভেট বা ব্লক করা হয়েছে।"
        return {
            "ok": False,
            "auth_state": ACCOUNT_DISABLED if err_code == "account_disabled" else AUTH_ERROR,
            "error": err_code,
            "message": custom_msg,
            "message_key": err_code,
            "hint": sanitize_auth_error(raw_err, 160),
        }

    customer = dict(data.get("customer") or {})
    token = data.get("token")
    if not token:
        return {
            "ok": False,
            "auth_state": AUTH_ERROR,
            "error": "token_missing",
            **customer_message(AUTH_ERROR),
        }
    client.token = str(token)
    try:
        me = client.me()
        if me.get("ok") and me.get("customer"):
            customer = {**customer, **(me.get("customer") or {})}
    except Exception as exc:
        logger.info("license me() soft-fail: %s", sanitize_auth_error(str(exc)))

    # Normalize status/entitlement fields if website uses alternate keys
    if "status" not in customer and customer.get("active") is True:
        customer["status"] = "active"
    if "status" not in customer and customer.get("active") is False:
        customer["status"] = "disabled"

    persist_session(
        login_id=login_id,
        token=str(token),
        customer=customer,
        api_base=api_base,
        auth_mode="license",
    )
    settings.api_base_url = api_base
    identity = evaluate_session()
    if identity.get("auth_state") == ACCOUNT_DISABLED:
        return {
            "ok": False,
            "auth_state": ACCOUNT_DISABLED,
            "error": "account_disabled",
            "identity": identity,
            **customer_message(ACCOUNT_DISABLED),
        }
    if identity.get("auth_state") == ENTITLEMENT_REQUIRED:
        # Session saved but production blocked — login "ok" for shell, produce denied
        return {
            "ok": True,
            "mode": "license",
            "identity": identity,
            "customer": _public_customer(customer),
            "warning": "entitlement_required",
        }
    return {"ok": True, "mode": "license", "identity": identity, "customer": _public_customer(customer)}


def _public_customer(customer: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"id", "name", "login_id", "status", "plan", "plan_name", "tier", "unlocked"}
    return {k: customer.get(k) for k in allowed if k in customer}


def logout() -> Dict[str, Any]:
    clear_session()
    return {"ok": True, "identity": evaluate_session()}


def require_authenticated_session() -> Optional[Dict[str, Any]]:
    """Return raw session only if auth allows authenticated shell access.

    Shell access requires a non-expired session. Production still needs can_customer_produce.
    Expired / missing → None (and clear expired).
    """
    ensure_session_columns()
    session = store.get_session()
    if not session:
        return None
    if is_session_expired(session):
        clear_session()
        return None
    return session


def can_customer_produce(
    *,
    channel: Optional[Dict[str, Any]] = None,
    foundation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """ONE authoritative production access decision: Auth ∧ Account ∧ Entitlement ∧ C01 readiness."""
    identity = evaluate_session()
    auth_state = identity.get("auth_state")
    if auth_state in (UNAUTHENTICATED, SESSION_EXPIRED):
        return {
            "allowed": False,
            "identity": identity,
            "block_reason": identity.get("block_reason") or auth_state.lower(),
            "foundation": foundation,
            **customer_message(str(auth_state)),
        }
    if auth_state == ACCOUNT_DISABLED:
        return {
            "allowed": False,
            "identity": identity,
            "block_reason": "account_disabled",
            "foundation": foundation,
            **customer_message(ACCOUNT_DISABLED),
        }
    if auth_state == ENTITLEMENT_REQUIRED:
        return {
            "allowed": False,
            "identity": identity,
            "block_reason": identity.get("block_reason") or "entitlement_required",
            "foundation": foundation,
            **customer_message(ENTITLEMENT_REQUIRED),
        }
    if auth_state == AUTH_ERROR or identity.get("account_state") == ACCOUNT_UNKNOWN:
        return {
            "allowed": False,
            "identity": identity,
            "block_reason": "auth_unknown_fail_closed",
            "foundation": foundation,
            **customer_message(AUTH_ERROR),
        }
    if not identity.get("production_access"):
        return {
            "allowed": False,
            "identity": identity,
            "block_reason": identity.get("block_reason") or "production_access_denied",
            "foundation": foundation,
            **customer_message(ENTITLEMENT_REQUIRED),
        }

    from app.customer_tiers import can_produce_video_studio, TIER_UPGRADE_MESSAGE_VIDEO_STUDIO

    if not can_produce_video_studio(identity):
        return {
            "allowed": False,
            "identity": {**identity, "production_allowed": False},
            "block_reason": "tier_upgrade_required",
            "foundation": foundation,
            "message_key": "tier_upgrade_required",
            "message": TIER_UPGRADE_MESSAGE_VIDEO_STUDIO,
        }

    # C01 readiness — do not recalculate; build snapshot from existing authorities
    if foundation is None:
        from app.config import validate_production_operational
        from app.customer_foundation import build_foundation_snapshot
        from pipeline.compose import probe_media_tool_capability

        api_readiness = None
        if channel is not None:
            from pipeline.channel_api_slots import evaluate_readiness

            api_readiness = evaluate_readiness(channel=channel)
        elif store.get_session():
            from pipeline.channel_api_slots import evaluate_readiness
            from app.customer_config import list_owned_channels, resolve_session_login_id

            channels = list_owned_channels(resolve_session_login_id())
            api_readiness = evaluate_readiness(channel=channels[0] if channels else {})

        foundation = build_foundation_snapshot(
            app_started=True,
            media_cap=probe_media_tool_capability(),
            operational=validate_production_operational(),
            api_readiness=api_readiness,
        )

    if not foundation.get("generate_allowed"):
        reasons = list(foundation.get("generate_block_reasons") or [])
        return {
            "allowed": False,
            "identity": {**identity, "production_allowed": False},
            "block_reason": "production_prerequisites_blocked",
            "generate_block_reasons": reasons,
            "foundation": foundation,
            "message_key": "production_prerequisites_blocked",
            "message": "Production cannot start because application readiness is blocked or unknown.",
        }

    identity = {**identity, "production_allowed": True, "logged_in": True}
    return {
        "allowed": True,
        "identity": identity,
        "block_reason": None,
        "foundation": foundation,
        "message_key": "production_allowed",
        "message": "Production access authorized (does not imply a video is ready).",
    }


def refresh_remote_account_state() -> Dict[str, Any]:
    """Best-effort LicenseClient.me() and heartbeat refresh into session.
    Enforces remote kill-switch: if blocked by admin, session is immediately revoked.
    """
    session = store.get_session()
    if not session:
        return evaluate_session()
    if str(session.get("auth_mode") or "") == "local_dev" or str(session.get("token") or "").startswith("local-"):
        return evaluate_session()
    if is_session_expired(session):
        clear_session()
        return evaluate_session()
    try:
        from app.api_client import LicenseClient
        from app.auth.hardware_id import get_hardware_fingerprint

        client = LicenseClient(session.get("api_base_url"), session.get("token"))
        # Execute heartbeat with hardware fingerprint check
        client.heartbeat(hwid=get_hardware_fingerprint())
        me = client.me()
        if me.get("ok") and me.get("customer"):
            customer = {**(session.get("customer") or {}), **(me.get("customer") or {})}
            if customer.get("status") not in {"active", "ok"}:
                clear_session()
                return evaluate_session()
            persist_session(
                login_id=str(session.get("login_id") or customer.get("login_id") or ""),
                token=str(session.get("token") or ""),
                customer=customer,
                api_base=str(session.get("api_base_url") or ""),
                auth_mode="license",
            )
    except Exception as exc:
        err_str = str(exc)
        logger.info("remote account refresh / heartbeat failed: %s", sanitize_auth_error(err_str))
        if "ACCOUNT_BLOCKED" in err_str or "account_blocked" in err_str or "license_revoked" in err_str:
            clear_session()
            return evaluate_session()
    return evaluate_session()


def request_password_otp(login_id_or_email: str, api_base: Optional[str] = None) -> Dict[str, Any]:
    """Requests a 6-digit OTP for password reset."""
    from app.api_client import LicenseClient

    client = LicenseClient(api_base or settings.api_base_url)
    try:
        return client.request_password_otp(login_id_or_email)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "message": str(exc)}


def reset_password(login_id_or_email: str, otp: str, new_password: str, api_base: Optional[str] = None) -> Dict[str, Any]:
    """Verifies OTP and resets account password."""
    from app.api_client import LicenseClient

    client = LicenseClient(api_base or settings.api_base_url)
    try:
        return client.reset_password_with_otp(login_id_or_email, otp, new_password)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "message": str(exc)}
