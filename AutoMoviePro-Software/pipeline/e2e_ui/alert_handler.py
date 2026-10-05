"""Challenge detection + operator alert / pause-resume failover."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ChallengePaused(RuntimeError):
    """Automation paused pending operator resolution of a verification challenge."""


# Common challenge / gate selectors (best-effort heuristics)
DEFAULT_CHALLENGE_SELECTORS: List[str] = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='challenge']",
    "div.g-recaptcha",
    "#captcha",
    "[id*='captcha' i]",
    "[class*='captcha' i]",
    "text=/verify you are human/i",
    "text=/unusual traffic/i",
    "text=/confirm you.?re not a bot/i",
    "text=/security check/i",
    "text=/enter the characters/i",
    "[aria-label*='captcha' i]",
]


class AlertHandler:
    """
    Continuously watches for challenge overlays.
    On hit: pause → alert (webhook / local / existing captcha_alerts) → wait for resume.
    """

    def __init__(
        self,
        page: Any,
        *,
        platform: str = "e2e",
        screenshot_dir: str = "",
        extra_selectors: Optional[List[str]] = None,
        poll_interval_sec: float = 2.0,
        resume_timeout_sec: float = 1800.0,
        webhook_url: str = "",
    ) -> None:
        self.page = page
        self.platform = platform
        self.poll_interval_sec = poll_interval_sec
        self.resume_timeout_sec = resume_timeout_sec
        self.webhook_url = (webhook_url or "").strip()
        self.selectors = list(DEFAULT_CHALLENGE_SELECTORS) + list(extra_selectors or [])
        if screenshot_dir:
            self.screenshot_dir = Path(screenshot_dir)
        else:
            try:
                from app.config import DATA_DIR

                self.screenshot_dir = Path(DATA_DIR) / "e2e_ui_alerts"
            except Exception:
                self.screenshot_dir = Path(__file__).resolve().parents[2] / "data" / "e2e_ui_alerts"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._paused = threading.Event()
        self._resume = threading.Event()
        self._stop_watch = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None
        self.last_challenge: Dict[str, Any] = {}

    # ------------------------------------------------------------------ detect
    def challenge_visible(self) -> bool:
        for sel in self.selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:
                continue
        # Heuristic: large modal with verify language
        try:
            body = (self.page.inner_text("body") or "").lower()
            needles = ("captcha", "verify you are", "unusual traffic", "not a robot", "security check")
            if any(n in body for n in needles):
                # Avoid false positives on help pages mentioning captcha
                if "recaptcha" in body or "hcaptcha" in body or "verify you" in body:
                    return True
        except Exception:
            pass
        return False

    def check_or_raise(self) -> None:
        if self.challenge_visible():
            self._handle_challenge()

    # ------------------------------------------------------------------ alert
    def _screenshot(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.screenshot_dir / f"challenge_{self.platform}_{ts}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            try:
                self.page.screenshot(path=str(path))
            except Exception as exc:
                logger.warning("challenge screenshot failed: %s", exc)
                return ""
        return str(path)

    def _notify(self, payload: Dict[str, Any]) -> None:
        logger.error(
            "E2E CHALLENGE DETECTED platform=%s url=%s shot=%s",
            payload.get("platform"),
            payload.get("url"),
            payload.get("screenshot"),
        )
        # Prefer existing captcha alert stack
        try:
            from publishers.captcha_alerts import send_alert_once

            send_alert_once(payload)
        except Exception as exc:
            logger.debug("captcha_alerts hook skip: %s", exc)

        # Optional direct webhook override
        url = self.webhook_url
        if not url:
            try:
                from app import db as store

                url = (store.get_meta("captcha_webhook_url", "") or "").strip()
            except Exception:
                url = ""
        if url:
            try:
                import json
                import urllib.request

                data = json.dumps({"text": "E2E challenge pause", "e2e": payload}).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    resp.read()
            except Exception as exc:
                logger.warning("e2e webhook failed: %s", exc)

        # Local beep
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            print("\a", end="", flush=True)

        # Persist pause meta for dashboard
        try:
            from app import db as store

            store.set_meta("e2e_challenge_paused", "1")
            store.set_meta("e2e_challenge_url", str(payload.get("url") or ""))
            store.set_meta("e2e_challenge_screenshot", str(payload.get("screenshot") or ""))
            store.set_meta("e2e_challenge_at", str(payload.get("at") or ""))
        except Exception:
            pass

    def _handle_challenge(self) -> None:
        url = ""
        try:
            url = self.page.url
        except Exception:
            pass
        shot = self._screenshot()
        payload = {
            "platform": self.platform,
            "url": url,
            "screenshot": shot,
            "at": datetime.now(timezone.utc).isoformat(),
            "source": "e2e_ui.AlertHandler",
        }
        self.last_challenge = payload
        self._notify(payload)
        self._paused.set()
        self._resume.clear()
        logger.warning(
            "Automation PAUSED — solve challenge in browser, then call AlertHandler.resume() "
            "or set meta e2e_challenge_resume=1 (timeout=%.0fs)",
            self.resume_timeout_sec,
        )
        deadline = time.time() + self.resume_timeout_sec
        while time.time() < deadline:
            if self._resume.is_set():
                break
            # Dashboard unlock
            try:
                from app import db as store

                if (store.get_meta("e2e_challenge_resume", "") or "").strip() in ("1", "true", "yes"):
                    store.set_meta("e2e_challenge_resume", "0")
                    break
                if (store.get_meta("captcha_lock", "") or "").strip() in ("0", "", "false"):
                    # If global captcha unlocked and challenge gone
                    if not self.challenge_visible():
                        break
            except Exception:
                pass
            if not self.challenge_visible():
                logger.info("Challenge DOM cleared — auto-resume")
                break
            time.sleep(2.0)
        else:
            raise ChallengePaused(
                f"Operator did not resolve challenge within {self.resume_timeout_sec:.0f}s url={url}"
            )

        self._paused.clear()
        self._resume.set()
        try:
            from app import db as store

            store.set_meta("e2e_challenge_paused", "0")
        except Exception:
            pass
        logger.info("E2E challenge resolved — resuming automation")

    def resume(self) -> None:
        self._resume.set()
        try:
            from app import db as store

            store.set_meta("e2e_challenge_resume", "1")
        except Exception:
            pass

    # ------------------------------------------------------------------ watchdog thread
    def start_watchdog(self) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._stop_watch.clear()

        def _loop() -> None:
            while not self._stop_watch.is_set():
                try:
                    if not self._paused.is_set() and self.challenge_visible():
                        try:
                            self._handle_challenge()
                        except ChallengePaused as exc:
                            logger.error("challenge wait timed out in watchdog: %s", exc)
                except Exception as exc:
                    logger.debug("challenge watch tick: %s", exc)
                self._stop_watch.wait(self.poll_interval_sec)

        self._watch_thread = threading.Thread(target=_loop, name="e2e-challenge-watch", daemon=True)
        self._watch_thread.start()

    def stop_watchdog(self) -> None:
        self._stop_watch.set()
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=3.0)

    def guarded(self, fn: Callable[[], Any]) -> Any:
        """Run a callable, checking for challenges before and after."""
        self.check_or_raise()
        result = fn()
        self.check_or_raise()
        return result
