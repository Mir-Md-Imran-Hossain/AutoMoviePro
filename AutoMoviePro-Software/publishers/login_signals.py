"""Logged-in heuristics for YouTube / Facebook / TikTok (UI + cookie backup)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional, Set

YT_COOKIE_HINTS = {
    "SID",
    "SSID",
    "LOGIN_INFO",
    "SAPISID",
    "APISID",
    "__Secure-1PSID",
    "__Secure-3PSID",
}
FB_COOKIE_HINTS = {"c_user", "xs"}  # datr/sb alone are NOT proof of login
FB_COOKIE_REQUIRED = {"c_user", "xs"}  # both required for cookie-based FB proof
TIKTOK_COOKIE_HINTS = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}


def cookie_names(storage_state: Any) -> Set[str]:
    if isinstance(storage_state, (str, Path)):
        p = Path(storage_state)
        if not p.exists():
            return set()
        try:
            storage_state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return set()
    if not isinstance(storage_state, dict):
        return set()
    names: Set[str] = set()
    for c in storage_state.get("cookies") or []:
        n = str((c or {}).get("name") or "").strip()
        if n:
            names.add(n)
    return names


def cookies_indicate_login(platform: str, storage_state: Any) -> bool:
    names = cookie_names(storage_state)
    plat = (platform or "").lower()
    if plat == "facebook":
        # Require real session cookies — datr/sb alone caused false "connected"
        return FB_COOKIE_REQUIRED.issubset(names)
    elif plat == "tiktok":
        return bool(names & TIKTOK_COOKIE_HINTS)
    return bool(names & YT_COOKIE_HINTS)


def youtube_page_logged_in(page: Any) -> bool:
    try:
        url = (page.url or "").lower()
        if "accounts.google.com" in url or "/signin" in url or "ServiceLogin" in (page.url or ""):
            return False
        for sel in (
            "#avatar-btn",
            "button#avatar-btn",
            "ytd-topbar-menu-button-renderer #avatar",
            "button[aria-label*='Account' i]",
        ):
            try:
                if page.locator(sel).count():
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def facebook_page_logged_in(page: Any) -> bool:
    try:
        url = (page.url or "").lower()
        if "login" in url or "checkpoint" in url or "recover" in url:
            return False
        try:
            if page.locator('input#email, input[name="email"][type="text"], form[data-testid="royal_login_form"]').count():
                return False
        except Exception:
            pass
        for sel in (
            '[aria-label="Your profile"]',
            '[aria-label="Account"]',
            '[aria-label*="Your profile" i]',
            '[aria-label*="Account" i]',
            '[aria-label*="What\'s on your mind" i]',
            'div[role="banner"] [aria-label*="profile" i]',
        ):
            try:
                if page.locator(sel).count():
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def tiktok_page_logged_in(page: Any) -> bool:
    try:
        url = (page.url or "").lower()
        if "/login" in url:
            return False
        for sel in (
            '[data-e2e="profile-icon"]',
            'a[href*="/upload"]',
            '[aria-label*="Profile" i]',
            'div[data-e2e="user-avatar"]',
            'button:has-text("Upload")',
        ):
            try:
                if page.locator(sel).count():
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def page_logged_in(page: Any, platform: str) -> bool:
    plat = (platform or "").lower()
    if plat == "facebook":
        return facebook_page_logged_in(page)
    elif plat == "tiktok":
        return tiktok_page_logged_in(page)
    return youtube_page_logged_in(page)


def patch_env_dry_run(text: str, dry: bool) -> str:
    """Replace or append DRY_RUN_PUBLISH in a .env blob (does not touch other keys)."""
    line = f"DRY_RUN_PUBLISH={'true' if dry else 'false'}"
    raw = text or ""
    lines = raw.splitlines()
    found = False
    out = []
    for ln in lines:
        if ln.strip().startswith("DRY_RUN_PUBLISH="):
            out.append(line)
            found = True
        else:
            out.append(ln)
    if not found:
        if out and out[-1].strip():
            out.append(line)
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if raw.endswith("\n") or not raw else "\n")
