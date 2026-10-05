"""
Peer customer video feed — only AutoMovie Pro customer uploads.
Never targets random public channels.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, List

from app import db as store
from app.api_client import LicenseClient

logger = logging.getLogger(__name__)


def fetch_peer_videos(*, limit: int = 40) -> List[Dict[str, Any]]:
    """
    Prefer website peer feed (other customers' uploaded videos).
    Local fallback: own remote posts only for warmup when peers empty
    (logged as self_pool — still AMP network, not strangers).
    """
    session = store.get_session()
    peers: List[Dict[str, Any]] = []
    if session:
        try:
            client = LicenseClient(session["api_base_url"], session["token"])
            peers = client.peer_videos(limit=limit) or []
        except Exception as exc:
            logger.warning("peer_videos fetch failed: %s", exc)

    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for item in peers:
        url = (item.get("url") or item.get("remote_url") or "").strip()
        platform = (item.get("platform") or "").strip().lower()
        if not url or platform not in ("youtube", "facebook"):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "platform": platform,
                "url": url,
                "title": (item.get("title") or "")[:300],
                "description": (item.get("description") or "")[:800],
                "video_type": item.get("video_type") or "short",
                "channel_name": item.get("channel_name") or "",
                "customer_id": item.get("customer_id"),
                "source": "peer",
            }
        )

    if cleaned:
        random.shuffle(cleaned)
        return cleaned[:limit]

    # Soft fallback: own uploaded posts (still within AMP ecosystem)
    own = _local_own_posts(limit=limit)
    return own


def _local_own_posts(*, limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        posts = store.list_posts(limit=80)
    except Exception:
        return []
    for p in posts:
        url = (p.get("remote_url") or "").strip()
        platform = (p.get("platform") or "").strip().lower()
        if not url or platform not in ("youtube", "facebook"):
            continue
        if "youtube.com" not in url and "youtu.be" not in url and "facebook.com" not in url and "fb.watch" not in url:
            continue
        out.append(
            {
                "platform": platform,
                "url": url,
                "title": (p.get("title") or "")[:300],
                "description": "",
                "video_type": "short",
                "channel_name": "",
                "customer_id": None,
                "source": "self_pool",
            }
        )
    random.shuffle(out)
    return out[:limit]


def pick_targets(peers: List[Dict[str, Any]], *, max_items: int = 4) -> List[Dict[str, Any]]:
    if not peers:
        return []
    yt = [p for p in peers if p["platform"] == "youtube"]
    fb = [p for p in peers if p["platform"] == "facebook"]
    picks: List[Dict[str, Any]] = []
    # Prefer mix
    if yt:
        picks.append(random.choice(yt))
    if fb and len(picks) < max_items:
        picks.append(random.choice(fb))
    rest = [p for p in peers if p not in picks]
    random.shuffle(rest)
    for p in rest:
        if len(picks) >= max_items:
            break
        picks.append(p)
    return picks
