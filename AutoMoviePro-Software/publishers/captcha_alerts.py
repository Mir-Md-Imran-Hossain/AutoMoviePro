"""
Aggressive CAPTCHA admin alerting + auto-resume hooks.

When captcha_lock engages:
  - Dashboard banner (existing)
  - Repeating nag every ~30s (sound + meta counter + optional webhook/Telegram)
  - Escalation ticket once
  - On unlock OR DOM clear: resume marker for paused tasks
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_nag_thread: Optional[threading.Thread] = None
_nag_stop = threading.Event()


def _webhook_url() -> str:
    from app import db as store
    from app.config import settings

    return (
        store.get_meta("captcha_webhook_url", "")
        or getattr(settings, "captcha_webhook_url", "")
        or ""
    ).strip()


def _telegram_cfg() -> Dict[str, str]:
    from app import db as store

    return {
        "token": (store.get_meta("telegram_bot_token", "") or "").strip(),
        "chat_id": (store.get_meta("telegram_chat_id", "") or "").strip(),
    }


def _beep() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        winsound.Beep(880, 180)
        winsound.Beep(660, 180)
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


def _post_json(url: str, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        resp.read()


def send_alert_once(payload: Dict[str, Any]) -> None:
    """Fire all configured channels once."""
    _beep()
    msg = (
        f"🚨 CAPTCHA LOCK — AutoMovie Pro\n"
        f"Platform: {payload.get('platform')}\n"
        f"URL: {payload.get('url')}\n"
        f"Solve in the open browser, then Admin Unlock in the app.\n"
        f"At: {payload.get('at')}"
    )
    wh = _webhook_url()
    if wh:
        try:
            _post_json(wh, {"text": msg, "captcha": payload})
        except Exception as exc:
            logger.warning("captcha webhook failed: %s", exc)
    tg = _telegram_cfg()
    if tg["token"] and tg["chat_id"]:
        try:
            url = f"https://api.telegram.org/bot{tg['token']}/sendMessage"
            _post_json(url, {"chat_id": tg["chat_id"], "text": msg})
        except Exception as exc:
            logger.warning("telegram captcha alert failed: %s", exc)
    # Local escalation row
    try:
        from app import db as store

        store.add_agent_escalation(
            reason=f"CAPTCHA: {payload.get('platform')} {payload.get('url')}",
            detail=json.dumps(payload, ensure_ascii=False)[:2000],
        )
    except Exception:
        try:
            from app import db as store

            store.set_meta(
                "captcha_last_escalation",
                json.dumps({"at": datetime.now().isoformat(), "payload": payload}, ensure_ascii=False),
            )
        except Exception:
            pass


def start_nag_loop() -> None:
    global _nag_thread
    if _nag_thread and _nag_thread.is_alive():
        return
    _nag_stop.clear()

    def _loop():
        from publishers.human_browser import captcha_is_locked, captcha_status

        n = 0
        while not _nag_stop.is_set():
            if not captcha_is_locked():
                break
            n += 1
            st = captcha_status()
            try:
                from app import db as store

                store.set_meta("captcha_nag_count", str(n))
                store.set_meta("captcha_nag_at", datetime.now().isoformat())
            except Exception:
                pass
            if n == 1 or n % 1 == 0:
                # Every tick (~30s) beep + optional remote
                _beep()
                if n == 1 or n % 2 == 0:
                    send_alert_once(st if isinstance(st, dict) else {})
            # Wait 30s or until stop
            if _nag_stop.wait(30):
                break
        logger.info("captcha nag loop ended")

    _nag_thread = threading.Thread(target=_loop, daemon=True, name="captcha-nag")
    _nag_thread.start()


def stop_nag_loop() -> None:
    _nag_stop.set()


def on_captcha_locked(payload: Dict[str, Any]) -> None:
    send_alert_once(payload)
    start_nag_loop()
    # Mark paused work
    try:
        from app import db as store

        store.set_meta(
            "captcha_paused_task",
            json.dumps(
                {
                    "platform": payload.get("platform"),
                    "url": payload.get("url"),
                    "at": payload.get("at"),
                    "resume": "pending",
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        pass


def on_captcha_unlocked(*, note: str = "") -> Dict[str, Any]:
    stop_nag_loop()
    from app import db as store

    raw = store.get_meta("captcha_paused_task", "")
    paused: Dict[str, Any] = {}
    try:
        paused = json.loads(raw) if raw else {}
    except Exception:
        paused = {}
    paused["resume"] = "ready"
    paused["unlocked_at"] = datetime.now().isoformat()
    paused["admin_note"] = note
    store.set_meta("captcha_paused_task", json.dumps(paused, ensure_ascii=False))
    store.set_meta("captcha_nag_count", "0")
    return paused


def tick_captcha_watch() -> None:
    """Called from scheduler — keep nag alive if lock still set."""
    from publishers.human_browser import captcha_is_locked

    if captcha_is_locked():
        start_nag_loop()
    else:
        stop_nag_loop()
