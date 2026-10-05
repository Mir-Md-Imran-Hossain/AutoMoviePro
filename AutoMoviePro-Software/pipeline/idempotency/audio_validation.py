"""Audio asset validation (BUILD-04B)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pipeline.idempotency.fingerprint import hash_artifact


def _is_wav(path: Path) -> bool:
    try:
        return path.read_bytes()[:4] == b"RIFF"
    except OSError:
        return False


def _is_mp3(path: Path) -> bool:
    try:
        head = path.read_bytes()[:3]
        return head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    except OSError:
        return False


def _is_m4a(path: Path) -> bool:
    try:
        head = path.read_bytes()[:12]
        return b"ftyp" in head[:8]
    except OSError:
        return False


def validate_audio_asset(
    path: str,
    *,
    min_bytes: int = 800,
    expected_hash: str = "",
) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, "file_missing"
    try:
        size = p.stat().st_size
    except OSError:
        return False, "stat_failed"
    if size < min_bytes:
        return False, f"too_small:{size}"
    if size == 0:
        return False, "zero_bytes"
    if not (_is_wav(p) or _is_mp3(p) or _is_m4a(p)):
        return False, "invalid_audio_format"
    if expected_hash:
        actual = hash_artifact(str(p))
        if actual != expected_hash:
            return False, "hash_mismatch"
    return True, "ok"


def probe_duration_sec(path: str) -> Optional[float]:
    try:
        from pipeline.compose import ffprobe_duration

        d = float(ffprobe_duration(Path(path)))
        return d if d > 0 else None
    except Exception:
        return None
