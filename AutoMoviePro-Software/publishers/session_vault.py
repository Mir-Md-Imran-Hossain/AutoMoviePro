"""
Cookie / persistent-profile session vault for YouTube, Facebook & TikTok.

WhatsApp-marketing analogy:
  WhatsApp uses QR → saves a multi-device session.
  YouTube/Facebook/TikTok have no public QR for desktop automation — the equivalent is:
    1) One-time headed login in a dedicated Chrome profile
    2) Persist cookies + localStorage (storage_state) + the same user_data_dir
    3) Later runs reopen that profile — no password again until cookies expire

Best stack (analysis 2026):
  - Patchright + real Chrome + persistent user_data_dir (fingerprint + CDP patches)
  - storage_state JSON backup (portable cookie snapshot)
  - Our human_browser mouse/keyboard layer (behavioral)
  - Do NOT pull random "FB/YT marketing bot" GitHub repos (malware / ToS / unmaintained)
  - nodriver is strong but async-only rewrite; keep as optional future engine
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

VAULT_ROOT = DATA_DIR / "session_vault"


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (s or "default"))[:48]


def profile_dir(platform: str, channel_id: int, lang_code: str = "en") -> Path:
    p = str(platform or "").lower()
    if "tiktok" in p:
        plat = "tiktok"
    elif "youtube" in p:
        plat = "youtube"
    else:
        plat = "facebook"
    lang = _safe(lang_code or "en")
    d = VAULT_ROOT / f"{plat}_ch{int(channel_id)}_{lang}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def storage_path(platform: str, channel_id: int, lang_code: str = "en") -> Path:
    return profile_dir(platform, channel_id, lang_code) / "storage_state.json"


def meta_path(platform: str, channel_id: int, lang_code: str = "en") -> Path:
    return profile_dir(platform, channel_id, lang_code) / "meta.json"


def read_meta(platform: str, channel_id: int, lang_code: str = "en") -> Dict[str, Any]:
    p = meta_path(platform, channel_id, lang_code)
    if not p.exists():
        return {"status": "disconnected"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "disconnected"}


def write_meta(platform: str, channel_id: int, lang_code: str, data: Dict[str, Any]) -> None:
    p = meta_path(platform, channel_id, lang_code)
    data = dict(data)
    data["updated_at"] = datetime.now().isoformat()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def session_status(platform: str, channel_id: int, lang_code: str = "en") -> Dict[str, Any]:
    """
    Returns WhatsApp-like connection status:
      connected | needs_login | expired | disconnected
    """
    store = storage_path(platform, channel_id, lang_code)
    meta = read_meta(platform, channel_id, lang_code)
    profile = profile_dir(platform, channel_id, lang_code)
    has_store = store.exists() and store.stat().st_size > 50
    has_profile = any(profile.iterdir()) if profile.exists() else False

    if not has_store and not has_profile:
        return {
            "ok": True,
            "platform": platform,
            "channel_id": channel_id,
            "lang_code": lang_code or "en",
            "status": "needs_login",
            "connected": False,
            "message": "Not linked — connect once (like WhatsApp QR), then cookies persist.",
            "profile_dir": str(profile),
            "storage_state": "",
        }

    # Cookie freshness heuristic from storage_state
    expired_hint = False
    cookie_count = 0
    try:
        if has_store:
            raw = json.loads(store.read_text(encoding="utf-8"))
            cookies = raw.get("cookies") or []
            cookie_count = len(cookies)
            now = time.time()
            # If all session cookies expired (expires > 0 and < now)
            lasting = [c for c in cookies if float(c.get("expires") or -1) > now]
            if cookies and not lasting and any(float(c.get("expires") or -1) > 0 for c in cookies):
                expired_hint = True
    except Exception:
        pass

    status = meta.get("status") or ("connected" if has_store else "needs_login")
    if expired_hint:
        status = "expired"
    connected = status == "connected" and has_store

    return {
        "ok": True,
        "platform": platform,
        "channel_id": channel_id,
        "lang_code": lang_code or "en",
        "status": status,
        "connected": connected,
        "cookie_count": cookie_count,
        "message": {
            "connected": "Linked — no password needed until cookies expire.",
            "needs_login": "Open connect window and sign in once.",
            "expired": "Session expired — reconnect (one-time login).",
            "disconnected": "Disconnected.",
        }.get(status, status),
        "profile_dir": str(profile),
        "storage_state": str(store) if has_store else "",
        "linked_at": meta.get("linked_at") or "",
        "account_hint": meta.get("account_hint") or "",
    }


def list_sessions(channel_id: int = 0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not VAULT_ROOT.exists():
        return out
    for d in sorted(VAULT_ROOT.iterdir()):
        if not d.is_dir():
            continue
        parts = d.name.split("_")
        if len(parts) < 3:
            continue
        platform = parts[0]
        cid_str = parts[1].replace("ch", "")
        lang_code = "_".join(parts[2:])
        try:
            cid = int(cid_str)
        except ValueError:
            continue
        if channel_id and cid != channel_id:
            continue
        out.append(session_status(platform, cid, lang_code))
    return out


def resolve_paths(
    platform: str,
    channel_id: int,
    lang_code: str = "en",
    *,
    legacy_storage: str = "",
) -> Dict[str, str]:
    """Prefer vault paths; fall back to legacy channel session path."""
    st = storage_path(platform, channel_id, lang_code)
    prof = profile_dir(platform, channel_id, lang_code)
    connect = prof / "chrome_connect"
    classic = prof / "chrome_profile"
    if (connect / "Default").exists():
        user_data = connect
    elif (classic / "Default").exists():
        user_data = classic
    else:
        user_data = connect
    if st.exists():
        return {"storage_state": str(st), "user_data_dir": str(user_data)}
    if legacy_storage and Path(legacy_storage).exists():
        return {"storage_state": legacy_storage, "user_data_dir": str(user_data)}
    return {"storage_state": str(st), "user_data_dir": str(user_data)}


def mark_linked(
    platform: str,
    channel_id: int,
    lang_code: str,
    *,
    account_hint: str = "",
    storage_file: str = "",
) -> Dict[str, Any]:
    write_meta(
        platform,
        channel_id,
        lang_code,
        {
            "status": "connected",
            "linked_at": datetime.now().isoformat(),
            "account_hint": account_hint,
            "storage_file": storage_file,
        },
    )
    return session_status(platform, channel_id, lang_code)


def mark_disconnected(platform: str, channel_id: int, lang_code: str = "en") -> Dict[str, Any]:
    write_meta(platform, channel_id, lang_code, {"status": "needs_login"})
    return session_status(platform, channel_id, lang_code)


def disconnect_session(platform: str, channel_id: int, lang_code: str = "en") -> Dict[str, Any]:
    """Clear linked flag + storage_state (keep empty chrome_profile folder)."""
    st = storage_path(platform, channel_id, lang_code)
    try:
        if st.exists():
            st.unlink()
    except Exception as exc:
        logger.warning("unlink storage failed: %s", exc)
    return mark_disconnected(platform, channel_id, lang_code)


def paths_for_channel(
    platform: str,
    channel: Dict[str, Any],
    *,
    lang_code: str = "en",
) -> Dict[str, str]:
    """Resolve vault paths from a channel row (+ optional lang destination)."""
    cid = int(channel.get("id") or 0)
    code = (lang_code or "en").strip().lower() or "en"
    plat = (platform or "").lower()
    if "tiktok" in plat:
        key = "tiktok_session"
    elif "youtube" in plat:
        key = "youtube_session"
    else:
        key = "facebook_session"
    legacy = str(channel.get(key) or "")
    if code and code not in ("en", "default"):
        try:
            from pipeline.lang_destinations import parse_lang_destinations

            dest = parse_lang_destinations(channel.get("lang_destinations_json"))
            slot = dest.get(code) or {}
            if slot.get(key):
                legacy = str(slot[key])
        except Exception:
            pass
    elif not legacy:
        try:
            from pipeline.lang_destinations import parse_lang_destinations

            dest = parse_lang_destinations(channel.get("lang_destinations_json"))
            slot = dest.get("en") or {}
            if slot.get(key):
                legacy = str(slot[key])
        except Exception:
            pass
    return resolve_paths(platform, cid, code if code != "default" else "en", legacy_storage=legacy)


def health_check(
    platform: str,
    channel_id: int,
    lang_code: str = "en",
    *,
    legacy_storage: str = "",
) -> Dict[str, Any]:
    """
    Quick headed/headless probe: open home, see if still logged in.
    Uses Patchright persistent profile when available.
    """
    paths = resolve_paths(platform, channel_id, lang_code, legacy_storage=legacy_storage)
    if not paths.get("storage_state") or not Path(paths["storage_state"]).exists():
        st = session_status(platform, channel_id, lang_code)
        st["healthy"] = False
        return st

    plat = (platform or "").lower()
    if "tiktok" in plat:
        url = "https://www.tiktok.com/"
    elif "youtube" in plat:
        url = "https://www.youtube.com/"
    else:
        url = "https://www.facebook.com/"

    try:
        from publishers.stealth_session import stealth_browser

        with stealth_browser(
            storage_state=paths["storage_state"],
            user_data_dir=paths["user_data_dir"],
            headless=False,
        ) as (_pw, _b, page, engine):
            from publishers.login_signals import page_logged_in

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2.5)
            logged_in = page_logged_in(page, platform)

            try:
                page.context.storage_state(path=paths["storage_state"])
            except Exception:
                pass

            if logged_in:
                mark_linked(platform, channel_id, lang_code, storage_file=paths["storage_state"])
                st = session_status(platform, channel_id, lang_code)
                st["healthy"] = True
                st["engine"] = engine
                return st
            mark_disconnected(platform, channel_id, lang_code)
            st = session_status(platform, channel_id, lang_code)
            st["status"] = "expired"
            st["connected"] = False
            st["healthy"] = False
            st["engine"] = engine
            return st
    except Exception as exc:
        logger.warning("session health check failed: %s", exc)
        st = session_status(platform, channel_id, lang_code)
        st["healthy"] = False
        st["error"] = str(exc)[:200]
        return st
