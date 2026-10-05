"""
Browser automation intelligence layer.

Purpose:
  - Make every UI action human-paced and non-looping
  - Detect glitches / anomalies that look automated
  - Persist fixable logs (error_notebook + jsonl) for the in-app agent
  - Soft-recover instead of hammering selectors

This does NOT claim permanent undetectability — it reduces the most common
bot fingerprints: fixed timing, action spam, retry storms, blind clicks.
"""
from __future__ import annotations

import json
import logging
import math
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LAST_ACTION_AT: Dict[str, float] = {}
_RECENT: Deque[Tuple[float, str]] = deque(maxlen=80)
_FAIL_STREAK: Dict[str, int] = {}
_CIRCUIT_UNTIL: Dict[str, float] = {}

GLITCH_DIR = DATA_DIR / "browser_glitches"
GLITCH_JSONL = GLITCH_DIR / "glitches.jsonl"

# Cooldowns (seconds) — prevent machine-gun clicks
DEFAULT_COOLDOWNS = {
    "click": (0.45, 1.4),
    "like": (2.5, 7.0),
    "comment": (8.0, 22.0),
    "share": (6.0, 18.0),
    "subscribe": (4.0, 12.0),
    "navigate": (1.2, 3.5),
    "scroll": (0.35, 1.2),
    "type": (0.2, 0.8),
}

# Same fingerprint failing this many times → circuit open
CIRCUIT_FAILS = 3
CIRCUIT_COOLDOWN_SEC = 120.0


def human_delay(lo: float = 0.4, hi: float = 1.8) -> float:
    """
    Log-normal-ish delay between lo..hi (humans are not uniform).
    Median closer to lo; occasional longer pauses.
    """
    lo = max(0.05, float(lo))
    hi = max(lo + 0.05, float(hi))
    # map normal → skewed positive
    mu = math.log((lo + hi) / 2.2)
    sigma = 0.45
    val = random.lognormvariate(mu, sigma)
    # rare "distraction" pause
    if random.random() < 0.07:
        val += random.uniform(1.2, 4.5)
    return max(lo, min(hi * 1.35, val))


def smart_sleep(lo: float = 0.4, hi: float = 1.8) -> None:
    time.sleep(human_delay(lo, hi))


def _key(platform: str, action: str, target: str = "") -> str:
    t = (target or "")[:120].lower()
    return f"{platform}|{action}|{t}"


def circuit_open(platform: str, action: str, target: str = "") -> bool:
    k = _key(platform, action, target)
    until = _CIRCUIT_UNTIL.get(k, 0.0)
    return time.time() < until


def _trip_circuit(platform: str, action: str, target: str = "", *, reason: str = "") -> None:
    k = _key(platform, action, target)
    _CIRCUIT_UNTIL[k] = time.time() + CIRCUIT_COOLDOWN_SEC
    note_glitch(
        platform=platform,
        fault_code="circuit_open",
        message=f"{action} paused {int(CIRCUIT_COOLDOWN_SEC)}s — {reason or 'repeat failures'}",
        severity="warn",
        context={"target": target[:200], "action": action},
    )


def respect_cooldown(action: str, *, platform: str = "", target: str = "") -> None:
    """Block until human-like gap since last similar action."""
    lo, hi = DEFAULT_COOLDOWNS.get(action, (0.4, 1.2))
    k = _key(platform or "any", action, target)
    with _LOCK:
        last = _LAST_ACTION_AT.get(k, 0.0)
        # Also enforce global click pacing
        g_last = _LAST_ACTION_AT.get("global_click", 0.0) if action == "click" else 0.0
    need = human_delay(lo, hi)
    wait = max(0.0, (last + need) - time.time())
    if action == "click":
        wait = max(wait, max(0.0, (g_last + human_delay(0.25, 0.9)) - time.time()))
    if wait > 0:
        time.sleep(wait)


def mark_action(action: str, *, platform: str = "", target: str = "", ok: bool = True) -> None:
    k = _key(platform or "any", action, target)
    now = time.time()
    with _LOCK:
        _LAST_ACTION_AT[k] = now
        if action == "click":
            _LAST_ACTION_AT["global_click"] = now
        _RECENT.append((now, f"{k}|{'ok' if ok else 'fail'}"))
        if ok:
            _FAIL_STREAK[k] = 0
        else:
            _FAIL_STREAK[k] = int(_FAIL_STREAK.get(k, 0)) + 1
            streak = _FAIL_STREAK[k]
        streak = _FAIL_STREAK.get(k, 0)
    if not ok and streak >= CIRCUIT_FAILS:
        _trip_circuit(platform or "any", action, target, reason=f"fail_streak={streak}")


