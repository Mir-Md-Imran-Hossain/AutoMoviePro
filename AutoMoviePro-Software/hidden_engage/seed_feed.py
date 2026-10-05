"""
Seed feed for trust-browse (early phase + growth).

Priority:
  1) Admin promo YouTube channels / Facebook pages (all customers)
  2) Peer customer uploaded videos (when ecosystem has content)
Never engages random public strangers.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, List

from app import db as store
from app.api_client import LicenseClient
from hidden_engage.peer_feed import fetch_peer_videos

logger = logging.getLogger(__name__)


def fetch_admin_promo_links() -> List[Dict[str, Any]]:
    session = store.get_session()
    if not session:
        return []
    try:
        client = LicenseClient(session["api_base_url"], session["token"])
        links = client.promo_links() or []
    except Exception as exc:
        logger.warning("promo_links fetch failed: %s", exc)
        return []

    out: List[Dict[str, Any]] = []
    seen = set()
    for item in links:
        url = (item.get("url") or "").strip()
        platform = (item.get("platform") or "").strip().lower()
        if not url or platform not in ("youtube", "facebook"):
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        kind = _classify_url(platform, url)
        ch_type = str(item.get("channel_type") or item.get("type") or ("A" if item.get("is_favorite") else "A")).upper()
        out.append(
            {
                "id": item.get("id"),
                "platform": platform,
                "url": url,
                "title": (item.get("title") or "")[:200],
                "description": "",
                "kind": kind,  # channel | page | video | unknown
                "source": "admin_promo",
                "channel_type": ch_type if ch_type in ("A", "B") else "A",
            }
        )
    return out


def _classify_url(platform: str, url: str) -> str:
    u = url.lower()
    if platform == "youtube":
        if "/watch" in u or "youtu.be/" in u or "/shorts/" in u:
            return "video"
        if "/@" in u or "/channel/" in u or "/c/" in u or "/user/" in u:
            return "channel"
        return "channel"
    # facebook
    if "/reel/" in u or "/videos/" in u or "/watch" in u:
        return "video"
    return "page"


def build_session_targets(*, max_promo: int = 2, max_peer: int = 2) -> Dict[str, Any]:
    """
    Build a human session plan:
      - 1–2 admin promo channels/pages (prefer incomplete engage_state)
      - 0–2 peer videos when available
      - flag for optional reels scroll
    """
    promo = fetch_admin_promo_links()
    peers = fetch_peer_videos(limit=30)

    # Prefer incomplete promo hubs (not yet subscribed / today's play done)
    ranked = sorted(promo, key=_promo_priority)
    promo_picks = ranked[: max(0, max_promo)]
    if len(promo_picks) < max_promo and promo:
        rest = [p for p in promo if p not in promo_picks]
        random.shuffle(rest)
        promo_picks.extend(rest[: max_promo - len(promo_picks)])

    peer_picks: List[Dict[str, Any]] = []
    if peers:
        yt = [p for p in peers if p.get("platform") == "youtube"]
        fb = [p for p in peers if p.get("platform") == "facebook"]
        pool = []
        if yt:
            pool.append(random.choice(yt))
        if fb:
            pool.append(random.choice(fb))
        leftover = [p for p in peers if p not in pool]
        random.shuffle(leftover)
        pool.extend(leftover)
        peer_picks = pool[:max_peer]

    return {
        "promo": promo_picks,
        "peers": peer_picks,
        "do_reels": random.random() < 0.55,  # human often scrolls reels mid-session
        "promo_total": len(promo),
        "peer_total": len(peers),
    }


def _promo_priority(item: Dict[str, Any]) -> int:
    """Lower = engage sooner. Incomplete subscriptions first."""
    platform = item.get("platform") or ""
    url = item.get("url") or ""
    score = 0
    if store.engage_done(platform, url, "follow"):
        score += 10
    if store.engage_done(platform, url, "latest_comment"):
        score += 5
    if store.engage_done(platform, url, "latest_share"):
        score += 3
    # slight shuffle noise
    score += random.randint(0, 2)
    return score
