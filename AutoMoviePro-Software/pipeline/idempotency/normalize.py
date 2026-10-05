"""Deterministic normalization for fingerprint inputs (BUILD-03)."""
from __future__ import annotations

import json
from typing import Any


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            return round(value, 6)
        return value
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {str(k): normalize_value(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [normalize_value(v) for v in value]
    return str(value)


def normalize_fingerprint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize deterministic fields; exclude volatile keys."""
    skip = {
        "timestamp",
        "created_at",
        "updated_at",
        "attempt",
        "attempt_number",
        "retry_count",
        "random_uuid",
        "log_line",
    }
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in skip:
            continue
        out[k] = normalize_value(v)
    return normalize_value(out)


def canonical_json(payload: dict[str, Any]) -> str:
    normalized = normalize_fingerprint_payload(payload)
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
