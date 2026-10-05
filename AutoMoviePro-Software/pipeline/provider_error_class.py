"""Classify Google provider failures without logging secrets.

Distinct classes: 429 rate/quota, 403 permission/config, 503 transient, other.
Project identity extracted from error metadata when present (consumer projects/N).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pipeline.api_keys import redact_sensitive_text

CLASS_429 = "http_429_quota_or_rate"
CLASS_403 = "http_403_permission_or_config"
CLASS_503 = "http_503_transient"
CLASS_OTHER = "other"


_PROJECT_RE = re.compile(
    r"(?:projects?/|consumer['\":\s]+(?:projects/)?|project[_ ]?(?:number|id)['\":\s]+)(\d{6,})",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(r"\b(429|403|503|401|400|500|502|504)\b")


def extract_http_status(exc_or_msg: Any) -> Optional[int]:
    msg = str(exc_or_msg or "")
    m = _STATUS_RE.search(msg)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    low = msg.lower()
    if "resource_exhausted" in low or "too many requests" in low:
        return 429
    if "permission_denied" in low or "has been suspended" in low:
        return 403
    if "unavailable" in low and "503" in msg:
        return 503
    return None


def extract_project_identity(exc_or_msg: Any) -> Optional[str]:
    """Return opaque project id like projects/123… — never an API key."""
    msg = redact_sensitive_text(str(exc_or_msg or ""))
    m = _PROJECT_RE.search(msg)
    if m:
        return f"projects/{m.group(1)}"
    # ErrorInfo metadata.consumer style already redacted of keys
    m2 = re.search(r"projects/(\d{6,})", msg)
    if m2:
        return f"projects/{m2.group(1)}"
    return None


def classify_provider_failure(exc_or_msg: Any) -> Dict[str, Any]:
    """Structured failure class for Google TTS / critic / semantic paths."""
    raw = str(exc_or_msg or "")
    safe = redact_sensitive_text(raw)
    status = extract_http_status(raw)
    low = safe.lower()
    project = extract_project_identity(raw)

    if status == 429 or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        cls = CLASS_429
        reason = "quota_or_rate_limit"
    elif (
        status == 403
        or "permission_denied" in low
        or "has been suspended" in low
        or "api_key_invalid" in low
        or "project has been denied" in low
    ):
        cls = CLASS_403
        reason = "permission_suspended_or_denied"
    elif status == 503 or ("unavailable" in low and (status == 503 or "503" in safe)):
        cls = CLASS_503
        reason = "service_temporarily_unavailable"
    else:
        cls = CLASS_OTHER
        reason = "non_classified"

    return {
        "class": cls,
        "http_status": status,
        "provider_reason": reason,
        "project_identity": project,
        "safe_message": safe[:240],
    }


def is_403_class(exc_or_msg: Any) -> bool:
    return classify_provider_failure(exc_or_msg)["class"] == CLASS_403


def is_429_class(exc_or_msg: Any) -> bool:
    return classify_provider_failure(exc_or_msg)["class"] == CLASS_429


def is_503_class(exc_or_msg: Any) -> bool:
    return classify_provider_failure(exc_or_msg)["class"] == CLASS_503
