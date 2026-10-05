"""
HARD Google API burn guard — single chokepoint for every generateContent call.

Root cause of the 18-key wipe
-----------------------------
Callers did: for key in ALL_KEYS: for model in MODELS: generate_content(...)
Free tier ~20 RPD/project. One translate failure × 18 keys × 3 models ≈ vault empty.

Non-negotiable policy (cannot be bypassed by callers)
------------------------------------------------------
1) ONE sticky healthy key per purpose (text/tts/critic/image) — never walk the vault.
2) ONE model attempt per key unless AMP_GOOGLE_MULTI_MODEL=1.
3) First free-tier limit:0 / generate_content_free_tier → OPEN circuit (~20h).
4) While circuit OPEN: gated_generate_content raises GoogleCircuitOpen (no more Google text).
5) Process-wide hourly budget (default 40) — further calls raise GoogleBudgetExceeded.
6) Text LLM should use pipeline.llm_router.chat_text (OpenRouter-first when circuit open).

Env knobs
---------
AMP_FORCE_GOOGLE=1           ignore circuit (dangerous; debug only)
AMP_PREFER_OPENROUTER=1      text path prefers OpenRouter always
AMP_GOOGLE_MAX_KEYS=1        keys tried per gated call (hard capped at 2)
AMP_GOOGLE_HOURLY_BUDGET=40  max gated Google calls / rolling hour
AMP_GOOGLE_MULTI_MODEL=1     allow 2nd model on same key (default off)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent / "google_circuit_state.json"
POOL_STATE_PATH = Path(__file__).resolve().parent / "google_pool_state.json"

CIRCUIT_TTL_SEC = 20 * 60 * 60
DEFAULT_HOURLY_BUDGET = 40
HARD_MAX_KEYS = 2  # absolute ceiling — never raise via env above this

_lock = threading.RLock()
_call_timestamps: List[float] = []
_sticky_index: Dict[str, int] = {}


class GoogleCircuitOpen(RuntimeError):
    """Google free-tier vault is burned — use OpenRouter / local fallbacks."""


class GoogleBudgetExceeded(RuntimeError):
    """Process hourly Google call budget exhausted."""


@dataclass
class GateResult:
    text: str = ""
    raw: Any = None
    key_tag: str = ""
    model: str = ""
    attempts: int = 0


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip() or default)
    except Exception:
        return default


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("gate state save failed: %s", exc)


def is_daily_quota_zero(exc_or_msg) -> bool:
    msg = str(exc_or_msg or "")
    return (
        "limit: 0" in msg
        or "FreeTier" in msg
        or "generate_content_free_tier" in msg
        or "PerDay" in msg
    )


def is_quota_error(exc_or_msg) -> bool:
    msg = str(exc_or_msg or "").lower()
    return any(
        x in msg
        for x in (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "too many requests",
        )
    )


def open_circuit(reason: str = "free_tier_limit_0") -> None:
    """Trip the breaker — blocks further Google generate until TTL."""
    now = time.time()
    state = {
        "open": True,
        "reason": reason,
        "opened_at": now,
        "expires_at": now + CIRCUIT_TTL_SEC,
    }
    _save_json(STATE_PATH, state)
    # Keep llm_router pool flag in sync
    _save_json(
        POOL_STATE_PATH,
        {"exhausted": True, "reason": reason, "ts": now},
    )
    logger.error(
        "GOOGLE CIRCUIT OPEN (%s) — all generateContent blocked ~%.0fh; use OpenRouter",
        reason,
        CIRCUIT_TTL_SEC / 3600.0,
    )


def maybe_trip_circuit_if_pool_dead(
    api_keys: Optional[Sequence[str]],
    *,
    reason: str,
) -> bool:
    """
    Open global circuit only when no healthy sibling keys remain.

    One key hitting daily0/429 must cool that key — not wipe the vault for
    semantic observation / TTS on other credentials.
    """
    from pipeline.quota_backoff import filter_usable_keys

    raw = [k.strip() for k in (api_keys or []) if (k or "").strip()]
    healthy = filter_usable_keys(raw)
    if healthy:
        logger.warning(
            "Google key failure (%s) — %s sibling key(s) still healthy; NOT opening global circuit",
            reason[:80],
            len(healthy),
        )
        return False
    open_circuit(reason)
    return True


def close_circuit() -> None:
    _save_json(STATE_PATH, {"open": False, "reason": "", "opened_at": 0, "expires_at": 0})
    _save_json(POOL_STATE_PATH, {"exhausted": False, "reason": "", "ts": 0.0})
    logger.warning("Google circuit CLOSED (operator reset)")


def circuit_is_open() -> bool:
    if os.environ.get("AMP_FORCE_GOOGLE", "").strip() == "1":
        return False
    state = _load_json(STATE_PATH)
    if not state.get("open"):
        # Also honor legacy pool exhausted flag
        pool = _load_json(POOL_STATE_PATH)
        if pool.get("exhausted"):
            ts = float(pool.get("ts") or 0)
            if ts and (time.time() - ts) > CIRCUIT_TTL_SEC:
                close_circuit()
                return False
            return True
        return False
    exp = float(state.get("expires_at") or 0)
    if exp and time.time() > exp:
        close_circuit()
        return False
    return True


def assert_circuit_allows_google() -> None:
    if circuit_is_open():
        raise GoogleCircuitOpen(
            "Google circuit open — refuse key spray; route to OpenRouter / local repair"
        )


def _hourly_budget() -> int:
    return max(5, _env_int("AMP_GOOGLE_HOURLY_BUDGET", DEFAULT_HOURLY_BUDGET))


def _record_call() -> None:
    """Persist rolling hourly timestamps so restarts still respect budget."""
    now = time.time()
    budget_path = STATE_PATH.parent / "google_hourly_calls.json"
    with _lock:
        global _call_timestamps
        # Merge disk + memory
        disk: List[float] = []
        try:
            if budget_path.is_file():
                disk = [
                    float(t)
                    for t in (json.loads(budget_path.read_text(encoding="utf-8")).get("calls") or [])
                ]
        except Exception:
            disk = []
        merged = [t for t in (list(_call_timestamps) + disk) if now - float(t) < 3600]
        # de-dupe near-identical timestamps
        merged = sorted(set(round(float(t), 3) for t in merged))
        if len(merged) >= _hourly_budget():
            raise GoogleBudgetExceeded(
                f"Google hourly budget {_hourly_budget()} exhausted "
                f"({len(merged)} calls in last hour)"
            )
        merged.append(now)
        _call_timestamps = merged
        try:
            budget_path.write_text(
                json.dumps({"calls": merged[-200:], "updated": now}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


def calls_in_last_hour() -> int:
    now = time.time()
    with _lock:
        return len([t for t in _call_timestamps if now - t < 3600])


def max_keys_for(purpose: str = "text") -> int:
    requested = _env_int("AMP_GOOGLE_MAX_KEYS", 1)
    # TTS may try 2 keys; everything else default 1
    base = 2 if purpose == "tts" else 1
    n = min(HARD_MAX_KEYS, max(1, requested if requested > 0 else base))
    if purpose != "tts":
        n = min(n, 1 if requested <= 1 else min(2, requested))
    return n


def select_keys(
    api_keys: Optional[Sequence[str]],
    *,
    purpose: str = "text",
) -> List[str]:
    """
    Return at most max_keys sticky keys. NEVER returns the full vault.
    Skips keys currently in per-key cool-down when possible.
    """
    assert_circuit_allows_google()
    raw = [k.strip() for k in (api_keys or []) if (k or "").strip()]
    if not raw:
        return []

    try:
        from pipeline.quota_backoff import filter_usable_keys, key_is_cooling

        usable = filter_usable_keys(raw) or [k for k in raw if not key_is_cooling(k)]
        if not usable:
            usable = raw[:1]  # last resort single key — still not full spray
    except Exception:
        usable = raw

    limit = max_keys_for(purpose)
    with _lock:
        idx = int(_sticky_index.get(purpose, 0)) % len(usable)
        # Rotate sticky only after success elsewhere; for selection take sticky + next
        chosen = []
        for i in range(min(limit, len(usable))):
            chosen.append(usable[(idx + i) % len(usable)])
        return chosen


def advance_sticky(purpose: str = "text") -> None:
    with _lock:
        _sticky_index[purpose] = int(_sticky_index.get(purpose, 0)) + 1


def models_for(purpose: str, models: Optional[Sequence[str]] = None) -> List[str]:
    if models:
        seq = [m for m in models if m]
    elif purpose == "tts":
        seq = [
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts",
        ]
    else:
        seq = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
    multi = os.environ.get("AMP_GOOGLE_MULTI_MODEL", "").strip() == "1"
    return list(seq[: 2 if multi else 1])


def gated_generate_content(
    *,
    api_keys: Optional[Sequence[str]],
    contents: Any,
    model: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    purpose: str = "text",
    config: Any = None,
    on_success: Optional[Callable[[], None]] = None,
) -> GateResult:
    """
    THE only sanctioned Google generateContent entry for text/critic/tts helpers.
    Raises GoogleCircuitOpen / GoogleBudgetExceeded instead of spraying keys.
    """
    assert_circuit_allows_google()
    keys = select_keys(api_keys, purpose=purpose)
    if not keys:
        raise RuntimeError("no Google API keys available for gated call")

    model_list = models_for(purpose, models or ([model] if model else None))
    last_err: Optional[Exception] = None
    attempts = 0

    for key in keys:
        for mdl in model_list:
            attempts += 1
            try:
                _record_call()
                from google import genai

                client = genai.Client(api_key=key)
                kwargs: Dict[str, Any] = {"model": mdl, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                resp = client.models.generate_content(**kwargs)
                text = (getattr(resp, "text", None) or "").strip()
                try:
                    from pipeline.quota_backoff import record_quota_ok

                    record_quota_ok("google")
                except Exception:
                    pass
                if on_success:
                    on_success()
                return GateResult(
                    text=text,
                    raw=resp,
                    key_tag=key[-4:],
                    model=mdl,
                    attempts=attempts,
                )
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                logger.warning(
                    "gated Google %s purpose=%s key…%s: %s",
                    mdl,
                    purpose,
                    key[-4:],
                    msg[:160],
                )
                try:
                    from pipeline.quota_backoff import record_key_quota_hit

                    if is_quota_error(exc):
                        record_key_quota_hit(key, "google")
                except Exception:
                    pass
                if is_daily_quota_zero(exc):
                    maybe_trip_circuit_if_pool_dead(
                        api_keys,
                        reason=f"{purpose}…{key[-4:]} daily0",
                    )
                    advance_sticky(purpose)
                    break
                if is_quota_error(exc):
                    # Do NOT try every model; advance sticky and try next key only if allowed
                    advance_sticky(purpose)
                    break
                # non-quota: try next model only if multi enabled (already truncated)
                continue
        # after finishing models for this key on quota, maybe next key
        if last_err and is_daily_quota_zero(last_err):
            continue

    if last_err and is_quota_error(last_err):
        try:
            from pipeline.quota_backoff import record_quota_hit

            record_quota_hit("google")
        except Exception:
            pass
    if circuit_is_open():
        raise GoogleCircuitOpen(
            f"gated Google generate failed; circuit open after {attempts} attempt(s): {last_err}"
        )
    raise RuntimeError(f"gated Google generate failed after {attempts} attempt(s): {last_err}")


def status_snapshot() -> Dict[str, Any]:
    state = _load_json(STATE_PATH)
    return {
        "circuit_open": circuit_is_open(),
        "circuit": state,
        "calls_last_hour": calls_in_last_hour(),
        "hourly_budget": _hourly_budget(),
        "max_keys_text": max_keys_for("text"),
        "max_keys_tts": max_keys_for("tts"),
        "sticky": dict(_sticky_index),
    }
