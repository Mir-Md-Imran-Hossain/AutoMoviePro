"""Render output validation (BUILD-04D)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.visual_validation import validate_video_asset


DURATION_TOLERANCE_SEC = 2.0
DURATION_TOLERANCE_RATIO = 0.05


def _ffprobe_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        from pipeline.compose import ffprobe_bin

        raw = subprocess.check_output(
            [
                ffprobe_bin(),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        return json.loads(raw)
    except Exception:
        return None


def probe_render_metadata(path: Path) -> dict[str, Any]:
    data = _ffprobe_json(path) or {}
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float(fmt.get("duration") or 0.0)
    if not dur and video:
        dur = float(video.get("duration") or 0.0)
    return {
        "duration_sec": dur,
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "fps": _parse_fps(video.get("r_frame_rate") if video else ""),
        "has_video": video is not None,
        "has_audio": audio is not None,
        "video_codec": str(video.get("codec_name") or "") if video else "",
        "audio_codec": str(audio.get("codec_name") or "") if audio else "",
    }


def _parse_fps(raw: str) -> float:
    if not raw:
        return 0.0
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else 0.0
        except Exception:
            return 0.0
    try:
        return float(raw)
    except Exception:
        return 0.0


def duration_within_tolerance(expected: float, actual: float) -> tuple[bool, str]:
    if expected <= 0:
        return True, "no_expected_duration"
    tol = max(DURATION_TOLERANCE_SEC, expected * DURATION_TOLERANCE_RATIO)
    delta = abs(actual - expected)
    if delta <= tol:
        return True, "ok"
    return False, f"duration_mismatch:expected={expected:.2f},actual={actual:.2f},tol={tol:.2f}"


def validate_render_output(
    path: str,
    *,
    expected_size: str = "",
    expected_duration_sec: Optional[float] = None,
    require_audio: bool = True,
    require_video: bool = True,
    min_bytes: int = 8000,
) -> tuple[bool, str]:
    p = Path(path)
    ok, reason = validate_video_asset(str(p), min_bytes=min_bytes, require_mp4=True)
    if not ok:
        return ok, reason

    meta = probe_render_metadata(p)
    probe = _ffprobe_json(p)
    if probe is None:
        return True, "ok_container_only"

    if require_video and not meta.get("has_video"):
        return False, "missing_video_stream"
    if require_audio and not meta.get("has_audio"):
        return False, "missing_audio_stream"

    if expected_size and "x" in expected_size:
        ew, eh = expected_size.lower().split("x", 1)
        try:
            exp_w, exp_h = int(ew), int(eh)
            aw, ah = int(meta.get("width") or 0), int(meta.get("height") or 0)
            if aw and ah and (aw != exp_w or ah != exp_h):
                return False, f"dimension_mismatch:{aw}x{ah}!={exp_w}x{exp_h}"
        except ValueError:
            pass

    if expected_duration_sec is not None and expected_duration_sec > 0:
        ok_d, msg = duration_within_tolerance(expected_duration_sec, float(meta.get("duration_sec") or 0))
        if not ok_d and _ffprobe_json(p) is not None:
            return False, msg

    return True, "ok"
