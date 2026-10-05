"""
Purpose-aware free-provider capability map + key pools.

Policy (hard — burn control)
----------------------------
- Google Gemini text/vision: ONLY for purpose translate|localize|condense.
- Script / topic / agent / critic / repair / precheck: Groq → Cerebras → OpenRouter → HF → FreeTheAI.
  Never Google (unless AMP_FORCE_GOOGLE=1).
- TTS: Edge-TTS first (keyless); Google Charon TTS optional fallback (same vault — use sparingly).
- Image: Pollinations → FreeTheAI → Goblin → HF  (no Google by default).
- Video: Agnes only.

Burn rules
----------
- At most 1–2 keys per call for text providers (org-level quotas on Groq).
- Provider circuit + hourly/daily budgets via provider_budget.
- Translate may use ONE Google key last-resort (or first if AMP_GOOGLE_TRANSLATE_FIRST=1).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

# What each provider can do for free (honest capability matrix)
CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "groq": {"text": True, "agent": True, "tts": False, "image": False, "video": False, "audio_stt": True},
    "cerebras": {"text": True, "agent": True, "tts": False, "image": False, "video": False, "audio_stt": False},
    "openrouter": {"text": True, "agent": True, "tts": False, "image": False, "video": False, "audio_stt": False},
    "huggingface": {"text": True, "agent": True, "tts": False, "image": True, "video": False, "audio_stt": False},
    "freetheai": {"text": True, "agent": True, "tts": False, "image": True, "video": False, "audio_stt": False},
    # Google text allowed for translate; image/video allowed with Google Pro
    "google": {"text": True, "agent": False, "tts": True, "image": True, "video": True, "audio_stt": False},
    "edge_tts": {"text": False, "agent": False, "tts": True, "image": False, "video": False, "audio_stt": False},
    "pollinations": {"text": False, "agent": False, "tts": False, "image": True, "video": False, "audio_stt": False},
    "goblin": {"text": False, "agent": False, "tts": False, "image": True, "video": False, "audio_stt": False},
    "agnes": {"text": False, "agent": False, "tts": False, "image": True, "video": True, "audio_stt": False},
}

# Default image order — includes Google Imagen 3 / 4 with free fallbacks
IMAGE_CHAIN_DEFAULT = ("google", "pollinations", "freetheai", "goblin", "huggingface")

# Text chains — Google NEVER appears except translate
TEXT_CHAIN_SCRIPT = ("groq", "cerebras", "openrouter", "huggingface", "freetheai")
TEXT_CHAIN_AGENT = ("groq", "cerebras", "openrouter", "huggingface", "freetheai")
TEXT_CHAIN_GENERAL = ("groq", "cerebras", "openrouter", "huggingface", "freetheai")
# Localization: prefer free routers; Google last (allowed purpose only)
TEXT_CHAIN_TRANSLATE = ("huggingface", "groq", "openrouter", "cerebras", "freetheai", "google")
TEXT_CHAIN_TRANSLATE_GOOGLE_FIRST = ("google", "huggingface", "groq", "openrouter", "cerebras", "freetheai")

# How many Google keys reserved per purpose (from the vault, sticky slice)
GOOGLE_PURPOSE_SLICES = {
    "translate": (0, 1),  # ONE key for localization only
    "tts": (0, 40),  # map walks healthy keys; Edge preferred first
    "other": (0, 0),  # no Google for non-translate purposes
}

# Non-Google: take at most N keys into the purpose pool
PURPOSE_KEY_COUNTS = {
    "script": {"groq": 2, "cerebras": 1, "openrouter": 2, "huggingface": 1, "freetheai": 1},
    "agent": {"groq": 2, "cerebras": 1, "openrouter": 2, "huggingface": 1, "freetheai": 1},
    "translate": {"groq": 2, "cerebras": 1, "openrouter": 2, "huggingface": 1, "freetheai": 1, "google": 1},
    "tts": {"google": 8},  # capped failover — do not spray full vault
    "image": {"freetheai": 1, "huggingface": 1},
}

GOOGLE_ALLOWED_PURPOSES = frozenset({"translate", "localize", "condense", "image", "video", "media"})


def google_allowed_for_purpose(purpose: str) -> bool:
    p = (purpose or "").lower().strip()
    if os.environ.get("AMP_FORCE_GOOGLE", "").strip() == "1":
        return True
    if os.environ.get("AMP_DISABLE_GOOGLE_MEDIA", "").strip() == "1" and p in ("image", "video", "media"):
        return False
    return p in GOOGLE_ALLOWED_PURPOSES


def chain_for_purpose(purpose: str) -> tuple:
    p = (purpose or "general").lower().strip()
    if p in ("script", "topic", "director", "niche"):
        chain = TEXT_CHAIN_SCRIPT
    elif p in ("agent", "critic", "repair", "precheck"):
        chain = TEXT_CHAIN_AGENT
    elif p in ("translate", "localize", "condense"):
        if os.environ.get("AMP_GOOGLE_TRANSLATE_FIRST", "").strip().lower() in ("1", "true", "yes"):
            chain = TEXT_CHAIN_TRANSLATE_GOOGLE_FIRST
        else:
            chain = TEXT_CHAIN_TRANSLATE
    else:
        chain = TEXT_CHAIN_GENERAL

    # OpenRouter preference: move openrouter to front (still after force-google if set)
    prefer_or = os.environ.get("AMP_PREFER_OPENROUTER", "").strip().lower() in ("1", "true", "yes")
    if prefer_or and "openrouter" in chain:
        chain = ("openrouter",) + tuple(x for x in chain if x != "openrouter")

    # Strip Google unless purpose allows it
    if not google_allowed_for_purpose(p):
        chain = tuple(x for x in chain if x != "google")
    return chain


def slice_keys(keys: Sequence[str], start: int, end: int) -> List[str]:
    raw = [k for k in keys if (k or "").strip()]
    if not raw:
        return []
    if end <= start:
        return []
    if len(raw) <= start:
        return raw[:1]
    return list(raw[start: min(end, len(raw))]) or raw[:1]


def google_keys_for_purpose(google_keys: Sequence[str], purpose: str) -> List[str]:
    p = (purpose or "other").lower().strip()
    if not google_allowed_for_purpose(p) and p != "tts":
        return []
    if p in ("translate", "localize", "condense"):
        sl = GOOGLE_PURPOSE_SLICES["translate"]
    elif p == "tts":
        sl = GOOGLE_PURPOSE_SLICES["tts"]
    else:
        sl = GOOGLE_PURPOSE_SLICES["other"]
    return slice_keys(google_keys, sl[0], sl[1])


def provider_keys_for_purpose(
    *,
    purpose: str,
    provider: str,
    bundle: Dict[str, Any],
) -> List[str]:
    """Return a capped key list for this purpose+provider (never full vault spray)."""
    p = (purpose or "general").lower().strip()
    if p in ("script", "topic", "director", "niche"):
        counts = PURPOSE_KEY_COUNTS["script"]
    elif p in ("agent", "critic", "repair", "precheck"):
        counts = PURPOSE_KEY_COUNTS["agent"]
    elif p in ("translate", "localize", "condense"):
        counts = PURPOSE_KEY_COUNTS["translate"]
    elif p == "tts":
        counts = PURPOSE_KEY_COUNTS["tts"]
    elif p == "image":
        counts = PURPOSE_KEY_COUNTS["image"]
    else:
        counts = PURPOSE_KEY_COUNTS["script"]

    key_map = {
        "groq": "groq_keys",
        "cerebras": "cerebras_keys",
        "openrouter": "openrouter_keys",
        "huggingface": "huggingface_keys",
        "freetheai": "freetheai_keys",
        "google": "google_keys",
    }
    field = key_map.get(provider)
    if not field:
        return []
    raw = list(bundle.get(field) or [])
    if provider == "google":
        return google_keys_for_purpose(raw, purpose)
    n = int(counts.get(provider, 1))
    return [k for k in raw if (k or "").strip()][: max(1, n)]


def image_provider_chain() -> List[str]:
    """Resolved image fallback order (env + Goblin primary flag)."""
    raw = (os.environ.get("IMAGE_PROVIDER_PRIORITY") or "").strip()
    if raw:
        chain = [p.strip().lower() for p in raw.split(",") if p.strip()]
    else:
        chain = list(IMAGE_CHAIN_DEFAULT)
    # Normalize aliases
    alias = {"agnes_image": "agnes", "google_image": "google", "hf": "huggingface"}
    chain = [alias.get(p, p) for p in chain]
    # Keep Google unless explicitly disabled (allows Imagen 3 / 4 for Google Pro accounts)
    disable_gimg = os.environ.get("AMP_ALLOW_GOOGLE_IMAGE", "").strip().lower() in ("0", "false", "no")
    if disable_gimg:
        chain = [p for p in chain if p != "google"]
    # Drop unknown / non-image
    chain = [p for p in chain if CAPABILITIES.get(p, {}).get("image")]
    try:
        from pipeline.goblin_image import goblin_enabled, goblin_primary

        if not goblin_enabled():
            chain = [p for p in chain if p != "goblin"]
        elif goblin_primary():
            chain = ["goblin"] + [p for p in chain if p != "goblin"]
        elif "goblin" not in chain:
            if "freetheai" in chain:
                i = chain.index("freetheai") + 1
                chain.insert(i, "goblin")
            else:
                chain.append("goblin")
    except Exception:
        pass
    seen = set()
    out: List[str] = []
    for p in chain:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out or list(IMAGE_CHAIN_DEFAULT)


def capability_summary() -> Dict[str, Any]:
    return {
        "capabilities": CAPABILITIES,
        "text_chain_script": list(TEXT_CHAIN_SCRIPT),
        "text_chain_agent": list(TEXT_CHAIN_AGENT),
        "text_chain_translate": list(chain_for_purpose("translate")),
        "tts_chain": ["edge_tts", "google"],
        "image_chain": image_provider_chain(),
        "video_chain": ["agnes"],
        "google_policy": "translate_localize_only",
        "notes": {
            "google": "ONLY translate/localize (and optional Charon TTS fallback). Never script/agent/critic/image.",
            "groq": "Primary for script/agent/critic text. Org-level limits — sticky 1–2 keys/call.",
            "openrouter": "Set AMP_PREFER_OPENROUTER=1 to put OR first on text chains.",
            "tts": "Edge-TTS primary; Google TTS only if Edge fails (set AMP_PREFER_EDGE_TTS=1).",
            "critic": "Default AMP_CRITIC_USE_GOOGLE=0 → text router (Groq/OR), not Gemini upload.",
        },
    }
