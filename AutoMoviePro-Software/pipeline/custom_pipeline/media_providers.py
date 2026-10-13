"""Image + video provider fallbacks for custom pipeline.

Image (quality-first to reduce Agnes-vs-still gap):
  1) Google Gemini image  2) Agnes image  3) OpenRouter
  4) HuggingFace          5) Kling        6) Pollinations (seeded Flux)
  7) FreeTheAI            8) Pexels/Pixabay stock

Video:
  1) Agnes (+ optional character-ref image + seed lock in prompt)
  2) Kling … Seedance → AV-matched stock → multi-still Ken Burns
"""

from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from pipeline.custom_pipeline.media_gap import wait_media_gap
from pipeline.custom_pipeline.media_prompts import NEGATIVE_IMAGE, NEGATIVE_VIDEO, fit_prompt_for_provider

logger = logging.getLogger(__name__)


def _env_keys(*prefixes: str, max_n: int = 20) -> List[str]:
    from pipeline.custom_pipeline.session_keys import _collect_numbered, _env_map

    return _collect_numbered(_env_map(), list(prefixes), max_n=max_n)


def _env_val(*names: str, default: str = "") -> str:
    """Read a single config value from merged .env + process env."""
    from pipeline.custom_pipeline.session_keys import _env_map

    env = _env_map()
    for n in names:
        v = (env.get(n) or os.environ.get(n) or "").strip()
        if v:
            return v
    return default


def _ffmpeg() -> str:
    try:
        from pipeline.compose import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def canvas_for_aspect(aspect: str) -> Tuple[int, int]:
    a = (aspect or "9:16").strip()
    if a in ("16:9", "landscape"):
        return 1920, 1080
    return 1080, 1920


# ─── IMAGE PROVIDERS ─────────────────────────────────────────────


def _sanitize_pollinations_prompt(prompt: str, max_chars: int = 1400) -> str:
    """Live-004: huge unicode / em-dash prompts → 500 on image.pollinations.ai."""
    t = (prompt or "").replace("—", "-").replace("–", "-").replace("…", "...")
    t = re.sub(r"[^\x20-\x7E\n]", " ", t)  # ASCII-safe for URL path
    t = re.sub(r"\s+", " ", t).strip()
    return fit_prompt_for_provider(t, max_chars)


def image_pollinations(
    prompt: str, out: Path, *, w: int, h: int, seed: Optional[int] = None
) -> Optional[Path]:
    wait_media_gap(reason="pollinations_image")
    safe_p = (prompt or "").strip()
    if "NO female robot" not in safe_p and "NO human face" not in safe_p:
        safe_p = (
            f"{safe_p}, bright 5600K high-bay illumination, photoreal 8k, "
            f"STRICT: NO human face, NO female face, NO female robot face, NO gynoid, NO doll face, "
            f"NO mannequin face, NO portrait headshot, NO talking head, NO erotic robot, NO breasts, NO watermark, NO logo"
        )
    keys = _env_keys("POLLINATIONS_API_KEY")
    # Shorter ASCII prompt first (stability); detail kept at START via fit_prompt
    variants = [
        _sanitize_pollinations_prompt(safe_p, 1400),
        _sanitize_pollinations_prompt(safe_p, 900),
    ]
    seed_q = f"&seed={int(seed)}" if seed is not None else ""
    free = (os.environ.get("POLLINATIONS_FREE_URL") or "").strip()
    for p in variants:
        if not p:
            continue
        encoded = quote(p)
        # Try without enhance first (enhance often 500), then with enhance
        url_specs = [
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={w}&height={h}&nologo=true&model=flux{seed_q}",
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={w}&height={h}&nologo=true&model=flux&enhance=true{seed_q}",
        ]
        if free:
            url_specs.insert(
                0,
                f"{free.rstrip('/')}/{encoded}?width={w}&height={h}&nologo=true{seed_q}",
            )
        if keys:
            url_specs.append(
                f"https://gen.pollinations.ai/image/{encoded}"
                f"?width={w}&height={h}&model=flux&key={keys[0]}{seed_q}"
            )
        for url in url_specs:
            try:
                with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                    r = client.get(url)
                    if r.status_code in (401, 403):
                        logger.warning("pollinations auth %s — try next URL", r.status_code)
                        continue
                    if r.status_code >= 500:
                        logger.warning("pollinations %s — retry shorter/no-enhance", r.status_code)
                        continue
                    r.raise_for_status()
                    if len(r.content) < 2000:
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(r.content)
                    try:
                        from pipeline.custom_pipeline.multi_still_clip import upscale_still_to_canvas
                        upscale_still_to_canvas(out, out, w=w, h=h)
                    except Exception as _e:
                        pass
                    return out
            except Exception as exc:
                logger.warning("pollinations image: %s", str(exc)[:160])
    return None