def detect_action_loop(*, window_sec: float = 25.0, same_limit: int = 5) -> Optional[str]:
    """If the same action fingerprint repeats too fast → loop smell."""
    now = time.time()
    counts: Dict[str, int] = {}
    with _LOCK:
        for ts, label in list(_RECENT):
            if now - ts > window_sec:
                continue
            # strip ok/fail
            base = label.rsplit("|", 1)[0]
            counts[base] = counts.get(base, 0) + 1
    for base, n in counts.items():
        if n >= same_limit:
            return base
    return None


def note_glitch(
    *,
    platform: str,
    fault_code: str,
    message: str,
    severity: str = "warn",
    context: Optional[Dict[str, Any]] = None,
    url: str = "",
) -> None:
    """Write to error_notebook + durable jsonl for agent / admin fix later."""
    ctx = dict(context or {})
    if url:
        ctx["url"] = url[:400]
    ctx["platform"] = platform
    ctx["logged_at"] = datetime.now().isoformat(timespec="seconds")

    try:
        from pipeline.error_notebook import note_error

        note_error(
            subsystem="browser_automation",
            fault_code=fault_code,
            message=message[:500],
            severity=severity,
            context=ctx,
        )
    except Exception as exc:
        logger.debug("notebook glitch write failed: %s", exc)

    try:
        GLITCH_DIR.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": ctx["logged_at"],
            "platform": platform,
            "fault_code": fault_code,
            "message": message[:500],
            "severity": severity,
            "context": ctx,
        }
        with GLITCH_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("jsonl glitch write failed: %s", exc)

    try:
        from pipeline.live_activity import log as live_log

        live_log("browser_glitch", f"{fault_code}: {message[:120]}")
    except Exception:
        pass


