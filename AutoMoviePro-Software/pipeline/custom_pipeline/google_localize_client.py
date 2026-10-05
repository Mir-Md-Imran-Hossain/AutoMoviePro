"""Google Gemini localization client — quota-safe rotate (90–95% cap)."""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence

import httpx

from pipeline.custom_pipeline.quota_rotate import (
    NeedMoreApiKeysError,
    is_quota_http_error,
    record_success,
)
from pipeline.custom_pipeline.session_keys import (
    get_session_localize_key,
    rotate_localize_key,
)

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_LOCALIZE_MODEL = "gemini-3-flash-preview"
# Prefer currently-available Flash models first (2.5-* often 404 for new keys; *-latest spikes 503).
LOCALIZE_MODEL_FALLBACKS = (
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)


def resolve_localize_model() -> str:
    return (
        (os.environ.get("LOCALIZATION_GOOGLE_MODEL") or "").strip()
        or (os.environ.get("GOOGLE_LOCALIZE_MODEL") or "").strip()
        or DEFAULT_LOCALIZE_MODEL
    )


def resolve_localize_models(explicit: Optional[str] = None) -> List[str]:
    primary = (explicit or resolve_localize_model()).strip()
    out: List[str] = []
    seen = set()
    for m in (primary, *LOCALIZE_MODEL_FALLBACKS):
        name = (m or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def google_localize_chat(
    prompt: str,
    *,
    system: str = "",
    language: str = "English",
    api_keys: Optional[Sequence[str]] = None,
    model: Optional[str] = None,
    temperature: float = 0.55,
    timeout: float = 180.0,
) -> str:
    """Gemini generateContent with per-language pin + soft/hard quota rotate."""
    explicit = (api_keys[0] if api_keys else None) or None
    models = resolve_localize_models(model)
    last_err: Optional[Exception] = None
    payload_base = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(temperature),
            "responseMimeType": "application/json",
        },
    }
    if (system or "").strip():
        payload_base["systemInstruction"] = {"parts": [{"text": system.strip()}]}

    attempts = 0
    while attempts < 10:
        attempts += 1
        try:
            key = get_session_localize_key(
                language, explicit=explicit if attempts == 1 else None
            )
        except NeedMoreApiKeysError:
            raise

        rotated = False
        saw_503 = False
        for model_id in models:
            url = f"{GEMINI_BASE}/models/{model_id}:generateContent"
            try:
                from pipeline.custom_pipeline.google_pacing_guard import (
                    analyze_quota_error,
                    wait_pacing_gap,
                )

                wait_pacing_gap(
                    modality="general",
                    provider="google_localize",
                    reason=f"localize_{language}_{model_id}",
                )

                with httpx.Client(timeout=timeout) as client:
                    r = client.post(
                        url,
                        headers={
                            "x-goog-api-key": key,
                            "Content-Type": "application/json",
                        },
                        json=payload_base,
                    )
                if r.status_code >= 400:
                    last_err = RuntimeError(
                        f"google_localize {model_id} {r.status_code}: {r.text[:300]}"
                    )
                    logger.warning(
                        "Localization %s lang=%s key…%s failed: %s",
                        model_id,
                        language,
                        key[-4:],
                        r.text[:140],
                    )
                    # Retired model — skip
                    if r.status_code == 404:
                        continue
                    # Temporary overload — try next model on SAME key
                    if r.status_code == 503:
                        saw_503 = True
                        continue

                    # Quota / Rate-limit analysis
                    if r.status_code == 429 or is_quota_http_error(last_err):
                        qa = analyze_quota_error(r.text, dict(r.headers))
                        if qa.can_auto_wait:
                            logger.warning(
                                "Google localization quota touched (%s, wait %s). "
                                "Pausing pipeline to let quota refill...",
                                qa.window_type,
                                qa.human_duration,
                            )
                            import time as _time

                            _time.sleep(qa.cooldown_seconds)
                            continue  # retry with fresh quota window

                        # Longer/Daily quota exhaustion — rotate key
                        try:
                            hours = max(1.0, qa.cooldown_seconds / 3600.0)
                            from pipeline.custom_pipeline.quota_rotate import mark_exhausted

                            mark_exhausted(
                                "google_localize",
                                key,
                                reason=f"quota:{qa.window_type}",
                                hours=hours,
                            )
                            rotate_localize_key(language, reason=f"http_{r.status_code}")
                        except NeedMoreApiKeysError:
                            raise
                        rotated = True
                        break

                    # Hard auth error (401, 403)
                    if r.status_code in (401, 403):
                        try:
                            from pipeline.custom_pipeline.quota_rotate import mark_exhausted

                            mark_exhausted(
                                "google_localize",
                                key,
                                reason=f"http_{r.status_code}",
                                hours=24.0,
                            )
                            rotate_localize_key(language, reason=f"http_{r.status_code}")
                        except NeedMoreApiKeysError:
                            raise
                        rotated = True
                        break
                    continue

                text = _extract_text(r.json())
                if not text:
                    last_err = RuntimeError(f"empty model={model_id}")
                    continue

                record_success("google_localize", key)
                logger.info(
                    "Localization OK model=%s lang=%s key…%s",
                    model_id,
                    language,
                    key[-4:],
                )
                return text.strip()
            except NeedMoreApiKeysError:
                raise
            except Exception as exc:
                last_err = exc
                if is_quota_http_error(exc):
                    try:
                        rotate_localize_key(language, reason=str(exc)[:80])
                    except NeedMoreApiKeysError:
                        raise
                    rotated = True
                    break
                logger.warning(
                    "Localization %s lang=%s error: %s", model_id, language, exc
                )

        if rotated:
            continue
        # All models overloaded on this key → brief backoff, then next key
        # Do NOT treat transient 503 as hard quota exhaustion (that burns keys 6h).
        if saw_503:
            import time as _time

            backoff = min(45.0, 5.0 * attempts)
            logger.warning(
                "Localization all models 503 lang=%s — backoff %.0fs then rotate key",
                language,
                backoff,
            )
            _time.sleep(backoff)
            try:
                rotate_localize_key(
                    language, reason="all_models_503_soft", exhaust=False
                )
                rotated = True
                continue
            except NeedMoreApiKeysError:
                raise
        break

    raise RuntimeError(f"Google localization chat failed: {last_err}")


def _extract_text(data: dict) -> str:
    chunks: List[str] = []
    for cand in data.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            t = part.get("text")
            if t:
                chunks.append(str(t))
    return "\n".join(chunks).strip()
