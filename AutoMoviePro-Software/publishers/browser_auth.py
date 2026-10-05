"""Async browser login capture — returns immediately so Chromium can open."""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def _session_dir() -> Path:
    d = DATA_DIR / "browser_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_path(platform: str, channel_id: int, lang_code: str = "") -> Path:
    code = (lang_code or "default").strip().lower() or "default"
    if code in ("", "default", "en") and platform in ("youtube", "facebook", "tiktok"):
        # Keep legacy default path for English / unspecified
        if code == "en" or code == "default":
            legacy = _session_dir() / f"{platform}_ch{channel_id}.json"
            if code == "default":
                return legacy
            # en uses lang-specific path but fall back to legacy on read
            return _session_dir() / f"{platform}_{code}_ch{channel_id}.json"
    return _session_dir() / f"{platform}_{code}_ch{channel_id}.json"


def start_login(
    channel_id: int,
    platform: str,
    *,
    lang_code: str = "",
    url: str = "",
) -> Dict[str, Any]:
    plat = (platform or "").lower()
    if plat == "tiktok":
        platform = "tiktok"
        if not url:
            url = "https://www.tiktok.com/login"
    elif plat == "facebook":
        platform = "facebook"
        if not url:
            url = "https://www.facebook.com/"
    else:
        platform = "youtube"
        if not url:
            url = "https://www.youtube.com/"
    job_id = uuid.uuid4().hex[:10]
    with _lock:
        # Cancel duplicate running jobs for same target
        for jid, st in list(_jobs.items()):
            if (
                st.get("channel_id") == channel_id
                and st.get("platform") == platform
                and (st.get("lang_code") or "") == (lang_code or "")
                and st.get("status") in ("starting", "opening", "waiting_login")
            ):
                return {
                    "ok": True,
                    "job_id": jid,
                    "status": st.get("status"),
                    "message": "already_running",
                }
        _jobs[job_id] = {
            "job_id": job_id,
            "channel_id": channel_id,
            "platform": platform,
            "lang_code": lang_code or "",
            "status": "starting",
            "path": "",
            "error": "",
            "started_at": time.time(),
        }

    t = threading.Thread(
        target=_run_capture,
        args=(job_id, channel_id, platform, url, lang_code or ""),
        daemon=True,
        name=f"browser-auth-{platform}-{channel_id}",
    )
    t.start()
    # Brief wait so launch errors surface in first poll
    time.sleep(0.35)
    return get_login_status(job_id)


def get_login_status(job_id: str) -> Dict[str, Any]:
    with _lock:
        st = dict(_jobs.get(job_id) or {})
    if not st:
        return {"ok": False, "status": "unknown", "error": "job_not_found"}
    st["ok"] = st.get("status") not in ("failed",)
    return st


