"""
YouTube Data API upload path (Mode A).
Requires channel youtube_access_token (OAuth) — falls through to browser if missing/fails.
Applies title, description, tags, thumbnail, and not-for-kids.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from publishers.upload_meta import normalize_job_meta, parse_tags

logger = logging.getLogger(__name__)


def _token(channel: Dict[str, Any]) -> str:
    return (
        channel.get("youtube_access_token")
        or channel.get("youtube_oauth_token")
        or channel.get("youtube_api_token")
        or ""
    ).strip()


def upload_youtube_api(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    token = _token(channel)
    if not token:
        raise RuntimeError("youtube_access_token_missing")

    try:
        import google.oauth2.credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(f"google_api_client_not_installed: {exc}") from exc

    meta = normalize_job_meta(job)
    tags: List[str] = list(meta.get("tags") or parse_tags(job.get("tags")))
    creds = google.oauth2.credentials.Credentials(token=token)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": tags[:30],
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(path), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            logger.info("YT API upload progress %.0f%%", status.progress() * 100)
    vid = (response or {}).get("id") or ""
    if not vid:
        raise RuntimeError("youtube_api_no_video_id")

    thumb = meta.get("thumbnail")
    if thumb and Path(thumb).is_file():
        try:
            youtube.thumbnails().set(
                videoId=vid,
                media_body=MediaFileUpload(str(thumb)),
            ).execute()
            logger.info("YouTube thumbnail set for %s", vid)
        except Exception as exc:
            logger.warning("YouTube thumbnail upload skipped: %s", exc)

    return f"https://www.youtube.com/watch?v={vid}"
