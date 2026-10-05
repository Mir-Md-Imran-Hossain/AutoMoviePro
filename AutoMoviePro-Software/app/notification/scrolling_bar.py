"""
AutoMovie Pro - Live Scrolling Notification Bar Engine
Manages marquee announcements, multi-language auto-localization,
and real-time alerts synchronized from the SaaS Admin Panel.
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("ScrollingNotification")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NOTIFICATIONS_FILE = DATA_DIR / "announcements.json"


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTIFICATIONS_FILE.exists():
        default_notices = [
            {
                "id": "notice_welcome_01",
                "title_en": "Welcome to AutoMovie Pro! All systems operational.",
                "title_bn": "অটোমুভি প্রো-তে স্বাগতম! সকল সিস্টেম সচল রয়েছে।",
                "title_hi": "ऑटोमूवी प्रो में आपका स्वागत है! सभी सिस्टम सक्रिय हैं।",
                "type": "info",
                "priority": "normal",
                "is_active": True,
                "timestamp": time.time()
            }
        ]
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_notices, f, indent=2, ensure_ascii=False)


class ScrollingNotificationManager:
    """
    Manages live tickers, translations, and marquee display settings.
    """

    SPEED_MAP = {
        "slow": 25,
        "normal": 50,
        "fast": 80
    }

    def __init__(self):
        _ensure_storage()

    def get_announcements(self, language: str = "bn") -> List[Dict[str, Any]]:
        try:
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []

        active_items = []
        for it in items:
            if it.get("is_active", True):
                # Localize title based on language requested
                lang_key = f"title_{language}"
                display_text = it.get(lang_key) or it.get("title_en") or it.get("title_bn") or ""
                active_items.append({
                    "id": it.get("id"),
                    "text": display_text,
                    "type": it.get("type", "info"),
                    "priority": it.get("priority", "normal"),
                    "timestamp": it.get("timestamp")
                })
        return active_items

    def add_announcement(
        self,
        title_en: str,
        title_bn: str,
        title_hi: Optional[str] = None,
        notice_type: str = "info",
        priority: str = "normal"
    ) -> Dict[str, Any]:
        notice_id = f"notice_{int(time.time()*1000)}"
        entry = {
            "id": notice_id,
            "title_en": title_en,
            "title_bn": title_bn,
            "title_hi": title_hi or title_en,
            "type": notice_type,
            "priority": priority,
            "is_active": True,
            "timestamp": time.time()
        }

        try:
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []

        items.insert(0, entry)
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

        return {"ok": True, "notice": entry}

    def get_marquee_settings(self, speed_mode: str = "normal") -> Dict[str, Any]:
        pixels_per_sec = self.SPEED_MAP.get(speed_mode, 50)
        return {
            "scroll_speed_px_sec": pixels_per_sec,
            "pause_on_hover": True,
            "theme": {
                "info": "#3B82F6",
                "warning": "#F59E0B",
                "urgent": "#EF4444"
            }
        }