def image_google(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
        release_claim,
    )

    # Dedicated IMAGE_GOOGLE keys only — never silently use localize/TTS pool
    try:
        from pipeline.custom_pipeline.session_keys import list_image_google_keys

        keys = list_image_google_keys()
    except Exception:
        keys = _env_keys("IMAGE_GOOGLE_API_KEY", "GOOGLE_IMAGE_API_KEY")
    if not keys:
        try:
            from pipeline.dedicated_api_registry import list_image_google_keys as _img, missing_api_notification

            # Last resort: borrow from idle localize pool with user warning
            keys = _img(allow_borrow=True)
            if not keys:
                note = missing_api_notification("image_google")
                logger.warning("%s", note.get("message_bn") or note.get("message"))
                return None
        except Exception:
            logger.warning(
                "IMAGE_GOOGLE_API_KEY missing — Google image skipped (no general-pool fallback)"
            )
            return None
    if is_circuit_open("google_image"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("google_image", fp):
        return None
    wait_media_gap(reason="google_image")
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        release_claim("google_image", fp, reason="no_sdk")
        return None
    # Live: rotate keys; never circuit on auth/permission alone
    from pipeline.custom_pipeline.quota_rotate import is_key_usable, mark_exhausted

    models = (
        "gemini-2.5-flash-image",
        "gemini-3.1-flash-image-preview",
    )
    last_err = ""
    keys_quota = 0
    keys_auth_dead = 0
    keys_tried = 0
    usable_keys = [k for k in keys[:8] if is_key_usable("google_image", k, for_new_call=True)]
    if not usable_keys:
        # All soft/hard exhausted — try any non-auth-dead once, else skip provider
        usable_keys = list(keys[:8])
    for key in usable_keys:
        keys_tried += 1
        client = genai.Client(api_key=key)
        key_had_quota = False
        key_auth_dead = False
        key_ok = False
        for model in models:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=f"{prompt}\n\nNegative: {NEGATIVE_IMAGE}",
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                for cand in getattr(resp, "candidates", None) or []:
                    for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                        inline = getattr(part, "inline_data", None)
                        if inline is not None and getattr(inline, "data", None):
                            data = inline.data
                            raw = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                            if len(raw) < 2000:
                                continue
                            out.parent.mkdir(parents=True, exist_ok=True)
                            out.write_bytes(raw)
                            release_claim("google_image", fp, reason="ok")
                            logger.info(
                                "Image OK provider=google model=%s …%s → %s (%s bytes)",
                                model,
                                key[-4:],
                                out.name,
                                len(raw),
                            )
                            return out
                # response without image bytes
                last_err = f"{model}:no_inline_image"
            except Exception as exc:
                msg = str(exc)
                last_err = msg
                logger.warning("google image %s …%s: %s", model, key[-4:], msg[:120])
                low = msg.lower()
                if any(
                    x in low
                    for x in (
                        "401",
                        "403",
                        "unauthorized",
                        "permission_denied",
                        "permission denied",
                        "api_key_invalid",
                        "service account is deleted",
                        "denied access",
                        "suspended",
                    )
                ):
                    key_auth_dead = True
                    try:
                        mark_exhausted(
                            "google_image",
                            key,
                            reason=f"auth:{msg[:80]}",
                            hours=24.0,
                        )
                    except Exception:
                        pass
                    break  # next key — do not burn more models on dead key
                from pipeline.custom_pipeline.google_pacing_guard import analyze_quota_error

                qa = analyze_quota_error(msg)
                if qa.is_quota and qa.can_auto_wait:
                    logger.warning(
                        "Google image quota touched (%s, wait %s). Pausing pipeline to let quota refill...",
                        qa.window_type,
                        qa.human_duration,
                    )
                    import time as _time

                    _time.sleep(qa.cooldown_seconds)
                    continue

                if any(x in low for x in ("429", "quota", "resource_exhausted")):
                    key_had_quota = True
                    try:
                        hours = max(1.0, qa.cooldown_seconds / 3600.0)
                        mark_exhausted(
                            "google_image",
                            key,
                            reason=f"quota:{qa.window_type}",
                            hours=hours,
                        )
                    except Exception:
                        pass
                    continue
        if key_auth_dead:
            keys_auth_dead += 1
        elif key_had_quota:
            keys_quota += 1
    # Circuit ONLY when every tried key hit quota (not auth-dead). Auth-dead ≠ burn limit.
    usable = keys_tried - keys_auth_dead
    if usable > 0 and keys_quota >= usable:
        circuit_cooldown = max(120, int(qa.cooldown_seconds)) if "qa" in locals() and qa.cooldown_seconds > 0 else 120
        open_circuit("google_image", circuit_cooldown, reason=f"all_usable_keys_quota:{last_err[:80]}")
    elif keys_tried and keys_auth_dead >= keys_tried:
        logger.warning(
            "All IMAGE_GOOGLE keys auth-dead (401/403) — skip circuit; "
            "add fresh AI Studio keys with image access. last=%s",
            last_err[:100],
        )
    release_claim("google_image", fp, reason="google_image_failed")
    return None


def image_workers_ai(prompt: str, out: Path, *, w: int, h: int, seed: Optional[int] = None) -> Optional[Path]:
    """Cloudflare Workers AI image — Pollinations fallback.

    Supports per-token Account IDs (Account_ID_N paired with WorkersAI_API_KEY_N).
    """
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
        release_claim,
    )

    try:
        from pipeline.dedicated_api_registry import list_workers_ai_credentials, workers_ai_account_id

        creds = list_workers_ai_credentials()
        if not creds:
            # Legacy: keys + single account
            from pipeline.dedicated_api_registry import list_workers_ai_keys

            keys = list_workers_ai_keys()
            acct = workers_ai_account_id()
            creds = [(k, acct) for k in keys if k and acct]
    except Exception:
        keys = _env_keys("WorkersAI_API_KEY", "WORKERS_AI_API_KEY", "CLOUDFLARE_API_TOKEN")
        account_id = (
            (os.environ.get("WorkersAI_ACCOUNT_ID") or "")
            or (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "")
            or (os.environ.get("Account_ID_1") or "")
        ).strip()
        creds = [(k, account_id) for k in keys if k and account_id]

    if not creds:
        logger.warning(
            "WorkersAI credentials incomplete — need WorkersAI_API_KEY_N + Account_ID_N "
            "(or WorkersAI_ACCOUNT_ID)"
        )
        return None
    if is_circuit_open("workers_ai") or is_circuit_open("workers_ai_image"):
        return None

    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("workers_ai_image", fp):
        return None
    wait_media_gap(reason="workers_ai_image")

    model = (
        os.environ.get("WorkersAI_IMAGE_MODEL")
        or os.environ.get("CLOUDFLARE_IMAGE_MODEL")
        or "@cf/black-forest-labs/flux-1-schnell"
    ).strip()
    # Keep prompt modest for Flux schnell
    short = (prompt or "").strip()
    if "NO female robot" not in short and "NO human face" not in short:
        short = (
            f"{short}. Bright commercial high-bay illumination, clean balanced 5600K daylight, razor-sharp 8k textures. "
            f"STRICT NEGATIVE: NO human face, NO female face, NO female robot face, NO gynoid, NO doll face, "
            f"NO mannequin face, NO robot face close-up, NO portrait headshot, NO talking head, NO erotic robot, NO breasts, NO dark underexposed shadows"
        )
    if len(short) > 1800:
        short = short[:1800]
    # Prefer prompt-only first (Flux schema); optional num_steps as second try
    lean = {"prompt": short}
    payloads = [lean]
    try:
        steps = int(os.environ.get("WorkersAI_FLUX_STEPS") or "0")
        if 1 <= steps <= 8:
            payloads.append({"prompt": short, "num_steps": steps})
    except ValueError:
        pass

    last_err = ""
    for key, account_id in creds[:6]:
        if not account_id:
            continue
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        for payload in payloads:
            try:
                r = httpx.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=90.0,
                )
                if r.status_code in (401, 403):
                    last_err = f"auth_{r.status_code}:{r.text[:80]}"
                    logger.warning(
                        "workers_ai auth %s acct=…%s key=…%s",
                        r.status_code,
                        account_id[-4:],
                        key[-4:],
                    )
                    break  # next credential
                if r.status_code == 429:
                    last_err = "429"
                    logger.warning("workers_ai 429 acct=…%s — try next", account_id[-4:])
                    break
                if r.status_code >= 400:
                    err_txt = r.text[:200]
                    last_err = f"{r.status_code}:{err_txt}"
                    # Schema reject → try simpler payload
                    if "not allowed" in err_txt.lower() or "bad input" in err_txt.lower():
                        logger.warning("workers_ai schema reject — retry lean payload")
                        continue
                    logger.warning("workers_ai %s", last_err)
                    break
                ctype = (r.headers.get("content-type") or "").lower()
                raw: bytes
                if "image" in ctype or r.content[:8] == b"\x89PNG\r\n\x1a\n" or r.content[:2] == b"\xff\xd8":
                    raw = r.content
                else:
                    try:
                        data = r.json()
                    except Exception:
                        last_err = "bad_json"
                        continue
                    result = data.get("result") if isinstance(data, dict) else None
                    b64 = None
                    if isinstance(result, str):
                        b64 = result
                    elif isinstance(result, dict):
                        b64 = result.get("image") or result.get("b64_json")
                        if isinstance(b64, list) and b64:
                            b64 = b64[0]
                    if not b64 and isinstance(data, dict):
                        b64 = data.get("image")
                    if not b64:
                        last_err = f"no_image_field:{str(data)[:120]}"
                        continue
                    if isinstance(b64, str) and b64.startswith("data:"):
                        b64 = b64.split(",", 1)[-1]
                    raw = base64.b64decode(b64)
                if len(raw) < 2000:
                    last_err = "tiny"
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(raw)
                try:
                    from pipeline.custom_pipeline.multi_still_clip import upscale_still_to_canvas
                    upscale_still_to_canvas(out, out, w=w, h=h)
                except Exception as _e:
                    logger.warning("workers_ai upscale: %s", _e)
                release_claim("workers_ai_image", fp, reason="ok")
                logger.info(
                    "Image OK provider=workers_ai acct=…%s → %s (%s bytes, canvas %sx%s)",
                    account_id[-4:],
                    out.name,
                    out.stat().st_size,
                    w,
                    h,
                )
                return out
            except Exception as exc:
                last_err = str(exc)[:120]
                logger.warning("workers_ai image: %s", last_err)
    open_circuit("workers_ai_image", 120, reason=last_err[:80] or "failed")
    release_claim("workers_ai_image", fp, reason="workers_ai_failed")
    return None


