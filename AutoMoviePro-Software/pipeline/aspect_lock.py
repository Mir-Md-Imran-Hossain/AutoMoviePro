"""Hard aspect lock for AutoMovie Pro outputs.

Product rule (always):
  - SHORT  → vertical   9:16  → 1080x1920
  - LONG   → horizontal 16:9  → 1920x1080

Any caller-supplied size that violates orientation is coerced.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

SHORT_SIZE = "1080x1920"
LONG_SIZE = "1920x1080"
SHORT_RATIO = "9:16"
LONG_RATIO = "16:9"
SHORT_ORIENTATION = "vertical"
LONG_ORIENTATION = "horizontal"


def normalize_video_type(video_type: str | None) -> str:
    raw = str(video_type or "short").strip().lower()
    if raw in ("long", "landscape", "horizontal", "widescreen", "yt_long"):
        return "long"
    return "short"


def parse_size(size: str | None) -> Tuple[int, int]:
    raw = str(size or "").strip().lower().replace("*", "x").replace("×", "x")
    if "x" not in raw:
        return 0, 0
    try:
        a, b = raw.split("x", 1)
        return int(float(a.strip())), int(float(b.strip()))
    except Exception:
        return 0, 0


def size_for_video_type(video_type: str | None) -> str:
    return LONG_SIZE if normalize_video_type(video_type) == "long" else SHORT_SIZE


def ratio_for_video_type(video_type: str | None) -> str:
    return LONG_RATIO if normalize_video_type(video_type) == "long" else SHORT_RATIO


def orientation_for_video_type(video_type: str | None) -> str:
    return LONG_ORIENTATION if normalize_video_type(video_type) == "long" else SHORT_ORIENTATION


def coerce_size(size: str | None, video_type: str | None) -> str:
    """Return canonical size; reject wrong orientation even if size was passed in."""
    expected = size_for_video_type(video_type)
    w, h = parse_size(size)
    if w <= 0 or h <= 0:
        return expected
    vt = normalize_video_type(video_type)
    if vt == "short" and w < h:
        # Already vertical — snap to canonical short canvas
        return SHORT_SIZE
    if vt == "long" and w > h:
        return LONG_SIZE
    # Wrong orientation (e.g. landscape short / portrait long) → force lock
    return expected


def assert_orientation(size: str | None, video_type: str | None) -> Dict[str, Any]:
    """Probe helper for gates / tests."""
    vt = normalize_video_type(video_type)
    locked = coerce_size(size, vt)
    w, h = parse_size(locked)
    ok = (w < h) if vt == "short" else (w > h)
    return {
        "ok": bool(ok and w > 0 and h > 0),
        "video_type": vt,
        "size": locked,
        "width": w,
        "height": h,
        "ratio": ratio_for_video_type(vt),
        "orientation": orientation_for_video_type(vt),
        "coerced_from": size,
    }


def aspect_prompt_lock(video_type: str | None) -> str:
    """Inject into visual prompts so generators respect canvas."""
    vt = normalize_video_type(video_type)
    if vt == "long":
        return (
            f"HORIZONTAL {LONG_RATIO} landscape frame only ({LONG_SIZE}). "
            "Do not generate vertical/portrait framing."
        )
    return (
        f"VERTICAL {SHORT_RATIO} portrait frame only ({SHORT_SIZE}). "
        "Do not generate horizontal/landscape framing."
    )


def render_profile(video_type: str | None) -> Dict[str, Any]:
    vt = normalize_video_type(video_type)
    size = size_for_video_type(vt)
    w, h = parse_size(size)
    return {
        "video_type": vt,
        "size": size,
        "width": w,
        "height": h,
        "fps": 25.0,
        "ratio": ratio_for_video_type(vt),
        "orientation": orientation_for_video_type(vt),
        "aspect_lock": True,
    }
