"""
Human-like interaction layer for browser automation.

Goals (best-effort, never claim permanent undetectability):
  - Bezier mouse paths, jitter, overshoot
  - Reading pauses, aimless scrolling, stray clicks
  - Large text via clipboard paste simulation (not robotic char typing)
  - Occasional likes / video opens / idle watching
  - Screenshot-assisted element finding
  - CAPTCHA hard-stop → admin unlock gate
"""
from __future__ import annotations

import json
import logging
import math
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

from app.config import DATA_DIR

logger = logging.getLogger(__name__)


class CaptchaBlockedError(RuntimeError):
    """Raised when a CAPTCHA / challenge is detected — automation must pause."""


def _rand(a: float, b: float) -> float:
    return random.uniform(a, b)


def human_sleep(a: float = 0.35, b: float = 1.4) -> None:
    """Human-skewed delay (log-normal via browser_intel when available)."""
    try:
        from publishers.browser_intel import smart_sleep

        smart_sleep(a, b)
    except Exception:
        time.sleep(_rand(a, b))


def micro_pause() -> None:
    time.sleep(_rand(0.05, 0.28))


def _bezier(p0, p1, p2, p3, t: float):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def human_move(page, x: float, y: float, *, steps: int = 0) -> None:
    """Move mouse along a noisy cubic Bézier path (Fitts-ish timing + mid-path hesitation)."""
    try:
        cur = getattr(page, "_amp_mouse", None) or (random.randint(80, 400), random.randint(80, 300))
    except Exception:
        cur = (200, 200)
    x2, y2 = float(x), float(y)
    dist = math.hypot(x2 - cur[0], y2 - cur[1])
    # Longer distance → more steps / slower (rough Fitts law)
    base_steps = max(14, min(48, int(12 + dist / 18)))
    n = steps or base_steps + random.randint(-3, 6)
    # Overshoot target slightly then settle (humans often do this)
    overshoot = random.random() < 0.35 and dist > 80
    tx, ty = x2, y2
    if overshoot:
        ang = math.atan2(y2 - cur[1], x2 - cur[0])
        ox = _rand(6, 18) * math.cos(ang)
        oy = _rand(6, 18) * math.sin(ang)
        tx, ty = x2 + ox, y2 + oy
    cx1 = cur[0] + (tx - cur[0]) * _rand(0.15, 0.4) + _rand(-40, 40)
    cy1 = cur[1] + (ty - cur[1]) * _rand(0.05, 0.3) + _rand(-60, 60)
    cx2 = cur[0] + (tx - cur[0]) * _rand(0.55, 0.85) + _rand(-30, 30)
    cy2 = cur[1] + (ty - cur[1]) * _rand(0.6, 0.95) + _rand(-40, 40)
    hesitate_at = random.randint(n // 3, max(n // 3 + 1, (2 * n) // 3)) if random.random() < 0.22 else -1
    for i in range(1, n + 1):
        t = i / n
        te = 0.5 - 0.5 * math.cos(math.pi * t)
        px, py = _bezier(cur, (cx1, cy1), (cx2, cy2), (tx, ty), te)
        page.mouse.move(px + _rand(-1.2, 1.2), py + _rand(-1.2, 1.2))
        delay = _rand(0.004, 0.016) * (1.0 + dist / 2500.0)
        if i == hesitate_at:
            delay += _rand(0.08, 0.22)
        time.sleep(delay)
    if overshoot:
        # settle onto true target
        for _ in range(random.randint(4, 9)):
            page.mouse.move(x2 + _rand(-0.8, 0.8), y2 + _rand(-0.8, 0.8))
            time.sleep(_rand(0.006, 0.02))
    page._amp_mouse = (x2, y2)  # type: ignore[attr-defined]


def human_click(page, locator, *, timeout: float = 8000) -> bool:
    try:
        loc = locator.first if hasattr(locator, "first") else locator
        if hasattr(loc, "count") and loc.count() == 0:
            return False
        # Gentle bring-into-view (avoids clicking off-screen targets)
        try:
            loc.scroll_into_view_if_needed(timeout=min(4000, timeout))
            micro_pause()
        except Exception:
            pass
        try:
            if hasattr(loc, "is_visible") and not loc.is_visible():
                return False
        except Exception:
            pass
        box = loc.bounding_box(timeout=timeout)
        if not box:
            # last resort — still paced
            human_sleep(0.1, 0.35)
            loc.click(timeout=timeout)
            human_sleep(0.25, 0.7)
            return True
        # Prefer center-ish but avoid exact geometric center (bot tell)
        tx = box["x"] + box["width"] * _rand(0.28, 0.72)
        ty = box["y"] + box["height"] * _rand(0.30, 0.70)
        human_move(page, tx, ty)
        human_sleep(0.08, 0.32)
        # occasional miss then correct (very human)
        if random.random() < 0.06:
            page.mouse.move(tx + _rand(-12, 12), ty + _rand(-10, 10))
            micro_pause()
            page.mouse.move(tx + _rand(-2, 2), ty + _rand(-2, 2))
        page.mouse.down()
        time.sleep(_rand(0.045, 0.14))
        page.mouse.up()
        human_sleep(0.22, 0.85)
        return True
    except Exception as exc:
        logger.debug("human_click failed: %s", exc)
        try:
            from publishers.browser_intel import note_glitch

            note_glitch(
                platform="",
                fault_code="human_click_fail",
                message=str(exc)[:200],
                severity="info",
            )
        except Exception:
            pass
        try:
            human_sleep(0.15, 0.4)
            locator.first.click(timeout=timeout)
            return True
        except Exception:
            return False


def aimless_scroll(page, bursts: int = 0) -> None:
    n = bursts or random.randint(2, 7)
    for _ in range(n):
        dy = random.choice([
            random.randint(180, 420),
            random.randint(500, 900),
            -random.randint(80, 220),
            random.randint(60, 140),
        ])
        page.mouse.wheel(0, dy)
        human_sleep(0.4, 1.8)
        if random.random() < 0.25:
            # tiny horizontal wobble
            page.mouse.wheel(random.randint(-40, 40), 0)
            micro_pause()


def reading_pause(seconds: Optional[float] = None) -> None:
    if seconds is None:
        human_sleep(1.5, 5.5)
    else:
        time.sleep(max(0.2, float(seconds) + _rand(-0.3, 0.8)))


def human_type_text(page, text: str) -> None:
    """
    Character typing with variable WPM, occasional typo + backspace, word-boundary pauses.
    Used for short fields; long body text should still go through human_paste_text.
    """
    neighbors = {
        "a": "sq", "s": "adw", "d": "sf", "f": "dg", "g": "fh", "h": "gj", "j": "hk",
        "k": "jl", "l": "k", "q": "wa", "w": "qe", "e": "wr", "r": "et", "t": "ry",
        "y": "tu", "u": "yi", "i": "uo", "o": "ip", "p": "o", "z": "x", "x": "zc",
        "c": "xv", "v": "cb", "b": "vn", "n": "bm", "m": "n",
    }
    i = 0
    while i < len(text):
        ch = text[i]
        # Rare typo on letters
        if ch.isalpha() and random.random() < 0.04:
            wrong = random.choice(neighbors.get(ch.lower(), ch) or ch)
            if ch.isupper():
                wrong = wrong.upper()
            page.keyboard.type(wrong, delay=random.randint(40, 110))
            time.sleep(_rand(0.12, 0.35))
            page.keyboard.press("Backspace")
            time.sleep(_rand(0.05, 0.18))
        page.keyboard.type(ch, delay=random.randint(35, 160))
        if ch in " .,!?;:\n" and random.random() < 0.55:
            time.sleep(_rand(0.12, 0.55))
        elif random.random() < 0.06:
            time.sleep(_rand(0.2, 0.65))
        i += 1


def human_paste_text(page, locator, text: str, *, prefer_type: Optional[bool] = None) -> None:
    """
    Large text: simulate copy-from-elsewhere → focus → paste (not char-by-char).
    Short fields (titles): prefer imperfect human typing.
    Mid fields: mix type+paste. Long: paste with human delays.
    """
    text = text or ""
    loc = locator.first if hasattr(locator, "first") else locator
    human_click(page, loc)
    human_sleep(0.35, 1.1)  # "switched from notepad"
    # Select-all clear like a human replacing content
    try:
        page.keyboard.press("Control+a")
        micro_pause()
        page.keyboard.press("Backspace")
        human_sleep(0.12, 0.4)
    except Exception:
        pass

    if prefer_type is None:
        if len(text) <= 70:
            prefer_type = random.random() < 0.82
        elif len(text) < 160:
            prefer_type = random.random() < 0.35
        else:
            prefer_type = False

    if prefer_type:
        human_type_text(page, text)
        # occasional re-read pause after typing a title
        if len(text) < 90 and random.random() < 0.4:
            reading_pause(_rand(0.6, 1.8))
        return

    # Clipboard paste path
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass
    pasted = False
    try:
        page.evaluate(
            """async (t) => {
              try { await navigator.clipboard.writeText(t); return true; }
              catch (e) { return false; }
            }""",
            text,
        )
        human_sleep(0.2, 0.55)
        page.keyboard.press("Control+v")
        pasted = True
        # humans often fix a character after paste
        if len(text) > 20 and random.random() < 0.18:
            human_sleep(0.2, 0.5)
            page.keyboard.press("End")
            micro_pause()
    except Exception:
        pasted = False

    if not pasted:
        # Fallback: insertText in one shot (still paste-like, not per-key)
        try:
            loc.evaluate(
                """(el, t) => {
                  el.focus();
                  if (document.execCommand) {
                    document.execCommand('insertText', false, t);
                  } else {
                    el.value = t;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                }""",
                text,
            )
        except Exception:
            try:
                loc.fill(text)
            except Exception as exc:
                logger.warning("paste fallback failed: %s", exc)
                try:
                    from pipeline.error_notebook import note_error

                    note_error(
                        subsystem="browser",
                        fault_code="paste_failed",
                        message=str(exc)[:300],
                        severity="warn",
                    )
                except Exception:
                    pass
    human_sleep(0.4, 1.2)


def screenshot_find_and_click(page, *, hint: str = "", out_dir: Optional[Path] = None) -> Optional[Path]:
    """Capture screenshot for vision/admin review; return path."""
    d = out_dir or (DATA_DIR / "browser_shots")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(100,999)}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        logger.info("screenshot saved (%s): %s", hint, path)
        return path
    except Exception as exc:
        logger.warning("screenshot failed: %s", exc)
        return None


CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha/api2/anchor']",
    "iframe[src*='recaptcha/enterprise/anchor']",
    "iframe[src*='recaptcha/api2/bframe']",
    "iframe[src*='hcaptcha.com']",
    "iframe[src*='challenges.cloudflare.com']",
    "iframe[src*='turnstile']",
    "#captcha",
    ".g-recaptcha",
    ".cf-turnstile",
    "#challenge-form",
    "#challenge-stage",
    "text=Verify you are human",
    "text=I'm not a robot",
    "text=Confirm you're not a bot",
    "text=Unusual traffic from your computer network",
    "text=Our systems have detected unusual traffic",
    "text=সম্পন্ন করুন",
]


def detect_captcha(page) -> bool:
    """Strict detection — avoid false positives on normal YouTube/Facebook pages with generic iframes."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(
        x in url
        for x in (
            "/sorry/",
            "google.com/sorry",
            "accounts.google.com/signin/challenge",
            "facebook.com/checkpoint",
            "facebook.com/consent",
        )
    ):
        return True

    for sel in CAPTCHA_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            continue

    # Visible challenge phrases only (not buried in scripts)
    for phrase in (
        "Unusual traffic from your computer network",
        "Our systems have detected unusual traffic",
        "Verify you are human",
        "Confirm you're not a bot",
        "Select all images with",
        "Please solve this puzzle",
    ):
        try:
            loc = page.get_by_text(phrase, exact=False)
            if loc.count() and loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def assert_no_captcha(page, *, platform: str = "", url: str = "") -> None:
    """
    If a challenge appears:
      1) Auto-solve easy ones (checkbox / single-click) without asking.
      2) Otherwise park headed browser + open system page for human.
      3) Only hard-fail after park timeout.
    """
    if not detect_captcha(page):
        return

    shot = screenshot_find_and_click(page, hint="captcha")
    target = url or getattr(page, "url", "") or ""

    try:
        from publishers.captcha_solver import park_for_human_solve, try_easy_solve

        auto = try_easy_solve(page)
        if auto.get("ok") and auto.get("method") not in ("", "none"):
            logger.info("CAPTCHA auto-solved via %s", auto.get("method"))
            try:
                from pipeline.live_activity import log as live_log

                live_log(
                    "captcha",
                    f"Auto-solved ({auto.get('method')}) — continuing",
                    dest=target,
                    force_new=True,
                )
            except Exception:
                pass
            return

        parked = park_for_human_solve(
            page,
            platform=platform,
            url=target,
            screenshot=str(shot or ""),
        )
        if parked.get("ok"):
            return
    except CaptchaBlockedError:
        raise
    except Exception as exc:
        logger.warning("captcha handler failed, falling back to lock: %s", exc)

    raise_captcha_block(platform=platform, url=target, screenshot=str(shot or ""))


def raise_captcha_block(*, platform: str, url: str, screenshot: str = "") -> None:
    from app import db as store

    payload = {
        "status": "waiting_admin",
        "platform": platform,
        "url": url,
        "screenshot": screenshot,
        "at": datetime.now().isoformat(),
        "message": "CAPTCHA needs attention — page should be open. Solve it, then Unlock if needed.",
    }
    store.set_meta("captcha_lock", json.dumps(payload, ensure_ascii=False))
    store.set_meta("captcha_lock_flag", "1")
    logger.error("CAPTCHA lock engaged: %s", payload)
    try:
        from publishers.captcha_alerts import on_captcha_locked

        on_captcha_locked(payload)
    except Exception as exc:
        logger.warning("captcha alert hook failed: %s", exc)
    try:
        from publishers.captcha_solver import open_captcha_page

        open_captcha_page(url, screenshot=screenshot)
    except Exception as exc:
        logger.warning("open captcha page failed: %s", exc)
    raise CaptchaBlockedError(payload["message"])


def captcha_is_locked() -> bool:
    """
    True while CAPTCHA needs human attention.
    Auto-expires after CAPTCHA_LOCK_TTL_SEC so a forgotten lock cannot
    permanently kill uploads / trust-browse.
    """
    from app import db as store

    if store.get_meta("captcha_lock_flag", "") != "1":
        return False
    # TTL: default 45 minutes
    ttl = 45 * 60
    try:
        import os

        ttl = int(os.environ.get("AMP_CAPTCHA_LOCK_TTL_SEC", str(ttl)) or ttl)
    except Exception:
        pass
    raw = store.get_meta("captcha_lock", "")
    if not raw:
        return True
    try:
        payload = json.loads(raw)
        at = str(payload.get("at") or "")
        if at:
            locked_at = datetime.fromisoformat(at.replace("Z", "+00:00").split("+")[0])
            age = (datetime.now() - locked_at.replace(tzinfo=None)).total_seconds()
            if age > ttl:
                store.set_meta("captcha_lock_flag", "0")
                payload["status"] = "auto_expired"
                payload["expired_at"] = datetime.now().isoformat()
                store.set_meta("captcha_lock", json.dumps(payload, ensure_ascii=False))
                logger.warning("CAPTCHA lock auto-expired after %ss", int(age))
                try:
                    from pipeline.error_notebook import note_error

                    note_error(
                        subsystem="browser_automation",
                        fault_code="captcha_lock_auto_expired",
                        message=f"Lock cleared after {int(age)}s — retry uploads cautiously",
                        severity="warn",
                    )
                except Exception:
                    pass
                return False
    except Exception as exc:
        logger.debug("captcha lock ttl parse: %s", exc)
    return True


def captcha_status() -> dict:
    from app import db as store

    raw = store.get_meta("captcha_lock", "")
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    data["locked"] = store.get_meta("captcha_lock_flag", "") == "1"
    data["nag_count"] = store.get_meta("captcha_nag_count", "0")
    return data


def captcha_unlock(*, note: str = "") -> dict:
    from app import db as store

    store.set_meta("captcha_lock_flag", "0")
    prev = captcha_status()
    prev["status"] = "unlocked"
    prev["unlocked_at"] = datetime.now().isoformat()
    prev["admin_note"] = note
    store.set_meta("captcha_lock", json.dumps(prev, ensure_ascii=False))
    try:
        from publishers.captcha_alerts import on_captcha_unlocked

        prev["paused_task"] = on_captcha_unlocked(note=note)
    except Exception as exc:
        logger.warning("captcha unlock hook failed: %s", exc)
    return prev


def maybe_like(page, platform: str) -> bool:
    return do_like(page, platform, force_prob=0.35)


def do_like(page, platform: str, *, force_prob: float = 1.0) -> bool:
    if random.random() > force_prob:
        return False
    names = {
        "youtube": ["Like", "লাইক"],
        "facebook": ["Like", "লাইক", "Love"],
    }.get(platform, ["Like"])
    for name in names:
        btn = page.get_by_role("button", name=name)
        if btn.count():
            return human_click(page, btn)
    if platform == "youtube":
        like = page.locator("button[aria-label*='like' i], button[aria-label*='Like']")
        if like.count():
            return human_click(page, like)
    if platform == "facebook":
        like = page.locator("[aria-label='Like'], [aria-label='লাইক']")
        if like.count():
            return human_click(page, like.first)
    return False


def maybe_share(page, platform: str) -> bool:
    return do_share(page, platform, force_prob=0.12)


def do_share(page, platform: str, *, force_prob: float = 1.0) -> bool:
    if random.random() > force_prob:
        return False
    for name in ["Share", "শেয়ার"]:
        btn = page.get_by_role("button", name=name)
        if btn.count():
            if human_click(page, btn):
                human_sleep(0.8, 2.0)
                # Prefer copy-link style share; rarely complete a feed share
                copied = False
                for label in ["Copy link", "লিংক কপি", "Copy"]:
                    c = page.get_by_role("button", name=label)
                    if c.count():
                        human_click(page, c)
                        copied = True
                        human_sleep(0.4, 1.0)
                        break
                if not copied and random.random() < 0.15:
                    # leave dialog briefly like a hesitant human, then cancel
                    human_sleep(1.2, 2.8)
                page.keyboard.press("Escape")
                return True
    return False


def maybe_comment(page, platform: str, comments: Sequence[str]) -> bool:
    if random.random() > 0.18 or not comments:
        return False
    text = random.choice(list(comments))
    return do_comment(page, platform, text, force_prob=1.0)


def do_comment(page, platform: str, text: str, *, force_prob: float = 1.0) -> bool:
    if random.random() > force_prob or not (text or "").strip():
        return False
    try:
        if platform == "youtube":
            box = page.locator(
                "#simplebox-placeholder, ytd-commentbox #placeholder-area, #contenteditable-root"
            )
            if not box.count():
                aimless_scroll(page, bursts=2)
                box = page.locator("#simplebox-placeholder, #contenteditable-root")
            if box.count():
                human_click(page, box)
                human_sleep(0.5, 1.2)
                editable = page.locator("#contenteditable-root, div[contenteditable='true']")
                if editable.count():
                    human_paste_text(page, editable, text)
                    human_sleep(0.6, 1.5)
                    submit = page.get_by_role("button", name="Comment")
                    if not submit.count():
                        submit = page.get_by_role("button", name="কমেন্ট")
                    if submit.count():
                        return human_click(page, submit)
        else:
            box = page.get_by_placeholder("Write a comment")
            if not box.count():
                box = page.locator("div[aria-label*='comment' i], div[contenteditable='true']")
            if box.count():
                human_paste_text(page, box, text)
                page.keyboard.press("Enter")
                return True
    except Exception as exc:
        logger.debug("comment skip: %s", exc)
    return False


def do_subscribe_or_follow(page, platform: str) -> bool:
    try:
        if platform == "youtube":
            # Never click if already subscribed
            for sel in (
                "button[aria-label*='Subscribed' i]",
                "button[aria-label*='Unsubscribe' i]",
            ):
                if page.locator(sel).count():
                    return True
            for name in ["Subscribe", "সাবস্ক্রাইব"]:
                btn = page.get_by_role("button", name=name)
                if btn.count():
                    try:
                        lab = (btn.first.get_attribute("aria-label") or "").lower()
                        if "subscribed" in lab or "unsubscribe" in lab:
                            return True
                    except Exception:
                        pass
                    return human_click(page, btn.first)
            ch = page.locator("ytd-channel-name a, #channel-name a").first
            if ch.count():
                human_click(page, ch)
                human_sleep(1.5, 3.0)
                btn = page.get_by_role("button", name="Subscribe")
                if btn.count():
                    return human_click(page, btn.first)
        else:
            if page.locator("[aria-label='Following'], [aria-label*='Following' i]").count():
                return True
            for name in ["Follow", "ফলো", "Like Page", "লাইক"]:
                btn = page.get_by_role("button", name=name)
                if btn.count():
                    return human_click(page, btn.first)
    except Exception as exc:
        logger.debug("subscribe/follow skip: %s", exc)
    return False


def edit_own_comment(page, platform: str, old_text: str, new_text: str) -> bool:
    """Best-effort: find a comment containing old_text and edit to new_text."""
    if not old_text or not new_text or old_text == new_text:
        return False
    try:
        if platform == "youtube":
            # Open menu on a thread that still shows the typo
            threads = page.locator("ytd-comment-thread-renderer")
            n = min(threads.count(), 8)
            for i in range(n):
                t = threads.nth(i)
                body = t.locator("#content-text, yt-formatted-string#content-text")
                if not body.count():
                    continue
                raw = (body.first.inner_text() or "").strip()
                if old_text[:20] not in raw and raw != old_text:
                    continue
                menu = t.locator("#action-menu button, button[aria-label*='Action' i], button[aria-label*='More' i]")
                if not menu.count():
                    continue
                human_click(page, menu.first)
                human_sleep(0.4, 1.0)
                edit_item = page.get_by_role("menuitem", name="Edit")
                if not edit_item.count():
                    edit_item = page.get_by_text("Edit", exact=True)
                if not edit_item.count():
                    page.keyboard.press("Escape")
                    continue
                human_click(page, edit_item)
                human_sleep(0.5, 1.2)
                editable = t.locator("#contenteditable-root, div[contenteditable='true']")
                if not editable.count():
                    editable = page.locator("#contenteditable-root, div[contenteditable='true']")
                if editable.count():
                    try:
                        editable.first.fill("")
                    except Exception:
                        pass
                    human_paste_text(page, editable, new_text)
                    human_sleep(0.4, 1.0)
                    save = page.get_by_role("button", name="Save")
                    if not save.count():
                        save = page.get_by_role("button", name="সেভ")
                    if save.count():
                        return human_click(page, save)
            return False
        # Facebook edit is brittle — attempt kebab → Edit
        nodes = page.locator(f"text={old_text[:24]}")
        if nodes.count():
            human_click(page, nodes.first)
            human_sleep(0.3, 0.8)
            more = page.locator("[aria-label*='More' i], [aria-label*='অ্যাকশন' i]").first
            if more.count():
                human_click(page, more)
                human_sleep(0.4, 1.0)
                edit = page.get_by_text("Edit", exact=False)
                if edit.count():
                    human_click(page, edit.first)
                    human_sleep(0.5, 1.2)
                    box = page.locator("div[contenteditable='true']")
                    if box.count():
                        human_paste_text(page, box, new_text)
                        page.keyboard.press("Enter")
                        return True
    except Exception as exc:
        logger.debug("edit comment skip: %s", exc)
    return False


def warmup_browse(page, platform: str) -> None:
    """Idle human-like browsing before the real target action."""
    home = "https://www.youtube.com/" if platform == "youtube" else "https://www.facebook.com/"
    try:
        page.goto(home, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        return
    assert_no_captcha(page, platform=platform, url=home)
    human_sleep(1.2, 3.0)
    aimless_scroll(page, bursts=random.randint(2, 5))
    reading_pause()
    if platform == "youtube" and random.random() < 0.55:
        thumbs = page.locator("ytd-rich-item-renderer a#thumbnail, a#video-title-link")
        if thumbs.count():
            idx = random.randint(0, min(6, thumbs.count() - 1))
            human_click(page, thumbs.nth(idx))
            human_sleep(4, 12)
            maybe_like(page, "youtube")
            aimless_scroll(page, bursts=random.randint(1, 3))
            page.go_back(wait_until="domcontentloaded")
            human_sleep(1.0, 2.5)


def upload_ritual(page, platform: str = "youtube") -> None:
    """
    Pre-upload human ritual: warm home feed, scroll, occasional hover, then proceed.
    Call before navigating to the upload URL.
    """
    try:
        warmup_browse(page, platform)
    except Exception as exc:
        logger.debug("warmup skip: %s", exc)
        try:
            from pipeline.error_notebook import note_error

            note_error(
                subsystem="browser",
                fault_code="warmup_failed",
                message=str(exc)[:300],
                severity="info",
            )
        except Exception:
            pass
    # Extra hesitation before "going to create"
    human_sleep(0.8, 2.2)
    if random.random() < 0.45:
        aimless_scroll(page, bursts=1)
        reading_pause(_rand(0.5, 1.5))
    # Random mouse wander (no click)
    try:
        human_move(page, _rand(200, 900), _rand(120, 500))
        micro_pause()
        human_move(page, _rand(250, 1000), _rand(150, 560))
    except Exception:
        pass


def wait_human(page, selector: str, *, timeout_ms: int = 25000) -> bool:
    """Event-driven wait + human jitter (avoids fixed sleep chains)."""
    try:
        page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
        human_sleep(0.25, 0.9)
        return True
    except Exception:
        human_sleep(0.6, 1.4)
        return False


DEFAULT_COMMENTS = [
    "Nice!",
    "Great content 🔥",
    "Helpful, thanks!",
    "ভালো লাগলো",
    "দারুণ ভিডিও",
    "Informative 👍",
]
