"""
AutoMovie Pro - In-App Helping Agent & Interactive "i" Button System
Provides interactive contextual guidance, automated intent execution,
and tooltip explanations for non-technical users in plain Bengali & English.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger("InAppHelper")
logger.setLevel(logging.INFO)

TOOLTIP_KNOWLEDGE_BASE = {
    "api_fallback": {
        "title_bn": "স্বয়ংক্রিয় ব্যাকআপ এপিআই",
        "desc_bn": "একটি এপিআই কি শেষ বা কোটা পার হলে সিস্টেম নিজে থেকেই ব্যাকআপ কি ব্যবহার করবে, যাতে ভিডিও তৈরি বন্ধ না হয়।",
        "title_en": "Automatic API Failover",
        "desc_en": "If your primary API key runs out of quota, backup keys take over seamlessly."
    },
    "intel_qsv": {
        "title_bn": "ইন্টেল কিউএসভি হার্ডওয়্যার ত্বরণ",
        "desc_bn": "এটি আপনার কম্পিউটারের প্রসেসর ব্যবহার করে স্বাভাবিকের চেয়ে ৫ গুণ দ্রুত ভিডিও রেন্ডার করে।",
        "title_en": "Intel QSV Hardware Acceleration",
        "desc_en": "Renders videos up to 5x faster using Intel hardware acceleration."
    },
    "islamic_greeting": {
        "title_bn": "ইসলামিক শিষ্টাচার",
        "desc_bn": "ভিডিওর শুরুতে সালাম এবং শেষে দোয়ামূলক সমাপ্তি স্বয়ংক্রিয়ভাবে স্ক্রিপ্টে যুক্ত হবে।",
        "title_en": "Islamic Greetings & Closings",
        "desc_en": "Automatically embeds authentic greetings at start and blessings at finish."
    },
    "sub_daily_limit": {
        "title_bn": "দৈনিক সাবস্ক্রাইব সীমা (সর্বোচ্চ ৩টি)",
        "desc_bn": "অ্যাকাউন্টের সুরক্ষা এবং বট প্রতিরোধ নিশ্চিত করতে দিনে সর্বোচ্চ ৩টি চ্যানেল সাবস্ক্রাইব করা হবে।",
        "title_en": "Daily Subscription Cap (Max 3)",
        "desc_en": "Caps daily follows at 3 to safeguard accounts from bot detection."
    }
}


class InAppHelperAgent:
    """
    Intelligent in-app conversational assistant for non-technical SaaS customers.
    """

    def get_tooltip_info(self, field_key: str, language: str = "bn") -> Dict[str, Any]:
        info = TOOLTIP_KNOWLEDGE_BASE.get(field_key, {
            "title_bn": "সহায়তা",
            "desc_bn": "এই অপশনটি স্বয়ংক্রিয়ভাবে ভিডিও তৈরিতে সাহায্য করে।",
            "title_en": "Help",
            "desc_en": "This setting assists in video production."
        })

        if language == "bn":
            return {
                "field": field_key,
                "title": info.get("title_bn"),
                "description": info.get("desc_bn")
            }
        else:
            return {
                "field": field_key,
                "title": info.get("title_en"),
                "description": info.get("desc_en")
            }

    def _query_history_db(self, date_str: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        """Queries local SQLite database for historical video production and uploads."""
        try:
            from app import db as store
            store.init_db()
            with store.db() as conn:
                if date_str:
                    # Match date pattern YYYY-MM-DD or partial
                    cur = conn.execute(
                        """
                        SELECT id, title, video_type, platform, upload_status, error, created_at, uploaded_at, remote_url
                        FROM jobs
                        WHERE created_at LIKE ? OR uploaded_at LIKE ?
                        ORDER BY id DESC LIMIT ?
                        """,
                        (f"%{date_str}%", f"%{date_str}%", limit)
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id, title, video_type, platform, upload_status, error, created_at, uploaded_at, remote_url
                        FROM jobs
                        ORDER BY id DESC LIMIT ?
                        """,
                        (limit,)
                    )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.debug("Database query in inapp_helper skipped: %s", exc)
            return []

    def _query_pending_job(self) -> Optional[Dict[str, Any]]:
        """Queries any currently pending, rendering, or errored jobs."""
        try:
            from app import db as store
            store.init_db()
            with store.db() as conn:
                cur = conn.execute(
                    """
                    SELECT id, title, video_type, platform, upload_status, error, created_at
                    FROM jobs
                    WHERE upload_status NOT IN ('done', 'uploaded', 'success')
                    ORDER BY id DESC LIMIT 1
                    """
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.debug("Database pending query skipped: %s", exc)
            return None

    def handle_user_query(
        self,
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
        language: str = "bn"
    ) -> Dict[str, Any]:
        """
        Interprets natural language questions and returns direct helpful answers
        grounded in actual local SQLite jobs data, with UI action shortcuts.
        """
        q_lower = query.lower()
        context = user_context or {}

        # Intent: Why is my video pending or slow
        if any(w in q_lower for w in ["pending", "slow", "delay", "দেরি", "পেন্ডিং", "থেমে", "আটকে"]):
            pending_job = self._query_pending_job()
            if pending_job:
                p_title = pending_job.get("title") or "চলমান ভিডিও"
                p_status = pending_job.get("upload_status") or "প্রসেসিং"
                p_err = pending_job.get("error")
                if p_err and language == "bn":
                    reply = f"আপনার '{p_title}' ভিডিওটিতে একটি সাময়িক সমস্যা হয়েছে: '{p_err}'। আপনি ড্যাশবোর্ড থেকে 'পুনরায় চেষ্টা করুন' বাটনে ক্লিক করতে পারেন।"
                elif p_err:
                    reply = f"Your video '{p_title}' encountered a temporary issue: '{p_err}'. You can retry from the dashboard."
                elif language == "bn":
                    reply = f"আপনার '{p_title}' ভিডিওটি বর্তমানে প্রসেসিং হচ্ছে (স্ট্যাটাস: {p_status})। সিস্টেম স্বয়ংক্রিয়ভাবে এটি সম্পূর্ণ করে আপলোড করবে।"
                else:
                    reply = f"Your video '{p_title}' is currently in progress (status: {p_status}). It will upload automatically."
            else:
                if language == "bn":
                    reply = "বর্তমানে কোনো ভিডিও কিউতে আটকে নেই। আপনার সিস্টেম স্বাভাবিক ও সক্রিয় রয়েছে।"
                else:
                    reply = "No pending jobs found in queue. Your pipeline is idle and healthy."

            return {
                "intent": "explain_status",
                "reply": reply,
                "action": "check_status",
                "pending_job": pending_job
            }

        # Intent: Check uploaded videos / history query (including specific date search)
        if any(w in q_lower for w in ["uploaded", "video list", "ভিডিও", "আপলোড", "তারিখ", "হিস্ট্রি"]):
            # Check if user mentioned a specific date, e.g. "৫ তারিখ" or "5" or "গত মাস"
            date_filter = ""
            import re
            m = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', query)
            if m:
                date_filter = m.group(1).replace('/', '-')
            
            jobs = self._query_history_db(date_str=date_filter, limit=5)
            if jobs:
                if language == "bn":
                    items_txt = []
                    for i, j in enumerate(jobs, 1):
                        title = j.get("title") or "শিরোনামহীন ভিডিও"
                        plat = j.get("platform") or "সোশ্যাল মিডিয়া"
                        stat = "আপলোড সম্পন্ন" if j.get("upload_status") in ("done", "uploaded", "success") else "প্রসেসিং"
                        items_txt.append(f"{i}. '{title}' ({plat} — {stat})")
                    reply = "আপনার ডাটাবেস থেকে প্রাপ্ত ভিডিও তালিকা:\n" + "\n".join(items_txt)
                else:
                    items_txt = [f"{i}. '{j.get('title')}' ({j.get('platform')} - {j.get('upload_status')})" for i, j in enumerate(jobs, 1)]
                    reply = "Records found in your database:\n" + "\n".join(items_txt)
            else:
                if language == "bn":
                    reply = "এই মুহূর্তে কোনো পূর্ববর্তী আপলোড হিস্ট্রি পাওয়া যায়নি অথবা নির্দিষ্ট তারিখের কোনো ভিডিও নেই। বিস্তারিত দেখতে আপলোড হিস্ট্রি স্ক্রিন খুলুন।"
                else:
                    reply = "No specific upload records found for this query. You can check the complete Upload History screen."

            return {
                "intent": "view_upload_history",
                "reply": reply,
                "action": "open_screen",
                "target_screen": "upload_history",
                "records_count": len(jobs)
            }

        # Intent: How to setup API
        if any(w in q_lower for w in ["api", "key", "কী", "এপিআই"]):
            if language == "bn":
                reply = "এপিআই সেটিংসে গিয়ে বিনামূল্যে Google AI Studio এবং Grok থেকে কী কপি করে পেস্ট করুন। ব্যাকআপ কি যুক্ত রাখলে কখনোই কাজ আটকাবে না।"
            else:
                reply = "Navigate to API Hub settings to paste your free Google AI and Grok keys."
            return {
                "intent": "api_help",
                "reply": reply,
                "action": "open_screen",
                "target_screen": "api_hub"
            }

        # General fallback
        if language == "bn":
            reply = "আমি আপনার অটোমুভি প্রো সহায়ক। ভিডিও তৈরি, শিডিউল বা এপিআই সেটিংস সম্পর্কিত যেকোনো প্রশ্ন করতে পারেন।"
        else:
            reply = "I am your AutoMovie Pro Assistant. Ask me anything about video creation, scheduling, or setup."

        return {
            "intent": "general_faq",
            "reply": reply,
            "action": "none"
        }

