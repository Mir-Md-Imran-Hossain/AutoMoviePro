"""
Task router — thin façade over hybrid_mode for upload/engage call sites.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from pipeline.hybrid_mode import route_task

logger = logging.getLogger(__name__)


def upload_youtube_routed(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> Dict[str, Any]:
    decision = route_task("upload_youtube", channel=channel, platform="youtube")
    logger.info("YT upload route: %s", decision)
    if decision["transport"] == "skip":
        return {"ok": False, "platform": "youtube", "error": decision["reason"], "route": decision}
    if decision["transport"] == "api":
        try:
            from publishers.youtube_api_uploader import upload_youtube_api

            url = upload_youtube_api(path, job, channel)
            return {"ok": True, "platform": "youtube", "url": url, "route": decision}
        except Exception as exc:
            logger.warning("YouTube API upload failed, falling back to browser: %s", exc)
            if decision.get("mode") == "api":
                return {"ok": False, "platform": "youtube", "error": str(exc), "route": decision}
            # hybrid → browser
    from publishers.youtube_uploader import upload_youtube

    url = upload_youtube(path, job, channel)
    return {"ok": True, "platform": "youtube", "url": url, "route": {**decision, "transport": "browser"}}


def upload_facebook_routed(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> Dict[str, Any]:
    decision = route_task("upload_facebook", channel=channel, platform="facebook")
    logger.info("FB upload route: %s", decision)
    if decision["transport"] == "skip":
        return {"ok": False, "platform": "facebook", "error": decision["reason"], "route": decision}
    if decision["transport"] == "api":
        try:
            from publishers.facebook_api_uploader import upload_facebook_api

            url = upload_facebook_api(path, job, channel)
            return {"ok": True, "platform": "facebook", "url": url, "route": decision}
        except Exception as exc:
            logger.warning("Facebook API upload failed, falling back to browser: %s", exc)
            if decision.get("mode") == "api":
                return {"ok": False, "platform": "facebook", "error": str(exc), "route": decision}
    from publishers.facebook_uploader import upload_facebook

    url = upload_facebook(path, job, channel)
    return {"ok": True, "platform": "facebook", "url": url, "route": {**decision, "transport": "browser"}}
