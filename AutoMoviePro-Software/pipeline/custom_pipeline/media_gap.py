"""Shared call-gap & pacing helper for media generation.

Maintains 100% backwards-compatibility for existing tests and call sites,
while delegating to google_pacing_guard for randomized jitter delays and modality-specific pacing.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from pipeline.custom_pipeline.google_pacing_guard import (
    compute_random_gap,
    set_pacing_package_context,
    wait_pacing_gap,
)

logger = logging.getLogger(__name__)

_DEFAULT_GAP = 45.0
_lock = threading.Lock()
_last_mono = 0.0
_tls = threading.local()


def set_media_gap_package(package_root: str = "", state: Any = None) -> None:
    _tls.package_root = package_root or ""
    _tls.state = state
    set_pacing_package_context(package_root, state)


def media_call_gap_seconds() -> float:
    raw = (os.environ.get("AMP_MEDIA_CALL_GAP_SEC") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_GAP


def _infer_modality_from_reason(reason: str) -> str:
    r = (reason or "").lower()
    if "video" in r or "veo" in r or "agnes_video" in r or "kling_video" in r:
        return "video"
    if "audio" in r or "tts" in r or "speech" in r or "voice" in r:
        return "audio"
    if "image" in r or "photo" in r or "still" in r or "pollinations" in r or "flux" in r:
        return "image"
    return "general"


def wait_media_gap(
    *,
    reason: str = "",
    package_root: str = "",
    state: Any = None,
) -> None:
    global _last_mono
    from pipeline.custom_pipeline.pipeline_control import (
        PipelineCancelled,
        check_cancelled,
        interruptible_sleep,
    )

    pkg = package_root or getattr(_tls, "package_root", "") or ""
    st = state if state is not None else getattr(_tls, "state", None)

    # If explicit AMP_MEDIA_CALL_GAP_SEC is set, honor it for test determinism
    raw_env = (os.environ.get("AMP_MEDIA_CALL_GAP_SEC") or "").strip()
    if raw_env:
        try:
            gap = max(0.0, float(raw_env))
        except ValueError:
            gap = _DEFAULT_GAP
    else:
        modality = _infer_modality_from_reason(reason)
        gap = compute_random_gap(modality)

    if gap <= 0:
        return

    with _lock:
        now = time.monotonic()
        wait = gap - (now - _last_mono) if _last_mono > 0 else 0.0
        if wait <= 0:
            _last_mono = time.monotonic()
            return

    logger.info(
        "Media gap: waiting %.1fs%s (gap=%.1fs)",
        wait,
        f" ({reason})" if reason else "",
        gap,
    )
    try:
        interruptible_sleep(wait, package_root=pkg, state=st)
    except PipelineCancelled:
        raise
    except Exception as exc:
        logger.debug("interruptible_sleep soft-fail, falling back: %s", exc)
        check_cancelled(pkg, st)
        time.sleep(wait)

    with _lock:
        _last_mono = time.monotonic()