def _set(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _launch_browser(p):
    last_err = None
    for kwargs in (
        {"headless": False, "channel": "chrome", "args": ["--disable-blink-features=AutomationControlled"]},
        {"headless": False, "channel": "msedge", "args": ["--disable-blink-features=AutomationControlled"]},
        {"headless": False, "args": ["--disable-blink-features=AutomationControlled"]},
    ):
        try:
            return p.chromium.launch(**kwargs)
        except Exception as exc:
            last_err = exc
            logger.info("browser launch try %s failed: %s", kwargs.get("channel"), exc)
    raise RuntimeError(f"Could not launch Chromium/Chrome/Edge: {last_err}")


def _sync_playwright():
    try:
        from patchright.sync_api import sync_playwright

        return sync_playwright, "patchright"
    except Exception:
        from playwright.sync_api import sync_playwright

        return sync_playwright, "playwright"

def _persist_login(
    *,
    job_id: str,
    platform: str,
    channel_id: int,
    code: str,
    out: Path,
    user_data: Path,
    linked: bool,
) -> None:
    from publishers.login_signals import cookies_indicate_login
    from publishers.session_vault import mark_linked, profile_dir

    if not out.exists() or out.stat().st_size < 20:
        _set(job_id, status="failed", error="session_not_saved")
        return
    if not linked and not cookies_indicate_login(platform, out):
        _set(job_id, status="failed", error="login_not_detected — sign in fully, then try Connect again")
        return
    mark_linked(platform, channel_id, code, account_hint="", storage_file=str(out))
    meta = {
        "platform": platform,
        "channel_id": channel_id,
        "lang_code": code,
        "path": str(out),
        "profile": str(user_data),
        "linked": linked,
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    profile_dir(platform, channel_id, code).joinpath("connect_ok.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    try:
        from app import db as store

        ch = store.get_channel(channel_id)
        if ch:
            if code == "en":
                if platform == "youtube":
                    ch["youtube_session"] = str(out)
                elif platform == "tiktok":
                    ch["tiktok_session"] = str(out)
                else:
                    ch["facebook_session"] = str(out)
            dest = _parse_dest(ch.get("lang_destinations_json"))
            slot = dict(dest.get(code) or {})
            if platform == "youtube":
                slot["youtube_session"] = str(out)
            elif platform == "tiktok":
                slot["tiktok_session"] = str(out)
            else:
                slot["facebook_session"] = str(out)
            dest[code] = slot
            ch["lang_destinations_json"] = json.dumps(dest, ensure_ascii=False)
            store.upsert_channel(ch, channel_id)
    except Exception as exc:
        logger.warning("persist session to channel failed: %s", exc)
    _set(job_id, status="saved", path=str(out), linked=linked)


def _save_states(context, out: Path, legacy: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(out))
    context.storage_state(path=str(legacy))


def _run_capture(
    job_id: str,
    channel_id: int,
    platform: str,
    url: str,
    lang_code: str,
) -> None:
    """
    One-time connect: real installed Chrome (CDP), not Playwright-launched Chrome.
    Playwright automation flags make Google/Facebook login spin forever.
    """
    from publishers.session_vault import resolve_paths

    code = "en" if not lang_code or lang_code == "default" else lang_code
    paths = resolve_paths(platform, channel_id, code)
    out = Path(paths["storage_state"])
    user_data = Path(paths["user_data_dir"])
    user_data.mkdir(parents=True, exist_ok=True)
    legacy = _session_path(platform, channel_id, lang_code or "default")

    try:
        from publishers.login_signals import cookies_indicate_login, page_logged_in
        from publishers.real_chrome import launch_connectable_chrome
        from playwright.sync_api import sync_playwright

        _set(job_id, status="opening", engine="chrome-cdp")
        proc, port, exe_name = launch_connectable_chrome(user_data, url)
        logger.info("login capture chrome=%s port=%s profile=%s", exe_name, port, user_data)
        wait_msg = (
            "Facebook: sign in, then switch to your Page. Close the window when done."
            if platform == "facebook"
            else "YouTube: sign in to the channel Google account. Close the window when you see your avatar."
        )
        _set(job_id, status="waiting_login", message=wait_msg, engine=exe_name)

        linked = False
        saved_ok = False
        deadline = time.time() + 900  # 15 minutes
        extra_until = 0.0

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            try:
                if url not in (page.url or ""):
                    page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                pass
            try:
                page.bring_to_front()
            except Exception:
                pass

            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    if page.is_closed():
                        if context.pages:
                            page = context.pages[0]
                        else:
                            break
                    if page_logged_in(page, platform) or cookies_indicate_login(platform, context.storage_state()):
                        linked = True
                        try:
                            _save_states(context, out, legacy)
                            saved_ok = True
                        except Exception as exc:
                            logger.warning("mid-login save: %s", exc)
                        if extra_until <= 0:
                            extra_until = time.time() + (45 if platform == "facebook" else 8)
                        elif time.time() >= extra_until:
                            break
                except Exception:
                    pass
                time.sleep(1.2)

            try:
                _save_states(context, out, legacy)
                saved_ok = True
            except Exception as exc:
                logger.warning("final storage_state save: %s", exc)

        if proc.poll() is None:
            # Leave Chrome open so the user can finish 2FA; don't kill it.
            pass

        if not saved_ok and (not out.exists() or out.stat().st_size < 20):
            _set(job_id, status="failed", error="session_not_saved")
            return
        _persist_login(
            job_id=job_id,
            platform=platform,
            channel_id=channel_id,
            code=code,
            out=out,
            user_data=user_data,
            linked=linked or cookies_indicate_login(platform, out),
        )
    except Exception as exc:
        logger.exception("browser capture failed")
        _set(job_id, status="failed", error=str(exc)[:300])


def _parse_dest(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


# Back-compat sync wrappers (prefer start_login)
def capture_youtube_session(channel_id: int) -> str:
    res = start_login(channel_id, "youtube")
    job_id = res.get("job_id") or ""
    for _ in range(200):
        st = get_login_status(job_id)
        if st.get("status") in ("saved", "failed"):
            if st.get("status") == "saved":
                return str(st.get("path") or "")
            raise RuntimeError(st.get("error") or "login_failed")
        time.sleep(1)
    raise RuntimeError("login_timeout")


def capture_facebook_session(channel_id: int) -> str:
    res = start_login(channel_id, "facebook")
    job_id = res.get("job_id") or ""
    for _ in range(200):
        st = get_login_status(job_id)
        if st.get("status") in ("saved", "failed"):
            if st.get("status") == "saved":
                return str(st.get("path") or "")
            raise RuntimeError(st.get("error") or "login_failed")
        time.sleep(1)
    raise RuntimeError("login_timeout")
