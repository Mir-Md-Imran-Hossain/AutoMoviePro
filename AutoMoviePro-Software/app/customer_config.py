"""C04 — Customer-owned channel / language / provider configuration authority.

Extends existing db channels + crypto, channel_api_slots, lang_entitlement.
Does NOT replace C01/C02/C03 or create a second secret vault.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app import db as store

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "NOT_CONFIGURED"
CONFIGURED = "CONFIGURED"
VALID = "VALID"
INVALID = "INVALID"
UNKNOWN = "UNKNOWN"
BLOCKED = "BLOCKED"
NOT_ENTITLED = "NOT_ENTITLED"

MAX_CHANNELS_PER_CUSTOMER = 1

CLASSIFICATION = {
    "channel": "CUSTOMER-OWNED (owner_login_id)",
    "language_configuration": "CUSTOMER-OWNED (via owned channel)",
    "provider_configuration": "CUSTOMER-OWNED (via owned channel)",
    "api_credential": "CUSTOMER-OWNED + DEVICE-LOCAL encryption (app.crypto)",
    "production_configuration": "COMPOSITE (C01+C02+C04)",
}


def ensure_channel_owner_column() -> None:
    with store.db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(channels)").fetchall()}
        if "owner_login_id" not in cols:
            conn.execute("ALTER TABLE channels ADD COLUMN owner_login_id TEXT")


def resolve_session_login_id(session: Optional[Dict[str, Any]] = None) -> str:
    sess = session if session is not None else store.get_session()
    if not sess:
        return ""
    return str(sess.get("login_id") or (sess.get("customer") or {}).get("login_id") or "").strip()


def assert_no_forged_identity(payload: Optional[Dict[str, Any]], session_login: str) -> Optional[str]:
    if not payload:
        return None
    for key in ("login_id", "customer_id", "user_id", "owner_login_id"):
        raw = payload.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        if key == "customer_id":
            sess = store.get_session() or {}
            cid = (sess.get("customer") or {}).get("id")
            if cid is not None and str(raw).strip() != str(cid):
                return "customer_scope_denied"
            continue
        if str(raw).strip() != session_login:
            return "customer_scope_denied"
    return None


def list_owned_channels(login_id: str) -> List[Dict[str, Any]]:
    ensure_channel_owner_column()
    lid = (login_id or "").strip()
    if not lid:
        return []
    return [c for c in store.list_channels() if str(c.get("owner_login_id") or "").strip() == lid]


def list_orphan_channels() -> List[Dict[str, Any]]:
    ensure_channel_owner_column()
    return [c for c in store.list_channels() if not str(c.get("owner_login_id") or "").strip()]


def get_owned_channel(channel_id: int, login_id: str) -> Optional[Dict[str, Any]]:
    ch = store.get_channel(int(channel_id))
    if not ch:
        return None
    owner = str(ch.get("owner_login_id") or "").strip()
    if not owner or owner != (login_id or "").strip():
        return None
    return ch


def require_owned_channel(
    channel_id: int, login_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ensure_channel_owner_column()
    lid = (login_id or "").strip()
    if not lid:
        return None, {"ok": False, "error": "login_required"}
    ch = store.get_channel(int(channel_id))
    if not ch:
        return None, {"ok": False, "error": "channel_not_found"}
    owner = str(ch.get("owner_login_id") or "").strip()
    if not owner:
        return None, {
            "ok": False,
            "error": "channel_unowned",
            "message": "This channel is not assigned to a customer. Claim it first if you are the owner.",
        }
    if owner != lid:
        return None, {
            "ok": False,
            "error": "channel_forbidden",
            "message": "You do not have access to this channel.",
        }
    return ch, None


def claim_orphan_channel(channel_id: int, login_id: str) -> Dict[str, Any]:
    ensure_channel_owner_column()
    lid = (login_id or "").strip()
    if not lid:
        return {"ok": False, "error": "login_required"}
    if list_owned_channels(lid):
        return {"ok": False, "error": "channel_limit", "message": "This account already owns a channel."}
    ch = store.get_channel(int(channel_id))
    if not ch:
        return {"ok": False, "error": "channel_not_found"}
    owner = str(ch.get("owner_login_id") or "").strip()
    if owner and owner != lid:
        return {"ok": False, "error": "channel_forbidden"}
    if owner == lid:
        return {"ok": True, "channel_id": int(channel_id), "already_owned": True}
    with store.db() as conn:
        conn.execute(
            "UPDATE channels SET owner_login_id=? WHERE id=? AND (owner_login_id IS NULL OR owner_login_id='')",
            (lid, int(channel_id)),
        )
        row = conn.execute("SELECT owner_login_id FROM channels WHERE id=?", (int(channel_id),)).fetchone()
    if not row or str(row["owner_login_id"] or "") != lid:
        return {"ok": False, "error": "claim_failed"}
    return {"ok": True, "channel_id": int(channel_id), "claimed": True}


def set_channel_owner_on_payload(payload: Dict[str, Any], login_id: str) -> Dict[str, Any]:
    out = dict(payload)
    out["owner_login_id"] = (login_id or "").strip()
    return out


def upsert_owned_channel(
    payload: Dict[str, Any], login_id: str, channel_id: Optional[int] = None
) -> Dict[str, Any]:
    ensure_channel_owner_column()
    lid = (login_id or "").strip()
    if not lid:
        return {"ok": False, "error": "login_required"}
    if channel_id is None:
        if len(list_owned_channels(lid)) >= MAX_CHANNELS_PER_CUSTOMER:
            return {"ok": False, "error": "channel_already_setup", "hint": "One channel per customer account."}
        payload = set_channel_owner_on_payload(payload, lid)
        cid = store.upsert_channel(payload, None)
        return {"ok": True, "channel_id": cid}
    ch, err = require_owned_channel(int(channel_id), lid)
    if err:
        return err
    payload = set_channel_owner_on_payload({**ch, **payload}, lid)
    cid = store.upsert_channel(payload, int(channel_id))
    return {"ok": True, "channel_id": cid}


def set_channel_enabled(channel_id: int, login_id: str, enabled: bool) -> Dict[str, Any]:
    ch, err = require_owned_channel(channel_id, login_id)
    if err:
        return err
    payload = set_channel_owner_on_payload({**ch, "enabled": 1 if enabled else 0}, login_id)
    store.upsert_channel(payload, int(channel_id))
    return {"ok": True, "channel_id": int(channel_id), "enabled": bool(enabled)}


def sanitize_config_error(message: str, limit: int = 180) -> str:
    s = " ".join(str(message or "").replace("\r", " ").split())
    s = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", s)
    s = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[redacted]", s)
    s = re.sub(r"\bsk-[0-9A-Za-z]{8,}\b", "[redacted]", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def channel_languages_safe(ch: Dict[str, Any]) -> List[str]:
    from pipeline.lang_entitlement import channel_languages

    return channel_languages(ch)


def to_safe_channel_view(channel: Dict[str, Any]) -> Dict[str, Any]:
    from pipeline.channel_api_slots import PROVIDER_DEFS, channel_provider_keys, evaluate_readiness, mask_slots
    from pipeline.lang_entitlement import catalog, channel_languages

    r = channel
    slots = channel_provider_keys(r)
    ready = evaluate_readiness(channel=r)
    langs = channel_languages(r)
    missing = set(ready.get("missing") or ready.get("missing_providers") or [])
    provider_status = {}
    for pid, label, required in PROVIDER_DEFS:
        keys = slots.get(pid) or []
        if not keys:
            st = NOT_CONFIGURED
        elif required and pid in missing:
            st = INVALID
        elif ready.get("active"):
            st = VALID
        else:
            st = CONFIGURED
        provider_status[pid] = {
            "id": pid,
            "label": label,
            "required": required,
            "state": st,
            "configured": bool(keys),
            "slot_count": len(keys),
            "slots_masked": mask_slots({pid: keys}).get(pid) or [],
        }

    enabled = bool(int(r.get("enabled") or 0))
    if not enabled:
        channel_state = BLOCKED
    elif ready.get("active"):
        channel_state = VALID
    elif langs:
        channel_state = CONFIGURED
    else:
        channel_state = NOT_CONFIGURED

    return {
        "id": r.get("id"),
        "owner_login_id": r.get("owner_login_id"),
        "youtube_name": r.get("youtube_name") or "",
        "facebook_name": r.get("facebook_name") or "",
        "niche": r.get("niche") or "",
        "niche_id": r.get("niche_id"),
        "enabled": enabled,
        "languages": langs,
        "language_names": [
            next((c["name"] for c in catalog() if c["code"] == code), code) for code in langs
        ],
        "language_state": VALID if len(langs) >= 2 else (CONFIGURED if langs else NOT_CONFIGURED),
        "providers": provider_status,
        "api_active": bool(ready.get("active")),
        "api_message": ready.get("message"),
        "api_message_key": ready.get("message_key"),
        "configuration_state": channel_state,
        "youtube_session": "configured" if r.get("youtube_session") else "not_configured",
        "facebook_session": "configured" if r.get("facebook_session") else "not_configured",
        "classification": CLASSIFICATION["channel"],
    }


def provider_capability_matrix(channel: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from pipeline.dedicated_api_registry import providers_ui_meta_dedicated
    from pipeline.lang_entitlement import channel_languages

    unlocked = channel_languages(channel) if channel else ["en"]
    meta = providers_ui_meta_dedicated(unlocked=unlocked, channel=channel)
    out = []
    for p in meta:
        configured = int(p.get("filled") or 0) > 0
        required = bool(p.get("required"))
        ok = bool(p.get("ok"))
        if not configured and not required:
            state = NOT_CONFIGURED
        elif not ok:
            state = INVALID
        elif configured:
            state = VALID
        else:
            state = NOT_CONFIGURED
        out.append(
            {
                "provider_id": p["id"],
                "label": p.get("label_bn") or p.get("label"),
                "required": required,
                "configured": configured,
                "valid": ok,
                "entitled": True,
                "ready": ok,
                "state": state,
                "min_keys": p.get("min_required") or 0,
                "slot_count": p.get("filled") or 0,
                "language_gate": p.get("language_gate"),
                "free_url_ok": p.get("free_url_ok"),
            }
        )
    return out


def set_channel_languages(
    channel_id: int,
    login_id: str,
    languages: Sequence[str],
    *,
    entitled_unlocked: Optional[Sequence[str]] = None,
    allow_setup_pair: bool = False,
) -> Dict[str, Any]:
    from pipeline.lang_config import SOURCE_LANG, TARGET_LANG_CODES
    from pipeline.lang_entitlement import parse_languages, serialize_languages

    ch, err = require_owned_channel(channel_id, login_id)
    if err:
        return err
    if not int(ch.get("enabled") or 0):
        return {"ok": False, "error": "channel_inactive", "message": "Activate the channel before changing languages."}

    from pipeline.lang_entitlement import normalize_code

    raw_list = [normalize_code(str(x)) for x in languages if str(x).strip()]
    for c in raw_list:
        if c not in TARGET_LANG_CODES:
            return {"ok": False, "error": "unsupported_language", "lang_code": c, "state": INVALID}

    codes = parse_languages(list(languages))
    if len(codes) != len(set(codes)):
        return {"ok": False, "error": "duplicate_language"}
    for c in codes:
        if c not in TARGET_LANG_CODES:
            return {"ok": False, "error": "unsupported_language", "lang_code": c, "state": INVALID}

    entitled = set(parse_languages(list(entitled_unlocked or []) + channel_languages_safe(ch)))
    for c in codes:
        if c == SOURCE_LANG:
            continue
        if c not in entitled:
            if allow_setup_pair and len(codes) == 2 and SOURCE_LANG in codes:
                continue
            return {
                "ok": False,
                "error": "language_not_entitled",
                "lang_code": c,
                "state": NOT_ENTITLED,
                "message": "This language is not entitled for this account.",
            }

    payload = set_channel_owner_on_payload({**ch, "languages_json": serialize_languages(codes)}, login_id)
    store.upsert_channel(payload, int(channel_id))
    return {"ok": True, "channel_id": int(channel_id), "languages": parse_languages(codes)}


def save_owned_provider_slots(
    channel_id: int,
    login_id: str,
    incoming_slots: Dict[str, List[str]],
) -> Dict[str, Any]:
    from pipeline.channel_api_slots import (
        PROVIDER_DEFS,
        channel_provider_keys,
        evaluate_readiness,
        merge_keep_existing,
        serialize_api_keys_json,
        sync_legacy_fields,
    )
    from pipeline.dedicated_api_registry import (
        all_possible_slot_defs,
        channel_dedicated_keys,
        serialize_dedicated_json,
        validate_dedicated_submission,
    )
    from pipeline.lang_entitlement import channel_languages

    ch, err = require_owned_channel(channel_id, login_id)
    if err:
        return err
    known_legacy = {pid for pid, _, _ in PROVIDER_DEFS}
    known_dedicated = {s.id for s in all_possible_slot_defs()} | {
        f"{s.id}_accounts" for s in all_possible_slot_defs() if s.requires_account_id
    }
    legacy_in: Dict[str, List[str]] = {}
    dedicated_in: Dict[str, List[str]] = {}
    for pid, vals in (incoming_slots or {}).items():
        if pid in known_dedicated:
            dedicated_in[pid] = list(vals or [])
        elif pid in known_legacy:
            legacy_in[pid] = list(vals or [])
        else:
            return {"ok": False, "error": "unsupported_provider", "provider_id": pid}

    slots = merge_keep_existing(legacy_in, channel_provider_keys(ch)) if legacy_in else channel_provider_keys(ch)
    if not legacy_in and not dedicated_in:
        slots = channel_provider_keys(ch)

    existing_ded = channel_dedicated_keys(ch)
    unlocked = channel_languages(ch)
    if dedicated_in:
        check = validate_dedicated_submission(
            dedicated_in,
            existing_ded,
            unlocked=unlocked,
        )
        if not check.get("ok"):
            msgs = [
                str(e.get("message_bn") or e.get("message") or e)
                for e in (check.get("errors") or [])
            ]
            return {
                "ok": False,
                "error": "dedicated_api_validation_failed",
                "message": msgs[0] if msgs else "API validation failed",
                "messages": msgs,
                "errors": check.get("errors") or [],
                "duplicates": check.get("duplicates") or [],
                "hint": "একই API কী দুই জায়গায় দেওয়া যাবে না; Workers AI-তে API দিলে Account ID বাধ্যতামূলক।",
            }
        dedicated = check["merged"]
    else:
        dedicated = existing_ded

    legacy = sync_legacy_fields(slots)
    payload = set_channel_owner_on_payload(
        {
            **ch,
            "api_keys_json": serialize_api_keys_json(slots),
            "dedicated_api_keys_json": serialize_dedicated_json(dedicated),
            "google_api_1": legacy.get("google_api_1") or ch.get("google_api_1"),
            "google_api_2": legacy.get("google_api_2") or ch.get("google_api_2"),
            "agnes_api": legacy.get("agnes_api") or ch.get("agnes_api"),
            "pexels_api": legacy.get("pexels_api") or ch.get("pexels_api"),
            "pollinations_api": legacy.get("pollinations_api") or ch.get("pollinations_api"),
        },
        login_id,
    )
    store.upsert_channel(payload, int(channel_id))
    fresh = store.get_channel(int(channel_id)) or payload
    ready = evaluate_readiness(channel=fresh)
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "app_active": bool(ready.get("active")),
        "api_readiness": {
            "active": ready.get("active"),
            "message": ready.get("message"),
            "message_key": ready.get("message_key"),
            "warnings": ready.get("warnings") or [],
            "missing": ready.get("missing") or [],
        },
        "providers": provider_capability_matrix(fresh),
        "channel": to_safe_channel_view(fresh),
    }


def clear_owned_provider(channel_id: int, login_id: str, provider_id: str) -> Dict[str, Any]:
    from pipeline.channel_api_slots import (
        PROVIDER_DEFS,
        channel_provider_keys,
        evaluate_readiness,
        serialize_api_keys_json,
        sync_legacy_fields,
    )

    known = {pid for pid, _, _ in PROVIDER_DEFS}
    if provider_id not in known:
        return {"ok": False, "error": "unsupported_provider", "provider_id": provider_id}
    ch, err = require_owned_channel(channel_id, login_id)
    if err:
        return err
    slots = channel_provider_keys(ch)
    slots[provider_id] = []
    legacy = sync_legacy_fields(slots)
    payload = set_channel_owner_on_payload(
        {
            **ch,
            "api_keys_json": serialize_api_keys_json(slots),
            "google_api_1": legacy.get("google_api_1") or "",
            "google_api_2": legacy.get("google_api_2") or "",
            "agnes_api": legacy.get("agnes_api") or "",
            "pexels_api": legacy.get("pexels_api") or "",
            "pollinations_api": legacy.get("pollinations_api") or "",
        },
        login_id,
    )
    store.upsert_channel(payload, int(channel_id))
    fresh = store.get_channel(int(channel_id)) or payload
    ready = evaluate_readiness(channel=fresh)
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "provider_id": provider_id,
        "cleared": True,
        "app_active": bool(ready.get("active")),
        "channel": to_safe_channel_view(fresh),
    }


def configuration_summary(login_id: str) -> Dict[str, Any]:
    owned = list_owned_channels(login_id)
    orphans = list_orphan_channels()
    if not owned:
        return {
            "channel_state": NOT_CONFIGURED,
            "language_state": NOT_CONFIGURED,
            "provider_state": NOT_CONFIGURED,
            "channels": [],
            "orphan_count": len(orphans),
            "orphan_ids": [int(o["id"]) for o in orphans if o.get("id") is not None],
            "providers": provider_capability_matrix(None),
            "note": "No customer-owned channel for this account.",
        }
    ch = owned[0]
    view = to_safe_channel_view(ch)
    from pipeline.channel_api_slots import evaluate_readiness

    ready = evaluate_readiness(channel=ch)
    if ready.get("active"):
        provider_state = VALID
    elif any(p.get("configured") for p in view["providers"].values()):
        provider_state = INVALID
    else:
        provider_state = NOT_CONFIGURED
    return {
        "channel_state": view["configuration_state"],
        "language_state": view["language_state"],
        "provider_state": provider_state,
        "channels": [view],
        "orphan_count": len(orphans),
        "orphan_ids": [int(o["id"]) for o in orphans if o.get("id") is not None],
        "providers": provider_capability_matrix(ch),
        "api_active": bool(ready.get("active")),
    }
