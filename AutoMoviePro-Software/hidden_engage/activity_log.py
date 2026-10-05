"""
Local trust-browse activity log + website sync for admin visibility.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app import db as store

logger = logging.getLogger(__name__)


def log_action(
    *,
    platform: str,
    action: str,
    url: str = "",
    title: str = "",
    detail: str = "",
    ok: bool = True,
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    return store.add_engage_activity(
        platform=platform,
        action=action,
        url=url,
        title=title,
        detail=detail,
        ok=ok,
        meta=meta,
        day=date.today().isoformat(),
    )


def list_today(limit: int = 200) -> List[Dict[str, Any]]:
    return store.list_engage_activity(day=date.today().isoformat(), limit=limit)


def sync_unsynced_to_website(*, limit: int = 80) -> Dict[str, Any]:
    session = store.get_session()
    if not session:
        return {"ok": False, "error": "not_logged_in"}
    rows = store.list_engage_activity_unsynced(limit=limit)
    if not rows:
        return {"ok": True, "synced": 0}
    try:
        from app.api_client import LicenseClient

        client = LicenseClient(session["api_base_url"], session["token"])
        payload = {
            "day": date.today().isoformat(),
            "events": [
                {
                    "local_id": r["id"],
                    "platform": r.get("platform"),
                    "action": r.get("action"),
                    "url": r.get("url"),
                    "title": r.get("title"),
                    "detail": r.get("detail"),
                    "ok": bool(r.get("ok", 1)),
                    "meta": r.get("meta_json"),
                    "created_at": r.get("created_at"),
                }
                for r in rows
            ],
        }
        res = client.sync_engage_log(payload)
        if res.get("ok"):
            ids = [int(r["id"]) for r in rows]
            store.mark_engage_activity_synced(ids)
            return {"ok": True, "synced": len(ids)}
        return {"ok": False, "error": res.get("error") or "sync_failed", "raw": res}
    except Exception as exc:
        logger.warning("engage log sync failed: %s", exc)
        return {"ok": False, "error": str(exc)}
