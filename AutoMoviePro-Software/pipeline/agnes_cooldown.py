"""
Agnes pacing + long cooldown.

- Normal gap between creates (all-day rate-limit friendly).
- On 429 / hard API trouble: wait COOLDOWN (default 90 min, clamp 60–120)
  with heartbeats and periodic probe retries, THEN allow image fallback.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = SOFTWARE_ROOT / "data" / "live_lab" / "agnes_cooldown.json"

# Gap between successful/attempted creates — ~1/min keeps daily quota usable
DEFAULT_CREATE_GAP_SEC = float(os.environ.get("AMP_AGNES_CREATE_GAP_SEC", "55") or 55)
# After rate-limit / outage: wait this long before giving up to image fallback
DEFAULT_COOLDOWN_SEC = float(os.environ.get("AMP_AGNES_COOLDOWN_SEC", "5400") or 5400)  # 90m
COOLDOWN_MIN = 3600.0   # 1h floor
COOLDOWN_MAX = 7200.0   # 2h ceiling
PROBE_EVERY_SEC = float(os.environ.get("AMP_AGNES_PROBE_EVERY_SEC", "300") or 300)  # 5m


def _load() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(st: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def create_gap_seconds() -> float:
    return max(35.0, float(DEFAULT_CREATE_GAP_SEC))


def cooldown_seconds() -> float:
    return max(COOLDOWN_MIN, min(COOLDOWN_MAX, float(DEFAULT_COOLDOWN_SEC)))


def is_in_cooldown(now: Optional[float] = None) -> bool:
    st = _load()
    until = float(st.get("until_ts") or 0)
    return until > float(now or time.time())


def cooldown_remaining(now: Optional[float] = None) -> float:
    st = _load()
    until = float(st.get("until_ts") or 0)
    return max(0.0, until - float(now or time.time()))


def arm_cooldown(*, reason: str, seconds: Optional[float] = None) -> Dict[str, Any]:
    """Start / refresh Agnes cooldown window."""
    sec = float(seconds) if seconds is not None else cooldown_seconds()
    sec = max(COOLDOWN_MIN, min(COOLDOWN_MAX, sec))
    now = time.time()
    st = _load()
    # Don't shorten an existing longer window
    until = max(float(st.get("until_ts") or 0), now + sec)
    st.update(
        {
            "until_ts": until,
            "armed_at": now,
            "reason": (reason or "agnes_rate_limit")[:200],
            "probes": int(st.get("probes") or 0),
        }
    )
    _save(st)
    logger.warning(
        "Agnes cooldown armed %.0fm — reason=%s until=%s",
        (until - now) / 60.0,
        st["reason"],
        time.strftime("%H:%M:%S", time.localtime(until)),
    )
    try:
        from pipeline.live_activity import log as live_log

        live_log(
            "media",
            f"Agnes cooldown {(until - now) / 60.0:.0f}m — {st['reason']}",
            api="agnes",
            action="cooldown",
            level="warn",
        )
    except Exception:
        pass
    return st


def clear_cooldown() -> None:
    _save({"until_ts": 0, "cleared_at": time.time()})


def wait_create_gap(min_gap_s: Optional[float] = None, *, last_create_ts: float = 0.0) -> None:
    gap_need = float(min_gap_s) if min_gap_s is not None else create_gap_seconds()
    if last_create_ts <= 0:
        return
    wait = gap_need - (time.time() - last_create_ts)
    if wait <= 0:
        return
    logger.info("Agnes create gap: waiting %.1fs", wait)
    try:
        from pipeline.live_activity import log as live_log

        live_log("media", f"Agnes pacing {wait:.0f}s", api="agnes", action="rate_limit")
    except Exception:
        pass
    time.sleep(wait)


def wait_out_cooldown_or_abort(*, cancel_check=None) -> bool:
    """
    Block until cooldown ends (with heartbeats).
    Returns True if cooldown cleared / expired (caller may retry Agnes).
    Returns False if cancelled.
    """
    rem = cooldown_remaining()
    if rem <= 0:
        return True
    logger.warning("Agnes in cooldown — waiting %.0f min before retry/fallback", rem / 60.0)
    end = time.time() + rem
    next_beat = 0.0
    while time.time() < end:
        if cancel_check and cancel_check():
            return False
        left = end - time.time()
        if time.time() >= next_beat:
            try:
                from pipeline.live_activity import log as live_log

                live_log(
                    "media",
                    f"Agnes cooldown wait — {left / 60.0:.0f}m left (then retry, else image)",
                    api="agnes",
                    action="cooldown_wait",
                    level="warn",
                )
            except Exception:
                pass
            next_beat = time.time() + 60.0
        time.sleep(min(30.0, max(1.0, left)))
    clear_cooldown()
    return True


def looks_like_rate_limit(err: str) -> bool:
    t = (err or "").lower()
    return any(
        x in t
        for x in (
            "429",
            "rate limit",
            "rate_limit",
            "quota",
            "too many",
            "throttle",
            "503",
            "502",
            "capacity",
        )
    )
