"""
Easy CAPTCHA / bot-check handling for AutoMovie Pro.

Policy:
  - Easy challenges (checkbox, single-click Turnstile, Continue buttons) are
    solved automatically without asking the user.
  - Hard challenges park the headed browser, open the page for the user,
    and wait for unlock or DOM clear — never silently close the window.
"""
from __future__ import annotations

import logging
import time
import webbrowser
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Soft park timeout — admin can still unlock earlier
PARK_TIMEOUT_SEC = 18 * 60
PARK_POLL_SEC = 2.5


def _live(msg: str, **extra: Any) -> None:
    try:
        from pipeline.live_activity import log as live_log

        live_log("captcha", msg, **extra)
    except Exception:
        pass


def classify_challenge(page) -> str:
    """
    Return one of: none | easy_checkbox | easy_click | hard | unknown
    """
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(x in url for x in ("/sorry/", "google.com/sorry", "accounts.google.com/signin/challenge")):
        return "hard"

    # reCAPTCHA checkbox (anchor) — often one click
    for sel in (
        "iframe[src*='recaptcha/api2/anchor']",
        "iframe[title*='reCAPTCHA' i]",
        "iframe[title*='recaptcha' i]",
    ):
        try:
            if page.locator(sel).count() and page.locator(sel).first.is_visible():
                # Image challenge iframe present → hard
                if page.locator("iframe[src*='recaptcha/api2/bframe']").count():
                    try:
                        if page.locator("iframe[src*='recaptcha/api2/bframe']").first.is_visible():
                            return "hard"
                    except Exception:
                        return "hard"
                return "easy_checkbox"
        except Exception:
            continue

    # Cloudflare Turnstile / managed challenge — often a single click
    for sel in (
        "iframe[src*='challenges.cloudflare.com']",
        "iframe[src*='turnstile']",
        ".cf-turnstile",
        "#challenge-stage",
        "#cf-challenge-running",
    ):
        try:
            if page.locator(sel).count() and page.locator(sel).first.is_visible():
                return "easy_click"
        except Exception:
            continue

    # Simple confirm buttons
    for text in (
        "Verify you are human",
        "I'm not a robot",
        "Confirm you're not a bot",
        "Continue",
        "সামনে যান",
        "সম্পন্ন করুন",
    ):
        try:
            loc = page.get_by_role("button", name=text)
            if loc.count() and loc.first.is_visible():
                return "easy_click"
        except Exception:
            continue

    # Visible challenge copy without a clear easy control
    for text in (
        "Unusual traffic from your computer network",
        "Our systems have detected unusual traffic",
        "Select all images",
        "select all squares",
    ):
        try:
            loc = page.get_by_text(text, exact=False)
            if loc.count() and loc.first.is_visible():
                return "hard"
        except Exception:
            continue

    return "unknown"


def try_easy_solve(page) -> Dict[str, Any]:
    """
    Attempt automatic solve for easy challenges. Never asks the user.
    Returns {ok, method, detail}.
    """
    from publishers.human_browser import detect_captcha, human_click, human_sleep

    if not detect_captcha(page):
        return {"ok": True, "method": "none", "detail": "no_challenge"}

    kind = classify_challenge(page)
    _live(f"CAPTCHA auto-try ({kind})", dest=str(getattr(page, "url", "") or ""))

    if kind == "hard":
        return {"ok": False, "method": "skip", "detail": "hard_challenge"}

    # 1) Click reCAPTCHA checkbox inside anchor iframe
    try:
        frames = page.frames
        for fr in frames:
            furl = (fr.url or "").lower()
            if "recaptcha" in furl and "anchor" in furl:
                box = fr.locator("#recaptcha-anchor, .recaptcha-checkbox-border, span.recaptcha-checkbox")
                if box.count():
                    box.first.click(timeout=4000)
                    human_sleep(1.2, 2.4)
                    _live("Clicked reCAPTCHA checkbox", dest=furl[:120])
                    if not detect_captcha(page):
                        return {"ok": True, "method": "recaptcha_checkbox", "detail": "cleared"}
                    # Image challenge may have appeared
                    if page.locator("iframe[src*='recaptcha/api2/bframe']").count():
                        return {"ok": False, "method": "recaptcha_checkbox", "detail": "escalated_to_image"}
    except Exception as exc:
        logger.debug("recaptcha checkbox try failed: %s", exc)

    # 2) Turnstile / Cloudflare — click widget or checkbox in frame
    try:
        for fr in page.frames:
            furl = (fr.url or "").lower()
            if "turnstile" in furl or "challenges.cloudflare" in furl:
                for sel in ("input[type='checkbox']", "body", "#content", ".ctp-checkbox-label"):
                    loc = fr.locator(sel)
                    if loc.count():
                        try:
                            loc.first.click(timeout=3000)
                            human_sleep(1.5, 3.0)
                            if not detect_captcha(page):
                                return {"ok": True, "method": "turnstile_click", "detail": "cleared"}
                        except Exception:
                            continue
        # Host-page turnstile
        tw = page.locator(".cf-turnstile, [data-sitekey]")
        if tw.count() and tw.first.is_visible():
            human_click(page, tw.first)
            human_sleep(1.5, 3.0)
            if not detect_captcha(page):
                return {"ok": True, "method": "turnstile_host", "detail": "cleared"}
    except Exception as exc:
        logger.debug("turnstile try failed: %s", exc)

    # 3) Obvious verify / continue buttons
    for label in (
        "Verify you are human",
        "I'm not a robot",
        "Confirm you're not a bot",
        "Continue",
        "Verify",
        "সামনে যান",
        "সম্পন্ন করুন",
    ):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() and btn.first.is_visible():
                if human_click(page, btn.first):
                    human_sleep(1.2, 2.5)
                    if not detect_captcha(page):
                        return {"ok": True, "method": f"button:{label}", "detail": "cleared"}
        except Exception:
            continue

    # 4) Checkbox on main page
    try:
        cb = page.locator("input[type='checkbox']").filter(has=page.locator("xpath=.."))
        for i in range(min(3, cb.count())):
            el = cb.nth(i)
            if el.is_visible():
                human_click(page, el)
                human_sleep(1.0, 2.0)
                if not detect_captcha(page):
                    return {"ok": True, "method": "page_checkbox", "detail": "cleared"}
    except Exception:
        pass

    return {"ok": False, "method": kind or "unknown", "detail": "still_present"}


