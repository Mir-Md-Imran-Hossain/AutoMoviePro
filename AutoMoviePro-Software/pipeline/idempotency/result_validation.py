"""Result validation before reuse (BUILD-03)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.fingerprint import hash_artifact


def validate_file_result(
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
    effective_min = min_bytes
    if p.suffix.lower() in {".srt", ".vtt", ".ass"}:
        effective_min = min(min_bytes, 10)
    if size < effective_min:
        return False, f"too_small:{size}"
    if expected_hash:
        actual = hash_artifact(str(p))
        if actual != expected_hash:
            return False, "hash_mismatch"
    return True, "ok"


def validate_json_result(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, "file_missing"
    try:
        import json

        json.loads(p.read_text(encoding="utf-8"))
        return True, "ok"
    except Exception:
        return False, "json_invalid"
