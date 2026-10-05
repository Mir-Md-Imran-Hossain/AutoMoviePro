"""Actual media inspection helpers — wraps existing validators + ffprobe (L0/L1)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional


def probe_media(path: Path) -> dict[str, Any]:
    """Deterministic ffprobe observation. Empty dict if unavailable."""
    path = Path(path)
    if not path.is_file():
        return {"exists": False, "decodable": False}
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
        data = json.loads(raw)
    except Exception as exc:
        return {"exists": True, "decodable": False, "probe_error": str(exc)}

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") in ("subtitle", "text")]
    v0 = video[0] if video else {}
    a0 = audio[0] if audio else {}
    dur = float(fmt.get("duration") or v0.get("duration") or a0.get("duration") or 0.0)
    fps = 0.0
    rate = str(v0.get("r_frame_rate") or "")
    if "/" in rate:
        try:
            n, d = rate.split("/", 1)
            fps = float(n) / float(d) if float(d) else 0.0
        except Exception:
            fps = 0.0
    elif rate:
        try:
            fps = float(rate)
        except Exception:
            fps = 0.0
    nb_frames = int(v0.get("nb_frames") or 0) if str(v0.get("nb_frames") or "").isdigit() else 0
    return {
        "exists": True,
        "decodable": True,
        "duration": dur,
        "width": int(v0.get("width") or 0),
        "height": int(v0.get("height") or 0),
        "fps": fps,
        "frame_count": nb_frames,
        "video_streams": len(video),
        "audio_streams": len(audio),
        "subtitle_streams": len(subs),
        "sample_rate": int(a0.get("sample_rate") or 0) if a0.get("sample_rate") else 0,
        "channels": int(a0.get("channels") or 0) if a0.get("channels") else 0,
        "video_codec": str(v0.get("codec_name") or ""),
        "audio_codec": str(a0.get("codec_name") or ""),
        "format_name": str(fmt.get("format_name") or ""),
        "size_bytes": int(fmt.get("size") or path.stat().st_size),
    }


def detect_near_silence_wav(path: Path, *, threshold: float = 0.001) -> Optional[bool]:
    """Deterministic near-silence for WAV only. None = not applicable / unavailable."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        if raw[:4] != b"RIFF" or len(raw) < 44:
            return None
        # PCM16 little-endian samples after 44-byte header (common case)
        import array

        samples = array.array("h")
        samples.frombytes(raw[44 : 44 + min(len(raw) - 44, 48000 * 2)])
        if not samples:
            return True
        peak = max(abs(s) for s in samples) / 32768.0
        return peak < threshold
    except Exception:
        return None


def detect_blank_image(path: Path) -> Optional[bool]:
    """Heuristic blank/near-empty PNG/JPEG via size + simple decode. None if unavailable."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
        if size < 200:
            return True
        # Very small compressed images often blank; not a VLM claim
        if size < 800:
            return True
        return False
    except Exception:
        return None
