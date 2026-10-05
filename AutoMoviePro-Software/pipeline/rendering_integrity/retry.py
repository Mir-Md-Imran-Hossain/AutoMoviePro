"""Render failure classification + bounded retry (no AI regeneration)."""
from __future__ import annotations

from typing import Any, Optional

RETRY_CLASSES = {
    "TRANSIENT",
    "DETERMINISTIC_INPUT_ERROR",
    "FILTERGRAPH_ERROR",
    "ENCODING_ERROR",
    "RESOURCE_ERROR",
    "OUTPUT_VALIDATION_FAILURE",
    "UNKNOWN",
}

MAX_RENDER_INTEGRITY_RETRIES = 3


def classify_render_failure(
    *,
    issues: Optional[list[str]] = None,
    exit_code: Optional[int] = None,
    timed_out: bool = False,
    stderr: str = "",
    validation_ok: Optional[bool] = None,
) -> str:
    issues = list(issues or [])
    err = (stderr or "").lower()
    if timed_out:
        return "TRANSIENT"
    if any("missing_" in i or "zero_duration" in i or "negative_duration" in i or "accidental_" in i for i in issues):
        return "DETERMINISTIC_INPUT_ERROR"
    if any("filter" in i or "stream" in i or "filtergraph" in i for i in issues):
        return "FILTERGRAPH_ERROR"
    if validation_ok is False:
        return "OUTPUT_VALIDATION_FAILURE"
    if exit_code not in (None, 0):
        if "no space" in err or "cannot allocate" in err or "resource" in err:
            return "RESOURCE_ERROR"
        if "encoder" in err or "codec" in err or "invalid argument" in err:
            return "ENCODING_ERROR"
        return "ENCODING_ERROR"
    if issues:
        return "DETERMINISTIC_INPUT_ERROR"
    return "UNKNOWN"


def should_retry_render(classification: str, *, attempt: int, max_attempts: int = MAX_RENDER_INTEGRITY_RETRIES) -> bool:
    if attempt >= max_attempts:
        return False
    if classification in ("DETERMINISTIC_INPUT_ERROR", "FILTERGRAPH_ERROR"):
        return False  # repair contract first — never re-render same invalid config
    if classification == "OUTPUT_VALIDATION_FAILURE":
        return attempt < max_attempts  # may retry once if transient mux glitch
    if classification == "TRANSIENT":
        return True
    if classification == "RESOURCE_ERROR":
        return attempt < 2
    if classification == "UNKNOWN":
        return False  # do not burn retries on UNKNOWN
    return False
