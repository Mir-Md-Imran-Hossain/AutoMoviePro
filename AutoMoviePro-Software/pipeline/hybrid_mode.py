"""
Dual-Mode architecture for AutoMovie Pro.

Mode A — Direct API: use official credentials when present (upload/analytics/messages).
Mode B — Hybrid Agent (default): API when available, else browser automation
         (session vault + human layer) for engage / restricted actions.

Non-tech users stay in Mode B; advanced users can force Mode A via settings.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

ModeName = Literal["api", "hybrid", "browser"]

# Task → preferred transport (policy matrix)
TASK_POLICY: Dict[str, str] = {
    "upload_youtube": "api_then_browser",
    "upload_facebook": "api_then_browser",
    "analytics": "api_then_browser",
    "inbox_reply": "api_then_browser",
    "engage_scroll": "browser",
    "engage_like": "browser",
    "engage_comment": "browser",
    "engage_subscribe": "browser",
    "feed_browse": "browser",
}


def get_automation_mode() -> ModeName:
    from app import db as store

    raw = (store.get_meta("automation_mode", "hybrid") or "hybrid").strip().lower()
    if raw in ("api", "a", "mode_a", "direct"):
        return "api"
    if raw in ("browser", "b_browser", "browser_only"):
        return "browser"
    return "hybrid"


def set_automation_mode(mode: str) -> ModeName:
    from app import db as store

    m = (mode or "hybrid").strip().lower()
    if m in ("api", "a", "mode_a", "direct"):
        resolved: ModeName = "api"
    elif m in ("browser", "browser_only"):
        resolved = "browser"
    else:
        resolved = "hybrid"
    store.set_meta("automation_mode", resolved)
    return resolved


def channel_has_youtube_api(channel: Optional[Dict[str, Any]]) -> bool:
    ch = channel or {}
    tok = (
        ch.get("youtube_access_token")
        or ch.get("youtube_oauth_token")
        or ch.get("youtube_api_token")
        or ""
    ).strip()
    if tok:
        return True
    raw = ch.get("youtube_oauth_json") or ""
    if isinstance(raw, str) and len(raw) > 40:
        return True
    return False


def channel_has_facebook_api(channel: Optional[Dict[str, Any]]) -> bool:
    ch = channel or {}
    tok = (
        ch.get("facebook_access_token")
        or ch.get("facebook_page_token")
        or ch.get("meta_access_token")
        or ""
    ).strip()
    return bool(tok)


def channel_has_browser_session(platform: str, channel: Optional[Dict[str, Any]]) -> bool:
    from pathlib import Path

    ch = channel or {}
    try:
        from publishers.session_vault import paths_for_channel

        paths = paths_for_channel(platform, ch, lang_code=str(ch.get("_lang_code") or "en"))
        store = paths.get("storage_state") or ""
        profile = paths.get("user_data_dir") or ""
        if store and Path(store).exists() and Path(store).stat().st_size > 50:
            return True
        if profile and (Path(profile) / "Default").exists():
            return True
    except Exception:
        pass
    key = "youtube_session" if platform == "youtube" else "facebook_session"
    p = str(ch.get(key) or "")
    return bool(p and Path(p).exists())


def route_task(
    task: str,
    *,
    channel: Optional[Dict[str, Any]] = None,
    platform: str = "",
) -> Dict[str, Any]:
    """
    Decide transport for a task.
    Returns: {mode, transport: 'api'|'browser'|'dry_run'|'skip', reason, policy}
    """
    mode = get_automation_mode()
    policy = TASK_POLICY.get(task, "browser")
    plat = platform or ("youtube" if "youtube" in task else "facebook" if "facebook" in task else "")

    # Pure browser tasks never use Graph/Data API
    if policy == "browser" or mode == "browser":
        if plat and not channel_has_browser_session(plat, channel):
            return {
                "mode": mode,
                "transport": "skip",
                "reason": "browser_session_missing",
                "policy": policy,
            }
        return {"mode": mode, "transport": "browser", "reason": "policy_browser", "policy": policy}

    wants_api = policy.startswith("api") or mode == "api"
    has_api = False
    if "youtube" in task or plat == "youtube":
        has_api = channel_has_youtube_api(channel)
    elif "facebook" in task or plat == "facebook":
        has_api = channel_has_facebook_api(channel)

    if wants_api and has_api:
        return {"mode": mode, "transport": "api", "reason": "credentials_present", "policy": policy}

    if mode == "api" and not has_api:
        # Mode A strict: no silent browser unless hybrid
        return {
            "mode": mode,
            "transport": "skip",
            "reason": "api_credentials_missing",
            "policy": policy,
        }

    # Hybrid fallback → browser
    if plat and not channel_has_browser_session(plat, channel):
        return {
            "mode": mode,
            "transport": "skip",
            "reason": "no_api_and_no_browser_session",
            "policy": policy,
        }
    return {
        "mode": mode,
        "transport": "browser",
        "reason": "hybrid_fallback_browser",
        "policy": policy,
    }


def mode_status() -> Dict[str, Any]:
    mode = get_automation_mode()
    return {
        "ok": True,
        "mode": mode,
        "label": {
            "api": "Mode A — Direct API",
            "hybrid": "Mode B — Hybrid Agent (recommended)",
            "browser": "Browser only",
        }.get(mode, mode),
        "policy": TASK_POLICY,
        "hint": (
            "Non-tech users: keep Hybrid. Connect YouTube/Facebook once (cookies). "
            "Advanced: paste official OAuth tokens for Mode A uploads."
        ),
    }


def describe_for_agent() -> str:
    st = mode_status()
    return (
        f"Automation mode={st['mode']} ({st['label']}). "
        "API keys for video generation live in Settings. "
        "YouTube/Facebook publish uses API tokens if set, else browser session vault. "
        "Engage (like/comment/scroll) always uses browser."
    )
