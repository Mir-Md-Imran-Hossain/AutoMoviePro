"""Smooth Ken Burns / still-motion presets — no shaky zoompan.

Why old filters shook:
  - Grok often emitted broken ``d=17`` / truncated zoompan strings
  - Aggressive zoom steps (0.0015–0.002) on small source → subpixel jitter
  - Missing large intermediate scale before zoompan

Policy:
  - Always rebuild filter from duration + canvas + preset name
  - Ignore untrusted Grok ffmpeg_filter strings (keep animation_type only)
  - Rotate presets per shot so IMAGE clips are not identical
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# (id, human label)
MOTION_PRESET_IDS: List[Tuple[str, str]] = [
    ("slow_zoom_in", "Slow Center Zoom In"),
    ("slow_zoom_out", "Slow Center Zoom Out"),
    ("pan_left", "Gentle Pan Left"),
    ("pan_right", "Gentle Pan Right"),
    ("tilt_up", "Gentle Tilt Up"),
    ("tilt_down", "Gentle Tilt Down"),
    ("zoom_in_pan_right", "Slow Zoom In + Pan Right"),
    ("zoom_in_pan_left", "Slow Zoom In + Pan Left"),
]


def pick_motion_preset(shot_number: int, *, preferred: str = "") -> str:
    """Rotate presets by shot index; honor known preferred labels/ids."""
    pref = (preferred or "").strip().lower()
    if pref:
        # Exact id / exact label first
        for pid, label in MOTION_PRESET_IDS:
            if pref == pid or pref == label.lower():
                return pid
        # Specific keywords BEFORE generic "zoom" (avoids swallowing "zoom + tilt")
        if "zoom out" in pref:
            return "slow_zoom_out"
        if "pan left" in pref:
            return "pan_left"
        if "pan right" in pref:
            return "pan_right"
        if "tilt up" in pref or "tilt_up" in pref:
            return "tilt_up"
        if "tilt down" in pref or "tilt_down" in pref:
            return "tilt_down"
        if "zoom" in pref and "right" in pref:
            return "zoom_in_pan_right"
        if "zoom" in pref and "left" in pref:
            return "zoom_in_pan_left"
        if "pan" in pref and "left" in pref:
            return "pan_left"
        if "pan" in pref and "right" in pref:
            return "pan_right"
        if "tilt" in pref and "up" in pref:
            return "tilt_up"
        if "tilt" in pref and "down" in pref:
            return "tilt_down"
        if "zoom" in pref:
            return "slow_zoom_in"
        # Partial label containment last
        for pid, label in MOTION_PRESET_IDS:
            if pref in label.lower() or label.lower() in pref:
                return pid
    n = max(1, int(shot_number or 1))
    return MOTION_PRESET_IDS[(n - 1) % len(MOTION_PRESET_IDS)][0]


def build_smooth_kenburns_filter(
    *,
    w: int,
    h: int,
    duration: float,
    preset: str = "slow_zoom_in",
    fps: int = 25,
) -> str:
    """Industrial smooth still→video filter (silent, yuv420p-ready via caller)."""
    frames = max(int(fps * 2), int(round(max(2.0, float(duration or 5.0)) * fps)))
    # Large working canvas reduces zoompan subpixel shake
    work = max(w, h) * 4
    # Very small zoom increment → cinematic, not shaky
    z_step = 0.00045
    z_max = 1.12

    pid = (preset or "slow_zoom_in").strip().lower()
    # on = frame index 0..d-1; progress = on/(d-1)
    prog = f"(on/{max(1, frames - 1)})"

    if pid == "slow_zoom_out":
        # Start zoomed, ease out toward 1.0
        z_expr = f"max(1.0,{z_max}-({z_max}-1.0)*{prog})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pid == "pan_left":
        z_expr = "1.08"
        x_expr = f"(iw-iw/zoom)*(1-{prog})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pid == "pan_right":
        z_expr = "1.08"
        x_expr = f"(iw-iw/zoom)*{prog}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pid == "tilt_up":
        z_expr = "1.08"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(1-{prog})"
    elif pid == "tilt_down":
        z_expr = "1.08"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*{prog}"
    elif pid == "zoom_in_pan_right":
        z_expr = f"min(zoom+{z_step},{z_max})"
        x_expr = f"(iw-iw/zoom)*{prog}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pid == "zoom_in_pan_left":
        z_expr = f"min(zoom+{z_step},{z_max})"
        x_expr = f"(iw-iw/zoom)*(1-{prog})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:  # slow_zoom_in
        z_expr = f"min(zoom+{z_step},{z_max})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    # scale → zoompan → exact canvas
    return (
        f"scale={work}:-1,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={frames}:s={w}x{h}:fps={fps},"
        f"fps={fps},format=yuv420p"
    )


def motion_directive_for_shot(
    shot_number: int,
    *,
    duration: float,
    w: int,
    h: int,
    preferred_label: str = "",
) -> Dict[str, str]:
    pid = pick_motion_preset(shot_number, preferred=preferred_label)
    label = next((lbl for i, lbl in MOTION_PRESET_IDS if i == pid), pid)
    return {
        "animation_type": label,
        "motion_preset": pid,
        "ffmpeg_filter": build_smooth_kenburns_filter(
            w=w, h=h, duration=duration, preset=pid
        ),
    }


def is_trusted_ffmpeg_filter(vf: str, *, w: int, h: int, duration: float) -> bool:
    """Reject truncated / tiny-d / wrong-canvas Grok filters."""
    raw = (vf or "").strip()
    if not raw or "zoompan" not in raw.lower():
        return False
    # Must include frame count roughly matching duration
    import re

    m = re.search(r":d=(\d+)", raw)
    if not m:
        return False
    d = int(m.group(1))
    need = int(round(max(2.0, float(duration or 5.0)) * 25))
    if d < max(40, int(need * 0.5)):
        return False
    # Portrait shorts must not hardcode landscape canvas
    if w < h and "1920x1080" in raw and f"{w}x{h}" not in raw:
        return False
    return True
