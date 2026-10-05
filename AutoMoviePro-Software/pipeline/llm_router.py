"""
Text-LLM router — purpose-aware free provider chain.

Default text/agent order:
  Groq → Cerebras → OpenRouter → HuggingFace → FreeTheAI → Google(gated)

Burn guards: provider_budget circuits + purpose_caps key slices (never vault spray).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

# Model IDs from C11-B list-models + minimal chat readiness (2026-09-06).
# Prior llama-* Groq/Cerebras IDs returned 404 model_not_found on this account.
GROQ_MODELS_SCRIPT = (
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
)
GROQ_MODELS_AGENT = (
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
)
CEREBRAS_MODELS = (
    "qwen-3.8-27b",  # only model listed for account; chat may still 402 if billing locked
)
OPENROUTER_MODELS = (
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.2-3b-instruct",
    "qwen/qwen3.6-27b",
)
HF_CHAT_MODELS = (
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "HuggingFaceH4/zephyr-7b-beta",
)
# Translate / localize prefers models that fit free-tier token caps.
GROQ_MODELS_TRANSLATE = (
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
)
FREETHEAI_TEXT_MODELS = ("gpt-4o-mini", "gpt-4o", "eve/gpt-4o-mini")
GOOGLE_TEXT_MODEL = "gemini-flash-lite-latest"


def is_daily_quota_zero(exc_or_msg) -> bool:
    from pipeline.google_api_gate import is_daily_quota_zero as _z

    return _z(exc_or_msg)


def mark_google_pool_exhausted(reason: str = "free_tier_limit_0") -> None:
    from pipeline.google_api_gate import open_circuit

    open_circuit(reason)


def clear_google_pool_exhausted() -> None:
    from pipeline.google_api_gate import close_circuit

    close_circuit()


def google_pool_exhausted() -> bool:
    from pipeline.google_api_gate import circuit_is_open

    return circuit_is_open()


def prefer_openrouter() -> bool:
    """True when OpenRouter should lead text chains (env) or Google force is off."""
    if os.environ.get("AMP_FORCE_GOOGLE", "").strip() == "1":
        return False
    if os.environ.get("AMP_PREFER_OPENROUTER", "").strip().lower() in ("1", "true", "yes"):
        return True
    # Default: prefer non-Google text routers (Google reserved for translate)
    return True


def _dedupe(keys: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for k in keys:
        v = (k or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _bundle():
    from pipeline.api_keys import load_api_bundle

    return load_api_bundle()


def resolve_keys(provider: str, explicit: Optional[Sequence[str]] = None) -> List[str]:
    if explicit:
        return _dedupe(list(explicit))
    b = _bundle()
    field = {
        "groq": "groq_keys",
        "cerebras": "cerebras_keys",
        "openrouter": "openrouter_keys",
        "huggingface": "huggingface_keys",
        "freetheai": "freetheai_keys",
        "google": "google_keys",
    }.get(provider)
    return _dedupe(list(b.get(field) or [])) if field else []


def resolve_openrouter_keys(
    *,
    openrouter_api: str = "",
    openrouter_keys: Optional[List[str]] = None,
) -> List[str]:
    return resolve_keys("openrouter", [openrouter_api, *(openrouter_keys or [])])


def resolve_huggingface_keys(
    *,
    huggingface_api: str = "",
    huggingface_keys: Optional[List[str]] = None,
) -> List[str]:
    return resolve_keys("huggingface", [huggingface_api, *(huggingface_keys or [])])


def openai_compatible_chat(
    *,
    provider: str,
    base_url: str,
    api_keys: List[str],
    models: Sequence[str],
    prompt: str,
    json_mode: bool = False,
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    from pipeline.provider_budget import (
        circuit_is_open,
        is_rate_limit_error,
        max_models,
        record_failure,
        record_success,
        select_provider_keys,
    )

    if circuit_is_open(provider):
        raise RuntimeError(f"{provider}_circuit_open")
    keys = select_provider_keys(api_keys, provider)
    if not keys:
        raise RuntimeError(f"no {provider} keys")
    model_list = list(models)[: max_models(provider)]
    sys_msg = system or (
        "You are a helpful assistant. "
        + ("Respond with valid JSON only." if json_mode else "Be concise and accurate.")
    )
    temp = 0.3 if temperature is None else float(temperature)
    last_err: Optional[Exception] = None
    url = base_url.rstrip("/") + "/chat/completions"

    for key in keys:
        for model in model_list:
            try:
                with httpx.Client(timeout=120.0) as client:
                    payload: Dict[str, Any] = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temp,
                    }
                    if json_mode:
                        payload["response_format"] = {"type": "json_object"}
                    r = client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if r.status_code >= 400:
                        last_err = RuntimeError(
                            f"{provider} {r.status_code}: {r.text[:220]}"
                        )
                        logger.warning(
                            "%s %s key…%s: %s",
                            provider,
                            model,
                            key[-4:],
                            r.text[:140],
                        )
                        record_failure(provider, r.text)
                        if r.status_code in (401, 403):
                            break
                        if r.status_code in (402, 429):
                            raise last_err
                        continue
                    content = (
                        r.json().get("choices", [{}])[0].get("message", {}).get("content")
                        or ""
                    ).strip()
                    if not content:
                        continue
                    record_success(provider)
                    logger.info("%s OK model=%s key…%s", provider, model, key[-4:])
                    return content
            except Exception as exc:
                last_err = exc
                record_failure(provider, exc)
                if is_rate_limit_error(exc) or circuit_is_open(provider):
                    break
        if circuit_is_open(provider):
            break
    raise RuntimeError(f"{provider} chat failed: {last_err}")


def groq_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    purpose: str = "script",
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    if purpose in ("translate", "localize", "condense"):
        models = GROQ_MODELS_TRANSLATE
    elif purpose in ("agent", "critic", "repair"):
        models = GROQ_MODELS_AGENT
    else:
        models = GROQ_MODELS_SCRIPT
    return openai_compatible_chat(
        provider="groq",
        base_url="https://api.groq.com/openai/v1",
        api_keys=api_keys,
        models=models,
        prompt=prompt,
        json_mode=json_mode,
        system=system,
        temperature=temperature,
    )


def cerebras_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    return openai_compatible_chat(
        provider="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_keys=api_keys,
        models=CEREBRAS_MODELS,
        prompt=prompt,
        json_mode=json_mode,
        system=system,
        temperature=temperature,
    )


def openrouter_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    models=None,
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    return openai_compatible_chat(
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_keys=api_keys,
        models=models or OPENROUTER_MODELS,
        prompt=prompt,
        json_mode=json_mode,
        system=system,
        temperature=temperature,
    )


def freetheai_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    base_url: str = "",
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    b = _bundle()
    base = (base_url or str(b.get("freetheai_base_url") or "https://api.freetheai.xyz/v1")).rstrip("/")
    return openai_compatible_chat(
        provider="freetheai",
        base_url=base,
        api_keys=api_keys,
        models=FREETHEAI_TEXT_MODELS,
        prompt=prompt,
        json_mode=json_mode,
        system=system,
        temperature=temperature,
    )


def _hf_extract_text(data: Any) -> str:
    if isinstance(data, dict):
        if "choices" in data:
            return str(data["choices"][0]["message"]["content"] or "").strip()
        if "generated_text" in data:
            return str(data["generated_text"] or "").strip()
        if isinstance(data.get("error"), str):
            raise RuntimeError(data["error"])
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict) and "generated_text" in item:
            return str(item["generated_text"] or "").strip()
    return str(data or "").strip()


def huggingface_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    models=None,
    system: str = "",
    temperature: Optional[float] = None,
) -> str:
    from pipeline.provider_budget import (
        circuit_is_open,
        is_rate_limit_error,
        max_models,
        record_failure,
        record_success,
        select_provider_keys,
    )

    keys = select_provider_keys(api_keys, "huggingface")
    if not keys:
        raise RuntimeError("no HuggingFace keys")
    model_list = list(models or HF_CHAT_MODELS)[: max_models("huggingface")]
    sys_msg = system or (
        "You are a helpful assistant. "
        + ("Respond with valid JSON only." if json_mode else "Be concise and accurate.")
    )
    temp = 0.3 if temperature is None else float(temperature)
    last_err: Optional[Exception] = None
    for key in keys:
        for model in model_list:
            try:
                with httpx.Client(timeout=180.0) as client:
                    r = client.post(
                        "https://router.huggingface.co/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": sys_msg},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": 2048,
                            "temperature": temp,
                        },
                    )
                    if r.status_code < 400:
                        text = _hf_extract_text(r.json())
                        if text:
                            record_success("huggingface")
                            return text
                    last_err = RuntimeError(f"hf {r.status_code}: {r.text[:200]}")
                    record_failure("huggingface", r.text)
                    if r.status_code in (402, 429):
                        raise last_err
            except Exception as exc:
                last_err = exc
                record_failure("huggingface", exc)
                if is_rate_limit_error(exc) or circuit_is_open("huggingface"):
                    break
        if circuit_is_open("huggingface"):
            break
    raise RuntimeError(f"HuggingFace chat failed: {last_err}")


def google_chat(
    prompt: str,
    *,
    api_keys: List[str],
    json_mode: bool = False,
    model: str = GOOGLE_TEXT_MODEL,
    system: str = "",
) -> str:
    from pipeline.google_api_gate import GoogleCircuitOpen, gated_generate_content

    cfg = None
    if json_mode:
        from google.genai import types

        cfg = types.GenerateContentConfig(response_mime_type="application/json")
    contents = prompt
    if (system or "").strip():
        contents = f"{system.strip()}\n\n{prompt}"
    try:
        result = gated_generate_content(
            api_keys=api_keys,
            contents=contents,
            model=model,
            purpose="text",
            config=cfg,
        )
    except GoogleCircuitOpen:
        raise RuntimeError("google_pool_exhausted") from None
    if not result.text:
        raise RuntimeError("Google chat empty response")
    return result.text


def chat_text(
    prompt: str,
    *,
    purpose: str = "script",
    google_api_keys: Optional[List[str]] = None,
    openrouter_api: str = "",
    openrouter_keys: Optional[List[str]] = None,
    huggingface_api: str = "",
    huggingface_keys: Optional[List[str]] = None,
    groq_keys: Optional[List[str]] = None,
    cerebras_keys: Optional[List[str]] = None,
    freetheai_keys: Optional[List[str]] = None,
    json_mode: bool = False,
    prefer_or: Optional[bool] = None,
    system: str = "",
) -> Dict[str, str]:
    """
    Returns {"text": "...", "provider": "..."}.
    Purpose drives chain + key pools.
    Google is only attempted for translate/localize/condense (see purpose_caps).
    """
    from pipeline.purpose_caps import (
        chain_for_purpose,
        google_allowed_for_purpose,
        provider_keys_for_purpose,
    )
    from pipeline.provider_budget import circuit_is_open

    b = _bundle()
    # Merge explicit keys into a working bundle view
    work = dict(b)
    if google_api_keys:
        work["google_keys"] = _dedupe(list(google_api_keys))
    if openrouter_keys or openrouter_api:
        work["openrouter_keys"] = resolve_openrouter_keys(
            openrouter_api=openrouter_api, openrouter_keys=openrouter_keys
        )
    if huggingface_keys or huggingface_api:
        work["huggingface_keys"] = resolve_huggingface_keys(
            huggingface_api=huggingface_api, huggingface_keys=huggingface_keys
        )
    if groq_keys:
        work["groq_keys"] = _dedupe(list(groq_keys))
    if cerebras_keys:
        work["cerebras_keys"] = _dedupe(list(cerebras_keys))
    if freetheai_keys:
        work["freetheai_keys"] = _dedupe(list(freetheai_keys))

    chain = list(chain_for_purpose(purpose))
    # Legacy prefer_or arg / AMP_PREFER_OPENROUTER already applied in chain_for_purpose;
    # honor explicit prefer_or=True by moving OR first once more.
    if prefer_or is True and "openrouter" in chain:
        chain = ["openrouter"] + [p for p in chain if p != "openrouter"]
    if prefer_or is False and "openrouter" in chain:
        # demote OR but keep it available
        chain = [p for p in chain if p != "openrouter"] + ["openrouter"]

    if os.environ.get("AMP_FORCE_GOOGLE", "").strip() == "1":
        chain = ["google"] + [p for p in chain if p != "google"]

    errors: List[str] = []
    sys_msg = (system or "").strip()
    if not sys_msg:
        try:
            from pipeline.prompt_engineering import system_for_purpose

            sys_msg = system_for_purpose(purpose, json_mode=json_mode)
        except Exception:
            sys_msg = ""
    # Cultural localization benefits from slightly freer phrasing than rigid MT.
    temp = 0.55 if purpose in ("translate", "localize") else None

    for provider in chain:
        if provider == "google" and not google_allowed_for_purpose(purpose):
            errors.append("google:blocked_non_translate_purpose")
            continue
        if provider != "google" and circuit_is_open(provider):
            errors.append(f"{provider}:circuit_open")
            continue
        if provider == "google" and google_pool_exhausted():
            errors.append("google:circuit_open")
            continue
        keys = provider_keys_for_purpose(purpose=purpose, provider=provider, bundle=work)
        if not keys:
            continue
        try:
            if provider == "groq":
                text = groq_chat(
                    prompt,
                    api_keys=keys,
                    json_mode=json_mode,
                    purpose=purpose,
                    system=sys_msg,
                    temperature=temp,
                )
            elif provider == "cerebras":
                text = cerebras_chat(
                    prompt,
                    api_keys=keys,
                    json_mode=json_mode,
                    system=sys_msg,
                    temperature=temp,
                )
            elif provider == "openrouter":
                text = openrouter_chat(
                    prompt,
                    api_keys=keys,
                    json_mode=json_mode,
                    system=sys_msg,
                    temperature=temp,
                )
            elif provider == "huggingface":
                text = huggingface_chat(
                    prompt,
                    api_keys=keys,
                    json_mode=json_mode,
                    system=sys_msg,
                    temperature=temp,
                )
            elif provider == "freetheai":
                text = freetheai_chat(
                    prompt,
                    api_keys=keys,
                    json_mode=json_mode,
                    system=sys_msg,
                    temperature=temp,
                )
            elif provider == "google":
                text = google_chat(prompt, api_keys=keys, json_mode=json_mode, system=sys_msg)
            else:
                continue
            return {"text": text, "provider": provider}
        except Exception as exc:
            errors.append(f"{provider}:{exc}")
            logger.warning("chat_text provider=%s purpose=%s failed: %s", provider, purpose, str(exc)[:160])
            continue

    raise RuntimeError("chat_text failed: " + " | ".join(errors[:5]))


def extract_json_object(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text
