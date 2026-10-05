"""Deterministic loudness / clipping / silence observation (AMP-004 Phase-05).

Extends existing audio validation — does NOT claim broadcast LUFS compliance.
"""
from __future__ import annotations

import array
import struct
from pathlib import Path
from typing import Any, Optional


def analyze_wav_levels(path: Path) -> dict[str, Any]:
    """Peak/RMS/clipping/silence for PCM16 WAV. UNKNOWN if format unsupported."""
    path = Path(path)
    if not path.is_file():
        return {"status": "FAIL", "method": "DETERMINISTIC", "issues": ["missing_artifact"]}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"status": "FAIL", "method": "DETERMINISTIC", "issues": [f"unreadable:{exc}"]}

    if raw[:4] != b"RIFF" or len(raw) < 44:
        return {
            "status": "UNKNOWN",
            "method": "UNAVAILABLE",
            "issues": ["non_wav_loudness_unverified"],
            "claim": "no_broadcast_lufs",
        }

    try:
        channels = struct.unpack_from("<H", raw, 22)[0]
        sample_rate = struct.unpack_from("<I", raw, 24)[0]
        bits = struct.unpack_from("<H", raw, 34)[0]
        data_size = struct.unpack_from("<I", raw, 40)[0]
        if bits != 16:
            return {
                "status": "UNKNOWN",
                "method": "UNAVAILABLE",
                "issues": ["unsupported_bit_depth"],
                "sample_rate": sample_rate,
                "channels": channels,
            }
        if sample_rate <= 0 or channels <= 0:
            return {"status": "FAIL", "method": "DETERMINISTIC", "issues": ["invalid_stream_config"]}

        pcm = array.array("h")
        pcm.frombytes(raw[44 : 44 + data_size])
        if not pcm:
            return {"status": "FAIL", "method": "DETERMINISTIC", "issues": ["empty_pcm", "unexpected_complete_silence"]}

        peak = max(abs(s) for s in pcm) / 32768.0
        # Simple RMS
        step = max(1, len(pcm) // 50000)
        acc = sum((s / 32768.0) ** 2 for s in pcm[::step])
        n = max(1, len(pcm[::step]))
        rms = (acc / n) ** 0.5
        clipped = sum(1 for s in pcm if abs(s) >= 32767) 
        clip_ratio = clipped / max(1, len(pcm))
        near_silence = peak < 0.001

        issues: list[str] = []
        status = "PASS"
        if clip_ratio > 0.001 or peak >= 0.999:
            issues.append("clipping_detected")
            status = "FAIL"
        if near_silence:
            issues.append("unexpected_complete_silence")
            status = "FAIL"
        if sample_rate not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
            issues.append(f"unusual_sample_rate:{sample_rate}")
            # advisory — not auto FAIL
        if channels not in (1, 2):
            issues.append(f"invalid_channel_configuration:{channels}")
            status = "FAIL"

        return {
            "status": status,
            "method": "DETERMINISTIC",
            "peak": round(peak, 5),
            "rms": round(rms, 5),
            "clip_ratio": round(clip_ratio, 6),
            "sample_rate": sample_rate,
            "channels": channels,
            "issues": issues,
            "broadcast_lufs_claimed": False,
            "loudness_policy": "dialogue_primary_v1",
        }
    except Exception as exc:
        return {"status": "UNKNOWN", "method": "UNAVAILABLE", "issues": [f"analyze_failed:{exc}"]}


def classify_silence_region(
    *,
    intentional_pause: bool = False,
    near_silence: bool = False,
    dialogue_expected: bool = True,
) -> str:
    """Distinguish intentional silence vs missing audio."""
    if intentional_pause and near_silence:
        return "intentional_pause"
    if near_silence and dialogue_expected:
        return "unexpected_silence"
    if near_silence:
        return "ambient_or_scene_silence"
    return "active_audio"
