"""
Google Pro Media Integration: Veo 3 / 2 Video Generation & Imagen 3 / 4 Image Generation.

Uses the official google-genai SDK to generate high-fidelity video clips and
photorealistic images with Google Pro credentials, with graceful fallback.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Default model priorities
VEO_MODELS = [
    "veo-3.1-generate-preview",
    "veo-3.1-fast-generate-preview",
    "veo-3.1-lite-generate-preview",
]

IMAGEN_MODELS = [
    "imagen-3.0-generate-002",
    "imagen-4.0-generate-001",
]

FLASH_IMAGE_MODELS = [
    "gemini-3.1-flash-image-preview",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
]


def is_google_pro_available(google_api_keys: Optional[Sequence[str]] = None) -> bool:
    """Check if any Google API key is configured in parameters or environment."""
    if google_api_keys:
        for k in google_api_keys:
            if (k or "").strip():
                return True
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def normalize_aspect_ratio(aspect_ratio: str, width: int = 0, height: int = 0) -> str:
    """Normalize aspect ratio to Veo / Imagen supported values: '16:9', '9:16', '1:1'."""
    raw = (aspect_ratio or "").strip().lower()
    if raw in ("9:16", "portrait", "vertical", "reel", "short", "tiktok"):
        return "9:16"
    if raw in ("16:9", "landscape", "horizontal", "wide"):
        return "16:9"
    if raw in ("1:1", "square"):
        return "1:1"
    if width > 0 and height > 0:
        if height > width:
            return "9:16"
        return "16:9"
    return "16:9"


def generate_veo_video(
    prompt: str,
    out_path: Path,
    api_key: str,
    *,
    aspect_ratio: str = "16:9",
    duration_seconds: int = 5,
    max_poll_seconds: int = 120,
    poll_interval: int = 8,
    model: Optional[str] = None,
) -> Optional[Path]:
    """
    Generate video using Google Veo (Veo 3.1 / Veo 2.0).

    Returns path to generated video on success, or None on failure/quota limit.
    """
    api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        logger.warning("Veo generation skipped: No Google API key provided")
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        logger.warning("Veo generation unavailable: google-genai SDK not installed (%s)", e)
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ar = normalize_aspect_ratio(aspect_ratio)

    candidate_models = [model] if model else VEO_MODELS
    client = genai.Client(api_key=api_key)

    for m in candidate_models:
        try:
            dur_raw = int(duration_seconds or 6)
            veo_dur = 4 if dur_raw <= 4 else (6 if dur_raw <= 7 else 8)
            config_kwargs: Dict[str, Any] = {
                "number_of_videos": 1,
                "duration_seconds": veo_dur,
            }
            try:
                config = types.GenerateVideosConfig(
                    aspect_ratio=ar,
                    **config_kwargs,
                )
            except Exception:
                config = types.GenerateVideosConfig(**config_kwargs)

            operation = client.models.generate_videos(
                model=m,
                prompt=prompt,
                config=config,
            )

            # Poll operation
            start_time = time.time()
            while not operation.done:
                elapsed = time.time() - start_time
                if elapsed > max_poll_seconds:
                    logger.warning("Veo video generation timed out after %ds for model %s", max_poll_seconds, m)
                    break
                time.sleep(poll_interval)
                operation = client.operations.get(operation)

            if not operation.done:
                continue

            resp = getattr(operation, "response", None)
            if not resp or not getattr(resp, "generated_videos", None):
                logger.warning("Veo operation completed but returned no videos: %s", operation)
                continue

            first_vid = resp.generated_videos[0]
            vid_file = getattr(first_vid, "video", None)
            if vid_file is not None:
                client.files.download(file=vid_file, destination=str(out_path))
                if out_path.is_file() and out_path.stat().st_size > 5000:
                    logger.info("Successfully generated Google Veo video: %s (%d bytes)", out_path.name, out_path.stat().st_size)
                    return out_path

        except Exception as exc:
            err_msg = str(exc)
            logger.warning("Google Veo model %s error: %s", m, err_msg[:200])
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                from pipeline.quota_backoff import record_quota_hit
                record_quota_hit("google")
            continue

    return None


def generate_imagen_image(
    prompt: str,
    out_path: Path,
    api_key: str,
    *,
    aspect_ratio: str = "16:9",
    width: int = 1920,
    height: int = 1080,
    model: Optional[str] = None,
) -> Optional[Path]:
    """
    Generate image using Google Imagen 3 / 4, with fallback to Flash Image multimodal.

    Returns path to generated image on success, or None on failure.
    """
    api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ar = normalize_aspect_ratio(aspect_ratio, width=width, height=height)
    client = genai.Client(api_key=api_key)

    # 1) Try Imagen models
    candidate_imagen = [model] if model else IMAGEN_MODELS
    for m in candidate_imagen:
        try:
            logger.debug("Attempting Google Imagen generation: model=%s ar=%s", m, ar)
            cfg = types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=ar,
                output_mime_type="image/jpeg",
            )
            resp = client.models.generate_images(
                model=m,
                prompt=prompt,
                config=cfg,
            )
            gen_imgs = getattr(resp, "generated_images", None) or []
            if gen_imgs:
                img_obj = gen_imgs[0]
                img_bytes = getattr(getattr(img_obj, "image", None), "image_bytes", None)
                if img_bytes:
                    out_path.write_bytes(img_bytes)
                    if out_path.is_file() and out_path.stat().st_size > 3000:
                        logger.info("Successfully generated Imagen image %s (%d bytes)", out_path.name, out_path.stat().st_size)
                        return out_path
        except Exception as exc:
            err_msg = str(exc)
            logger.debug("Google Imagen model %s failed: %s", m, err_msg[:160])
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                from pipeline.quota_backoff import record_quota_hit
                record_quota_hit("google")
            continue

    # 2) Fallback to Flash Image multimodal (gemini-2.5-flash-image)
    for m in FLASH_IMAGE_MODELS:
        try:
            logger.debug("Attempting Flash Image multimodal generation: model=%s", m)
            resp = client.models.generate_content(
                model=m,
                contents=prompt,
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
                        out_path.write_bytes(raw)
                        if out_path.is_file() and out_path.stat().st_size > 2000:
                            logger.info("Successfully generated Flash multimodal image %s (%d bytes)", out_path.name, out_path.stat().st_size)
                            return out_path
        except Exception as exc:
            logger.debug("Flash Image model %s failed: %s", m, str(exc)[:160])
            continue

    return None
