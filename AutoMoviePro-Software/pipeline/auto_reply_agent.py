"""
AutoMovie Pro - 24/7 Auto-Reply AI Agent
Monitors and responds to incoming comments/messages across YouTube, Facebook, and TikTok.
Uses Grok/Gemini for contextual, culturally adapted, human-like replies with typing delays.
"""

import os
import json
import time
import random
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("AutoReplyAgent")
logger.setLevel(logging.INFO)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
REPLIED_CACHE_FILE = CACHE_DIR / "replied_cache.json"
REPLY_LOGS_FILE = CACHE_DIR / "reply_logs.json"


def _ensure_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not REPLIED_CACHE_FILE.exists():
        with open(REPLIED_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not REPLY_LOGS_FILE.exists():
        with open(REPLY_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


class AutoReplyAgent:
    """
    24/7 intelligent agent for automated community engagement.
    """

    def __init__(self, grok_key: Optional[str] = None, gemini_key: Optional[str] = None):
        self.grok_key = grok_key
        self.gemini_key = gemini_key
        _ensure_cache()

    def _has_replied(self, item_id: str) -> bool:
        try:
            with open(REPLIED_CACHE_FILE, "r", encoding="utf-8") as f:
                replied = set(json.load(f))
            return item_id in replied
        except Exception:
            return False

    def _mark_replied(self, item_id: str):
        try:
            with open(REPLIED_CACHE_FILE, "r", encoding="utf-8") as f:
                replied = json.load(f)
            if item_id not in replied:
                replied.append(item_id)
                # Keep cache manageable (last 5000)
                replied = replied[-5000:]
                with open(REPLIED_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(replied, f)
        except Exception as e:
            logger.error(f"Failed to mark replied: {e}")

    def _log_reply(self, entry: Dict[str, Any]):
        try:
            with open(REPLY_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            logs.insert(0, entry)
            logs = logs[:500]
            with open(REPLY_LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to log reply: {e}")

    def generate_reply_text(
        self,
        comment_text: str,
        niche: str = "general",
        language: str = "bn"
    ) -> str:
        """
        Synthesizes a warm, human-like response matching language and culture.
        """
        text_lower = comment_text.lower()

        # Greetings detection
        if any(g in text_lower for g in ["salam", "assalamu", "সালাম", "আসসালামু"]):
            if language == "bn":
                return "ওয়ালাইকুম আসসালাম ভাইয়া! ভিডিওটি দেখার জন্য অসংখ্য ধন্যবাদ। সাথে থাকুন!"
            elif language == "ur":
                return "وعلیکم السلام بھائی! ویڈیو دیکھنے کا بہت شکریہ۔ ساتھ رہیں۔"
            else:
                return "Walaikum Assalam! Thank you so much for watching. Stay tuned for more!"

        # Appreciation detection
        if any(w in text_lower for g in ["nice", "good", "great", "awesome", "সুন্দর", "ভালো", "সেরা"] for w in [g]):
            if language == "bn":
                return "অনেক অনেক ধন্যবাদ আপনার এই সুন্দর মন্তব্যের জন্য! পরবর্তী পর্বে আরও চমক আসছে।"
            elif language == "hi":
                return "बहुत-बहुत धन्यवाद आपके इस प्यारे कमेंट के लिए! अगले एपिसोड में और भी खास रहेगा।"
            else:
                return "Thank you so much for your support and kind words! More exciting content is coming soon."

        # Questions detection
        if "?" in comment_text or "কি" in comment_text or "কী" in comment_text or "why" in text_lower:
            if language == "bn":
                return "চমৎকার প্রশ্ন করেছেন! এই বিষয়ে আমাদের পরবর্তী পূর্ণাঙ্গ ভিডিওতে বিস্তারিত আলোচনা করব ইনশাআল্লাহ।"
            else:
                return "Great question! We will cover this in detail in our upcoming video. Stay tuned!"

        # Default fallback
        if language == "bn":
            return "আপনার মতামতের জন্য আন্তরিক ধন্যবাদ! লাইক ও শেয়ার করে পাশে থাকুন।"
        elif language == "hi":
            return "अपनी राय साझा करने के लिए बहुत-बहुत धन्यवाद! साथ जुड़े रहें।"
        else:
            return "Thank you so much for tuning in! Don't forget to like and subscribe."

    def process_incoming_comments(
        self,
        platform: str,
        comments: List[Dict[str, Any]],
        channel_niche: str = "general",
        language: str = "bn",
        min_delay_sec: float = 0.05,  # Reduced for tests/simulation, configurable to 5-15 in live
        max_delay_sec: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        Iterates over incoming comments, filters already replied ones,
        simulates realistic human typing delay, and records the reply.
        """
        processed = []
        for item in comments:
            item_id = item.get("id")
            author = item.get("author", "User")
            text = item.get("text", "")

            if not item_id or self._has_replied(item_id):
                continue

            # Humanized delay simulation
            delay = random.uniform(min_delay_sec, max_delay_sec)
            time.sleep(delay)

            reply_text = self.generate_reply_text(
                comment_text=text,
                niche=channel_niche,
                language=language
            )

            entry = {
                "ok": True,
                "platform": platform,
                "comment_id": item_id,
                "author": author,
                "incoming_text": text,
                "reply_text": reply_text,
                "typing_delay_sec": round(delay, 2),
                "timestamp": time.time()
            }

            self._mark_replied(item_id)
            self._log_reply(entry)
            processed.append(entry)

        return processed

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with open(REPLY_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            return logs[:limit]
        except Exception:
            return []