def image_agnes(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
        release_claim,
    )

    keys = _env_keys("AGNES_API_KEY", "AGNES_API")
    try:
        from pipeline.api_keys import load_api_bundle
        bundle_agnes = load_api_bundle().get("agnes_keys") or []
        for bk in bundle_agnes:
            if bk and str(bk).strip() and str(bk).strip() not in keys:
                keys.append(str(bk).strip())
    except Exception:
        pass

    if not keys or is_circuit_open("agnes_image"):
        return None

    from pipeline.custom_pipeline.quota_rotate import is_key_usable, mark_exhausted
    usable_keys = [k for k in keys if is_key_usable("agnes_image", k, for_new_call=True)]
    if not usable_keys:
        usable_keys = list(keys)

    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("agnes_image", fp):
        return None
    wait_media_gap(reason="agnes_image")
    free_url = (os.environ.get("AGNES_FREE_IMAGE_URL") or "").strip()
    base = (os.environ.get("AGNES_API_BASE_URL") or "https://apihub.agnes-ai.com").rstrip("/")
    endpoints = []
    if free_url:
        endpoints.append(free_url)
    # Prefer paid/v1 before legacy free path that 403'd in live-004
    endpoints.extend(
        [
            f"{base}/v1/images",
            f"{base}/v1/images/generations",
            f"{base}/free/image",
        ]
    )
    # de-dupe
    seen = set()
    uniq = []
    for u in endpoints:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)

    keys_tried = 0
    keys_auth_or_quota = 0
    last_err = ""

    for key in usable_keys:
        keys_tried += 1
        key_ok = False
        for url in uniq:
            is_free = "free" in url.lower() or "pollinations" in url.lower()
            try:
                with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                    r = client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "prompt": prompt,
                            "width": w,
                            "height": h,
                            "negative_prompt": NEGATIVE_IMAGE,
                        },
                    )
                    if r.status_code >= 400:
                        if is_free:
                            r = client.get(
                                url,
                                params={
                                    "prompt": fit_prompt_for_provider(prompt, 800),
                                    "width": w,
                                    "height": h,
                                },
                            )
                        if r.status_code >= 400:
                            if r.status_code in (401, 403) and is_free:
                                continue
                            if r.status_code in (401, 403) and not is_free:
                                keys_auth_or_quota += 1
                                try:
                                    mark_exhausted("agnes_image", key, reason=f"auth:{r.text[:60]}", hours=24.0)
                                except Exception:
                                    pass
                                break
                            if r.status_code == 429:
                                keys_auth_or_quota += 1
                                try:
                                    mark_exhausted("agnes_image", key, reason="quota:429", hours=1.0)
                                except Exception:
                                    pass
                                break
                            continue
                    ctype = r.headers.get("content-type", "")
                    if "image" in ctype or len(r.content) > 5000:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(r.content)
                        if out.stat().st_size > 2000:
                            release_claim("agnes_image", fp, reason="ok")
                            return out
                    data = {}
                    try:
                        data = r.json()
                    except Exception:
                        continue
                    img_url = (
                        data.get("url")
                        or data.get("image_url")
                        or (data.get("data") or [{}])[0].get("url")
                        if isinstance(data.get("data"), list)
                        else (data.get("data") or {}).get("url")
                    )
                    if img_url:
                        media = client.get(str(img_url))
                        media.raise_for_status()
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(media.content)
                        if out.stat().st_size > 2000:
                            release_claim("agnes_image", fp, reason="ok")
                            return out
            except Exception as exc:
                logger.warning("agnes image %s: %s", url[:60], str(exc)[:120])
                continue
    open_circuit("agnes_image", 1800, reason="all_endpoints_failed")
    release_claim("agnes_image", fp, reason="agnes_image_failed")
    return None


def image_openrouter(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("OPENROUTER_API_KEY")
    if not keys or is_circuit_open("openrouter_image"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("openrouter_image", fp):
        return None
    wait_media_gap(reason="openrouter_image")
    # One key, one model — no key×model fan-out
    model = (
        os.environ.get("AMP_OPENROUTER_IMAGE_MODEL")
        or "google/gemini-2.5-flash-image-preview:free"
    ).strip()
    key = keys[0]
    try:
        with httpx.Client(timeout=180.0) as client:
            r = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Generate an image.\n{prompt}\nNegative: {NEGATIVE_IMAGE}",
                        }
                    ],
                    "modalities": ["image", "text"],
                },
            )
            if r.status_code >= 400:
                logger.warning("openrouter image %s: %s", model, r.text[:120])
                if r.status_code in (401, 403):
                    open_circuit("openrouter_image", 1800, reason=r.text[:120])
                return None
            data = r.json()
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            images = msg.get("images") or []
            for im in images:
                url = (im.get("image_url") or {}).get("url") or im.get("url") or ""
                if url.startswith("data:image") and "," in url:
                    raw = base64.b64decode(url.split(",", 1)[1])
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(raw)
                    if out.stat().st_size > 2000:
                        return out
                elif url.startswith("http"):
                    media = client.get(url)
                    media.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(media.content)
                    if out.stat().st_size > 2000:
                        return out
    except Exception as exc:
        logger.warning("openrouter image: %s", str(exc)[:140])
    return None


def image_huggingface(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        prompt_fingerprint,
    )

    keys = _env_keys("HUGGINGFACE_API_KEY", "HF_TOKEN", "HF_API_KEY")
    if not keys or is_circuit_open("huggingface_image"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("huggingface_image", fp):
        return None
    wait_media_gap(reason="huggingface_image")
    model = (
        os.environ.get("AMP_HF_IMAGE_MODEL") or "black-forest-labs/FLUX.1-schnell"
    ).strip()
    key = keys[0]
    url = f"https://api-inference.huggingface.co/models/{model}"
    try:
        with httpx.Client(timeout=180.0) as client:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "inputs": fit_prompt_for_provider(prompt, 1500),
                    "parameters": {"width": min(w, 1024), "height": min(h, 1024)},
                },
            )
            if r.status_code >= 400 or len(r.content) < 2000:
                return None
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)
            return out
    except Exception as exc:
        logger.warning("hf image %s: %s", model, str(exc)[:120])
    return None


