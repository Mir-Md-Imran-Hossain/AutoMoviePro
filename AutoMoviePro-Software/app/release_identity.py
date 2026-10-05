"""Canonical application release identity (H5) — single authority."""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# ONE source of truth for product release versioning.
APP_NAME = "AutoMovie Pro"
RELEASE_VERSION = "0.5.0"
# Static build tag for source releases; CI may override via AMP_BUILD_ID.
DEFAULT_BUILD_ID = "h5-source"


def get_release_identity(
    *,
    build_id: Optional[str] = None,
    include_media: bool = True,
) -> dict[str, Any]:
    """Return safe, non-secret release identity for runtime/manifest/diagnostics."""
    import os

    bid = (build_id or os.environ.get("AMP_BUILD_ID") or DEFAULT_BUILD_ID).strip()
    built = (os.environ.get("AMP_BUILD_TIMESTAMP") or "").strip()
    if not built:
        built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out: dict[str, Any] = {
        "app_name": APP_NAME,
        "release_version": RELEASE_VERSION,
        "build_id": bid,
        "build_timestamp": built,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "os_name": os.name,
        "supported_deployment": "windows_local_source_venv",
        "checkpoint": "AMP004-H5-RELEASE-OPERATIONAL-READINESS",
    }
    if include_media:
        try:
            from pipeline.compose import probe_media_tool_capability, media_tool_versions

            cap = probe_media_tool_capability()
            vers = media_tool_versions()
            out["ffmpeg_available"] = bool(cap.get("FFMPEG_AVAILABLE"))
            out["ffprobe_available"] = bool(cap.get("FFPROBE_AVAILABLE"))
            out["ffmpeg_source"] = cap.get("ffmpeg_source")
            out["ffprobe_source"] = cap.get("ffprobe_source")
            out["ffmpeg_version"] = vers.get("ffmpeg_version") or "UNKNOWN"
            out["ffprobe_version"] = vers.get("ffprobe_version") or "UNKNOWN"
        except Exception as exc:
            out["ffmpeg_available"] = False
            out["ffprobe_available"] = False
            out["media_probe_error"] = type(exc).__name__
    return out
