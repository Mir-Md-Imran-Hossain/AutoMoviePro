"""
Facebook Graph API video upload path (Mode A).
Requires facebook_page_token + facebook_page_id on channel.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def upload_facebook_api(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    token = (
        channel.get("facebook_page_token")
        or channel.get("facebook_access_token")
        or channel.get("meta_access_token")
        or ""
    ).strip()
    page_id = str(channel.get("facebook_page_id") or channel.get("facebook_page") or "").strip()
    if not token:
        raise RuntimeError("facebook_access_token_missing")
    if not page_id:
        # Some tokens are page tokens; page_id may be embedded — require explicit for safety
        raise RuntimeError("facebook_page_id_missing")

    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(f"requests_missing: {exc}") from exc

    caption = f"{job.get('title') or ''}\n\n{job.get('description') or ''}".strip()[:2000]
    url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
    with path.open("rb") as fh:
        resp = requests.post(
            url,
            data={"description": caption, "access_token": token},
            files={"source": (path.name, fh, "video/mp4")},
            timeout=600,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"facebook_graph_error: {resp.status_code} {resp.text[:300]}")
    data = resp.json() if resp.content else {}
    vid = data.get("id") or ""
    if not vid:
        raise RuntimeError("facebook_api_no_id")
    return f"https://www.facebook.com/{page_id}/videos/{vid}"