def list_recent_glitches(limit: int = 80) -> List[Dict[str, Any]]:
    if not GLITCH_JSONL.exists():
        return []
    try:
        lines = GLITCH_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines()
        out: List[Dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        out.reverse()
        return out[:limit]
    except Exception:
        return []


def summarize_glitches_for_agent(limit: int = 12) -> str:
    rows = list_recent_glitches(limit=limit)
    if not rows:
        return ""
    parts = ["Recent browser-automation glitches (fix later):"]
    for r in rows[:limit]:
        parts.append(
            f"- [{r.get('severity')}] {r.get('fault_code')}: {r.get('message')} "
            f"({r.get('platform')})"
        )
    return "\n".join(parts)


def page_health(page, *, platform: str = "") -> Dict[str, Any]:
    """
    Quick health scan — blank/error/login-wall pages should abort the action,
    not keep clicking into the void (classic bot smell).
    """
    info: Dict[str, Any] = {"ok": True, "reason": ""}
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
        info.update({"ok": False, "reason": "no_url"})
        return info

    bad_markers = (
        "chrome-error://",
        "about:blank",
        "/sorry/",
        "err_internet",
        "err_connection",
        "err_timed_out",
        "err_name_not_resolved",
    )
    if any(m in url for m in bad_markers):
        info.update({"ok": False, "reason": "error_page", "url": url})
        note_glitch(platform=platform, fault_code="error_page", message=url[:200], severity="error", url=url)
        return info

    # Login walls that block engage
    login_walls = (
        "accounts.google.com/signin",
        "facebook.com/login",
        "facebook.com/checkpoint",
    )
    if any(m in url for m in login_walls):
        info.update({"ok": False, "reason": "login_wall", "url": url})
        note_glitch(
            platform=platform,
            fault_code="login_wall",
            message="Session looks logged out — reconnect YouTube/Facebook",
            severity="error",
            url=url,
        )
        return info

    try:
        title = (page.title() or "").strip().lower()
        if title in ("", "about:blank") or "isn't working" in title or "error" == title:
            # soft — don't always fail
            if random.random() < 0.5:
                info.update({"ok": False, "reason": "blank_or_error_title", "title": title})
                note_glitch(
                    platform=platform,
                    fault_code="blank_page",
                    message=f"title={title}",
                    severity="warn",
                    url=url,
                )
                return info
    except Exception:
        pass

    info["url"] = url
    return info


def safe_goto(page, url: str, *, platform: str = "", timeout_ms: int = 90000) -> bool:
    """Navigate with settle time + health check — no instant action after load."""
    if circuit_open(platform, "navigate", url):
        note_glitch(platform=platform, fault_code="navigate_circuit", message=url[:180], url=url)
        return False
    respect_cooldown("navigate", platform=platform, target=url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as exc:
        mark_action("navigate", platform=platform, target=url, ok=False)
        note_glitch(
            platform=platform,
            fault_code="navigate_failed",
            message=str(exc)[:240],
            severity="error",
            url=url,
        )
        return False

    # Human settle: look at page before acting
    smart_sleep(1.2, 3.2)
    try:
        # Prefer network quieter, but don't hang forever
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        smart_sleep(0.6, 1.6)

    health = page_health(page, platform=platform)
    ok = bool(health.get("ok"))
    mark_action("navigate", platform=platform, target=url, ok=ok)
    if not ok:
        return False

    loop = detect_action_loop()
    if loop:
        note_glitch(
            platform=platform,
            fault_code="action_loop_smell",
            message=f"Repeated pattern: {loop}",
            severity="warn",
            url=url,
        )
        smart_sleep(3.0, 7.0)  # break the rhythm
    return True


def smart_click(page, locator, *, platform: str = "", action: str = "click", target: str = "") -> bool:
    """
    Scroll into view → human move → click, with cooldown + circuit breaker.
    Never hammers the same dead locator.
    """
    if circuit_open(platform, action, target):
        return False
    respect_cooldown(action if action != "click" else "click", platform=platform, target=target)

    try:
        loc = locator.first if hasattr(locator, "first") else locator
        if hasattr(loc, "count") and loc.count() == 0:
            mark_action(action, platform=platform, target=target, ok=False)
            return False

        # Bring into view gently
        try:
            loc.scroll_into_view_if_needed(timeout=4000)
            smart_sleep(0.15, 0.55)
        except Exception:
            pass

        # Visibility guard
        try:
            if hasattr(loc, "is_visible") and not loc.is_visible():
                mark_action(action, platform=platform, target=target, ok=False)
                note_glitch(
                    platform=platform,
                    fault_code="click_invisible",
                    message=f"action={action} target={target[:80]}",
                    severity="info",
                )
                return False
        except Exception:
            pass

        from publishers.human_browser import human_click

        ok = bool(human_click(page, loc))
        mark_action(action, platform=platform, target=target, ok=ok)
        if not ok:
            note_glitch(
                platform=platform,
                fault_code="click_failed",
                message=f"action={action}",
                severity="info",
                context={"target": target[:120]},
            )
        return ok
    except Exception as exc:
        mark_action(action, platform=platform, target=target, ok=False)
        note_glitch(
            platform=platform,
            fault_code="click_exception",
            message=str(exc)[:240],
            severity="warn",
            context={"action": action, "target": target[:120]},
        )
        return False


def run_guarded(
    fn: Callable[[], bool],
    *,
    platform: str,
    action: str,
    target: str = "",
    retries: int = 2,
) -> bool:
    """Soft retries with backoff; trips circuit on repeated failure; never infinite."""
    if circuit_open(platform, action, target):
        return False
    retries = max(1, min(3, int(retries)))
    for attempt in range(retries):
        loop = detect_action_loop(window_sec=20, same_limit=6)
        if loop and action in loop:
            note_glitch(
                platform=platform,
                fault_code="abort_loop",
                message=f"Aborted {action} — loop smell on {loop}",
                severity="warn",
            )
            smart_sleep(4.0, 9.0)
            return False
        try:
            if fn():
                mark_action(action, platform=platform, target=target, ok=True)
                return True
        except Exception as exc:
            # Captcha must bubble
            if exc.__class__.__name__ == "CaptchaBlockedError":
                raise
            note_glitch(
                platform=platform,
                fault_code=f"{action}_exception",
                message=str(exc)[:240],
                severity="warn",
                context={"attempt": attempt + 1, "target": target[:120]},
            )
        mark_action(action, platform=platform, target=target, ok=False)
        smart_sleep(0.5 + attempt * 0.6, 1.4 + attempt * 1.1)
    return False


def idle_human_moment(page, *, chance: float = 0.28) -> None:
    """Occasional aimless mouse / tiny scroll — breaks robotic cadence."""
    if random.random() > chance:
        return
    try:
        from publishers.human_browser import aimless_scroll, human_move

        if random.random() < 0.55:
            human_move(page, random.randint(120, 1100), random.randint(100, 700))
        if random.random() < 0.4:
            aimless_scroll(page, bursts=1)
        smart_sleep(0.4, 1.8)
    except Exception:
        smart_sleep(0.3, 1.0)


def inject_stealth_init(context_or_page) -> None:
    """Best-effort webdriver / chrome-runtime patches when not using Patchright."""
    script = """
    (() => {
      try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      } catch (e) {}
      try {
        window.chrome = window.chrome || { runtime: {} };
      } catch (e) {}
      try {
        const orig = navigator.permissions && navigator.permissions.query;
        if (orig) {
          navigator.permissions.query = (params) => (
            params && params.name === 'notifications'
              ? Promise.resolve({ state: Notification.permission })
              : orig(params)
          );
        }
      } catch (e) {}
      try {
        Object.defineProperty(navigator, 'plugins', {
          get: () => [1, 2, 3, 4, 5],
        });
      } catch (e) {}
      try {
        Object.defineProperty(navigator, 'languages', {
          get: () => ['en-US', 'en', 'bn'],
        });
      } catch (e) {}
    })();
    """
    try:
        # Playwright Page
        if hasattr(context_or_page, "add_init_script"):
            context_or_page.add_init_script(script)
            return
    except Exception as exc:
        logger.debug("stealth init skip: %s", exc)
