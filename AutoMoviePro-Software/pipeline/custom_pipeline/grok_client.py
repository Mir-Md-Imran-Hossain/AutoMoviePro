"""xAI Grok chat client with free-tier quota rotate (90–95% cap).

Falls back to OpenRouter x-ai/grok models when no XAI key is available.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence

import httpx

import time

from pipeline.custom_pipeline.quota_rotate import (
    NeedMoreApiKeysError,
    is_quota_http_error,
    record_success,
)
from pipeline.custom_pipeline.session_keys import (
    get_grok_provider,
    get_session_grok_key,
    rotate_grok_key,
)

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"
OR_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_GROK_MODELS = ("grok-3", "grok-3-mini", "grok-2-latest")
DEFAULT_OR_GROK_MODELS = ("x-ai/grok-4.7", "x-ai/grok-4.6", "x-ai/grok-4.5", "x-ai/grok-4.3")


def resolve_grok_models(provider: str = "grok") -> List[str]:
    if provider == "openrouter_grok":
        raw = (os.environ.get("OPENROUTER_GROK_MODEL") or "").strip()
        if raw:
            return [m.strip() for m in raw.split(",") if m.strip()]
        return list(DEFAULT_OR_GROK_MODELS)
    raw = (os.environ.get("GROK_MODEL") or os.environ.get("XAI_MODEL") or "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_GROK_MODELS)


def grok_chat(
    prompt: str,
    *,
    system: str = "",
    api_keys: Optional[Sequence[str]] = None,
    models: Optional[Sequence[str]] = None,
    json_mode: bool = True,
    temperature: float = 0.7,
    timeout: float = 180.0,
) -> str:
    """Grok completion with session pin + auto-rotate before 100% quota."""
    explicit = (api_keys[0] if api_keys else None) or None
    attempts = 0
    last_err: Optional[Exception] = None

    while attempts < 6:
        attempts += 1
        try:
            key = get_session_grok_key(explicit=explicit if attempts == 1 else None)
        except NeedMoreApiKeysError:
            raise
        provider = get_grok_provider()
        model_list = list(models) if models else resolve_grok_models(provider)
        sys_msg = system or (
            "You are a helpful assistant. "
            + ("Respond with valid JSON only." if json_mode else "")
        )
        base = OR_BASE_URL if provider == "openrouter_grok" else XAI_BASE_URL
        url = base.rstrip("/") + "/chat/completions"

        for model in model_list:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": float(temperature),
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                if provider == "openrouter_grok":
                    headers["HTTP-Referer"] = "https://automoviepro.local"
                    headers["X-Title"] = "AutoMoviePro CustomPipeline"

                with httpx.Client(timeout=timeout) as client:
                    r = client.post(url, headers=headers, json=payload)
                if r.status_code >= 400:
                    err = RuntimeError(f"grok {r.status_code}: {r.text[:300]}")
                    last_err = err
                    logger.warning(
                        "Grok %s %s key…%s failed: %s",
                        provider,
                        model,
                        key[-4:],
                        r.text[:140],
                    )
                    if is_quota_http_error(err) or r.status_code in (429, 402):
                        try:
                            rotate_grok_key(reason=f"http_{r.status_code}")
                        except NeedMoreApiKeysError:
                            raise
                        break  # retry outer while with new key
                    body_l = (r.text or "").lower()
                    auth_like = r.status_code in (401, 403) or (
                        r.status_code == 400
                        and ("incorrect api key" in body_l or "invalid api key" in body_l)
                    )
                    if auth_like:
                        try:
                            rotate_grok_key(reason=f"auth_{r.status_code}")
                        except NeedMoreApiKeysError:
                            raise
                        break
                    continue

                content = (
                    r.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content")
                    or ""
                ).strip()
                if not content:
                    last_err = RuntimeError(f"grok empty model={model}")
                    continue

                record_success(provider, key)
                logger.info("Grok OK provider=%s model=%s key…%s", provider, model, key[-4:])
                return content
            except NeedMoreApiKeysError:
                raise
            except Exception as exc:
                last_err = exc
                if is_quota_http_error(exc):
                    try:
                        rotate_grok_key(reason=str(exc)[:80])
                    except NeedMoreApiKeysError:
                        raise
                    break
                logger.warning("Grok %s error: %s", model, exc)
                time.sleep(1.5)
        else:
            time.sleep(2.5)
            continue

    raise RuntimeError(f"Grok chat failed: {last_err}")
