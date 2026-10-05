"""Free-tier API quota guard + auto-rotate for custom pipeline.

Rules:
  - Soft rotate when a key reaches ROTATE_AT (default 90%) of hourly/daily limit
  - Hard block at HARD_CAP (default 95%) — never allow a call that would cross ~100%
  - On HTTP 429 / quota errors: mark key exhausted and rotate immediately
  - If no healthy key remains: raise NeedMoreApiKeysError (ask user to add keys)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.RLock()
STATE_DIR = Path(__file__).resolve().parent / "_quota_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Conservative free-tier ceilings (override via env)
PROVIDER_LIMITS: Dict[str, Dict[str, float]] = {
    "google_localize": {
        "hourly": float(os.environ.get("AMP_LOCALIZE_HOURLY", "12")),
        "daily": float(os.environ.get("AMP_LOCALIZE_DAILY", "40")),
    },
    # Gemini TTS burns one call per shot — slightly tighter defaults
    "google_tts": {
        "hourly": float(os.environ.get("AMP_TTS_HOURLY", "20")),
        "daily": float(os.environ.get("AMP_TTS_DAILY", "60")),
    },
    "grok": {
        "hourly": float(os.environ.get("AMP_GROK_HOURLY", "20")),
        "daily": float(os.environ.get("AMP_GROK_DAILY", "50")),
    },
    "openrouter_grok": {
        "hourly": float(os.environ.get("AMP_OR_GROK_HOURLY", "30")),
        "daily": float(os.environ.get("AMP_OR_GROK_DAILY", "80")),
    },
}

ROTATE_AT = float(os.environ.get("AMP_API_ROTATE_AT", "0.90"))  # 90%
HARD_CAP = float(os.environ.get("AMP_API_HARD_CAP", "0.95"))  # 95% — never cross toward 100%


class NeedMoreApiKeysError(RuntimeError):
    """Raised when every key is at soft/hard quota — user must add more keys."""

    def __init__(self, provider: str, detail: str = ""):
        self.provider = provider
        msg = (
            f"API key pool exhausted for '{provider}'. "
            f"All keys reached {int(ROTATE_AT * 100)}–{int(HARD_CAP * 100)}% free-tier usage. "
            f"Please add another API key in .env and retry. {detail}"
        ).strip()
        super().__init__(msg)


def key_id(api_key: str) -> str:
    raw = (api_key or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _mask(api_key: str) -> str:
    k = (api_key or "").strip()
    return f"…{k[-4:]}" if len(k) >= 4 else "…????"


def _state_path(provider: str) -> Path:
    return STATE_DIR / f"{provider}_key_usage.json"


def _load(provider: str) -> dict:
    path = _state_path(provider)
    if not path.exists():
        return {"keys": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"keys": {}}


def _save(provider: str, state: dict) -> None:
    try:
        _state_path(provider).write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        logger.debug("quota save failed %s: %s", provider, exc)


def _limits(provider: str) -> Tuple[float, float]:
    cfg = PROVIDER_LIMITS.get(provider) or {"hourly": 20, "daily": 50}
    return float(cfg["hourly"]), float(cfg["daily"])


def _prune(calls: List[float], now: float) -> List[float]:
    day = 86400.0
    return [float(t) for t in calls if now - float(t) < day]


def usage_ratios(provider: str, api_key: str) -> Dict[str, Any]:
    """Return hourly/daily counts and fractions for one key."""
    hourly_lim, daily_lim = _limits(provider)
    kid = key_id(api_key)
    now = time.time()
    with _lock:
        state = _load(provider)
        entry = state.get("keys", {}).get(kid) or {}
        calls = _prune(list(entry.get("calls") or []), now)
        exhausted_until = float(entry.get("exhausted_until") or 0)
    hour_n = sum(1 for t in calls if now - t < 3600)
    day_n = len(calls)
    return {
        "key": _mask(api_key),
        "key_id": kid,
        "hourly_used": hour_n,
        "daily_used": day_n,
        "hourly_limit": hourly_lim,
        "daily_limit": daily_lim,
        "hourly_pct": (hour_n / hourly_lim) if hourly_lim else 0.0,
        "daily_pct": (day_n / daily_lim) if daily_lim else 0.0,
        "exhausted": bool(exhausted_until and exhausted_until > now),
        "exhausted_until": exhausted_until,
        "exhausted_reason": str(entry.get("exhausted_reason") or ""),
    }


def is_key_usable(provider: str, api_key: str, *, for_new_call: bool = True) -> bool:
    """True if key is under HARD_CAP and not marked exhausted."""
    info = usage_ratios(provider, api_key)
    if info["exhausted"]:
        return False
    # Projected usage after one more call
    h = info["hourly_used"] + (1 if for_new_call else 0)
    d = info["daily_used"] + (1 if for_new_call else 0)
    h_pct = h / info["hourly_limit"] if info["hourly_limit"] else 0
    d_pct = d / info["daily_limit"] if info["daily_limit"] else 0
    if h_pct >= HARD_CAP or d_pct >= HARD_CAP:
        return False
    return True


def should_rotate(provider: str, api_key: str) -> bool:
    """True when key reached soft rotate threshold (90%)."""
    info = usage_ratios(provider, api_key)
    if info["exhausted"]:
        return True
    return info["hourly_pct"] >= ROTATE_AT or info["daily_pct"] >= ROTATE_AT


def record_success(provider: str, api_key: str) -> Dict[str, Any]:
    now = time.time()
    kid = key_id(api_key)
    with _lock:
        state = _load(provider)
        keys = state.setdefault("keys", {})
        entry = keys.setdefault(kid, {"calls": [], "exhausted_until": 0.0, "last4": _mask(api_key)})
        calls = _prune(list(entry.get("calls") or []), now)
        calls.append(now)
        entry["calls"] = calls
        entry["last4"] = _mask(api_key)
        keys[kid] = entry
        state["keys"] = keys
        _save(provider, state)
    info = usage_ratios(provider, api_key)
    logger.info(
        "Quota %s %s hourly=%s/%s (%.0f%%) daily=%s/%s (%.0f%%)",
        provider,
        _mask(api_key),
        info["hourly_used"],
        int(info["hourly_limit"]),
        info["hourly_pct"] * 100,
        info["daily_used"],
        int(info["daily_limit"]),
        info["daily_pct"] * 100,
    )
    return info


def mark_exhausted(provider: str, api_key: str, reason: str = "rate_limit", *, hours: float = 6.0) -> None:
    """Cooldown key unusable until cooldown (never push to 100% again this window)."""
    now = time.time()
    kid = key_id(api_key)
    with _lock:
        state = _load(provider)
        keys = state.setdefault("keys", {})
        entry = keys.setdefault(kid, {"calls": [], "exhausted_until": 0.0, "last4": _mask(api_key)})
        entry["exhausted_until"] = now + max(1.0, hours) * 3600.0
        entry["exhausted_reason"] = str(reason)[:200]
        entry["last4"] = _mask(api_key)
        keys[kid] = entry
        state["keys"] = keys
        _save(provider, state)
    logger.warning(
        "Quota EXHAUSTED %s %s reason=%s cooldown=%.1fh",
        provider,
        _mask(api_key),
        reason,
        hours,
    )


def is_quota_http_error(exc_or_msg: Any) -> bool:
    msg = str(exc_or_msg or "").lower()
    needles = (
        "429",
        "402",
        "rate limit",
        "rate_limit",
        "too many requests",
        "quota",
        "resource_exhausted",
        "usage limit",
        "free_tier",
        "free-tier",
        "high demand",  # gemini 503 overload — treat as rotate signal
    )
    return any(n in msg for n in needles)


def pick_usable_key(
    provider: str,
    pool: List[str],
    *,
    prefer: Optional[str] = None,
    exclude: Optional[set] = None,
) -> str:
    """Pick first key under soft/hard caps. Raises NeedMoreApiKeysError if none."""
    exclude = exclude or set()
    ordered: List[str] = []
    if prefer and prefer in pool:
        ordered.append(prefer)
    for k in pool:
        if k not in ordered:
            ordered.append(k)

    soft_ok: List[str] = []
    for k in ordered:
        if k in exclude:
            continue
        if not is_key_usable(provider, k, for_new_call=True):
            continue
        if should_rotate(provider, k) and k == prefer:
            # Prefer already soft — try others first but keep as fallback
            soft_ok.append(k)
            continue
        if should_rotate(provider, k):
            soft_ok.append(k)
            continue
        return k

    if soft_ok:
        # Only soft-rotated keys left but still under HARD_CAP — use least-used
        soft_ok.sort(key=lambda k: usage_ratios(provider, k)["daily_pct"])
        return soft_ok[0]

    raise NeedMoreApiKeysError(
        provider,
        detail=f"Checked {len(pool)} key(s). Add more keys so the system can rotate before 100% limit.",
    )


def ensure_key_or_rotate(
    provider: str,
    current: Optional[str],
    pool: List[str],
) -> str:
    """Return current if still healthy; else auto-rotate to next usable key."""
    if current and is_key_usable(provider, current) and not should_rotate(provider, current):
        return current
    if current and is_key_usable(provider, current) and should_rotate(provider, current):
        logger.info(
            "Soft-rotate %s from %s at ≥%.0f%% usage",
            provider,
            _mask(current),
            ROTATE_AT * 100,
        )
    return pick_usable_key(provider, pool, prefer=None, exclude=set())