def image_kling(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("KLING_API_KEY")
    if not keys or is_circuit_open("kling_image"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}")
    if not claim_create("kling_image", fp):
        return None
    wait_media_gap(reason="kling_image")
    base = (os.environ.get("KLING_API_BASE_URL") or "https://api.klingai.com").rstrip("/")
    key = keys[0]
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{base}/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"prompt": prompt, "aspect_ratio": f"{w}:{h}"},
            )
            if r.status_code >= 400:
                if r.status_code in (401, 403):
                    open_circuit("kling_image", 1800, reason=r.text[:120])
                return None
            data = r.json()
            url = (
                data.get("data", {}).get("url")
                if isinstance(data.get("data"), dict)
                else None
            ) or data.get("url")
            if not url and isinstance(data.get("data"), list) and data["data"]:
                url = data["data"][0].get("url")
            if not url:
                return None
            media = client.get(str(url))
            media.raise_for_status()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(media.content)
            if out.stat().st_size > 2000:
                return out
    except Exception as exc:
        logger.warning("kling image: %s", str(exc)[:120])
    return None


def image_pexels_stock(query: str, out: Path, *, portrait: bool = True) -> Optional[Path]:
    keys = _env_keys("PEXELS_API_KEY")
    if not keys:
        return None
    wait_media_gap(reason="pexels_photo")
    q = (query or "cinematic tech studio").strip()
    variants = [q[:80]]
    # Multi-try: shorten query if first pass empty
    words = q.split()
    if len(words) > 4:
        variants.append(" ".join(words[:4]))
    variants.append("cinematic technology smartphone")
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            for key in keys[:2]:
                for vq in variants:
                    r = client.get(
                        "https://api.pexels.com/v1/search",
                        params={
                            "query": vq,
                            "per_page": 8,
                            "orientation": "portrait" if portrait else "landscape",
                        },
                        headers={"Authorization": key},
                    )
                    if r.status_code >= 400:
                        continue
                    photos = r.json().get("photos") or []
                    for photo in photos:
                        src = (photo.get("src") or {}).get("large2x") or (
                            photo.get("src") or {}
                        ).get("large")
                        if not src:
                            continue
                        media = client.get(src)
                        media.raise_for_status()
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(media.content)
                        if out.stat().st_size > 2000:
                            return out
    except Exception as exc:
        logger.warning("pexels photo: %s", exc)
        return None
    return None


def image_pixabay_stock(query: str, out: Path, *, portrait: bool = True) -> Optional[Path]:
    keys = _env_keys("PIXABAY_API_KEY")
    if not keys:
        return None
    wait_media_gap(reason="pixabay_photo")
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            r = client.get(
                "https://pixabay.com/api/",
                params={
                    "key": keys[0],
                    "q": (query or "cinematic tech")[:100],
                    "image_type": "photo",
                    "orientation": "vertical" if portrait else "horizontal",
                    "per_page": 8,
                    "safesearch": "true",
                },
            )
            if r.status_code >= 400:
                return None
            hits = r.json().get("hits") or []
            for hit in hits:
                src = hit.get("largeImageURL") or hit.get("webformatURL")
                if not src:
                    continue
                media = client.get(src)
                media.raise_for_status()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(media.content)
                if out.stat().st_size > 2000:
                    return out
    except Exception as exc:
        logger.warning("pixabay photo: %s", exc)
    return None


def image_freetheai(prompt: str, out: Path, *, w: int, h: int) -> Optional[Path]:
    keys = _env_keys("FREETHEAI_API_KEY")
    if not keys:
        return None
    wait_media_gap(reason="freetheai_image")
    base = (os.environ.get("FREETHEAI_API_BASE_URL") or "https://api.freetheai.xyz/v1").rstrip(
        "/"
    )
    url = f"{base}/images/generations"
    for key in keys[:2]:
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={"prompt": fit_prompt_for_provider(prompt, 2000), "size": f"{min(w,1024)}x{min(h,1024)}", "n": 1},
                )
                if r.status_code >= 400:
                    logger.warning("freetheai image http=%s", r.status_code)
                    continue
                data = r.json()
                item = (data.get("data") or [{}])[0] if isinstance(data.get("data"), list) else {}
                b64 = item.get("b64_json")
                img_url = item.get("url") or data.get("url")
                if b64:
                    raw = base64.b64decode(b64)
                    if len(raw) > 2000:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(raw)
                        return out
                if img_url:
                    media = client.get(str(img_url))
                    media.raise_for_status()
                    if len(media.content) > 2000:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(media.content)
                        return out
        except Exception as exc:
            logger.warning("freetheai image: %s", str(exc)[:120])
    return None


IMAGE_CHAIN = (
    # Cloudflare Workers AI FLUX: fast, photoreal, 100% watermark-free
    ("workers_ai", image_workers_ai),
    ("google", image_google),
    ("agnes", image_agnes),
    # Pollinations: fallback when keys unavailable
    ("pollinations", image_pollinations),
    ("openrouter", image_openrouter),
    ("huggingface", image_huggingface),
    ("kling", image_kling),
    ("freetheai", image_freetheai),
)


def generate_image_with_fallback(
    prompt: str,
    out_path: Path,
    *,
    aspect: str = "9:16",
    stock_query: str = "",
    seed: Optional[int] = None,
    allow_stock: bool = True,
) -> Dict[str, Any]:
    from pipeline.custom_pipeline.media_call_guard import is_circuit_open

    words = (prompt or "").split()
    if len(words) < 45:
        logger.info(
            "image prompt short (%s words) — enhancing with micro-detail", len(words)
        )
    w, h = canvas_for_aspect(aspect)
    out_path = Path(out_path)
    errors: List[str] = []
    use_prompt = (prompt or "").strip()
    if len(words) < 45:
        use_prompt = (
            f"{use_prompt}. Hyper-detailed cinematic composition, rich photoreal surface textures, "
            f"controlled documentary lighting, shallow depth of field, 8k resolution visual, "
            f"authentic scene props and setting."
        )
    if seed is not None:
        use_prompt = f"{use_prompt}. SEED LOCK {int(seed)}: identical identity/wardrobe/set."
    for name, fn in IMAGE_CHAIN:
        circuit = f"{name}_image" if name not in ("pollinations", "freetheai") else name
        if is_circuit_open(name) or is_circuit_open(circuit):
            logger.info("Skip image provider %s (circuit open)", name)
            continue
        try:
            if name == "pollinations":
                got = fn(use_prompt, out_path, w=w, h=h, seed=seed)
            elif name == "workers_ai":
                got = fn(use_prompt, out_path, w=w, h=h, seed=seed)
            else:
                got = fn(use_prompt, out_path, w=w, h=h)
            if got and got.exists() and got.stat().st_size > 2000:
                # Soft quality gate: only reject tiny icons. 576–720 stills
                # are accepted and upscaled to canvas (Pollinations free caps).
                try:
                    from pipeline.custom_pipeline.multi_still_clip import probe_image_min_edge

                    edge = probe_image_min_edge(got)
                    if edge and edge < 480 and max(w, h) >= 1080:
                        logger.warning(
                            "Image %s too small (min_edge=%s) — try next provider",
                            name,
                            edge,
                        )
                        errors.append(f"{name}:low_res_{edge}")
                        continue
                    if edge and edge < min(w, h):
                        logger.info(
                            "Image %s min_edge=%s (<canvas) — will upscale later",
                            name,
                            edge,
                        )
                except Exception:
                    pass
                logger.info(
                    "Image OK provider=%s seed=%s → %s",
                    name,
                    seed,
                    out_path.name,
                )
                return {
                    "ok": True,
                    "path": str(got),
                    "provider": name,
                    "seed": seed,
                }
        except Exception as exc:
            errors.append(f"{name}:{exc}")
            logger.warning("image provider %s failed: %s", name, exc)
    if not allow_stock:
        return {
            "ok": False,
            "path": None,
            "errors": errors + ["stock_forbidden_for_brand_ui"],
            "provider": None,
            "seed": seed,
        }
    q = stock_query or prompt[:60]
    portrait = "9:16" in aspect
    for stock_name, stock_fn in (
        ("pexels_stock", image_pexels_stock),
        ("pixabay_stock", image_pixabay_stock),
    ):
        try:
            stock = stock_fn(q, out_path, portrait=portrait)
            if stock:
                return {
                    "ok": True,
                    "path": str(stock),
                    "provider": stock_name,
                    "fallback": True,
                    "quality": "degraded",
                    "seed": seed,
                }
        except Exception as exc:
            errors.append(f"{stock_name}:{exc}")
    return {"ok": False, "path": None, "errors": errors, "provider": None, "seed": seed}


