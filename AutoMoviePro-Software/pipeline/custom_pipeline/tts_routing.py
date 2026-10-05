"""Industrial multi-language TTS engine routing + quota failover.

Engine Allocation Matrix
------------------------
  en / hi / ur  → always Microsoft Edge-TTS (free, unlimited) — never Google
  bn / ta / ml  → Google AI Studio (Gemini TTS) with dual-key quota routing
                  primary → secondary at 90–95% OR on 429/ResourceExhausted
                  both Google keys dead → Edge-TTS fallback (never hard-fail)

Quota events
------------
  QUOTA_THRESHOLD_WARNING — emitted when a Google key hits soft threshold (90%)
  QUOTA_HARD_BLOCK        — key at hard cap (95%); preemptively switched away
  TTS_FALLBACK_EDGE       — both Google keys unusable; diverted to Edge-TTS
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pipeline.custom_pipeline.quota_rotate import (
    HARD_CAP,
    ROTATE_AT,
    is_key_usable,
    should_rotate,
    usage_ratios,
)

logger = logging.getLogger(__name__)

ENGINE_EDGE = "EDGE_TTS"
ENGINE_GOOGLE = "GOOGLE_AI_STUDIO"
ENGINE_CF_MELOTTS = "CLOUDFLARE_MELOTTS"
ENGINE_CF_AURA = "CLOUDFLARE_AURA"

# ---------------------------------------------------------------------------
# Canonical routing matrix (product policy)
# ---------------------------------------------------------------------------

TTS_ROUTING_CONFIG: Dict[str, Any] = {
    "tts_routing_config": {
        "quota_switch_threshold_percent": int(ROTATE_AT * 100),
        "quota_hard_cap_percent": int(HARD_CAP * 100),
        "languages": {
            "en": {
                "engine": ENGINE_EDGE,
                "voice": "en-US-JennyNeural",
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "en-US-JennyNeural",
                "aura_speaker": "asteria",
            },
            "hi": {
                "engine": ENGINE_EDGE,
                "voice": "hi-IN-SwaraNeural",
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "hi-IN-SwaraNeural",
            },
            "ur": {
                "engine": ENGINE_EDGE,
                "voice": "ur-PK-UzmaNeural",
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "ur-PK-UzmaNeural",
            },
            "bn": {
                "engine": ENGINE_GOOGLE,
                "primary_key": "GOOGLE_API_KEY_BN_PRIMARY",
                "secondary_key": "GOOGLE_API_KEY_BN_SECONDARY",
                "quota_switch_threshold_percent": int(ROTATE_AT * 100),
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "bn-BD-NabanitaNeural",
            },
            "ta": {
                "engine": ENGINE_GOOGLE,
                "primary_key": "GOOGLE_API_KEY_TA_PRIMARY",
                "secondary_key": "GOOGLE_API_KEY_TA_SECONDARY",
                "quota_switch_threshold_percent": int(ROTATE_AT * 100),
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "ta-IN-PallaviNeural",
            },
            "ml": {
                "engine": ENGINE_GOOGLE,
                "primary_key": "GOOGLE_API_KEY_ML_PRIMARY",
                "secondary_key": "GOOGLE_API_KEY_ML_SECONDARY",
                "quota_switch_threshold_percent": int(ROTATE_AT * 100),
                "fallback_engine": ENGINE_EDGE,
                "fallback_voice": "ml-IN-SobhanaNeural",
            },
        },
    }
}

# Free/unlimited Edge-only ISO codes
EDGE_ONLY_LANGS = frozenset({"en", "hi", "ur"})
# High-accuracy Google-primary ISO codes
GOOGLE_PRIMARY_LANGS = frozenset({"bn", "ta", "ml"})
ALL_TTS_LANGS = frozenset({"en", "hi", "ur", "bn", "ta", "ml"})

# Pool-slot fallback when dedicated dual keys are missing:
# bn→(0,1)  ta→(2,3)  ml→(4,5) of TTS_GOOGLE_API_KEY_* / GOOGLE_API_KEY_*
_POOL_SLOT: Dict[str, Tuple[int, int]] = {
    "bn": (0, 1),
    "ta": (2, 3),
    "ml": (4, 5),
}

_event_lock = threading.RLock()
_event_sinks: List[Callable[[Dict[str, Any]], None]] = []
_recent_warnings: Dict[str, float] = {}  # dedupe key → last emit mono


@dataclass
class TtsRouteDecision:
    """Resolved engine + credentials for one synthesize call."""

    lang: str
    engine: str
    voice: str = ""
    api_key: str = ""
    key_slot: str = ""  # primary | secondary | pool | ""
    fallback_engine: str = ""
    fallback_voice: str = ""
    secondary_key: str = ""
    reason: str = ""
    quota_pct: float = 0.0
    cf_account_id: str = ""
    aura_speaker: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lang": self.lang,
            "engine": self.engine,
            "voice": self.voice,
            "key_slot": self.key_slot,
            "api_key_tail": (self.api_key[-4:] if len(self.api_key) >= 4 else ""),
            "secondary_key_tail": (
                self.secondary_key[-4:] if len(self.secondary_key) >= 4 else ""
            ),
            "fallback_engine": self.fallback_engine,
            "fallback_voice": self.fallback_voice,
            "cf_account_tail": (self.cf_account_id[-4:] if len(self.cf_account_id) >= 4 else ""),
            "aura_speaker": self.aura_speaker,
            "reason": self.reason,
            "quota_pct": round(self.quota_pct, 1),
            "events": list(self.events),
        }


def routing_config() -> Dict[str, Any]:
    """Return a deep copy of the canonical routing JSON."""
    import copy

    return copy.deepcopy(TTS_ROUTING_CONFIG)


def normalize_lang_code(language: str) -> str:
    raw = (language or "en").strip().lower()
    aliases = {
        "english": "en",
        "bangla": "bn",
        "bengali": "bn",
        "hindi": "hi",
        "urdu": "ur",
        "tamil": "ta",
        "malayalam": "ml",
        "bn": "bn",
        "en": "en",
        "hi": "hi",
        "ur": "ur",
        "ta": "ta",
        "ml": "ml",
    }
    if raw in aliases:
        return aliases[raw]
    return raw[:2] if len(raw) >= 2 else "en"


def lang_route(lang_or_name: str) -> Dict[str, Any]:
    code = normalize_lang_code(lang_or_name)
    langs = TTS_ROUTING_CONFIG["tts_routing_config"]["languages"]
    return dict(langs.get(code) or langs["en"])


def register_quota_event_sink(fn: Callable[[Dict[str, Any]], None]) -> None:
    with _event_lock:
        if fn not in _event_sinks:
            _event_sinks.append(fn)


def emit_quota_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    """Fire QUOTA_THRESHOLD_WARNING / QUOTA_HARD_BLOCK / TTS_FALLBACK_EDGE etc."""
    evt = {
        "event": event_type,
        "ts": time.time(),
        **payload,
    }
    dedupe = f"{event_type}:{payload.get('lang','')}:{payload.get('key_tail','')}"
    now = time.monotonic()
    with _event_lock:
        last = _recent_warnings.get(dedupe, 0.0)
        if now - last < 30.0 and event_type == "QUOTA_THRESHOLD_WARNING":
            return evt
        _recent_warnings[dedupe] = now
        sinks = list(_event_sinks)

    logger.warning(
        "[%s] lang=%s slot=%s pct=%.0f%% %s",
        event_type,
        payload.get("lang"),
        payload.get("key_slot"),
        float(payload.get("quota_pct") or 0),
        payload.get("detail") or "",
    )
    for sink in sinks:
        try:
            sink(evt)
        except Exception as exc:
            logger.debug("quota sink failed: %s", exc)
    # Soft telemetry — package-scoped emit needs a root; log sink is enough here.
    return evt


def _env_map() -> Dict[str, str]:
    try:
        from pipeline.api_keys import merge_env_maps, parse_env_file
        from app.config import software_env_paths

        maps = [parse_env_file(p) for p in software_env_paths()]
        return merge_env_maps(
            *[m for m in maps if m],
            {k: v for k, v in os.environ.items() if v},
        )
    except Exception:
        return {k: v for k, v in os.environ.items() if v}


def _first_env(env: Dict[str, str], names: Sequence[str]) -> str:
    for name in names:
        val = (env.get(name) or "").strip()
        if val:
            return val
    return ""


def _collect_pool(env: Dict[str, str]) -> List[str]:
    """Ordered TTS Google key pool (paid master keys first, then dedicated TTS_*, then GOOGLE_API_KEY_*)."""
    found: List[str] = []
    seen = set()

    def _add(v: str) -> None:
        k = (v or "").strip()
        if k and k not in seen:
            seen.add(k)
            found.append(k)

    for prefix in (
        "GOOGLE_AI_STUDIO_PAID_API_KEY",
        "GOOGLE_PAID_MASTER_KEY",
        "GOOGLE_MASTER_PAID_API_KEY",
        "GOOGLE_PAID_API_KEY",
    ):
        _add(env.get(prefix) or "")
        for i in range(1, 11):
            _add(env.get(f"{prefix}_{i}") or "")
            _add(env.get(f"{prefix}{i}") or "")

    for prefix in ("TTS_GOOGLE_API_KEY", "GOOGLE_TTS_API_KEY"):
        _add(env.get(prefix) or "")
        for i in range(1, 41):
            _add(env.get(f"{prefix}_{i}") or "")
            _add(env.get(f"{prefix}{i}") or "")

    for prefix in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        _add(env.get(prefix) or "")
        for i in range(1, 41):
            _add(env.get(f"{prefix}_{i}") or "")
            _add(env.get(f"{prefix}{i}") or "")
    return found


def resolve_dual_google_keys(lang_or_name: str) -> Tuple[str, str]:
    """Return (primary, secondary) Google keys for bn/ta/ml.

    Resolution order per language:
      1) GOOGLE_API_KEY_{LANG}_PRIMARY / _SECONDARY
      2) TTS_GOOGLE_API_KEY_{LANG}_PRIMARY / _SECONDARY
      3) ENV_{LANG}_PRIMARY_KEY / ENV_{LANG}_SECONDARY_KEY (alias from product JSON)
      4) Shared GOOGLE_API_KEY_PRIMARY / GOOGLE_API_KEY_SECONDARY
      5) Paid master keys (GOOGLE_PAID_MASTER_KEY / GOOGLE_PAID_API_KEY_*)
      6) Pool slots (bn=0,1 ta=2,3 ml=4,5)
    """
    code = normalize_lang_code(lang_or_name)
    if code not in GOOGLE_PRIMARY_LANGS:
        return "", ""

    env = _env_map()
    paid_keys: List[str] = []
    for prefix in (
        "GOOGLE_AI_STUDIO_PAID_API_KEY",
        "GOOGLE_PAID_MASTER_KEY",
        "GOOGLE_MASTER_PAID_API_KEY",
        "GOOGLE_PAID_API_KEY",
    ):
        val = env.get(prefix)
        if val and val.strip() and val.strip() not in paid_keys:
            paid_keys.append(val.strip())
        for i in range(1, 11):
            val = env.get(f"{prefix}_{i}") or env.get(f"{prefix}{i}")
            if val and val.strip() and val.strip() not in paid_keys:
                paid_keys.append(val.strip())

    upper = code.upper()
    primary = _first_env(
        env,
        [
            f"GOOGLE_API_KEY_{upper}_PRIMARY",
            f"TTS_GOOGLE_API_KEY_{upper}_PRIMARY",
            f"ENV_{upper}_PRIMARY_KEY",
            f"GOOGLE_TTS_{upper}_PRIMARY",
        ],
    )
    secondary = _first_env(
        env,
        [
            f"GOOGLE_API_KEY_{upper}_SECONDARY",
            f"TTS_GOOGLE_API_KEY_{upper}_SECONDARY",
            f"ENV_{upper}_SECONDARY_KEY",
            f"GOOGLE_TTS_{upper}_SECONDARY",
        ],
    )

    # If configured primary is known exhausted/dead, swap with healthy paid key if available
    if primary and not is_key_usable("google_tts", primary):
        usable_paid = [k for k in paid_keys if is_key_usable("google_tts", k)]
        if usable_paid and usable_paid[0] != secondary:
            primary = usable_paid[0]

    if not primary and paid_keys:
        primary = paid_keys[0]
    if not secondary and len(paid_keys) > 1:
        secondary = paid_keys[1]

    if not primary:
        primary = _first_env(env, ["GOOGLE_API_KEY_PRIMARY", "TTS_GOOGLE_API_KEY_PRIMARY"])
    if not secondary:
        secondary = _first_env(
            env, ["GOOGLE_API_KEY_SECONDARY", "TTS_GOOGLE_API_KEY_SECONDARY"]
        )

    pool = _collect_pool(env)
    slot_p, slot_s = _POOL_SLOT.get(code, (0, 1))
    if not primary and pool:
        primary = pool[slot_p % len(pool)]
    if not secondary and pool:
        cand = pool[slot_s % len(pool)]
        if cand != primary:
            secondary = cand
        elif len(pool) > 1:
            secondary = pool[(slot_s + 1) % len(pool)]
            if secondary == primary:
                secondary = ""

    if secondary and secondary == primary:
        secondary = ""
    return primary, secondary


def _max_quota_pct(api_key: str) -> float:
    if not api_key:
        return 0.0
    info = usage_ratios("google_tts", api_key)
    return max(float(info["hourly_pct"]), float(info["daily_pct"])) * 100.0


def select_google_key_for_lang(
    lang_or_name: str,
    *,
    force_slot: str = "",
) -> TtsRouteDecision:
    """Pick primary or secondary Google key with preemptive 90% switch."""
    code = normalize_lang_code(lang_or_name)
    cfg = lang_route(code)
    primary, secondary = resolve_dual_google_keys(code)
    events: List[Dict[str, Any]] = []

    def _decision(
        key: str,
        slot: str,
        reason: str,
        *,
        pct: float = 0.0,
    ) -> TtsRouteDecision:
        return TtsRouteDecision(
            lang=code,
            engine=ENGINE_GOOGLE,
            voice="",  # Gemini voice resolved by tts_client (Charon lock)
            api_key=key,
            key_slot=slot,
            fallback_engine=str(cfg.get("fallback_engine") or ENGINE_EDGE),
            fallback_voice=str(cfg.get("fallback_voice") or ""),
            secondary_key=secondary if slot == "primary" else primary,
            reason=reason,
            quota_pct=pct,
            events=list(events),
        )

    if force_slot == "secondary" and secondary:
        pct = _max_quota_pct(secondary)
        return _decision(secondary, "secondary", "forced_secondary", pct=pct)
    if force_slot == "primary" and primary:
        pct = _max_quota_pct(primary)
        return _decision(primary, "primary", "forced_primary", pct=pct)

    # Evaluate primary
    if primary:
        pct = _max_quota_pct(primary)
        usable = is_key_usable("google_tts", primary)
        soft = should_rotate("google_tts", primary)
        if usable and not soft:
            return _decision(primary, "primary", "primary_healthy", pct=pct)

        if soft or not usable:
            evt_type = (
                "QUOTA_HARD_BLOCK"
                if (not usable or pct >= HARD_CAP * 100)
                else "QUOTA_THRESHOLD_WARNING"
            )
            events.append(
                emit_quota_event(
                    evt_type,
                    lang=code,
                    key_slot="primary",
                    key_tail=primary[-4:],
                    quota_pct=pct,
                    detail="preemptive switch to secondary",
                )
            )
            if secondary and is_key_usable("google_tts", secondary):
                sp = _max_quota_pct(secondary)
                if should_rotate("google_tts", secondary):
                    events.append(
                        emit_quota_event(
                            "QUOTA_THRESHOLD_WARNING",
                            lang=code,
                            key_slot="secondary",
                            key_tail=secondary[-4:],
                            quota_pct=sp,
                            detail="secondary also near threshold",
                        )
                    )
                if is_key_usable("google_tts", secondary) and not (
                    _max_quota_pct(secondary) >= HARD_CAP * 100
                ):
                    return _decision(
                        secondary,
                        "secondary",
                        "preemptive_switch_from_primary",
                        pct=sp,
                    )

    # Secondary only path
    if secondary and is_key_usable("google_tts", secondary):
        sp = _max_quota_pct(secondary)
        if should_rotate("google_tts", secondary):
            events.append(
                emit_quota_event(
                    "QUOTA_THRESHOLD_WARNING",
                    lang=code,
                    key_slot="secondary",
                    key_tail=secondary[-4:],
                    quota_pct=sp,
                    detail="secondary at soft threshold — last Google key",
                )
            )
        if sp < HARD_CAP * 100:
            return _decision(secondary, "secondary", "secondary_only", pct=sp)

    # Check general pool before completely abandoning Google TTS
    pool = _collect_pool(os.environ)
    for p_key in pool:
        if p_key not in (primary, secondary) and is_key_usable("google_tts", p_key):
            sp = _max_quota_pct(p_key)
            if sp < HARD_CAP * 100:
                events.append(
                    emit_quota_event(
                        "QUOTA_THRESHOLD_WARNING",
                        lang=code,
                        key_slot="pool",
                        key_tail=p_key[-4:],
                        quota_pct=sp,
                        detail="dual keys unusable → using healthy pool key",
                    )
                )
                return _decision(p_key, "pool", "pool_key_fallback", pct=sp)

    # Both Google keys dead → Edge fallback decision (caller executes Edge)
    fb_voice = str(cfg.get("fallback_voice") or "")
    events.append(
        emit_quota_event(
            "TTS_FALLBACK_EDGE",
            lang=code,
            key_slot="",
            key_tail="",
            quota_pct=100.0,
            detail=f"both Google keys unusable → Edge {fb_voice}",
        )
    )
    return TtsRouteDecision(
        lang=code,
        engine=ENGINE_EDGE,
        voice=fb_voice,
        api_key="",
        key_slot="",
        fallback_engine=ENGINE_EDGE,
        fallback_voice=fb_voice,
        secondary_key="",
        reason="google_dual_key_exhausted",
        quota_pct=100.0,
        events=events,
    )


def _cf_decision(code: str, engine: str, *, reason: str) -> Optional[TtsRouteDecision]:
    """Build Cloudflare MeloTTS/Aura route when credentials + language allow."""
    try:
        from pipeline.custom_pipeline.tts_cloudflare import (
            aura_supports,
            list_tts_cf_credentials,
            melotts_supports,
        )
    except Exception:
        return None
    cfg = lang_route(code)
    fb = str(cfg.get("fallback_voice") or cfg.get("voice") or "")
    creds = list_tts_cf_credentials(code)
    if not creds:
        return None
    if engine == ENGINE_CF_MELOTTS:
        if not melotts_supports(code):
            return None
        key, acct, role = creds[0]
        return TtsRouteDecision(
            lang=code,
            engine=ENGINE_CF_MELOTTS,
            voice=fb,
            api_key=key,
            key_slot=f"cf_{role}",
            cf_account_id=acct,
            fallback_engine=ENGINE_EDGE,
            fallback_voice=fb,
            reason=reason,
        )
    if engine == ENGINE_CF_AURA:
        if not aura_supports(code):
            return None
        # Prefer secondary credential for Aura
        ordered = [c for c in creds if c[2] == "secondary"] + [
            c for c in creds if c[2] != "secondary"
        ]
        key, acct, role = ordered[0]
        return TtsRouteDecision(
            lang=code,
            engine=ENGINE_CF_AURA,
            voice=fb,
            api_key=key,
            key_slot=f"cf_{role}",
            cf_account_id=acct,
            aura_speaker=str(cfg.get("aura_speaker") or "asteria"),
            fallback_engine=ENGINE_EDGE,
            fallback_voice=fb,
            reason=reason,
        )
    return None


def resolve_tts_route(lang_or_name: str) -> TtsRouteDecision:
    """Top-level router: Cloudflare free → Google → Edge emergency."""
    code = normalize_lang_code(lang_or_name)
    cfg = lang_route(code)
    fb = str(cfg.get("fallback_voice") or cfg.get("voice") or "")

    # 1) Cloudflare MeloTTS (EN + supported European/CJK)
    if code in ("en", "es", "fr", "zh", "jp", "kr"):
        melo = _cf_decision(code, ENGINE_CF_MELOTTS, reason="cf_melotts_primary")
        if melo:
            return melo

        # 2) Cloudflare Aura-1 (English)
        aura = _cf_decision(code, ENGINE_CF_AURA, reason="cf_aura_primary")
        if aura:
            return aura

    # 3) Edge-only languages (hi, ur, or en when Cloudflare is unconfigured) NEVER use Google
    if code in EDGE_ONLY_LANGS:
        return TtsRouteDecision(
            lang=code,
            engine=ENGINE_EDGE,
            voice=fb or str(cfg.get("voice") or "en-US-JennyNeural"),
            reason="edge_only_language",
            fallback_engine=ENGINE_EDGE,
            fallback_voice=fb,
        )

    # 4) Google Gemini TTS when dual keys exist (bn/ta/ml) or any GOOGLE keys for lang
    if code in GOOGLE_PRIMARY_LANGS:
        return select_google_key_for_lang(code)
    primary, secondary = resolve_dual_google_keys(code)
    if primary or secondary:
        return select_google_key_for_lang(code)

    # 5) Edge emergency (always)
    return TtsRouteDecision(
        lang=code,
        engine=ENGINE_EDGE,
        voice=fb or str(cfg.get("voice") or "en-US-JennyNeural"),
        reason="edge_emergency",
        fallback_engine=ENGINE_EDGE,
        fallback_voice=fb,
    )


def next_tts_failover(decision: TtsRouteDecision) -> Optional[TtsRouteDecision]:
    """Advance along CF MeloTTS → CF Aura → Google → Edge."""
    code = decision.lang
    cfg = lang_route(code)
    fb = str(cfg.get("fallback_voice") or decision.fallback_voice or cfg.get("voice") or "")

    if decision.engine == ENGINE_CF_MELOTTS:
        aura = _cf_decision(code, ENGINE_CF_AURA, reason="failover_cf_aura")
        if aura:
            return aura
        if code in GOOGLE_PRIMARY_LANGS:
            return select_google_key_for_lang(code)
        return TtsRouteDecision(
            lang=code, engine=ENGINE_EDGE, voice=fb, reason="failover_edge_after_melo"
        )

    if decision.engine == ENGINE_CF_AURA:
        if code in GOOGLE_PRIMARY_LANGS:
            return select_google_key_for_lang(code)
        return TtsRouteDecision(
            lang=code, engine=ENGINE_EDGE, voice=fb, reason="failover_edge_after_aura"
        )

    if decision.engine == ENGINE_GOOGLE:
        return next_google_failover_key(decision)

    return None


def next_google_failover_key(decision: TtsRouteDecision) -> Optional[TtsRouteDecision]:
    """After 429/ResourceExhausted on current key, return secondary or pool key (or Edge)."""
    code = decision.lang
    current_key = decision.api_key

    # 1. Try secondary if primary just failed
    if decision.key_slot == "primary" and decision.secondary_key:
        if is_key_usable("google_tts", decision.secondary_key):
            emit_quota_event(
                "QUOTA_THRESHOLD_WARNING",
                lang=code,
                key_slot="primary",
                key_tail=decision.api_key[-4:] if decision.api_key else "",
                quota_pct=decision.quota_pct,
                detail="429/ResourceExhausted → catch-block secondary retry",
            )
            return select_google_key_for_lang(code, force_slot="secondary")

    # 2. Try any healthy key from the pool that isn't current_key or secondary
    pool = _collect_pool(os.environ)
    for p_key in pool:
        if p_key != current_key and p_key != decision.secondary_key and is_key_usable("google_tts", p_key):
            pct = _max_quota_pct(p_key)
            if pct < HARD_CAP * 100:
                cfg = lang_route(code)
                emit_quota_event(
                    "QUOTA_THRESHOLD_WARNING",
                    lang=code,
                    key_slot="pool",
                    key_tail=p_key[-4:],
                    quota_pct=pct,
                    detail="primary/secondary exhausted → failover to pool key",
                )
                return TtsRouteDecision(
                    lang=code,
                    engine=ENGINE_GOOGLE,
                    voice="",
                    api_key=p_key,
                    key_slot="pool",
                    fallback_engine=str(cfg.get("fallback_engine") or ENGINE_EDGE),
                    fallback_voice=str(cfg.get("fallback_voice") or ""),
                    secondary_key="",
                    reason="pool_key_failover",
                    quota_pct=pct,
                )

    # 3. Try Cloudflare free providers before Edge when Google dies (bn/ta/ml)
    if decision.engine == ENGINE_GOOGLE:
        melo = _cf_decision(code, ENGINE_CF_MELOTTS, reason="google_dead_try_melotts")
        if melo:
            return melo
        aura = _cf_decision(code, ENGINE_CF_AURA, reason="google_dead_try_aura")
        if aura:
            return aura

    cfg = lang_route(code)
    fb = str(cfg.get("fallback_voice") or decision.fallback_voice or "")
    emit_quota_event(
        "TTS_FALLBACK_EDGE",
        lang=code,
        key_slot=decision.key_slot,
        key_tail=decision.api_key[-4:] if decision.api_key else "",
        quota_pct=100.0,
        detail=f"Google retry exhausted → Edge {fb}",
    )
    return TtsRouteDecision(
        lang=code,
        engine=ENGINE_EDGE,
        voice=fb,
        reason="catch_block_edge_fallback",
        fallback_voice=fb,
        fallback_engine=ENGINE_EDGE,
    )

