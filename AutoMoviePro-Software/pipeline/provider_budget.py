"""
Per-provider free-tier budgets + circuit breakers (OpenRouter, HuggingFace).

Prevents the Google-style wipe: never spray every key × every model when
one free-tier endpoint returns 429/402.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent
_lock = threading.RLock()

# Conservative free-tier defaults (override via env)
DEFAULTS = {
    "openrouter": {
        "hourly": 40,
        "daily": 150,
        "max_keys_per_call": 1,
        "max_models_per_call": 2,
        "circuit_ttl_sec": 2 * 60 * 60,
        "circuit_strikes": 3,
    },
    "huggingface": {
        "hourly": 60,
        "daily": 400,
        "max_keys_per_call": 1,
        "max_models_per_call": 2,
        "circuit_ttl_sec": 1 * 60 * 60,
        "circuit_strikes": 3,
    },
    "groq": {
        "hourly": 80,
        "daily": 500,
        "max_keys_per_call": 1,
        "max_models_per_call": 2,
        "circuit_ttl_sec": 30 * 60,  # 30m — do not black out for hours on one 429
        "circuit_strikes": 3,
    },
    "cerebras": {
        "hourly": 60,
        "daily": 300,
        "max_keys_per_call": 1,
        "max_models_per_call": 2,
        "circuit_ttl_sec": 30 * 60,
        "circuit_strikes": 3,
    },
    "freetheai": {
        "hourly": 40,
        "daily": 200,
        "max_keys_per_call": 1,
        "max_models_per_call": 1,
        "circuit_ttl_sec": 60 * 60,
        "circuit_strikes": 3,
    },
}


class ProviderCircuitOpen(RuntimeError):
    pass


class ProviderBudgetExceeded(RuntimeError):
    pass


def _state_path(provider: str) -> Path:
    return STATE_DIR / f"{provider}_budget_state.json"


def _load(provider: str) -> dict:
    path = _state_path(provider)
    if not path.exists():
        return {
            "calls": [],
            "circuit_open": False,
            "circuit_reason": "",
            "circuit_until": 0.0,
            "strikes": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("strikes", [])
        return data
    except Exception:
        return {
            "calls": [],
            "circuit_open": False,
            "circuit_reason": "",
            "circuit_until": 0.0,
            "strikes": [],
        }


def record_failure(provider: str, exc_or_msg) -> None:
    """Open circuit only after N rate-limit strikes in a short window (default 3 / 10m)."""
    if not is_rate_limit_error(exc_or_msg):
        return
    cfg = _cfg(provider)
    need = max(1, int(cfg.get("circuit_strikes") or 3))
    now = time.time()
    window = 600.0  # 10 minutes
    with _lock:
        state = _load(provider)
        strikes = [float(t) for t in (state.get("strikes") or []) if now - float(t) < window]
        strikes.append(now)
        state["strikes"] = strikes
        _save(provider, state)
        if len(strikes) < need:
            logger.warning(
                "%s rate-limit strike %s/%s — not opening circuit yet: %s",
                provider,
                len(strikes),
                need,
                str(exc_or_msg)[:100],
            )
            return
    open_circuit(provider, str(exc_or_msg)[:120])


def _save(provider: str, state: dict) -> None:
    try:
        _state_path(provider).write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("%s budget save failed: %s", provider, exc)


def _cfg(provider: str) -> dict:
    base = dict(DEFAULTS.get(provider) or DEFAULTS["openrouter"])
    prefix = provider.upper()
    base["hourly"] = int(os.environ.get(f"AMP_{prefix}_HOURLY", base["hourly"]))
    base["daily"] = int(os.environ.get(f"AMP_{prefix}_DAILY", base["daily"]))
    base["max_keys_per_call"] = int(
        os.environ.get(f"AMP_{prefix}_MAX_KEYS", base["max_keys_per_call"])
    )
    base["max_models_per_call"] = int(
        os.environ.get(f"AMP_{prefix}_MAX_MODELS", base["max_models_per_call"])
    )
    base["circuit_ttl_sec"] = int(
        os.environ.get(f"AMP_{prefix}_CIRCUIT_TTL", base.get("circuit_ttl_sec", 3600))
    )
    base["circuit_strikes"] = int(
        os.environ.get(f"AMP_{prefix}_CIRCUIT_STRIKES", base.get("circuit_strikes", 3))
    )
    return base


def is_rate_limit_error(exc_or_msg) -> bool:
    msg = str(exc_or_msg or "").lower()
    # Payload / model-capacity errors are NOT org-wide rate limits — try next model.
    if "request too large" in msg or "payload too large" in msg or "context_length" in msg:
        return False
    if "model_not_found" in msg or "does not exist" in msg or "invalid model" in msg:
        return False
    # Narrow needles — avoid matching generic "exceeded" / "credit" in unrelated errors
    needles = (
        "429",
        "402",
        "rate limit",
        "rate_limit",
        "rate_limit_exceeded",
        "too many requests",
        "insufficient credits",
        "quota exceeded",
        "quota_exceeded",
        "free_tier",
        "free-tier",
        "free tier",
        "usage limit",
        "monthly limit",
        "payment required",
        "resource_exhausted",
    )
    return any(n in msg for n in needles)


def circuit_is_open(provider: str) -> bool:
    force = os.environ.get(f"AMP_FORCE_{provider.upper()}", "").strip() == "1"
    if force:
        return False
    with _lock:
        state = _load(provider)
        if not state.get("circuit_open"):
            return False
        until = float(state.get("circuit_until") or 0)
        if until and time.time() > until:
            state["circuit_open"] = False
            state["circuit_reason"] = ""
            state["circuit_until"] = 0.0
            _save(provider, state)
            return False
        return True


def open_circuit(provider: str, reason: str = "rate_limit") -> None:
    cfg = _cfg(provider)
    until = time.time() + float(cfg["circuit_ttl_sec"])
    with _lock:
        state = _load(provider)
        state["circuit_open"] = True
        state["circuit_reason"] = reason
        state["circuit_until"] = until
        _save(provider, state)
    logger.error(
        "%s CIRCUIT OPEN (%s) until %.0fs — skip to next provider",
        provider,
        reason,
        until - time.time(),
    )


def close_circuit(provider: str) -> None:
    with _lock:
        state = _load(provider)
        state["circuit_open"] = False
        state["circuit_reason"] = ""
        state["circuit_until"] = 0.0
        _save(provider, state)


def assert_allowed(provider: str) -> None:
    if circuit_is_open(provider):
        raise ProviderCircuitOpen(f"{provider} circuit open")
    cfg = _cfg(provider)
    now = time.time()
    with _lock:
        state = _load(provider)
        calls = [float(t) for t in (state.get("calls") or []) if now - float(t) < 86400]
        hourly = len([t for t in calls if now - t < 3600])
        daily = len(calls)
        if hourly >= int(cfg["hourly"]):
            raise ProviderBudgetExceeded(
                f"{provider} hourly budget {cfg['hourly']} hit ({hourly})"
            )
        if daily >= int(cfg["daily"]):
            open_circuit(provider, "daily_budget")
            raise ProviderBudgetExceeded(
                f"{provider} daily budget {cfg['daily']} hit ({daily})"
            )


def record_success(provider: str) -> None:
    now = time.time()
    with _lock:
        state = _load(provider)
        calls = [float(t) for t in (state.get("calls") or []) if now - float(t) < 86400]
        calls.append(now)
        state["calls"] = calls
        _save(provider, state)


def select_provider_keys(api_keys: Optional[List[str]], provider: str) -> List[str]:
    assert_allowed(provider)
    raw = [k.strip() for k in (api_keys or []) if (k or "").strip()]
    if not raw:
        return []
    n = max(1, min(2, int(_cfg(provider)["max_keys_per_call"])))
    return raw[:n]


def max_models(provider: str) -> int:
    return max(1, min(3, int(_cfg(provider)["max_models_per_call"])))


def status(provider: str) -> Dict[str, Any]:
    cfg = _cfg(provider)
    now = time.time()
    state = _load(provider)
    calls = [float(t) for t in (state.get("calls") or []) if now - float(t) < 86400]
    return {
        "provider": provider,
        "circuit_open": circuit_is_open(provider),
        "circuit_reason": state.get("circuit_reason"),
        "hourly_used": len([t for t in calls if now - t < 3600]),
        "daily_used": len(calls),
        "hourly_budget": cfg["hourly"],
        "daily_budget": cfg["daily"],
    }
