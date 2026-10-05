"""Visual asset validation (BUILD-04A)."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from pipeline.idempotency.fingerprint import hash_artifact


def _read_box_type(data: bytes, offset: int) -> Optional[str]:
    if offset + 8 > len(data):
        return None
    size = struct.unpack(">I", data[offset : offset + 4])[0]
    box_type = data[offset + 4 : offset + 8].decode("latin-1", errors="ignore")
    return box_type


def is_mp4_container(path: Path) -> bool:
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return False
    if len(head) < 8:
        return False
    # MP4/MOV: ftyp at offset 4
    if head[4:8] == b"ftyp":
        return True
    return b"ftyp" in head[:24]


def is_png(path: Path) -> bool:
    try:
        return path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def is_jpeg(path: Path) -> bool:
    try:
        b = path.read_bytes()[:3]
        return b[:2] == b"\xff\xd8"
    except OSError:
        return False


def validate_video_asset(
    path: str,
    *,
    min_bytes: int = 8000,
    expected_hash: str = "",
    require_mp4: bool = True,
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
    if require_mp4 and not is_mp4_container(p):
        return False, "invalid_container"
    if expected_hash:
        actual = hash_artifact(str(p))
        if actual != expected_hash:
            return False, "hash_mismatch"
    return True, "ok"


def validate_image_asset(
    path: str,
    *,
    min_bytes: int = 1000,
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
    if not (is_png(p) or is_jpeg(p)):
        return False, "invalid_image_format"
    if expected_hash:
        actual = hash_artifact(str(p))
        if actual != expected_hash:
            return False, "hash_mismatch"
    return True, "ok"


def validate_visual_asset(path: str, *, mode: str = "video", **kwargs) -> tuple[bool, str]:
    if mode == "image":
        return validate_image_asset(path, **kwargs)
    return validate_video_asset(path, **kwargs)