# ─── VIDEO PROVIDERS ─────────────────────────────────────────────


def video_google_veo(
    prompt: str,
    out: Path,
    *,
    w: int,
    h: int,
    duration: float,
    seed: Optional[int] = None,
    image_url: str = "",
) -> Optional[Path]:
    """Google Pro Veo video generation — Tier 1: Paid Google Master keys, Tier 2: Free Google keys -> Agnes fallback."""
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
        release_claim,
    )
    from pipeline.custom_pipeline.quota_rotate import is_key_usable, mark_exhausted

    paid_keys: List[str] = []
    try:
        from pipeline.custom_pipeline.session_keys import list_paid_google_keys

        paid_keys = [k for k in list_paid_google_keys() if k]
    except Exception:
        pass
    free_keys = _env_keys("GEMINI_API_KEY", "GOOGLE_API_KEY")
    keys: List[str] = list(paid_keys)
    for k in free_keys:
        if k and k not in keys:
            keys.append(k)

    if not keys or is_circuit_open("google_veo"):
        return None

    usable_keys = [k for k in keys if is_key_usable("google_veo", k, for_new_call=True)]
    if not usable_keys:
        usable_keys = list(keys)

    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("google_veo", fp):
        return None

    ar = "9:16" if h > w else "16:9"
    dur_sec = int(max(4, min(8, duration or 5)))
    keys_tried = 0
    keys_quota = 0
    last_err = ""

    for k in usable_keys:
        keys_tried += 1
        is_paid = k in paid_keys
        tier_label = "Paid Master" if is_paid else "Free Pool"
        wait_media_gap(reason="google_veo_video")
        try:
            from pipeline.google_media import generate_veo_video

            logger.info("Attempting Google Veo video (%s key …%s dur=%ds ar=%s)", tier_label, k[-4:], dur_sec, ar)
            path = generate_veo_video(
                prompt=prompt,
                out_path=out,
                api_key=k,
                aspect_ratio=ar,
                duration_seconds=dur_sec,
            )
            if path and path.exists() and path.stat().st_size > 5000:
                release_claim("google_veo", fp, reason="ok")
                logger.info(
                    "Google Veo video generated successfully (%s key …%s): %s (%d bytes)",
                    tier_label,
                    k[-4:],
                    path.name,
                    path.stat().st_size,
                )
                return path
            else:
                last_err = "no_video_returned"
        except Exception as exc:
            msg = str(exc)
            last_err = msg
            logger.warning("Google Veo (%s …%s) error: %s", tier_label, k[-4:], msg[:160])
            low = msg.lower()

            from pipeline.custom_pipeline.google_pacing_guard import analyze_quota_error

            qa = analyze_quota_error(msg)
            if qa.is_quota and qa.can_auto_wait:
                logger.warning(
                    "Google Veo quota touched (%s, wait %s). Pausing pipeline to let quota refill...",
                    qa.window_type,
                    qa.human_duration,
                )
                import time as _time

                _time.sleep(qa.cooldown_seconds)
                continue

            if any(x in low for x in ("429", "quota", "resource_exhausted")):
                keys_quota += 1
                try:
                    hours = max(2.0, qa.cooldown_seconds / 3600.0)
                    mark_exhausted("google_veo", k, reason=f"quota:{qa.window_type}", hours=hours)
                except Exception:
                    pass
                logger.info("Google Veo %s key …%s hit quota -> rotating to next key", tier_label, k[-4:])
                continue
            elif any(x in low for x in ("401", "403", "unauthorized", "api_key_invalid")):
                try:
                    mark_exhausted("google_veo", k, reason=f"auth:{msg[:80]}", hours=24.0)
                except Exception:
                    pass
                continue

    if keys_tried > 0 and keys_quota >= keys_tried:
        circuit_cooldown = max(120, int(qa.cooldown_seconds)) if "qa" in locals() and qa.cooldown_seconds > 0 else 120
        open_circuit("google_veo", circuit_cooldown, reason=f"all_keys_quota:{last_err[:80]}")

    logger.info("Google Veo not fulfilled across %d keys -> falling back to next video provider (Agnes)", keys_tried)
    release_claim("google_veo", fp, reason="google_veo_failed")
    return None


def video_agnes(
    prompt: str,
    out: Path,
    *,
    w: int,
    h: int,
    duration: float,
    seed: Optional[int] = None,
    image_url: str = "",
) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
        release_claim,
    )
    from pipeline.custom_pipeline.quota_rotate import is_key_usable, mark_exhausted

    keys = _env_keys("AGNES_API_KEY", "AGNES_API")
    try:
        from pipeline.api_keys import load_api_bundle
        bundle_agnes = load_api_bundle().get("agnes_keys") or []
        for bk in bundle_agnes:
            if bk and str(bk).strip() and str(bk).strip() not in keys:
                keys.append(str(bk).strip())
    except Exception:
        pass

    if not keys or is_circuit_open("agnes"):
        return None

    usable_keys = [k for k in keys if is_key_usable("agnes", k, for_new_call=True)]
    if not usable_keys:
        usable_keys = list(keys)

    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("agnes", fp):
        return None
    wait_media_gap(reason="agnes_video")

    fps = 24
    frames = int(max(49, min(121, round(float(duration or 5) * fps) + 1)))
    locked = (prompt or "").strip()
    if seed is not None:
        locked = f"{locked}\nSEED LOCK {int(seed)}: same character identity, wardrobe, set continuity."

    from pipeline.media_assets import _agnes_video, reset_agnes_scene_budget

    reset_agnes_scene_budget(max_creates=len(usable_keys))
    keys_tried = 0
    keys_auth_or_quota = 0
    last_err = ""

    for k in usable_keys:
        keys_tried += 1
        logger.info("Attempting Agnes Video key …%s (key %d/%d dur=%.1fs)", k[-4:], keys_tried, len(usable_keys), duration)
        try:
            path = _agnes_video(
                k,
                f"{locked}\nNegative: {NEGATIVE_VIDEO}",
                out,
                max_poll=40,
                width=w if w >= h else 768,
                height=h if h >= w else 1152,
                num_frames=frames,
                frame_rate=fps,
                image_url=(image_url or "").strip(),
            )
            if path and path.exists() and path.stat().st_size > 5000:
                release_claim("agnes", fp, reason="ok")
                logger.info(
                    "Agnes video generated successfully with key …%s: %s (%d bytes)",
                    k[-4:],
                    path.name,
                    path.stat().st_size,
                )
                return path
        except Exception as exc:
            msg = str(exc)
            last_err = msg
            logger.warning("Agnes video key …%s error: %s", k[-4:], msg[:140])
            low = msg.lower()
            if any(x in low for x in ("429", "quota", "rate limit")):
                keys_auth_or_quota += 1
                try:
                    mark_exhausted("agnes", k, reason=f"quota:{msg[:60]}", hours=1.0)
                except Exception:
                    pass
            elif any(x in low for x in ("401", "403", "unauthorized", "forbidden")):
                keys_auth_or_quota += 1
                try:
                    mark_exhausted("agnes", k, reason=f"auth:{msg[:60]}", hours=24.0)
                except Exception:
                    pass

    if keys_tried > 0 and keys_auth_or_quota >= keys_tried:
        open_circuit("agnes", 600, reason=f"all_agnes_keys_failed:{last_err[:80]}")

    release_claim("agnes", fp, reason="agnes_video_failed")
    return None


