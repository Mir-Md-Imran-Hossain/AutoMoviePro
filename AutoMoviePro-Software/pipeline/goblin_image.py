"""
Goblin AI image generation (keyless Python lib).

Requires: pip install goblin-ai camoufox && python -m camoufox fetch

Live notes
----------
Goblin scrapes ephemeral keys via Camoufox browser, then generates over HTTP.
On this host (2026-08) it was slow (~60s key acquire) and often 404'd downloads,
so it is wired as a mid-chain fallback with a hard timeout + circuit — not primary
unless GOBLIN_PRIMARY=true after a successful smoke.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loop_ready = False


def goblin_enabled() -> bool:
    return os.environ.get("GOBLIN_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def goblin_primary() -> bool:
    return os.environ.get("GOBLIN_PRIMARY", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _model() -> str:
    return (os.environ.get("GOBLIN_IMAGE_MODEL") or "goblin-flux").strip() or "goblin-flux"


def _timeout_sec() -> float:
    try:
        return max(15.0, float(os.environ.get("GOBLIN_TIMEOUT_SEC", "90")))
    except Exception:
        return 90.0


def _ensure_headless_env() -> None:
    os.environ.setdefault("GOBLIN_HEADLESS", "1")
    os.environ.setdefault("GOBLIN_NO_VIEWPORT", "1")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


async def _generate_async(
    prompt: str,
    out_path: Path,
    *,
    width: int,
    height: int,
    model: str,
) -> bytes:
    import goblin

    data = await goblin.generate(
        prompt,
        model=model,
        width=max(64, min(int(width), 2048)),
        height=max(64, min(int(height), 2048)),
        quality=os.environ.get("GOBLIN_QUALITY", "fast"),
        enhance_output=os.environ.get("GOBLIN_ENHANCE", "false").strip().lower()
        in {"1", "true", "yes"},
        upscale_output=False,
        output=str(out_path),
    )
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)
    if out_path.exists() and out_path.stat().st_size > 1000:
        return out_path.read_bytes()
    raise RuntimeError("goblin returned empty image")


def goblin_generate_image(
    prompt: str,
    out_path: Path,
    *,
    width: int = 1024,
    height: int = 1024,
    model: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Path:
    """Generate an image with Goblin. Raises on disable/circuit/timeout/failure."""
    if not goblin_enabled():
        raise RuntimeError("Goblin disabled (GOBLIN_ENABLED=false)")

    try:
        from pipeline.provider_budget import assert_allowed, record_failure, record_success
    except Exception:
        assert_allowed = None  # type: ignore
        record_failure = None  # type: ignore
        record_success = None  # type: ignore

    if assert_allowed is not None:
        assert_allowed("goblin")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_headless_env()
    mid = (model or _model()).strip()
    # Map legacy aliases used in AutoMoviePro config
    alias = {
        "flux": "goblin-flux",
        "sd": "goblin-sd",
        "sdxl": "goblin-sdxl",
        "anime": "goblin-anime",
        "realistic": "goblin-realistic",
        "photo": "goblin-photo",
    }
    mid = alias.get(mid.lower(), mid)
    limit = float(timeout_sec if timeout_sec is not None else _timeout_sec())

    with _lock:
        try:
            data = asyncio.run(
                asyncio.wait_for(
                    _generate_async(prompt, out_path, width=width, height=height, model=mid),
                    timeout=limit,
                )
            )
        except Exception as exc:
            if record_failure is not None:
                record_failure("goblin", exc)
            logger.warning("Goblin image failed (%s): %s", mid, str(exc)[:200])
            raise RuntimeError(f"goblin image failed: {exc}") from exc

    if not out_path.exists() or out_path.stat().st_size < 1000:
        out_path.write_bytes(data)
    if record_success is not None:
        record_success("goblin")
    logger.info("Goblin image ok model=%s size=%s", mid, out_path.stat().st_size)
    return out_path