def open_captcha_page(url: str = "", *, screenshot: str = "") -> Dict[str, Any]:
    """Open challenge URL in the system default browser so admin can solve easily."""
    from publishers.human_browser import captcha_status

    st = captcha_status()
    target = (url or st.get("url") or "https://www.youtube.com/").strip()
    opened = False
    try:
        opened = bool(webbrowser.open(target, new=1, autoraise=True))
    except Exception as exc:
        logger.warning("webbrowser.open failed: %s", exc)
    _live(f"Opened CAPTCHA page in browser", dest=target, force_new=True)
    try:
        from app import db as store

        store.set_meta(
            "captcha_page_opened_at",
            datetime.now().isoformat(timespec="seconds"),
        )
        store.set_meta("captcha_page_url", target)
    except Exception:
        pass
    return {"ok": True, "opened": opened, "url": target, "screenshot": screenshot or st.get("screenshot") or ""}


def park_for_human_solve(
    page,
    *,
    platform: str = "",
    url: str = "",
    screenshot: str = "",
    timeout_sec: float = PARK_TIMEOUT_SEC,
) -> Dict[str, Any]:
    """
    Keep headed Playwright page alive, open system browser, wait until
    challenge clears or admin unlocks.
    """
    from publishers.human_browser import captcha_is_locked, captcha_unlock, detect_captcha

    target = url or getattr(page, "url", "") or ""
    payload = {
        "status": "waiting_admin",
        "platform": platform,
        "url": target,
        "screenshot": screenshot,
        "at": datetime.now().isoformat(),
        "message": "CAPTCHA needs a quick human check — page is open. Easy ones auto-solved; hard ones wait here.",
        "mode": "parked_headed",
    }
    try:
        from app import db as store

        store.set_meta("captcha_lock", __import__("json").dumps(payload, ensure_ascii=False))
        store.set_meta("captcha_lock_flag", "1")
    except Exception:
        pass
    try:
        from publishers.captcha_alerts import on_captcha_locked

        on_captcha_locked(payload)
    except Exception as exc:
        logger.warning("captcha alert during park failed: %s", exc)

    open_captcha_page(target, screenshot=screenshot)

    # Bring headed window forward best-effort
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        page.evaluate("() => { try { window.focus(); } catch (e) {} }")
    except Exception:
        pass

    _live(
        f"CAPTCHA parked — headed window held + system browser opened ({platform})",
        dest=target,
        force_new=True,
    )

    deadline = time.time() + float(timeout_sec)
    while time.time() < deadline:
        # Admin unlock button
        if not captcha_is_locked():
            _live("CAPTCHA unlocked by admin — continuing", force_new=True)
            return {"ok": True, "via": "admin_unlock"}
        # DOM cleared (user solved in headed window)
        try:
            if not detect_captcha(page):
                captcha_unlock(note="dom_cleared_auto")
                _live("CAPTCHA cleared in headed window — continuing", force_new=True)
                return {"ok": True, "via": "dom_cleared"}
        except Exception:
            pass
        # Retry easy solve periodically (challenge may have simplified)
        try:
            again = try_easy_solve(page)
            if again.get("ok") and again.get("method") != "none":
                captcha_unlock(note=f"auto_retry:{again.get('method')}")
                _live(f"CAPTCHA auto-solved on retry ({again.get('method')})", force_new=True)
                return {"ok": True, "via": again.get("method")}
        except Exception:
            pass
        time.sleep(PARK_POLL_SEC)

    return {"ok": False, "via": "timeout", "detail": "park_timeout"}
