"""
Per-language Google TTS API assignment.

Policy (product):
  - Non-English (bn/hi/ur/ta/ml): ONE dedicated Google key each (slot index 0..4).
  - English: NOT always synthesized; when it IS needed, rotate ONE key per call
    across the vault (round-robin) so one video uses one API.

With 5 Google keys and 6 languages active:
  bn→k0, hi→k1, ur→k2, ta→k3, ml→k4, en→rotate(k0..k4).

If fewer keys than languages, map modulo len(keys) but still prefer 1 key/call.
Never spray 2+ Google TTS keys for a single language call.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Fixed slot ownership for localized voices (order matches user priority)
LANG_DEDICATED_INDEX: Dict[str, int] = {
    "bn": 0,
    "hi": 1,
    "ur": 2,
    "ta": 3,
    "ml": 4,
}

_en_lock = threading.Lock()
_en_rotate = 0


def reset_english_rotation(start: int = 0) -> None:
    global _en_rotate
    with _en_lock:
        _en_rotate = max(0, int(start))


def english_rotation_index() -> int:
    with _en_lock:
        return int(_en_rotate)


def advance_english_rotation() -> int:
    global _en_rotate
    with _en_lock:
        _en_rotate += 1
        return _en_rotate


def _clean(keys: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for k in keys or []:
        v = (k or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def describe_tts_map(keys: Sequence[str]) -> Dict[str, str]:
    pool = _clean(keys)
    desc: Dict[str, str] = {}
    for lang, idx in LANG_DEDICATED_INDEX.items():
        if not pool:
            desc[lang] = "no_keys"
        else:
            k = pool[idx % len(pool)]
            desc[lang] = f"slot{idx % len(pool)}…{k[-4:]}"
    desc["en"] = f"rotate@{english_rotation_index() % max(1, len(pool))} (one key per English synth)"
    return desc


def keys_for_tts_language(
    all_keys: Sequence[str],
    language_hint: str,
    *,
    fallthrough: bool = True,
) -> List[str]:
    """
    Return exactly one Google key for this language (best-effort).
    fallthrough=True: if dedicated key is cooled/empty, try next slots once.
    """
    pool = _clean(all_keys)
    if not pool:
        return []

    lang = (language_hint or "en").strip().lower()[:2] or "en"

    if lang == "en":
        with _en_lock:
            idx = int(_en_rotate) % len(pool)
        chosen = [pool[idx]]
        logger.info(
            "TTS key map EN rotate → slot %s …%s (call #%s)",
            idx,
            chosen[0][-4:],
            english_rotation_index(),
        )
        return chosen

    if lang in LANG_DEDICATED_INDEX:
        base = LANG_DEDICATED_INDEX[lang] % len(pool)
        ordered = [pool[base]]
        if fallthrough:
            # One alternate only if primary cooled — still max 2, preferred 1
            alt = pool[(base + 1) % len(pool)]
            if alt != ordered[0]:
                # Prefer primary only; caller may expand if primary fails
                pass
        logger.info(
            "TTS key map %s → dedicated slot %s …%s",
            lang,
            base,
            ordered[0][-4:],
        )
        return ordered

    # Unknown lang → first key
    return [pool[0]]


def keys_for_tts_language_with_fallback(
    all_keys: Sequence[str],
    language_hint: str,
) -> List[str]:
    """
    Ordered failover list for one synthesize call.

    - Prefer healthy (non-cooled) keys.
    - EN: start at rotation index, then walk the pool (deterministic rotation).
    - Localized: dedicated slot first, then remaining pool order.
    - Never spray the whole vault blindly for retries inside one attempt —
      caller iterates this list once per key on 429.
    """
    from pipeline.quota_backoff import filter_usable_keys

    pool = _clean(all_keys)
    if not pool:
        return []
    lang = (language_hint or "en").strip().lower()[:2] or "en"

    if lang == "en":
        with _en_lock:
            start = int(_en_rotate) % len(pool)
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
    # All currently cooling — still return ordered pool so caller can surface real errors
    # (do not silently invent PASS); prefer not to claim "exhausted" without trying.
    logger.warning(
        "TTS key map lang=%s: all %s keys in cool-down — trying rotation order anyway",
        lang,
        len(ordered),
    )
    return ordered


def on_tts_success(language_hint: str) -> None:
    """Advance English rotator only after a successful English synthesize."""
    lang = (language_hint or "").strip().lower()[:2]
    if lang == "en":
        n = advance_english_rotation()
        logger.info("TTS EN rotation advanced → next=%s", n)


def on_tts_key_rejected(language_hint: str, *, reason: str = "quota") -> None:
    """Advance EN rotator when current key is rejected (429/quota) so next call uses next slot."""
    lang = (language_hint or "").strip().lower()[:2]
    if lang == "en":
        n = advance_english_rotation()
        logger.info(
            "TTS EN rotation advanced after %s → next=%s",
            (reason or "reject")[:40],
            n,
        )
