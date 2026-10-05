"""
AutoMovie Pro - Admin WhatsApp & Telegram Bulk Marketing Engine
Orchestrates multi-account broadcasting, randomized anti-ban delays, lead tracking,
and Grok-powered automated sales objection handling, deal closing, and persuasive copy generation.
"""

import os
import re
import json
import time
import random
import logging
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

logger = logging.getLogger("BulkMarketing")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEADS_FILE = DATA_DIR / "leads_database.json"
CAMPAIGNS_FILE = DATA_DIR / "marketing_campaigns.json"


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LEADS_FILE.exists():
        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    if not CAMPAIGNS_FILE.exists():
        with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def sanitize_contact(contact: str, platform: str = "whatsapp") -> Optional[str]:
    """
    Cleans and validates a single contact for WhatsApp or Telegram.
    - WhatsApp: Extracts digits, normalizes Bangladeshi '01...' to '+8801...',
      validates international E.164 length (10-15 digits).
    - Telegram: Normalizes @username, t.me/links, or phone digits.
    Returns cleaned contact string or None if invalid.
    """
    if not contact or not isinstance(contact, str):
        return None
    raw = contact.strip()
    if not raw:
        return None

    p = platform.lower()
    if p in ("telegram", "tg"):
        # Handle t.me/username link
        m_link = re.search(r"(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{4,32})", raw)
        if m_link:
            return f"@{m_link.group(1)}"
        # Handle @username
        if raw.startswith("@"):
            cleaned = re.sub(r"[^a-zA-Z0-9_]", "", raw[1:])
            if 4 <= len(cleaned) <= 32:
                return f"@{cleaned}"
            return None
        # Handle username without @
        if re.match(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$", raw):
            return f"@{raw}"
        # Fall back to phone number format for Telegram
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10:
            if digits.startswith("01") and len(digits) == 11:
                return f"+880{digits[1:]}"
            return f"+{digits}"
        return None

    # Default: WhatsApp phone sanitization
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    # BD local mobile format (01XXXXXXXXX -> +8801XXXXXXXXX)
    if digits.startswith("01") and len(digits) == 11:
        return f"+880{digits[1:]}"
    # BD format without leading 0 or with 880
    if digits.startswith("8801") and len(digits) == 13:
        return f"+{digits}"
    # Standard international numbers (10 to 15 digits)
    if 10 <= len(digits) <= 15:
        return f"+{digits}"

    return None


def parse_and_clean_contacts(
    raw_input: Union[str, List[str]],
    platform: str = "whatsapp"
) -> Dict[str, Any]:
    """
    Takes bulk contacts (string with newlines/commas/semicolons or list),
    performs sanitization, deduplication, and format validation.
    """
    if isinstance(raw_input, str):
        raw_items = re.split(r"[\r\n,;\t|]+", raw_input)
    elif isinstance(raw_input, (list, tuple)):
        raw_items = list(raw_input)
    else:
        raw_items = [str(raw_input)]

    raw_items = [str(item).strip() for item in raw_items if item is not None and str(item).strip()]
    total_raw = len(raw_items)

    valid_contacts: List[str] = []
    seen = set()
    duplicates = 0
    invalid = 0

    for item in raw_items:
        clean = sanitize_contact(item, platform=platform)
        if not clean:
            invalid += 1
            continue
        lower_clean = clean.lower()
        if lower_clean in seen:
            duplicates += 1
            continue
        seen.add(lower_clean)
        valid_contacts.append(clean)

    return {
        "total_raw": total_raw,
        "valid_contacts": valid_contacts,
        "valid_count": len(valid_contacts),
        "duplicates_count": duplicates,
        "invalid_count": invalid,
    }


def calculate_anti_ban_delay(
    sent_count: int,
    is_live: bool = False,
    min_gap: float = 30.0,
    max_gap: float = 90.0
) -> float:
    """
    Computes an anti-ban randomized time gap between messages.
    - Live mode: 30-90s variable jitter, with extra rest breaks every 8-12 messages.
    - Test/simulation mode: small fast jitter (0.01 - 0.04s) for instant unit testing.
    """
    if not is_live:
        return round(random.uniform(0.01, 0.04), 3)

    base = random.uniform(min_gap, max_gap)
    # Natural human micro-delays
    jitter = random.choice([0.0, 1.5, 3.2, 5.0])
    delay = base + jitter

    # Rest pause every 10 messages to mimic human behavior
    if sent_count > 0 and (sent_count % 10 == 0):
        rest_pause = random.uniform(60.0, 150.0)
        delay += rest_pause

    return round(delay, 2)


def generate_persuasive_marketing_copy(
    niche: str = "faceless_youtube",
    platform: str = "whatsapp",
    discount_pct: int = 20,
    language: str = "bn"
) -> str:
    """
    Grok / LLM powered high-converting sales copy generator for bulk campaigns.
    Generates compelling hooks, key benefits, discount offers, and clear bKash/Nagad CTA.
    """
    prompt = (
        f"You are Grok, an elite high-converting direct-response sales copywriter.\n"
        f"Write an engaging, persuasive marketing message for '{platform}' target audience.\n"
        f"Product: AutoMovie Pro SAAS (Autonomous Faceless Video Creation Software)\n"
        f"Niche: {niche}\n"
        f"Special Discount: {discount_pct}% OFF today!\n"
        f"Language: {language} (if 'bn', write in friendly, respectful natural Bengali/Banglish; if 'en', clear English).\n"
        f"Include:\n"
        f"1. Compelling hook highlighting passive income and zero video editing effort.\n"
        f"2. Core features: 4-6 automated daily videos, auto voiceover, YouTube/FB/TikTok scheduler.\n"
        f"3. Urgency & {discount_pct}% limited-time promo code 'PRO{discount_pct}'.\n"
        f"4. Clear call-to-action to reply or check payment via bKash/Nagad agent.\n"
        f"Format with clean emojis, bullet points, and NO placeholders.\n"
    )

    try:
        from pipeline.llm_router import chat_text
        res = chat_text(prompt, purpose="agent", json_mode=False)
        text = (res.get("text") or "").strip()
        if len(text) >= 60:
            return text
    except Exception as exc:
        logger.debug("LLM copywriting fallback triggered: %s", exc)

    # High-converting local fallback templates
    if language == "bn":
        return (
            f"🎬 *ভিডিও এডিটিং ছাড়া ইউটিউব ও ফেসবুক থেকে প্যাসিভ ইনকাম করতে চান?*\n\n"
            f"অটোমুভি প্রো (AutoMovie Pro) নিয়ে এসেছে ১০০% স্বয়ংক্রিয় এআই ভিডিও ক্রিয়েশন ইঞ্জিন! 🚀\n\n"
            f"✨ *বিশেষ ফিচারসমূহ:*\n"
            f"• প্রতিদিন ৪-৬টি হাই-কোয়ালিটি সিনেমাটিক শর্টস ও লং ভিডিও অটোমেটিক তৈরি\n"
            f"• হিউম্যান-লাইক স্ক্রিপ্ট ও ন্যাচারাল ভয়েসওভার\n"
            f"• সরাসরি ইউটিউব ও ফেসবুক পেজে স্বয়ংক্রিয় শিডিউল ও পাবলিশ\n"
            f"• অটো-কমেন্ট রিপ্লাই ও গ্রোথ এনালিটিক্স সাপোর্ট\n\n"
            f"🔥 *আজকের স্পেশাল অফার:* কুপন 'PRO{discount_pct}' ব্যবহার করে পান ফ্ল্যাট {discount_pct}% ছাড়!\n"
            f"লাইফটাইম এক্সেস মাত্র ২৯৯৯ টাকা (রেগুলার ৫০০০ টাকা)।\n\n"
            f"💳 বিকাশ / নগদ এজেন্ট ক্যাশআউট সুবিধা রয়েছে। বিস্তারিত জানতে এখনই এই মেসেজে 'DETAILS' লিখে রিপ্লাই দিন! 🤝"
        )
    return (
        f"🎬 *Ready to Build a High-Earning Faceless Video Channel on Autopilot?*\n\n"
        f"Introducing AutoMovie Pro SAAS — The 100% Autonomous Video Production Suite! 🚀\n\n"
        f"✨ *Key Capabilities:*\n"
        f"• Generates 4-6 viral shorts & cinematic long videos every day\n"
        f"• AI scriptwriting, voiceover, and visual montage with zero manual editing\n"
        f"• Direct scheduled publishing to YouTube, Facebook, and TikTok\n"
        f"• Integrated auto-reply agent & engagement analytics\n\n"
        f"🔥 *Exclusive Offer:* Claim {discount_pct}% OFF today with promo code *PRO{discount_pct}*!\n\n"
        f"💬 Reply 'YES' to this message to claim your instant download & setup guide! 🚀"
    )


class GrokSalesCloserAgent:
    """
    Autonomous AI sales agent handling inquiries, objections, and payment handoffs.
    """

    @staticmethod
    def answer_inquiry(message: str, lead_name: str = "ভাইয়া", language: str = "bn") -> Dict[str, Any]:
        msg_lower = message.lower()

        # Price inquiry
        if any(w in msg_lower for w in ["price", "cost", "দাম", "টাকা", "কত"]):
            if language == "bn":
                text = (
                    f"আসসালামু আলাইকুম {lead_name}! অটোমুভি প্রো-এর লাইফটাইম কোর প্যাকেজ মাত্র ২৯৯৯ টাকা "
                    f"(ইংরেজি + আপনার পছন্দের ১টি ভাষা)। আর সব ৬টি ভাষা একসাথে নিলে বিশেষ ছাড়ে মাত্র ৪৯৯৯ টাকা। "
                    f"আপনি কোন প্যাকেজটি নিতে আগ্রহী?"
                )
            else:
                text = (
                    f"Greetings {lead_name}! AutoMovie Pro Lifetime Core is only ৳2999 (English + 1 language of choice). "
                    f"Full 6-language unlocked bundle is only ৳4999. Which package would you like to get started with?"
                )
            return {"intent": "pricing", "response": text, "suggested_action": "send_payment_info"}

        # How to pay / bkash inquiry
        if any(w in msg_lower for w in ["pay", "bkash", "nagad", "বিকাশ", "নগদ", "পেমেন্ট", "একাউন্ট"]):
            if language == "bn":
                text = (
                    f"পেমেন্ট একদম সহজ {lead_name}! আমাদের অনুমোদিত বিকাশ এজেন্ট: +880 1756-160993 (জাহিদ ফার্মেসি) "
                    f"অথবা নগদ এজেন্ট: +880 1611-824811 (সিমি ড্রাগ হাউস)-এ ক্যাশ আউট করে লাস্ট ৪ ডিজিট দিলেই "
                    f"সাথে সাথে ১-ক্লিক সফটওয়্যার ডাউনলোড ও লগইন পেয়ে যাবেন।"
                )
            else:
                text = (
                    f"Payment is straightforward! Cash-out to bKash Agent: +880 1756-160993 (Zahid Pharmacy) "
                    f"or Nagad Agent: +880 1611-824811 (Simi Drug House) or scan our Binance QR. Once sent, "
                    f"you receive instant 1-click software access."
                )
            return {"intent": "payment_info", "response": text, "suggested_action": "close_deal"}

        # Quality / proof inquiry
        if any(w in msg_lower for w in ["কাজ করে", "ভিডিও", "ডেমো", "প্রমাণ", "quality"]):
            if language == "bn":
                text = (
                    f"জী {lead_name}! অটোমুভি প্রো ১০০% স্বয়ংক্রিয়ভাবে দিনে ৪-৬টি শর্টস ও লং ভিডিও তৈরি করে "
                    f"ইউটিউব, ফেসবুক ও টিকটকে শিডিউল অনুযায়ী পোস্ট করে। আমাদের ওয়েবসাইটে শত শত গ্রাহকদের লাইভ রিভিউ "
                    f"দেখতে পারেন www.automoviepro.com-এ।"
                )
            else:
                text = (
                    f"Yes {lead_name}! AutoMovie Pro generates 4-6 high quality videos daily with full failover AI "
                    f"and publishes automatically to YouTube, Facebook, and TikTok."
                )
            return {"intent": "product_demo", "response": text, "suggested_action": "offer_discount"}

        # Default polite sales nudge
        if language == "bn":
            text = f"আসসালামু আলাইকুম {lead_name}! অটোমুভি প্রো সম্পর্কে আপনার যেকোনো প্রশ্ন করতে পারেন। আমি আপনাকে সেরা প্যাকেজটি বেছে নিতে সাহায্য করব।"
        else:
            text = f"Hello {lead_name}! Feel free to ask any question regarding AutoMovie Pro automation."

        return {"intent": "general", "response": text, "suggested_action": "follow_up"}


class BulkMarketingEngine:
    """
    Manages multi-account broadcast campaigns with safety delays, contact cleaning,
    and CRM lead status.
    """

    def __init__(self):
        _ensure_storage()
        self.sales_agent = GrokSalesCloserAgent()

    def add_lead(
        self,
        name: str,
        phone_or_tg: str,
        platform: str = "whatsapp",
        niche: str = "general"
    ) -> Dict[str, Any]:
        cleaned = sanitize_contact(phone_or_tg, platform=platform) or phone_or_tg
        lead_id = f"lead_{abs(hash(cleaned)) % 1000000}"
        record = {
            "lead_id": lead_id,
            "name": name,
            "contact": cleaned,
            "platform": platform,
            "niche": niche,
            "status": "new",
            "created_at": time.time(),
        }

        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                leads = json.load(f)
        except Exception:
            leads = []

        existing = next((l for l in leads if l.get("contact") == cleaned), None)
        if existing:
            existing.update(record)
        else:
            leads.append(record)

        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump(leads, f, indent=2, ensure_ascii=False)

        return {"ok": True, "lead": record}

    def import_bulk_numbers(
        self,
        contacts_raw: Union[str, List[str]],
        platform: str = "whatsapp",
        niche: str = "general",
        default_name: str = "Lead"
    ) -> Dict[str, Any]:
        """
        Parses bulk contacts, cleans and deduplicates them, and saves to leads database.
        """
        parsed = parse_and_clean_contacts(contacts_raw, platform=platform)
        imported_leads = []

        for idx, contact in enumerate(parsed["valid_contacts"]):
            lead_name = f"{default_name} #{idx+1}"
            res = self.add_lead(name=lead_name, phone_or_tg=contact, platform=platform, niche=niche)
            if res.get("ok"):
                imported_leads.append(res["lead"])

        return {
            "ok": True,
            "total_raw": parsed["total_raw"],
            "imported_count": len(imported_leads),
            "duplicates_count": parsed["duplicates_count"],
            "invalid_count": parsed["invalid_count"],
            "platform": platform,
            "niche": niche,
            "contacts": parsed["valid_contacts"],
        }

    def generate_persuasive_copy(
        self,
        niche: str = "faceless_youtube",
        platform: str = "whatsapp",
        discount_pct: int = 20,
        language: str = "bn"
    ) -> str:
        return generate_persuasive_marketing_copy(
            niche=niche,
            platform=platform,
            discount_pct=discount_pct,
            language=language
        )

    def update_lead_status(self, contact: str, new_status: str) -> bool:
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                leads = json.load(f)
            for l in leads:
                if l.get("contact") == contact:
                    l["status"] = new_status
                    l["updated_at"] = time.time()
                    with open(LEADS_FILE, "w", encoding="utf-8") as wf:
                        json.dump(leads, wf, indent=2)
                    return True
        except Exception:
            pass
        return False

    def get_leads(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                leads = json.load(f)
            if status:
                return [l for l in leads if l.get("status") == status]
            return leads
        except Exception:
            return []

    def run_broadcast_simulation(
        self,
        campaign_name: str,
        template: str,
        lead_contacts: List[str],
        platform: str = "whatsapp",
        is_live: bool = False
    ) -> Dict[str, Any]:
        """
        Executes campaign broadcast with anti-ban randomized delays.
        """
        parsed = parse_and_clean_contacts(lead_contacts, platform=platform)
        clean_contacts = parsed["valid_contacts"]

        dispatched = []
        for idx, contact in enumerate(clean_contacts):
            delay = calculate_anti_ban_delay(sent_count=idx, is_live=is_live)
            time.sleep(delay)

            msg = template.replace("{contact}", contact)
            dispatched.append({
                "contact": contact,
                "status": "sent",
                "delay_sec": delay,
                "sent_at": time.time(),
            })
            self.update_lead_status(contact, "contacted")

        campaign_record = {
            "campaign_id": f"cmp_{int(time.time()*1000)}",
            "name": campaign_name,
            "platform": platform,
            "total_recipients": len(clean_contacts),
            "sent_count": len(dispatched),
            "status": "completed",
            "timestamp": time.time(),
        }

        try:
            with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
                campaigns = json.load(f)
            campaigns.insert(0, campaign_record)
            with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
                json.dump(campaigns, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to record campaign: {e}")

        return {
            "ok": True,
            "campaign": campaign_record,
            "deliveries": dispatched,
            "stats": {
                "total_valid": len(clean_contacts),
                "sent": len(dispatched),
                "skipped_duplicates": parsed["duplicates_count"],
                "skipped_invalid": parsed["invalid_count"],
            }
        }
