"""C01-A — Truthful application / media / production readiness (observer only).

Does NOT claim publishability. Separates:
  APPLICATION vs MEDIA vs PRODUCTION vs JOB
"""
from __future__ import annotations

from typing import Any, Dict, Optional


APPLICATION_STARTING = "STARTING"
APPLICATION_READY = "READY"
APPLICATION_DEGRADED = "DEGRADED"
APPLICATION_FAILED = "FAILED"

MEDIA_AVAILABLE = "AVAILABLE"
MEDIA_UNAVAILABLE = "UNAVAILABLE"
MEDIA_UNKNOWN = "UNKNOWN"

PRODUCTION_READY = "READY"
PRODUCTION_BLOCKED = "BLOCKED"
PRODUCTION_UNKNOWN = "UNKNOWN"


def media_status_from_capability(cap: Optional[Dict[str, Any]]) -> str:
    if not isinstance(cap, dict):
        return MEDIA_UNKNOWN
    if "FFMPEG_AVAILABLE" not in cap and "ffmpeg_available" not in cap:
        return MEDIA_UNKNOWN
    ffmpeg_ok = bool(cap.get("FFMPEG_AVAILABLE", cap.get("ffmpeg_available")))
    ffprobe_ok = bool(cap.get("FFPROBE_AVAILABLE", cap.get("ffprobe_available")))
    if ffmpeg_ok and ffprobe_ok:
        return MEDIA_AVAILABLE
    return MEDIA_UNAVAILABLE


def build_foundation_snapshot(
    *,
    app_started: bool = True,
    media_cap: Optional[Dict[str, Any]] = None,
    operational: Optional[Dict[str, Any]] = None,
    api_readiness: Optional[Dict[str, Any]] = None,
    active_job: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate truthful readiness planes for the customer UI."""
    media = media_status_from_capability(media_cap)

    ops = operational or {}
    if not ops:
        production = PRODUCTION_UNKNOWN
        production_issues: list[str] = ["operational_report_absent"]
    elif ops.get("status") == "READY" and ops.get("production_ready"):
        production = PRODUCTION_READY
        production_issues = list(ops.get("issues") or [])
    elif ops.get("status") == "BLOCKED" or ops.get("production_ready") is False:
        production = PRODUCTION_BLOCKED
        production_issues = list(ops.get("issues") or [])
    else:
        production = PRODUCTION_UNKNOWN
        production_issues = list(ops.get("issues") or ["operational_status_unclear"])

    api_active = bool((api_readiness or {}).get("active"))
    if not app_started:
        application = APPLICATION_STARTING
    elif production == PRODUCTION_BLOCKED or media == MEDIA_UNAVAILABLE:
        application = APPLICATION_DEGRADED
    else:
        application = APPLICATION_READY

    generate_blocked = False
    generate_block_reasons: list[str] = []
    if media == MEDIA_UNAVAILABLE:
        generate_blocked = True
        generate_block_reasons.append("media_tools_unavailable")
    if media == MEDIA_UNKNOWN:
        generate_blocked = True
        generate_block_reasons.append("media_tools_unknown")
    if production == PRODUCTION_BLOCKED:
        generate_blocked = True
        generate_block_reasons.append("production_prerequisites_blocked")
    if production == PRODUCTION_UNKNOWN:
        generate_blocked = True
        generate_block_reasons.append("production_prerequisites_unknown")
    if api_readiness is not None and not api_active:
        generate_blocked = True
        generate_block_reasons.append("api_readiness_inactive")

    return {
        "application": application,
        "media": media,
        "production": production,
        "production_issues": production_issues,
        "api_active": api_active,
        "generate_allowed": not generate_blocked,
        "generate_block_reasons": generate_block_reasons,
        "active_job": active_job,
        "note": (
            "application READY ≠ production READY ≠ artifact publishability; "
            "UNKNOWN/BLOCKED remain fail-closed for Generate"
        ),
    }
