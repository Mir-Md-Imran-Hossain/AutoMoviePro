"""
Per-language Google TTS API assignment with Dynamic Multi-Key Round-Robin.

Policy:
  - Bengali (bn) and English (en): Dynamically rotate across ALL available Google keys in the pool
    so long 15-30 scene videos never hit 429 quota limits on a single key.
  - Other localized voices (hi/ur/ta/ml): Slot-mapped with multi-key failover fallback.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

LANG_DEDICATED_INDEX: Dict[str, int] = {
    "hi": 1,
    "ur": 2,
    "ta": 3,
    "ml": 4,
}

_rot_lock = threading.Lock()
_rot_counters: Dict[str, int] = {"en": 0, "bn": 0}


def reset_english_rotation(start: int = 0) -> None:
    with _rot_lock:
        _rot_counters["en"] = max(0, int(start))


def english_rotation_index() -> int:
    with _rot_lock:
        return int(_rot_counters.get("en", 0))


def advance_rotation(lang: str) -> int:
    with _rot_lock:
        _rot_counters[lang] = _rot_counters.get(lang, 0) + 1
        return _rot_counters[lang]


def advance_english_rotation() -> int:
    return advance_rotation("en")


def advance_bengali_rotation() -> int:
    return advance_rotation("bn")


def _clean(keys: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for k in keys:
        s = (k or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def order_google_tts_keys(all_keys: Sequence[str], language_hint: str) -> List[str]:
    """
    Returns keys for TTS synthesis.
    For Bengali (bn) and English (en), rotates round-robin across the entire pool
    to prevent single-key 429 quota exhaustion.
    """
    from pipeline.quota_backoff import filter_usable_keys

    pool = _clean(all_keys)
    if not pool:
        return []
    lang = (language_hint or "en").strip().lower()[:2] or "en"

    if lang in ("en", "bn"):
        with _rot_lock:
            start = int(_rot_counters.get(lang, 0)) % len(pool)
        ordered = [pool[(start + i) % len(pool)] for i in range(len(pool))]
    elif lang in LANG_DEDICATED_INDEX:
        base = LANG_DEDICATED_INDEX[lang] % len(pool)
        ordered = [pool[(base + i) % len(pool)] for i in range(len(pool))]
    else:
        ordered = list(pool)

    healthy = filter_usable_keys(ordered)
    if healthy:
        logger.info(
            "TTS key failover map lang=%s healthy=%s/%s start…%s",
            lang,
            len(healthy),
            len(ordered),
            healthy[0][-4:],
        )
        return healthy

    # If all cooling, return full pool so rotator tries next best candidate
    logger.warning("TTS key map lang=%s: all %s keys in cool-down — probing candidate before quick fallback", lang, len(ordered))
    return ordered


def on_tts_success(language_hint: str) -> None:
    """Advance rotator after a successful synthesize."""
    lang = (language_hint or "").strip().lower()[:2]
    if lang in ("en", "bn"):
        n = advance_rotation(lang)
        logger.info("TTS %s rotation advanced → next=%s", lang.upper(), n)


def on_tts_key_rejected(language_hint: str, *, reason: str = "quota") -> None:
    """Advance rotator when current key is rejected so next call uses next slot."""
    lang = (language_hint or "").strip().lower()[:2]
    if lang in ("en", "bn"):
        n = advance_rotation(lang)
        logger.info(
            "TTS %s rotation advanced after %s → next=%s",
            lang.upper(),
            (reason or "reject")[:40],
            n,
        )


# Alias for backward compatibility with tts_google.py
keys_for_tts_language_with_fallback = order_google_tts_keys
