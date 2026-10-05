"""Provider portal URLs + short help metadata for channel API UI.

Uses dedicated per-task slots (agent/topic/image/localize/TTS/…) as the
primary UI surface. Legacy PROVIDER_DEFS remain for older forms.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from pipeline.channel_api_slots import PROVIDER_DEFS

# Signup / API-key collection pages (open in browser from UI)
PROVIDER_PORTALS: Dict[str, Dict[str, str]] = {
    "google": {
        "portal_url": "https://aistudio.google.com/apikey",
        "portal_label": "Google AI Studio",
        "help_key": "help_api_google",
    },
    "groq": {
        "portal_url": "https://console.groq.com/keys",
        "portal_label": "Groq Console",
        "help_key": "help_api_groq",
    },
    "openrouter": {
        "portal_url": "https://openrouter.ai/keys",
        "portal_label": "OpenRouter Keys",
        "help_key": "help_api_openrouter",
    },
    "pollinations": {
        "portal_url": "https://auth.pollinations.ai/",
        "portal_label": "Pollinations Auth",
        "help_key": "help_api_pollinations",
    },
    "pexels": {
        "portal_url": "https://www.pexels.com/api/",
        "portal_label": "Pexels API",
        "help_key": "help_api_pexels",
    },
    "agnes": {
        "portal_url": "https://agnes-ai.com/",
        "portal_label": "Agnes AI",
        "help_key": "help_api_agnes",
    },
    "huggingface": {
        "portal_url": "https://huggingface.co/settings/tokens",
        "portal_label": "Hugging Face Tokens",
        "help_key": "help_api_huggingface",
    },
    "cerebras": {
        "portal_url": "https://cloud.cerebras.ai/",
        "portal_label": "Cerebras Cloud",
        "help_key": "help_api_cerebras",
    },
    "freetheai": {
        "portal_url": "https://www.freetheai.com/",
        "portal_label": "FreeTheAI",
        "help_key": "help_api_freetheai",
    },
    "workers_ai": {
        "portal_url": "https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
        "portal_label": "Cloudflare Workers AI",
        "help_key": "help_api_workers_ai",
    },
    "grok": {
        "portal_url": "https://console.x.ai/",
        "portal_label": "xAI Console",
        "help_key": "help_api_topic_grok",
    },
}


def providers_ui_meta() -> List[Dict[str, Any]]:
    """Legacy provider list (kept for older UI consumers)."""
    out: List[Dict[str, Any]] = []
    for pid, label, required in PROVIDER_DEFS:
        meta = PROVIDER_PORTALS.get(pid) or {}
        out.append(
            {
                "id": pid,
                "label": label,
                "required": required,
                "portal_url": meta.get("portal_url") or "",
                "portal_label": meta.get("portal_label") or label,
                "help_key": meta.get("help_key") or f"help_api_{pid}",
            }
        )
    return out


def dedicated_providers_ui_meta(
    *,
    unlocked: Optional[Sequence[str]] = None,
    channel: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    from pipeline.dedicated_api_registry import providers_ui_meta_dedicated

    return providers_ui_meta_dedicated(unlocked=unlocked, channel=channel)
