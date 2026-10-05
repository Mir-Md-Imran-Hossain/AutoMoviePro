"""
AutoMovie Pro - Terms & Conditions and Legal Disclaimer Consent Engine
Enforces mandatory initial acceptance of software terms, platform compliance,
ethical standards, and background browsing disclaimers before dashboard access.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("ConsentManager")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONSENTS_FILE = DATA_DIR / "legal_consents.json"

CURRENT_LEGAL_VERSION = "2026.1"

TERMS_CONTENT = {
    "bn": {
        "version": CURRENT_LEGAL_VERSION,
        "title": "অটোমুভি প্রো নিয়মাবলী, সম্মতি ও আইনি অস্বীকৃতি (Disclaimer)",
        "sections": [
            {
                "heading": "১. সাধারণ ব্যবহারের শর্তাবলী",
                "body": "এই সফটওয়্যারটি একটি স্বয়ংক্রিয় কন্টেন্ট জেনারেশন টুল। তৈরিকৃত যেকোনো কন্টেন্টের সত্যতা ও প্রচারের আইনি দায়িত্ব ব্যবহারকারীর।"
            },
            {
                "heading": "২. কপিরাইট ও সোশ্যাল মিডিয়া প্ল্যাটফর্ম পলিসি",
                "body": "ইউটিউব, ফেসবুক ও টিকটকের কমিউনিটি গাইডলাইন মেনে ভিডিও তৈরি করতে হবে। কপিরাইটযুক্ত কোনো অবৈধ ম্যাটেরিয়াল বা নিষিদ্ধ উপাদান প্রচার করা যাবে না।"
            },
            {
                "heading": "৩. ইসলামিক ও নৈতিক মূল্যবোধ",
                "body": "কোনো অশ্লীল, সহিংস, ইসলামবিরোধী বা ধর্মীয় অনুভূতিতে আঘাত হানার মতো কন্টেন্ট তৈরি সম্পূর্ণরূপে নিষিদ্ধ।"
            },
            {
                "heading": "৪. ব্যাকগ্রাউন্ড ব্রাউজিং ডিসক্লেইমার",
                "body": "অ্যাকাউন্ট ওয়ার্মিংয়ের সুবিধার্থে সফটওয়্যারের ব্যাকগ্রাউন্ড ব্রাউজিং ফিচারটি ব্যবহারকারীর সম্মতিক্রমে অত্যন্ত নিরাপদ মাত্রায় পরিচালিত হয়।"
            }
        ]
    },
    "en": {
        "version": CURRENT_LEGAL_VERSION,
        "title": "AutoMovie Pro Terms, Conditions & Legal Disclaimer",
        "sections": [
            {
                "heading": "1. Usage License",
                "body": "This software is an automated content production tool. Users bear sole responsibility for the publication of generated media."
            },
            {
                "heading": "2. Platform Compliance",
                "body": "Users must adhere to YouTube, Meta, and TikTok community standards. Dissemination of infringing or prohibited material is disallowed."
            },
            {
                "heading": "3. Ethical & Content Standards",
                "body": "Obscene, violent, or defamatory content generation is strictly prohibited."
            },
            {
                "heading": "4. Background Browsing Disclaimer",
                "body": "Account warming background sessions operate organically under strict safety limits with user consent."
            }
        ]
    }
}


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONSENTS_FILE.exists():
        with open(CONSENTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


class ConsentManager:
    """
    Guarantees that no customer operates the software without signing
    the mandatory legal compliance agreement.
    """

    def __init__(self):
        _ensure_storage()

    def get_terms(self, language: str = "bn") -> Dict[str, Any]:
        return TERMS_CONTENT.get(language, TERMS_CONTENT["bn"])

    def has_consented(self, user_id: str, hardware_id: Optional[str] = None) -> bool:
        try:
            with open(CONSENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            user_entry = data.get(user_id)
            if not user_entry:
                return False

            matches_version = user_entry.get("version") == CURRENT_LEGAL_VERSION
            if not matches_version:
                return False

            # If hardware_id is explicitly provided, it must match
            if hardware_id is not None:
                return user_entry.get("hardware_id") == hardware_id

            # If hardware_id was omitted, check against current system fingerprint
            try:
                from app.auth.hardware_id import get_hardware_fingerprint
                current_hw = get_hardware_fingerprint()
                return user_entry.get("hardware_id") in (current_hw, "AMP-HW-DEFAULT")
            except Exception:
                return True
        except Exception:
            return False

    def has_user_consented(self, user_id: str, hardware_id: Optional[str] = None) -> bool:
        """Dashboard access gate: strictly checks if user has signed legal disclaimer."""
        if not user_id:
            return False
        return self.has_consented(user_id, hardware_id)

    def record_consent(
        self,
        user_id: str,
        hardware_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        if not hardware_id:
            try:
                from app.auth.hardware_id import get_hardware_fingerprint
                hardware_id = get_hardware_fingerprint()
            except Exception:
                hardware_id = "AMP-HW-DEFAULT"

        entry = {
            "user_id": user_id,
            "hardware_id": hardware_id,
            "ip_address": ip_address or "127.0.0.1",
            "version": CURRENT_LEGAL_VERSION,
            "accepted_at": time.time()
        }

        try:
            with open(CONSENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        data[user_id] = entry
        with open(CONSENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return {
            "ok": True,
            "message": "সম্মতি সফলভাবে সংরক্ষিত হয়েছে। ড্যাশবোর্ড ব্যবহারের অনুমতি প্রদান করা হলো।"
        }
