"""Session-scoped API key pinning + free-tier auto-rotate (90–95% cap).

Picks keys from .env pools and keeps them sticky until soft quota → rotate.
Never allows a key to approach 100% free-tier usage.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, List, Optional

from pipeline.custom_pipeline.quota_rotate import (
    NeedMoreApiKeysError,
    ensure_key_or_rotate,
    is_key_usable,
    mark_exhausted,
    should_rotate,
    usage_ratios,
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_session_id: Optional[str] = None
_grok_key: Optional[str] = None
_grok_provider: str = "grok"  # or openrouter_grok
_localize_by_lang: Dict[str, str] = {}
_used_localize_keys: set[str] = set()
_tts_by_lang: Dict[str, str] = {}
_used_tts_keys: set[str] = set()


def _env_map() -> Dict[str, str]:
    try:
        from pipeline.api_keys import merge_env_maps, parse_env_file
        from app.config import software_env_paths

        maps = [parse_env_file(p) for p in software_env_paths()]
        return merge_env_maps(*[m for m in maps if m], {k: v for k, v in os.environ.items() if v})
    except Exception:
        return {k: v for k, v in os.environ.items() if v}


def _collect_numbered(env: Dict[str, str], prefixes: List[str], *, max_n: int = 40) -> List[str]:
    found: List[str] = []
    seen = set()

    def _add(val: str) -> None:
        v = (val or "").strip()
        if v and v not in seen:
            seen.add(v)
            found.append(v)

    for prefix in prefixes:
        _add(env.get(prefix) or "")
        for i in range(1, max_n + 1):
            _add(env.get(f"{prefix}_{i}") or "")
            _add(env.get(f"{prefix}{i}") or "")
    return found


def list_grok_keys() -> List[str]:
    """Prefer dedicated topic Grok keys; else legacy XAI/GROK pool."""
    try:
        from pipeline.dedicated_api_registry import list_topic_grok_keys

        dedicated = list_topic_grok_keys(allow_borrow=True)
        if dedicated:
            return dedicated
    except Exception:
        pass
    env = _env_map()
    keys = _collect_numbered(env, ["XAI_API_KEY", "GROK_API_KEY", "TOPIC_GROK_API_KEY"], max_n=40)
    try:
        from pipeline.api_keys import load_api_bundle

        for v in load_api_bundle().get("xai_keys") or []:
            if v and v not in keys:
                keys.append(str(v))
    except Exception:
        pass
    return keys


def list_agent_keys() -> List[str]:
    try:
        from pipeline.dedicated_api_registry import list_agent_grok_keys

        return list_agent_grok_keys(allow_borrow=True)
    except Exception:
        return list_grok_keys()


def list_openrouter_keys() -> List[str]:
    env = _env_map()
    keys = _collect_numbered(env, ["OPENROUTER_API_KEY"], max_n=20)
    try:
        from pipeline.api_keys import load_api_bundle

        for v in load_api_bundle().get("openrouter_keys") or []:
            if v and v not in keys:
                keys.append(str(v))
    except Exception:
        pass
    return keys


def list_paid_google_keys() -> List[str]:
    """Dedicated Google AI Studio Paid Master keys (channel + env)."""
    try:
        from pipeline.dedicated_api_registry import list_paid_google_keys as _paid

        keys = _paid()
        if keys:
            return keys
    except Exception:
        pass
    env = _env_map()
    return _collect_numbered(
        env,
        ["GOOGLE_PAID_API_KEY", "GOOGLE_PAID_MASTER_KEY", "PAID_GOOGLE_API_KEY"],
        max_n=10,
    )


def has_active_paid_google_key() -> bool:
    """Return True if at least one paid Google key is configured."""
    return len(list_paid_google_keys()) > 0


def list_localization_keys() -> List[str]:
    """Tier 1: Paid Google Master keys, Tier 2: Dedicated localization keys, then general Google pool overflow."""
    keys: List[str] = []
    for k in list_paid_google_keys():
        if k and k not in keys:
            keys.append(k)
    try:
        from pipeline.dedicated_api_registry import list_localize_google_keys

        for k in list_localize_google_keys(allow_borrow=True) or []:
            if k and k not in keys:
                keys.append(k)
    except Exception:
        pass
    env = _env_map()
    for prefix in (
        "LOCALIZATION_GOOGLE_API_KEY",
        "GOOGLE_LOCALIZE_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ):
        for k in _collect_numbered(env, [prefix], max_n=40):
            if k and k not in keys:
                keys.append(k)
    return keys


def list_image_google_keys() -> List[str]:
    """Tier 1: Paid Google Master keys, Tier 2: Dedicated IMAGE_GOOGLE keys."""
    keys: List[str] = []
    for k in list_paid_google_keys():
        if k and k not in keys:
            keys.append(k)
    try:
        from pipeline.dedicated_api_registry import list_image_google_keys as _img

        for k in _img(allow_borrow=False) or []:
            if k and k not in keys:
                keys.append(k)
        return keys
    except Exception:
        env = _env_map()
        for k in _collect_numbered(env, ["IMAGE_GOOGLE_API_KEY", "GOOGLE_IMAGE_API_KEY"], max_n=6):
            if k and k not in keys:
                keys.append(k)
        return keys


def list_tts_keys() -> List[str]:
    """Tier 1: Paid Google Master keys, Tier 2: Dedicated TTS keys, Tier 3: General Google pool."""
    paid = list_paid_google_keys()
    env = _env_map()
    dedicated = _collect_numbered(
        env,
        ["TTS_GOOGLE_API_KEY", "GOOGLE_TTS_API_KEY"],
        max_n=40,
    )
    pool = _collect_numbered(env, ["GOOGLE_API_KEY", "GEMINI_API_KEY"], max_n=40)
    all_keys = [k for k in paid if k]
    for k in (dedicated or pool):
        if k and k not in all_keys:
            all_keys.append(k)
    return all_keys


def start_session(session_id: Optional[str] = None) -> str:
    import uuid

    global _session_id, _grok_key, _grok_provider
    global _localize_by_lang, _used_localize_keys, _tts_by_lang, _used_tts_keys
    with _lock:
        _session_id = (session_id or "").strip() or uuid.uuid4().hex[:12]
        _grok_key = None
        _grok_provider = "grok"
        _localize_by_lang = {}
        _used_localize_keys = set()
        _tts_by_lang = {}
        _used_tts_keys = set()
        logger.info("Custom pipeline session started id=%s", _session_id)
        return _session_id


def current_session_id() -> str:
    with _lock:
        if not _session_id:
            return start_session()
        return _session_id


def reset_session() -> None:
    start_session()


def _mask(key: str) -> str:
    k = (key or "").strip()
    return f"…{k[-4:]}" if len(k) >= 4 else "…????"


def _is_openrouter_key(key: str) -> bool:
    """TOPIC/AGENT slots may hold OpenRouter keys (sk-or-…) for Grok models."""
    k = (key or "").strip().lower()
    return k.startswith("sk-or-") or k.startswith("sk-or_")


def _partition_grok_pool(keys: List[str]) -> tuple[List[str], List[str]]:
    """Split mixed topic/agent pools into native xAI vs OpenRouter keys."""
    xai: List[str] = []
    or_keys: List[str] = []
    for raw in keys or []:
        k = (raw or "").strip()
        if not k:
            continue
        if _is_openrouter_key(k):
            if k not in or_keys:
                or_keys.append(k)
        elif k not in xai:
            xai.append(k)
    return xai, or_keys


def _merged_openrouter_pool() -> List[str]:
    """OpenRouter keys from dedicated TOPIC/AGENT slots + OPENROUTER_API_KEY_*."""
    _, or_from_topic = _partition_grok_pool(list_grok_keys())
    pool = list(or_from_topic)
    for k in list_openrouter_keys():
        if k and k not in pool:
            pool.append(k)
    return pool


def get_session_grok_key(*, explicit: Optional[str] = None) -> str:
    """Pin / soft-rotate one Grok key (native xAI first, else OpenRouter)."""
    global _grok_key, _grok_provider
    with _lock:
        current_session_id()
        if explicit and explicit.strip():
            _grok_key = explicit.strip()
            _grok_provider = "openrouter_grok" if _is_openrouter_key(_grok_key) else "grok"
            return _grok_key

        xai_pool, _ = _partition_grok_pool(list_grok_keys())
        or_pool = _merged_openrouter_pool()

        if xai_pool:
            _grok_provider = "grok"
            _grok_key = ensure_key_or_rotate("grok", _grok_key if _grok_key in xai_pool else None, xai_pool)
            return _grok_key

        if or_pool:
            _grok_provider = "openrouter_grok"
            cur = _grok_key if _grok_key in or_pool else None
            _grok_key = ensure_key_or_rotate("openrouter_grok", cur, or_pool)
            return _grok_key

        raise NeedMoreApiKeysError(
            "grok",
            detail="Add XAI_API_KEY_* / TOPIC_GROK_API_KEY_* or OPENROUTER_API_KEY_* in .env",
        )


def get_grok_provider() -> str:
    with _lock:
        return _grok_provider


def rotate_grok_key(reason: str = "quota") -> str:
    """Force-rotate Grok key after soft limit / HTTP quota error."""
    global _grok_key, _grok_provider
    with _lock:
        current_session_id()
        old = _grok_key
        if old:
            mark_exhausted(_grok_provider, old, reason=reason)
        xai_pool, _ = _partition_grok_pool(list_grok_keys())
        or_pool = _merged_openrouter_pool()
        if _grok_provider == "grok":
            pool = xai_pool
            if not pool:
                pool = or_pool
                _grok_provider = "openrouter_grok"
        else:
            pool = or_pool
            if not pool:
                pool = xai_pool
                _grok_provider = "grok"
        if not pool:
            raise NeedMoreApiKeysError(_grok_provider, detail=f"Rotate failed ({reason}). Add more keys.")
        exclude = {old} if old else set()
        from pipeline.custom_pipeline.quota_rotate import pick_usable_key

        _grok_key = pick_usable_key(_grok_provider, pool, exclude=exclude)
        if _is_openrouter_key(_grok_key):
            _grok_provider = "openrouter_grok"
        else:
            _grok_provider = "grok"
        logger.info("Grok rotated %s → %s (%s)", _mask(old or ""), _mask(_grok_key), reason)
        return _grok_key


def get_session_localize_key(
    language: str,
    *,
    explicit: Optional[str] = None,
) -> str:
    """Pin one Google key per language; soft-rotate when near free-tier cap."""
    lang = (language or "English").strip() or "English"
    with _lock:
        current_session_id()
        pool = list_localization_keys()
        if not pool:
            raise NeedMoreApiKeysError(
                "google_localize",
                detail="Add LOCALIZATION_GOOGLE_API_KEY_* or GOOGLE_API_KEY_* in .env",
            )

        if explicit and explicit.strip():
            key = explicit.strip()
            _localize_by_lang[lang] = key
            _used_localize_keys.add(key)
            return key

        current = _localize_by_lang.get(lang)
        if current and is_key_usable("google_localize", current) and not should_rotate("google_localize", current):
            return current

        # Soft rotate or first pick — prefer unused keys for other languages
        from pipeline.custom_pipeline.quota_rotate import pick_usable_key

        exclude = set(_used_localize_keys) - ({current} if current else set())
        # If current needs rotate, exclude it so we move on
        if current and should_rotate("google_localize", current):
            mark_exhausted("google_localize", current, reason="soft_rotate_90pct", hours=1.0)
            exclude.add(current)
            _used_localize_keys.discard(current)

        try:
            chosen = pick_usable_key(
                "google_localize",
                pool,
                prefer=None,
                exclude=exclude,
            )
            unique = True
        except NeedMoreApiKeysError:
            # Prefer unique pins; if pool is smaller than language count, reuse
            # a healthy dedicated/overflow key with an explicit warning.
            try:
                chosen = pick_usable_key(
                    "google_localize",
                    pool,
                    prefer=None,
                    exclude=set(),
                )
                unique = False
                logger.warning(
                    "Localize key REUSE for lang=%s %s (pool smaller than language count; "
                    "already pinned: %s). Add more LOCALIZATION_GOOGLE_API_KEY_* to keep unique pins.",
                    lang,
                    _mask(chosen),
                    sorted(_localize_by_lang.keys()),
                )
            except NeedMoreApiKeysError:
                # Last resort industrial: least-used pool key even if soft-capped
                # (still better than hard-failing the whole language for the user).
                ranked = sorted(
                    pool,
                    key=lambda k: usage_facts("google_localize", k).get("daily_pct", 1.0),
                )
                chosen = ""
                for cand in ranked:
                    facts = usage_facts("google_localize", cand)
                    # Skip only hard auth cooldowns still active
                    reason = str(facts.get("exhausted_reason") or "").lower()
                    if facts.get("exhausted") and any(
                        x in reason for x in ("auth", "401", "403", "permission", "suspended")
                    ):
                        continue
                    chosen = cand
                    break
                if not chosen:
                    raise NeedMoreApiKeysError(
                        "google_localize",
                        detail=(
                            f"Need a key for language '{lang}'. "
                            f"Already pinned: {sorted(_localize_by_lang.keys())}. "
                            f"Add more LOCALIZATION_GOOGLE_API_KEY_* or GOOGLE_API_KEY_*."
                        ),
                    )
                unique = False
                logger.warning(
                    "Localize key FORCE-REUSE for lang=%s %s (soft-cap pool exhausted; "
                    "industrial degrade — add more keys).",
                    lang,
                    _mask(chosen),
                )

        # Prefer uniqueness; allow reuse only when overflow path above ran
        if chosen in _used_localize_keys and chosen != current and unique:
            raise NeedMoreApiKeysError(
                "google_localize",
                detail=f"No unused key left for language '{lang}'. Add another Google API key.",
            )

        _localize_by_lang[lang] = chosen
        _used_localize_keys.add(chosen)
        logger.info(
            "Localize key lang=%s %s %s daily=%.0f%%",
            lang,
            _mask(chosen),
            "UNIQUE" if unique else "REUSED",
            usage_ratios("google_localize", chosen)["daily_pct"] * 100,
        )
        return chosen


def rotate_localize_key(
    language: str,
    reason: str = "quota",
    *,
    exhaust: bool = True,
    exhaust_hours: float = 6.0,
) -> str:
    """Rotate pinned localize key for a language.

    exhaust=False: soft rotate (transient 503) — short cooldown so we do NOT
    immediately re-pin the same key (that caused infinite …GnmI loops).
    """
    lang = (language or "English").strip() or "English"
    with _lock:
        old = _localize_by_lang.get(lang)
        if old:
            if exhaust:
                mark_exhausted(
                    "google_localize",
                    old,
                    reason=reason,
                    hours=max(0.05, float(exhaust_hours)),
                )
            else:
                # ~4 minutes soft cool — enough to try next key in pool
                mark_exhausted(
                    "google_localize",
                    old,
                    reason=f"soft503:{reason}"[:120],
                    hours=0.07,
                )
                logger.info(
                    "Localize soft-rotate lang=%s %s reason=%s (cooldown≈4m)",
                    lang,
                    _mask(old),
                    reason[:80],
                )
            _used_localize_keys.discard(old)
            _localize_by_lang.pop(lang, None)
    return get_session_localize_key(lang)


def get_session_tts_key(
    language: str,
    *,
    explicit: Optional[str] = None,
) -> str:
    """Pin ONE Google key per language for TTS (session-sticky, soft-rotate)."""
    lang = (language or "English").strip() or "English"
    with _lock:
        current_session_id()
        pool = list_tts_keys()
        if not pool:
            raise NeedMoreApiKeysError(
                "google_tts",
                detail="Add TTS_GOOGLE_API_KEY_* or GOOGLE_API_KEY_* in .env",
            )

        if explicit and explicit.strip():
            key = explicit.strip()
            _tts_by_lang[lang] = key
            _used_tts_keys.add(key)
            return key

        current = _tts_by_lang.get(lang)
        if current and is_key_usable("google_tts", current) and not should_rotate(
            "google_tts", current
        ):
            return current

        # Prefer reusing THIS language's localize key only (true one-key-per-language)
        loc = _localize_by_lang.get(lang)
        if (
            loc
            and is_key_usable("google_tts", loc)
            and not should_rotate("google_tts", loc)
            and loc not in (_used_tts_keys - ({current} if current else set()))
        ):
            _tts_by_lang[lang] = loc
            _used_tts_keys.add(loc)
            logger.info(
                "TTS key lang=%s reuse-own-localize %s UNIQUE daily=%.0f%%",
                lang,
                _mask(loc),
                usage_ratios("google_tts", loc)["daily_pct"] * 100,
            )
            return loc

        from pipeline.custom_pipeline.quota_rotate import pick_usable_key

        exclude = set(_used_tts_keys) - ({current} if current else set())
        # Never take another language's localize/tts key
        exclude |= set(_used_localize_keys) - ({loc} if loc else set())
        if current and should_rotate("google_tts", current):
            mark_exhausted("google_tts", current, reason="soft_rotate_90pct", hours=1.0)
            exclude.add(current)
            _used_tts_keys.discard(current)

        try:
            chosen = pick_usable_key(
                "google_tts",
                pool,
                prefer=None,
                exclude=exclude,
            )
        except NeedMoreApiKeysError:
            raise NeedMoreApiKeysError(
                "google_tts",
                detail=(
                    f"Need a UNIQUE TTS key for language '{lang}'. "
                    f"Already pinned TTS: {sorted(_tts_by_lang.keys())}. "
                    f"Add more TTS_GOOGLE_API_KEY_* or GOOGLE_API_KEY_*."
                ),
            )

        if chosen in _used_tts_keys and chosen != current:
            raise NeedMoreApiKeysError(
                "google_tts",
                detail=f"No unused TTS key left for language '{lang}'. Add another Google API key.",
            )

        _tts_by_lang[lang] = chosen
        _used_tts_keys.add(chosen)
        logger.info(
            "TTS key lang=%s %s UNIQUE daily=%.0f%%",
            lang,
            _mask(chosen),
            usage_ratios("google_tts", chosen)["daily_pct"] * 100,
        )
        return chosen


def rotate_tts_key(language: str, reason: str = "quota") -> str:
    lang = (language or "English").strip() or "English"
    with _lock:
        old = _tts_by_lang.get(lang)
        if old:
            mark_exhausted("google_tts", old, reason=reason)
            _used_tts_keys.discard(old)
            _tts_by_lang.pop(lang, None)
    return get_session_tts_key(lang)


def session_key_report() -> Dict[str, object]:
    with _lock:
        loc_usage = {}
        for lang, k in _localize_by_lang.items():
            info = usage_ratios("google_localize", k)
            loc_usage[lang] = {
                "key": _mask(k),
                "daily_pct": round(info["daily_pct"] * 100, 1),
                "hourly_pct": round(info["hourly_pct"] * 100, 1),
            }
        tts_usage = {}
        for lang, k in _tts_by_lang.items():
            info = usage_ratios("google_tts", k)
            tts_usage[lang] = {
                "key": _mask(k),
                "daily_pct": round(info["daily_pct"] * 100, 1),
                "hourly_pct": round(info["hourly_pct"] * 100, 1),
            }
        grok_usage = None
        if _grok_key:
            info = usage_ratios(_grok_provider, _grok_key)
            grok_usage = {
                "provider": _grok_provider,
                "key": _mask(_grok_key),
                "daily_pct": round(info["daily_pct"] * 100, 1),
                "hourly_pct": round(info["hourly_pct"] * 100, 1),
            }
        return {
            "session_id": _session_id,
            "grok": grok_usage,
            "localize_by_lang": loc_usage,
            "tts_by_lang": tts_usage,
            "grok_pool_size": len(list_grok_keys()) or len(list_openrouter_keys()),
            "localize_pool_size": len(list_localization_keys()),
            "tts_pool_size": len(list_tts_keys()),
            "rotate_at_pct": 90,
            "hard_cap_pct": 95,
        }
