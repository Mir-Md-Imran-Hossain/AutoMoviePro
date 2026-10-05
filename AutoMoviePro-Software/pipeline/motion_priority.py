"""Parallax-lite image motion priority chain (protocol §46–47)."""
from __future__ import annotations

from typing import Any, Dict, List


MOTION_PRIORITY = [
    "real_video",
    "ai_image_i2v",
    "parallax_lite",
    "ken_burns",
]


def select_motion_fallback(available: Dict[str, bool]) -> str:
    for key in MOTION_PRIORITY:
        if available.get(key):
            return key
    return "ken_burns"


def parallax_lite_plan(*, duration_sec: float = 5.0) -> Dict[str, Any]:
    """Two-layer pan/zoom plan (foreground faster than background) — emergency above pure Ken Burns."""
    return {
        "method": "parallax_lite",
        "duration_sec": duration_sec,
        "layers": [
            {"name": "background", "zoom": 1.06, "pan_x": 0.04, "pan_y": 0.02},
            {"name": "foreground", "zoom": 1.12, "pan_x": -0.06, "pan_y": 0.03},
        ],
        "note": "Composite when depth map unavailable; prefer real_video/I2V when present",
    }