def video_openrouter(prompt: str, out: Path, *, w: int, h: int, duration: float) -> Optional[Path]:
    """OpenRouter async video — ONE model, ONE key (paid). Opt-in via AMP_OPENROUTER_VIDEO=1."""
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    if (_env_val("AMP_OPENROUTER_VIDEO", default="0") or "0").strip() not in ("1", "true", "yes"):
        logger.info("openrouter video skipped (set AMP_OPENROUTER_VIDEO=1 to enable paid creates)")
        return None
    keys = _env_keys("OPENROUTER_API_KEY")
    if not keys or is_circuit_open("openrouter_video"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("openrouter_video", fp):
        return None
    wait_media_gap(reason="openrouter_video")
    import time as _t

    model = _env_val("AMP_OPENROUTER_VIDEO_MODEL", default="bytedance/seedance-2.0-fast")
    aspect = "9:16" if h > w else "16:9"
    dur = int(max(4, min(8, duration or 5)))
    key = keys[0]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://automovie.pro",
        "X-Title": "AutoMovie Pro",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.post(
                "https://openrouter.ai/api/v1/videos",
                headers=headers,
                json={
                    "model": model,
                    "prompt": fit_prompt_for_provider(prompt, 1800),
                    "duration": dur,
                    "aspect_ratio": aspect,
                    "resolution": "720p",
                },
            )
            if r.status_code in (401, 402, 403):
                open_circuit("openrouter_video", 3600, reason=r.text[:160])
                return None
            if r.status_code >= 400:
                logger.warning("openrouter video %s: %s", model, r.text[:160])
                return None
            data = r.json()
            job_id = data.get("id") or (data.get("data") or {}).get("id")
            if not job_id:
                return None
            for _ in range(48):
                _t.sleep(5)
                pr = client.get(
                    f"https://openrouter.ai/api/v1/videos/{job_id}",
                    headers=headers,
                )
                if pr.status_code >= 400:
                    continue
                pdata = pr.json()
                status = str(pdata.get("status") or "").lower()
                url = (
                    pdata.get("url")
                    or pdata.get("video_url")
                    or (
                        (pdata.get("output") or {}).get("url")
                        if isinstance(pdata.get("output"), dict)
                        else None
                    )
                )
                if status in ("completed", "succeeded", "success") and url:
                    media = client.get(str(url))
                    media.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(media.content)
                    if out.stat().st_size > 5000:
                        return out
                if status in ("failed", "error", "cancelled"):
                    break
    except Exception as exc:
        logger.warning("openrouter video: %s", str(exc)[:140])
    return None


def video_huggingface(prompt: str, out: Path, *, w: int, h: int, duration: float) -> Optional[Path]:
    """HuggingFace T2V — ONE model, ONE key, ONE base (no combinatorial fan-out)."""
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("HUGGINGFACE_API_KEY", "HF_TOKEN", "HF_API_KEY")
    if not keys or is_circuit_open("huggingface_video"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("huggingface_video", fp):
        return None
    wait_media_gap(reason="huggingface_video")
    model = _env_val(
        "AMP_HF_VIDEO_MODEL",
        default="ali-vilab/text-to-video-ms-1.7b",
    )
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    try:
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {keys[0]}"},
                json={
                    "inputs": fit_prompt_for_provider(prompt, 1200),
                    "parameters": {
                        "num_frames": int(max(16, min(48, (duration or 5) * 8))),
                    },
                },
            )
            if r.status_code in (401, 403):
                open_circuit("huggingface_video", 1800, reason=r.text[:120])
                return None
            if r.status_code >= 400:
                logger.warning("hf video %s: %s", model, r.text[:120])
                return None
            ctype = r.headers.get("content-type", "")
            if "video" in ctype or "octet" in ctype or len(r.content) > 10000:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(r.content)
                if out.stat().st_size > 5000:
                    return out
    except Exception as exc:
        logger.warning("hf video: %s", str(exc)[:120])
        if "getaddrinfo" in str(exc).lower():
            open_circuit("huggingface_video", 600, reason=str(exc))
    return None


def video_kling(prompt: str, out: Path, *, w: int, h: int, duration: float) -> Optional[Path]:
    """Kling text2video — ONE model, ONE key. No model×key matrix."""
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("KLING_API_KEY")
    if not keys:
        logger.warning("Kling failed: no keys found")
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("kling", fp):
        logger.warning("Kling failed: claim_create rejected")
        return None
    wait_media_gap(reason="kling_video")
    raw_base = _env_val("KLING_API_BASE_URL", default="https://api.klingai.com")
    if raw_base.endswith("/v1"):
        raw_base = raw_base[:-3]
    base = raw_base.rstrip("/")
    key = keys[0]
    model_name = "kling-v1"
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{base}/v1/videos/text2video",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model_name": model_name,
                    "prompt": fit_prompt_for_provider(prompt, 1500),
                    "negative_prompt": NEGATIVE_VIDEO[:500],
                    "duration": str(int(max(5, min(10, duration or 5)))),
                    "aspect_ratio": "9:16" if h > w else "16:9",
                },
            )
            if r.status_code in (401, 403):
                open_circuit("kling", 3600, reason=r.text[:160])
                return None
            if r.status_code >= 400:
                logger.warning("kling create %s: %s", model_name, r.text[:160])
                # Auth-looking errors from invalid key format → circuit
                if "unauthorized" in r.text.lower() or r.status_code == 401:
                    open_circuit("kling", 3600, reason=r.text[:120])
                return None
            data = r.json()
            task_id = (
                (data.get("data") or {}).get("task_id")
                if isinstance(data.get("data"), dict)
                else data.get("task_id")
            )
            if not task_id:
                return None
            import time as _t

            for _ in range(40):
                _t.sleep(6)
                pr = client.get(
                    f"{base}/v1/videos/text2video/{task_id}",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if pr.status_code >= 400:
                    # fallback classic poll path
                    pr = client.get(
                        f"{base}/v1/videos/{task_id}",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    if pr.status_code >= 400:
                        continue
                pdata = pr.json()
                d = pdata.get("data") if isinstance(pdata.get("data"), dict) else pdata
                status = str(
                    (d or {}).get("task_status") or (d or {}).get("status") or ""
                ).lower()
                url = None
                if isinstance(d, dict):
                    videos = ((d.get("task_result") or {}).get("videos") or [])
                    if isinstance(videos, list) and videos:
                        url = videos[0].get("url")
                    url = url or d.get("url")
                if status in ("succeed", "success", "completed") and url:
                    media = client.get(str(url))
                    media.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(media.content)
                    if out.stat().st_size > 5000:
                        return out
                if status in ("failed", "error"):
                    break
    except Exception as exc:
        logger.warning("kling video: %s", str(exc)[:140])
    return None


def video_luma(prompt: str, out: Path, *, w: int, h: int, duration: float) -> Optional[Path]:
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("LUMA_API_KEY")
    if not keys:
        logger.warning("Luma failed: no keys found")
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("luma", fp):
        logger.warning("Luma failed: claim_create rejected")
        return None
    wait_media_gap(reason="luma_video")
    # .env may wrongly set .../v1 — Dream Machine path is /dream-machine/v1/...
    raw = _env_val("LUMA_API_BASE_URL", default="https://api.lumalabs.ai")
    raw = raw.rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    base = raw.rstrip("/") or "https://api.lumalabs.ai"
    key = keys[0]
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{base}/dream-machine/v1/generations",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": fit_prompt_for_provider(prompt, 1500),
                    "aspect_ratio": "9:16" if h > w else "16:9",
                },
            )
            if r.status_code in (401, 403):
                open_circuit("luma", 3600, reason=r.text[:160])
                logger.warning("luma auth fail: %s", r.text[:120])
                return None
            if r.status_code >= 400:
                logger.warning("luma create: %s", r.text[:140])
                return None
            data = r.json()
            gen_id = data.get("id")
            if not gen_id:
                return None
            import time as _t

            for _ in range(40):
                _t.sleep(6)
                pr = client.get(
                    f"{base}/dream-machine/v1/generations/{gen_id}",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if pr.status_code >= 400:
                    continue
                pdata = pr.json()
                state = str(pdata.get("state") or "").lower()
                url = (pdata.get("assets") or {}).get("video")
                if state == "completed" and url:
                    media = client.get(str(url))
                    media.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(media.content)
                    if out.stat().st_size > 5000:
                        return out
                if state in ("failed",):
                    break
    except Exception as exc:
        logger.warning("luma video: %s", str(exc)[:140])
    return None


def video_seedance(prompt: str, out: Path, *, w: int, h: int, duration: float) -> Optional[Path]:
    """Seedance via Replicate when keys look like r8_… tokens (env SEEDANCE_API_KEY_*)."""
    from pipeline.custom_pipeline.media_call_guard import (
        claim_create,
        is_circuit_open,
        open_circuit,
        prompt_fingerprint,
    )

    keys = _env_keys("SEEDANCE_API_KEY", "REPLICATE_API_TOKEN", "REPLICATE_API_KEY")
    keys = [k for k in keys if k]
    if not keys or is_circuit_open("seedance"):
        return None
    fp = prompt_fingerprint(prompt, aspect=f"{w}x{h}", duration=duration)
    if not claim_create("seedance", fp):
        return None
    wait_media_gap(reason="seedance_video")
    key = keys[0]
    # Replicate path for r8_ tokens
    if key.startswith("r8_"):
        model = _env_val(
            "AMP_SEEDANCE_REPLICATE_MODEL",
            default="bytedance/seedance-1-pro",
        )
        aspect = "9:16" if h > w else "16:9"
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.post(
                    "https://api.replicate.com/v1/predictions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Prefer": "wait",
                    },
                    json={
                        "version": model if ":" in model else None,
                        "input": {
                            "prompt": fit_prompt_for_provider(prompt, 1500),
                            "duration": int(max(5, min(10, duration or 5))),
                            "aspect_ratio": aspect,
                        },
                    }
                    if ":" in model
                    else {
                        "model": model,
                        "input": {
                            "prompt": fit_prompt_for_provider(prompt, 1500),
                            "duration": int(max(5, min(10, duration or 5))),
                            "aspect_ratio": aspect,
                        },
                    },
                )
                # Prefer models API create
                if r.status_code >= 400:
                    r = client.post(
                        f"https://api.replicate.com/v1/models/{model}/predictions",
                        headers={
                            "Authorization": f"Token {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "input": {
                                "prompt": fit_prompt_for_provider(prompt, 1500),
                                "duration": int(max(5, min(10, duration or 5))),
                                "aspect_ratio": aspect,
                            }
                        },
                    )
                if r.status_code in (401, 403):
                    open_circuit("seedance", 3600, reason=r.text[:160])
                    return None
                if r.status_code >= 400:
                    logger.warning("seedance/replicate: %s", r.text[:160])
                    return None
                data = r.json()
                # Prefer: wait response may already be succeeded
                import time as _t

                for _ in range(60):
                    status = str(data.get("status") or "").lower()
                    out_urls = data.get("output")
                    url = None
                    if isinstance(out_urls, str):
                        url = out_urls
                    elif isinstance(out_urls, list) and out_urls:
                        url = out_urls[0]
                    if status in ("succeeded", "success") and url:
                        media = client.get(str(url))
                        media.raise_for_status()
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(media.content)
                        if out.stat().st_size > 5000:
                            return out
                    if status in ("failed", "canceled", "cancelled"):
                        break
                    get_url = data.get("urls", {}).get("get") if isinstance(data.get("urls"), dict) else None
                    get_url = get_url or f"https://api.replicate.com/v1/predictions/{data.get('id')}"
                    _t.sleep(5)
                    pr = client.get(
                        get_url,
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    if pr.status_code >= 400:
                        pr = client.get(
                            get_url,
                            headers={"Authorization": f"Token {key}"},
                        )
                    if pr.status_code < 400:
                        data = pr.json()
        except Exception as exc:
            logger.warning("seedance video: %s", str(exc)[:140])
        return None

    # Legacy custom Seedance base (rarely used)
    base = _env_val("SEEDANCE_API_BASE_URL")
    if not base:
        return None
    base = base.rstrip("/")
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{base}/v1/video/generate",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"prompt": fit_prompt_for_provider(prompt, 1500), "duration": int(duration or 5)},
            )
            if r.status_code >= 400:
                return None
            data = r.json()
            url = data.get("url") or data.get("video_url") or (data.get("data") or {}).get("url")
            if not url:
                return None
            media = client.get(str(url))
            media.raise_for_status()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(media.content)
            if out.stat().st_size > 5000:
                return out
    except Exception as exc:
        logger.warning("seedance video: %s", str(exc)[:120])
    return None

