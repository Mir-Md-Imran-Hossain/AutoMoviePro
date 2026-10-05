"""
Background human-like trust browsing.

Early phase: admin promo FB pages / YT channels (all customers).
Growth phase: also peer customer uploads from the website feed.

Sessions are staggered (≥5 min/hour), budget-capped, and FSM-driven
so they do not loop, spam, or look like brittle automation.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import db as store
from hidden_engage import activity_log
from hidden_engage.channel_fsm import (
    SessionCaps,
    engage_peer_video,
    engage_promo_hub,
    scroll_reels,
)
from hidden_engage.schedule_plan import active_window_now, mark_window_done, plan_summary
from hidden_engage.seed_feed import build_session_targets
from publishers.human_browser import (
    CaptchaBlockedError,
    assert_no_captcha,
    captcha_is_locked,
    human_sleep,
    reading_pause,
    warmup_browse,
)
from publishers.stealth_session import stealth_browser

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_RUNNING = False
META_RUNNING = "trust_browse_running"


def is_running() -> bool:
    return _RUNNING or store.get_meta(META_RUNNING, "") == "1"


def _set_running(flag: bool) -> None:
    global _RUNNING
    _RUNNING = flag
    store.set_meta(META_RUNNING, "1" if flag else "0")


def _busy_gates() -> Optional[str]:
    if captcha_is_locked():
        return "captcha_locked"
    if store.get_meta("live_lab_active", "") in ("1", "true", "yes"):
        return "live_lab_active"
    if is_running():
        return "already_running"
    return None


def tick_trust_browse() -> Dict[str, Any]:
    gate = _busy_gates()
    if gate == "already_running":
        return {"ok": True, "skipped": True, "reason": gate}
    if gate:
        return {"ok": False, "skipped": True, "reason": gate}

    window = active_window_now()
    if not window:
        return {"ok": True, "skipped": True, "reason": "no_active_window", "plan": plan_summary()}

    if not store.get_session():
        return {"ok": False, "skipped": True, "reason": "not_logged_in"}

    t = threading.Thread(
        target=_run_window_safe,
        args=(window,),
        name=f"trust-browse-{window.get('id')}",
        daemon=True,
    )
    t.start()
    return {
        "ok": True,
        "started": True,
        "window": window.get("id"),
        "duration_min": window.get("duration_min"),
        "remaining_sec": window.get("remaining_sec"),
    }


def run_trust_session_now(*, minutes: int = 6) -> Dict[str, Any]:
    gate = _busy_gates()
    if gate and gate != "already_running":
        return {"ok": False, "error": gate}
    if is_running():
        return {"ok": False, "error": "already_running"}
    window = {
        "id": f"manual_{datetime.now().strftime('%H%M%S')}",
        "hour": datetime.now().hour,
        "start_min": datetime.now().minute,
        "duration_min": max(3, int(minutes)),
        "remaining_sec": max(180, int(minutes) * 60),
        "done": False,
        "manual": True,
    }
    return _run_window(window)


def _run_window_safe(window: Dict[str, Any]) -> None:
    try:
        _run_window(window)
    except Exception:
        logger.exception("trust browse window crashed")
        try:
            _set_running(False)
        except Exception:
            pass


def _run_window(window: Dict[str, Any]) -> Dict[str, Any]:
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "error": "lock_busy"}
    _set_running(True)
    summary: List[Dict[str, Any]] = []
    started = time.time()
    budget = int(window.get("remaining_sec") or int(window.get("duration_min", 5)) * 60)
    budget = max(120, min(budget, 18 * 60))
    deadline = started + budget

    activity_log.log_action(
        platform="system",
        action="session_start",
        detail=f"window={window.get('id')} budget_sec={budget}",
        meta={"window": window},
    )
    try:
        from pipeline.live_activity import log as live_log

        live_log("trust_browse", f"Trust browse started ({window.get('id')})")
    except Exception:
        pass

    channels = [c for c in store.list_channels() if c.get("enabled")]
    plan = build_session_targets(max_promo=random.randint(1, 2), max_peer=random.randint(0, 2))
    caps = SessionCaps()

    try:
        # Platform order randomized per session
        platforms = ["facebook", "youtube"]
        random.shuffle(platforms)

        for platform in platforms:
            if time.time() >= deadline - 25 or captcha_is_locked():
                break
            promo_for = [p for p in plan["promo"] if p.get("platform") == platform]
            peers_for = [p for p in plan["peers"] if p.get("platform") == platform]
            want_reels = bool(plan.get("do_reels") and platform == "facebook")

            if not promo_for and not peers_for and not want_reels:
                continue

            try:
                result = _run_platform_batch(
                    platform=platform,
                    channels=channels,
                    promo=promo_for,
                    peers=peers_for,
                    do_reels=want_reels,
                    caps=caps,
                    deadline=deadline,
                )
                summary.append(result)
            except CaptchaBlockedError as exc:
                activity_log.log_action(
                    platform=platform,
                    action="captcha_block",
                    detail=str(exc)[:200],
                    ok=False,
                )
                summary.append({"platform": platform, "ok": False, "error": "captcha_locked"})
                break
            except Exception as exc:
                logger.exception("platform batch failed: %s", platform)
                caps.errors += 1
                activity_log.log_action(
                    platform=platform,
                    action="batch_error",
                    detail=str(exc)[:240],
                    ok=False,
                )
                summary.append({"platform": platform, "ok": False, "error": str(exc)[:160]})
                # Soft continue other platform — don't cascade into a death loop
                if caps.errors >= 3:
                    break
                human_sleep(2.0, 5.0)
                continue

        if not window.get("manual"):
            mark_window_done(str(window.get("id")))

        try:
            activity_log.sync_unsynced_to_website()
        except Exception:
            pass

        elapsed = int(time.time() - started)
        activity_log.log_action(
            platform="system",
            action="session_end",
            detail=(
                f"window={window.get('id')} elapsed={elapsed}s "
                f"promo={plan.get('promo_total')} peer={plan.get('peer_total')} "
                f"caps_sub={caps.subscribes} comments={caps.comments}"
            ),
            meta={"summary": summary[:12]},
        )
        return {
            "ok": True,
            "window": window.get("id"),
            "elapsed_sec": elapsed,
            "summary": summary,
            "promo_total": plan.get("promo_total"),
            "peer_total": plan.get("peer_total"),
            "targets_promo": len(plan.get("promo") or []),
            "targets_peer": len(plan.get("peers") or []),
        }
    finally:
        _set_running(False)
        try:
            _LOCK.release()
        except Exception:
            pass
        try:
            from pipeline.live_activity import log as live_log

            live_log("trust_browse", "Trust browse session ended")
        except Exception:
            pass


def _pick_session(platform: str, channels: List[Dict[str, Any]]) -> Dict[str, str]:
    from publishers.session_vault import paths_for_channel

    key = "youtube_session" if platform == "youtube" else "facebook_session"
    for ch in channels:
        paths = paths_for_channel(platform, ch, lang_code="en")
        storage = paths.get("storage_state") or ""
        profile = paths.get("user_data_dir") or ""
        if (storage and Path(storage).exists()) or (Path(profile) / "Default").exists():
            return paths
        if ch.get(key):
            return {"storage_state": str(ch[key]), "user_data_dir": profile}
        try:
            from pipeline.lang_destinations import parse_lang_destinations

            dest = parse_lang_destinations(ch.get("lang_destinations_json"))
            for code, slot in dest.items():
                if slot.get(key):
                    return paths_for_channel(platform, ch, lang_code=code)
        except Exception:
            pass
    return {}


def _background_headless() -> bool:
    return os.environ.get("AMP_TRUST_HEADLESS", "").strip() == "1"


def _run_platform_batch(
    *,
    platform: str,
    channels: List[Dict[str, Any]],
    promo: List[Dict[str, Any]],
    peers: List[Dict[str, Any]],
    do_reels: bool,
    caps: SessionCaps,
    deadline: float,
) -> Dict[str, Any]:
    """
    One stealth browser per platform per session — avoids open/close thrash
    which looks more bot-like than a continuous human session.
    """
    paths = _pick_session(platform, channels)
    if not paths.get("storage_state") and not paths.get("user_data_dir"):
        activity_log.log_action(
            platform=platform,
            action="skip_no_session",
            ok=False,
            detail="Connect YouTube/Facebook session first",
        )
        return {"ok": False, "platform": platform, "error": "no_session"}

    actions: List[Dict[str, Any]] = []
    with stealth_browser(
        storage_state=paths.get("storage_state") or "",
        user_data_dir=paths.get("user_data_dir") or "",
        headless=_background_headless(),
        background=True,
    ) as (_pw, _browser, page, engine):
        logger.info("trust batch %s via %s promo=%s peers=%s", platform, engine, len(promo), len(peers))

        # Soft arrival — not every time (humans sometimes deep-link)
        if random.random() < 0.65:
            try:
                warmup_browse(page, platform)
                assert_no_captcha(page, platform=platform, url=page.url)
                reading_pause()
            except CaptchaBlockedError:
                raise
            except Exception as exc:
                logger.debug("warmup soft skip: %s", exc)

        # Admin promo hubs first (early-phase trust building)
        for hub in promo:
            if time.time() >= deadline - 30 or captcha_is_locked():
                break
            try:
                # Micro idle between hubs
                human_sleep(1.5, 4.5)
                res = engage_promo_hub(page, hub, caps=caps, deadline=deadline)
                actions.append({"type": "promo", **res})
            except CaptchaBlockedError:
                raise
            except Exception as exc:
                logger.warning("promo hub failed: %s", exc)
                caps.errors += 1
                activity_log.log_action(
                    platform=platform,
                    action="promo_error",
                    url=hub.get("url") or "",
                    detail=str(exc)[:200],
                    ok=False,
                )
                # Recover: try home, continue — never retry same hub in a tight loop
                try:
                    home = "https://www.youtube.com/" if platform == "youtube" else "https://www.facebook.com/"
                    page.goto(home, wait_until="domcontentloaded", timeout=45000)
                    human_sleep(1.5, 3.0)
                except Exception:
                    pass

        # Peer customer videos (when ecosystem has them)
        for item in peers:
            if time.time() >= deadline - 25 or captcha_is_locked():
                break
            try:
                human_sleep(1.2, 3.5)
                res = engage_peer_video(page, item, caps=caps, deadline=deadline)
                actions.append({"type": "peer", **res})
            except CaptchaBlockedError:
                raise
            except Exception as exc:
                caps.errors += 1
                activity_log.log_action(
                    platform=platform,
                    action="peer_error",
                    url=item.get("url") or "",
                    detail=str(exc)[:200],
                    ok=False,
                )

        # Occasional reels scroll — human habit
        if do_reels and platform == "facebook" and time.time() < deadline - 35:
            try:
                left = max(25.0, min(110.0, deadline - time.time() - 20))
                res = scroll_reels(page, seconds=left * random.uniform(0.45, 0.85), deadline=deadline)
                actions.append({"type": "reels", **res})
            except CaptchaBlockedError:
                raise
            except Exception as exc:
                logger.debug("reels skip: %s", exc)

        # Soft exit — land somewhere normal, pause (not abrupt close mid-video feel)
        try:
            if random.random() < 0.5:
                home = "https://www.youtube.com/" if platform == "youtube" else "https://www.facebook.com/"
                page.goto(home, wait_until="domcontentloaded", timeout=40000)
                human_sleep(1.0, 2.5)
        except Exception:
            pass

    return {
        "ok": True,
        "platform": platform,
        "engine": engine if "engine" in dir() else "stealth",
        "actions": actions,
        "caps": {
            "subscribes": caps.subscribes,
            "comments": caps.comments,
            "shares": caps.shares,
            "likes": caps.likes,
        },
    }
