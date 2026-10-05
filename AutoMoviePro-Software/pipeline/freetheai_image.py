"""
FreeTheAI image generation (OpenAI-compatible /images/generations).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


def freetheai_generate_image(
    prompt: str,
    out_path: Path,
    *,
    api_keys: Optional[List[str]] = None,
    base_url: str = "",
    model: str = "eve/gpt-image-2",
    size: str = "1024x1024",
) -> Path:
    from pipeline.api_keys import load_api_bundle
    from pipeline.provider_budget import (
        record_failure,
        record_success,
        select_provider_keys,
    )

    b = load_api_bundle()
    keys = select_provider_keys(api_keys or list(b.get("freetheai_keys") or []), "freetheai")
    if not keys:
        raise RuntimeError("no FreeTheAI keys for image")
    base = (base_url or str(b.get("freetheai_base_url") or "https://api.freetheai.xyz/v1")).rstrip("/")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for key in keys:
        try:
            with httpx.Client(timeout=180.0) as client:
                r = client.post(
                    f"{base}/images/generations",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "prompt": prompt,
                        "n": 1,
                        "size": size,
                        "response_format": "b64_json",
                    },
                )
                if r.status_code >= 400:
                    last_err = RuntimeError(f"freetheai image {r.status_code}: {r.text[:200]}")
                    record_failure("freetheai", r.text)
                    if r.status_code in (402, 429):
                        raise last_err
                    continue
                data = r.json()
                item = (data.get("data") or [{}])[0]
                b64 = item.get("b64_json") or ""
                url = item.get("url") or ""
                if b64:
                    out_path.write_bytes(base64.b64decode(b64))
                    record_success("freetheai")
                    return out_path
                if url:
                    img = client.get(url, timeout=120.0)
                    img.raise_for_status()
                    out_path.write_bytes(img.content)
                    record_success("freetheai")
                    return out_path
                last_err = RuntimeError("freetheai image empty payload")
        except Exception as exc:
            last_err = exc
            record_failure("freetheai", exc)
            continue
    raise RuntimeError(f"FreeTheAI image failed: {last_err}")