def video_pexels_stock(query: str, out: Path, *, portrait: bool = True) -> Optional[Path]:
    keys = _env_keys("PEXELS_API_KEY")
    if not keys:
        return None
    wait_media_gap(reason="pexels_video")
    q = (query or "cinematic tech").strip()
    variants = [q[:80]]
    words = q.split()
    if len(words) > 4:
        variants.append(" ".join(words[:4]))
    variants.append("technology smartphone studio")
    try:
        from pipeline.ai_providers import fetch_pexels_videos

        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            for key in keys[:2]:
                for vq in variants:
                    try:
                        urls = fetch_pexels_videos(
                            key,
                            vq,
                            per_page=3,
                            orientation="portrait" if portrait else "landscape",
                        )
                    except Exception:
                        urls = []
                    for u in urls or []:
                        media = client.get(u)
                        media.raise_for_status()
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(media.content)
                        if out.stat().st_size > 5000:
                            return out
    except Exception as exc:
        logger.warning("pexels video: %s", exc)
        return None
    return None


def video_pixabay_stock(query: str, out: Path, *, portrait: bool = True) -> Optional[Path]:
    keys = _env_keys("PIXABAY_API_KEY")
    if not keys or not str(keys[0]).strip():
        return None
    wait_media_gap(reason="pixabay_video")
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            r = client.get(
                "https://pixabay.com/api/videos/",
                params={
                    "key": keys[0],
                    "q": (query or "technology")[:100],
                    "per_page": 5,
                    "safesearch": "true",
                },
            )
            if r.status_code >= 400:
                return None
            hits = r.json().get("hits") or []
            for hit in hits:
                vids = hit.get("videos") or {}
                for quality in ("medium", "small", "large", "tiny"):
                    item = vids.get(quality) or {}
                    src = item.get("url") if isinstance(item, dict) else None
                    if not src:
                        continue
                    media = client.get(src)
                    media.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(media.content)
                    if out.stat().st_size > 5000:
                        return out
    except Exception as exc:
        logger.warning("pixabay video: %s", exc)
    return None


