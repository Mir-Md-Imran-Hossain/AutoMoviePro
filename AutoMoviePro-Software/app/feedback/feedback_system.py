"""
AutoMovie Pro - In-App Feedback, Bug Report & Customer Review Engine
Handles user tickets, urgent bug SLAs, token generation, and satisfaction reviews.
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("FeedbackSystem")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FEEDBACK_FILE = DATA_DIR / "feedback_tickets.json"
REVIEWS_FILE = DATA_DIR / "customer_reviews.json"


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not REVIEWS_FILE.exists():
        with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


class FeedbackSystem:
    """
    Manages user reports with SLA tracking, bug categorization, and rating collection.
    """

    def __init__(self):
        _ensure_storage()

    def submit_ticket(
        self,
        user_id: str,
        category: str,  # 'urgent_bug' or 'suggestion'
        title: str,
        description: str,
        attachment_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new support ticket with a unique token and SLA.
        """
        token = f"TK-{uuid.uuid4().hex[:6].upper()}"
        is_urgent = category == "urgent_bug"
        sla_hours = 72 if is_urgent else 168

        ticket = {
            "token": token,
            "user_id": user_id,
            "category": category,
            "title": title,
            "description": description,
            "attachment_path": attachment_path,
            "status": "open",
            "sla_hours": sla_hours,
            "created_at": time.time(),
            "target_resolution_time": time.time() + (sla_hours * 3600)
        }

        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                tickets = json.load(f)
            tickets.insert(0, ticket)
            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(tickets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save ticket: {e}")

        return {
            "ok": True,
            "token": token,
            "sla_hours": sla_hours,
            "message": f"টিকেট সফলভাবে গৃহীত হয়েছে। আপনার ট্র্যাকিং টোকেন: {token}"
        }

    def check_review_eligibility(self, total_usage_seconds: float) -> bool:
        """
        Checks if the user has completed at least 3 hours (10,800 sec) of usage.
        """
        return total_usage_seconds >= 10800

    def submit_review(
        self,
        user_id: str,
        user_name: str,
        rating: int,  # 1 to 5
        review_text: str
    ) -> Dict[str, Any]:
        """
        Submits customer satisfaction review. High ratings (4-5) can be showcased on the SaaS landing page.
        """
        clamped_rating = max(1, min(5, rating))
        can_showcase = clamped_rating >= 4

        record = {
            "id": f"rev_{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "user_name": user_name,
            "rating": clamped_rating,
            "review_text": review_text,
            "showcase_eligible": can_showcase,
            "created_at": time.time()
        }

        try:
            with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
                reviews = json.load(f)
            reviews.insert(0, record)
            with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
                json.dump(reviews, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to record review: {e}")

        return {
            "ok": True,
            "showcase_eligible": can_showcase,
            "message": "আপনার চমৎকার মতামতের জন্য আন্তরিক ধন্যবাদ!"
        }

    def get_ticket_status(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                tickets = json.load(f)
            for t in tickets:
                if t.get("token") == token:
                    return t
        except Exception:
            pass
        return None
