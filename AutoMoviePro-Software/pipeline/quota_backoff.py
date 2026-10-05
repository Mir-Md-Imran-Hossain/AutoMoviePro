"""
Adaptive quota / rate-limit backoff for Google, Agnes, and TTS.

Design goals:
  - Per-key cool-downs so one exhausted free-tier key does not block siblings.
  - Global streak only for true all-keys-exhausted moments (and capped sleeps).
  - Short ladder for train loops; never multi-hour mid-scene sleeps.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent / "quota_backoff_state.json"

# Consecutive GLOBAL all-keys failures → cool-down seconds (capped for train)
LADDER_SEC = (
    5 * 60,  # 5 min
    15 * 60,  # 15 min
    30 * 60,  # 30 min
    60 * 60,  # 1 hour max
)

# Per-key free-tier daily exhaustion — skip key for this long
PER_KEY_COOL_SEC = 20 * 60  # 20 minutes before retrying that key

# How long until a streak decays (no quota hit)
STREAK_DECAY_SEC = 6 * 60 * 60


def _load() -> dict:
    if not STATE_PATH.exists():
        return {"streak": 0, "last_hit_ts": 0.0, "provider_hits": {}, "keys": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        data.setdefault("keys", {})
        data.setdefault("provider_hits", {})
        return data
    except Exception:
        return {"streak": 0, "last_hit_ts": 0.0, "provider_hits": {}, "keys": {}}


def _save(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("quota state save failed: %s", exc)


def key_fingerprint(api_key: str) -> str:
    raw = (api_key or "").strip()
    if not raw:
        return "empty"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def is_quota_error(exc_or_msg) -> bool:
    msg = str(exc_or_msg or "")
    needles = (
        "429",
        "RESOURCE_EXHAUSTED",
        "quota",
        "rate limit",
        "rate_limit",
        "Too Many Requests",
        "queue_full",
    )
    low = msg.lower()
    return any(n.lower() in low for n in needles)


def cool_down_seconds(streak: int) -> int:
    if streak <= 0:
        return 0
    idx = min(len(LADDER_SEC) - 1, max(0, streak - 1))
    return int(LADDER_SEC[idx])


def record_key_quota_hit(api_key: str, provider: str = "google") -> int:
    """Mark one API key exhausted; siblings stay usable. Returns per-key cool seconds."""
    state = _load()
    fp = key_fingerprint(api_key)
    now = time.time()
    keys = state.setdefault("keys", {})
    entry = keys.get(fp) or {}
    entry["last_hit_ts"] = now
    entry["hits"] = int(entry.get("hits") or 0) + 1
    entry["provider"] = provider
    keys[fp] = entry
    hits = state.setdefault("provider_hits", {})
    hits[provider] = int(hits.get(provider) or 0) + 1
    # Do NOT inflate global streak on single-key failure
    _save(state)
    logger.warning(
        "Per-key quota hit provider=%s key=…%s cool=%ss",
        provider,
        (api_key or "")[-4:],
        PER_KEY_COOL_SEC,
    )
    return PER_KEY_COOL_SEC


def key_is_cooling(api_key: str) -> bool:
    state = _load()
    fp = key_fingerprint(api_key)
    entry = (state.get("keys") or {}).get(fp) or {}
    last = float(entry.get("last_hit_ts") or 0)
    if last <= 0:
        return False
    return (time.time() - last) < PER_KEY_COOL_SEC


def filter_usable_keys(api_keys: list, *, provider: str = "google") -> list:
    """Return keys not currently in per-key cool-down (preserves order)."""
    out = []
    for k in api_keys or []:
        k = (k or "").strip()
        if not k:
            continue
        if key_is_cooling(k):
            continue
        out.append(k)
    return out


def record_quota_hit(provider: str = "google") -> int:
    """
    Record a GLOBAL quota failure (all keys failed for this call).
    Returns recommended sleep seconds (does not sleep).
    """
    state = _load()
    now = time.time()
    last = float(state.get("last_hit_ts") or 0)
    streak = int(state.get("streak") or 0)
    if last and (now - last) > STREAK_DECAY_SEC:
        streak = 0
    streak += 1
    state["streak"] = streak
    state["last_hit_ts"] = now
    hits = state.setdefault("provider_hits", {})
    hits[provider] = int(hits.get(provider) or 0) + 1
    _save(state)
    wait = cool_down_seconds(streak)
    logger.warning(
        "Global quota hit provider=%s streak=%s → cool-down %ss (%.1fh)",
        provider,
        streak,
        wait,
        wait / 3600.0,
    )
    return wait


def record_quota_ok(provider: str = "google") -> None:
    """Successful API call — gently decay streak."""
    state = _load()
    streak = int(state.get("streak") or 0)
    if streak <= 0:
        return
    state["streak"] = max(0, streak - 1)
    _save(state)


def reset_quota_state(*, keep_per_key: bool = False) -> None:
    """Operator reset after false-positive global locks."""
    if keep_per_key:
        state = _load()
        state["streak"] = 0
        state["last_hit_ts"] = 0.0
        _save(state)
    else:
        _save({"streak": 0, "last_hit_ts": 0.0, "provider_hits": {}, "keys": {}})
    logger.warning("Quota state reset (keep_per_key=%s)", keep_per_key)


def pending_cool_down_remain(provider: str = "google") -> int:
    state = _load()
    last = float(state.get("last_hit_ts") or 0)
    streak = int(state.get("streak") or 0)
    if streak <= 0 or last <= 0:
        return 0
    need = cool_down_seconds(streak)
    remain = int(need - (time.time() - last))
    return max(0, remain)


def wait_for_quota_if_needed(
    *,
    provider: str = "google",
    exc_or_msg: Optional[object] = None,
    force: bool = False,
    max_sleep: Optional[int] = None,
) -> int:
    """
    If message looks like quota OR force=True, record hit and sleep the ladder.
    Returns seconds slept.
    """
    if not force and exc_or_msg is not None and not is_quota_error(exc_or_msg):
        return 0
    if not force and exc_or_msg is None:
        remain = pending_cool_down_remain(provider)
        if remain <= 0:
            return 0
        sleep_for = remain if max_sleep is None else min(remain, max_sleep)
        logger.warning(
            "Resuming after prior %s quota — sleeping remaining %ss (cap applied=%s)",
            provider,
            sleep_for,
            max_sleep is not None,
        )
        time.sleep(sleep_for)
        return sleep_for

    wait = record_quota_hit(provider)
    if max_sleep is not None:
        wait = min(wait, int(max_sleep))
    if wait > 0:
        logger.warning("Sleeping %ss for %s quota recovery…", wait, provider)
        time.sleep(wait)
    return wait