def ken_burns_from_image(
    image_path: Path,
    out: Path,
    *,
    duration: float,
    w: int,
    h: int,
    ffmpeg_filter: str = "",
    motion_preset: str = "",
    shot_number: int = 0,
) -> Optional[Path]:
    """Last-resort motion clip from a still — smooth, non-shaky, silent."""
    if not image_path.is_file():
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = max(2.0, float(duration or 5.0))

    from pipeline.custom_pipeline.motion_presets import (
        build_smooth_kenburns_filter,
        is_trusted_ffmpeg_filter,
        pick_motion_preset,
    )

    vf = (ffmpeg_filter or "").strip()
    if not is_trusted_ffmpeg_filter(vf, w=w, h=h, duration=dur):
        preset = motion_preset or pick_motion_preset(shot_number or 1)
        vf = build_smooth_kenburns_filter(w=w, h=h, duration=dur, preset=preset)
    cmd = [
        _ffmpeg(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{dur:.2f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and out.exists() and out.stat().st_size > 5000:
        return out
    # Absolute fallback: rebuild default slow zoom
    vf2 = build_smooth_kenburns_filter(w=w, h=h, duration=dur, preset="slow_zoom_in")
    cmd[cmd.index("-vf") + 1] = vf2
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and out.exists() and out.stat().st_size > 5000:
        return out
    logger.warning("kenburns failed: %s", (r.stderr or "")[:200])
    return None


VIDEO_CHAIN = (
    ("google_veo", video_google_veo),
    ("agnes", video_agnes),
    ("kling", video_kling),
    ("openrouter", video_openrouter),
    ("huggingface", video_huggingface),
    ("luma", video_luma),
    ("seedance", video_seedance),
)


def generate_video_with_fallback(
    prompt: str,
    out_path: Path,
    *,
    aspect: str = "9:16",
    duration: float = 6.0,
    stock_query: str = "",
    image_fallback_prompt: str = "",
    kenburns_filter: str = "",
    shot_key: str = "",
    seed: Optional[int] = None,
    image_url: str = "",
    prefer_stock_video: bool = False,
    allow_stock: bool = True,
) -> Dict[str, Any]:
    from pipeline.custom_pipeline.media_call_guard import begin_shot, is_circuit_open

    if shot_key:
        begin_shot(shot_key)
    w, h = canvas_for_aspect(aspect)
    out_path = Path(out_path)
    errors: List[str] = []
    locked_prompt = (prompt or "").strip()
    if seed is not None:
        locked_prompt = (
            f"{locked_prompt}. SEED LOCK {int(seed)}: match prior clips identity/wardrobe/set."
        )

    q = stock_query or prompt[:60]
    portrait = "9:16" in aspect

    def _try_stock() -> Optional[Dict[str, Any]]:
        if not allow_stock:
            return None
        for stock_name, stock_fn in (
            ("pexels_stock", video_pexels_stock),
            ("pixabay_stock", video_pixabay_stock),
        ):
            try:
                stock = stock_fn(q, out_path, portrait=portrait)
                if stock:
                    logger.info("Video OK provider=%s query=%s → %s", stock_name, q[:60], out_path.name)
                    return {
                        "ok": True,
                        "path": str(stock),
                        "provider": stock_name,
                        "fallback": True,
                        "quality": "degraded",
                        "seed": seed,
                        "stock_query": q,
                    }
            except Exception as exc:
                errors.append(f"{stock_name}:{exc}")
        return None

    # Brand UI: never prefer stock first — AI video/image first
    if prefer_stock_video and allow_stock:
        hit = _try_stock()
        if hit:
            return hit
    elif prefer_stock_video and not allow_stock:
        logger.info("STOCK_VIDEO requested but stock forbidden for brand UI — AI chain first")

    for name, fn in VIDEO_CHAIN:
        if is_circuit_open(name) or is_circuit_open(f"{name}_video"):
            logger.info("Skip provider %s (circuit open)", name)
            continue
        try:
            if name in ("agnes", "google_veo"):
                got = fn(
                    locked_prompt,
                    out_path,
                    w=w,
                    h=h,
                    duration=duration,
                    seed=seed,
                    image_url=image_url,
                )
            else:
                got = fn(locked_prompt, out_path, w=w, h=h, duration=duration)
            if got and got.exists() and got.stat().st_size > 5000:
                logger.info("Video OK provider=%s seed=%s → %s", name, seed, out_path.name)
                return {
                    "ok": True,
                    "path": str(got),
                    "provider": name,
                    "seed": seed,
                }
        except Exception as exc:
            errors.append(f"{name}:{exc}")
            logger.warning("video provider %s failed: %s", name, exc)

    # Never-die: image chain → ken burns (prioritize custom AI visual over generic stock)
    still = out_path.with_suffix(".still.png")
    img = generate_image_with_fallback(
        image_fallback_prompt or locked_prompt,
        still,
        aspect=aspect,
        stock_query=stock_query,
        seed=seed,
    )
    if img.get("ok"):
        kb = ken_burns_from_image(
            Path(img["path"]),
            out_path,
            duration=duration,
            w=w,
            h=h,
            ffmpeg_filter=kenburns_filter,
            shot_number=int("".join(ch for ch in shot_key if ch.isdigit()) or 0),
        )
        if kb:
            logger.info(
                "Video OK provider=kenburns_via_%s → %s",
                img.get("provider"),
                out_path.name,
            )
            return {
                "ok": True,
                "path": str(kb),
                "provider": f"kenburns_via_{img.get('provider')}",
                "fallback": True,
                "quality": "high_ai_image_animated",
                "seed": seed,
            }

    hit = _try_stock()
    if hit:
        return hit
    return {"ok": False, "path": None, "errors": errors, "provider": None, "seed": seed}
