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


_DEAD_GOOGLE_KEYS: set[str] = set()


def gemini_research_chat(
    prompt: str,
    *,
    system: str = "",
    json_mode: bool = True,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> str:
    """Fallback LLM chat using Google Gemini when Grok/OpenRouter keys are exhausted."""
    from pipeline.custom_pipeline.session_keys import list_localization_keys
    keys = list_localization_keys()
    if not keys:
        raise RuntimeError("No Google keys available for Gemini fallback")

    candidate_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(temperature),
        },
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    if system and system.strip():
        payload["systemInstruction"] = {"parts": [{"text": system.strip()}]}

    last_err = None
    for key in keys:
        if key in _DEAD_GOOGLE_KEYS:
            continue
        key_all_dead = True
        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                with httpx.Client(timeout=timeout) as client:
                    r = client.post(
                        url,
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                        json=payload,
                    )
                if r.status_code == 200:
                    key_all_dead = False
                    data = r.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text and text.strip():
                            logger.info("Gemini research fallback OK (model=%s, key=…%s)", model, key[-4:])
                            return text.strip()
                elif r.status_code in (404, 400):
                    continue
                elif r.status_code == 429:
                    key_all_dead = False
                    break
            except Exception as e:
                last_err = e
                continue
        if key_all_dead:
            _DEAD_GOOGLE_KEYS.add(key)
    raise RuntimeError(f"All Gemini fallback attempts failed: {last_err}")


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
    """Grok completion with session pin + auto-rotate before 100% quota, with Gemini fallback."""
    if os.environ.get("USE_GEMINI_RESEARCH", "").strip() in ("1", "true", "yes"):
        logger.info("USE_GEMINI_RESEARCH active — using Google Gemini directly.")
        return gemini_research_chat(
            prompt,
            system=system,
            json_mode=json_mode,
            temperature=temperature,
            timeout=timeout,
        )

    explicit = (api_keys[0] if api_keys else None) or None
    attempts = 0
    last_err: Optional[Exception] = None

    try:
        while attempts < 6:
            attempts += 1
            try:
                key = get_session_grok_key(explicit=explicit if attempts == 1 else None)
            except NeedMoreApiKeysError:
                logger.warning("NeedMoreApiKeysError for Grok — falling back to Google Gemini...")
                return gemini_research_chat(
                    prompt,
                    system=system,
                    json_mode=json_mode,
                    temperature=temperature,
                    timeout=timeout,
                )
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
                        "max_tokens": 4096,
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
                                logger.warning("Grok quota exhausted — falling back to Google Gemini...")
                                return gemini_research_chat(
                                    prompt,
                                    system=system,
                                    json_mode=json_mode,
                                    temperature=temperature,
                                    timeout=timeout,
                                )
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
                                logger.warning("Grok auth error & no keys — falling back to Google Gemini...")
                                return gemini_research_chat(
                                    prompt,
                                    system=system,
                                    json_mode=json_mode,
                                    temperature=temperature,
                                    timeout=timeout,
                                )
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
                    logger.warning("NeedMoreApiKeysError inside loop — falling back to Google Gemini...")
                    return gemini_research_chat(
                        prompt,
                        system=system,
                        json_mode=json_mode,
                        temperature=temperature,
                        timeout=timeout,
                    )
                except Exception as exc:
                    last_err = exc
                    if is_quota_http_error(exc):
                        try:
                            rotate_grok_key(reason=str(exc)[:80])
                        except NeedMoreApiKeysError:
                            logger.warning("Grok quota exhausted — falling back to Google Gemini...")
                            return gemini_research_chat(
                                prompt,
                                system=system,
                                json_mode=json_mode,
                                temperature=temperature,
                                timeout=timeout,
                            )
                        break
                    logger.warning("Grok %s error: %s", model, exc)
                    time.sleep(1.5)
            else:
                time.sleep(2.5)
                continue
    except Exception as exc:
        logger.warning("Grok chat outer exception %s — falling back to Google Gemini...", exc)
        return gemini_research_chat(
            prompt,
            system=system,
            json_mode=json_mode,
            temperature=temperature,
            timeout=timeout,
        )

    logger.warning("Grok attempts exhausted — falling back to Google Gemini...")
    return gemini_research_chat(
        prompt,
        system=system,
        json_mode=json_mode,
        temperature=temperature,
        timeout=timeout,
    )
