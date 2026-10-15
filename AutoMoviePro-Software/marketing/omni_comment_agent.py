"""
=============================================================================
OmniSocial AI Smart Comment & Inbox Intelligence Agent
=============================================================================
Scans comments and visitor inquiries on Facebook Page / Meta Business Suite.
Analyzes the specific context of the post, understands the customer's question,
and drafts a contextually accurate, warm, respectful reply.
"""

import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

ROOT_DIR = Path(r"E:\AI Assistant\Social Media Hub")
PROFILES_DIR = ROOT_DIR / "Profiles"

# System Prompt Templates for Deep Contextual Replies
BRAND_PROMPTS = {
    "automovie_pro_page": """
You are the Senior Customer Relations Consultant for AutoMovie Pro (অটোমুভি প্রো).
Brand Tone: Warm, highly courteous, professional, encouraging Bengali (বাংলা).
Key Knowledge:
- AutoMovie Pro is a 100% industrial automated video creation software.
- Features: Auto trending topic research, deep emotional cinematic script writing, human-like voiceover, 50+ languages auto-dubbing, auto upload to Facebook & YouTube with viral SEO, tags, and thumbnails.
- Pricing: Lifetime Deal is only ৳2,998 (one-time payment, no monthly fees). Additional language addon is ৳499.
- Official Website: https://automoviepro.com
- Helpline / WhatsApp: +880 1684-355055
- Payment Agents: bKash (01756160993), Nagad (01611-824811), Personal (01717820998).
Rule: Answer the user's specific question directly with immense clarity and polite emojis. If asking how to buy, guide them to the website or WhatsApp hotline.
""",
    "assunnah_path_page": """
You are the Respectful Dawah & Community Assistant for As-Sunnah Path (আস-সুন্নাহ পাথ).
Brand Tone: Extremely humble, spiritually warm, polite Islamic etiquette, respectful Bengali (বাংলা).
Key Knowledge:
- Dedicated to authentic Quranic wisdom and Sahih Hadiths.
- Official Website: www.assunnahpath.com
- Email: assunnahpath@gmail.com
Rule: Always begin with Islamic greetings (আসসালামু আলাইকুম ওয়া রাহমাতুল্লাহ). Express heartfelt gratitude for their comment or dua. If someone asks for Islamic reference, encourage them with peace and provide references gently. Never argue.
"""
}


SETTINGS_FILE = ROOT_DIR / "agent_settings.json"


class APIKeyPoolManager:
    """Manages rotation, active key selection, and auto-failover for LLM API keys."""
    _current_index = 0
    _exhausted_keys = set()

    @classmethod
    def load_keys(cls) -> List[str]:
        keys = []
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pool = data.get("api_keys_pool", [])
                    if isinstance(pool, list):
                        keys.extend([k.strip() for k in pool if k and isinstance(k, str) and not k.startswith("#")])
                    single_key = data.get("api_key", "").strip()
                    if single_key and single_key not in keys and not single_key.startswith("#"):
                        keys.append(single_key)
            except Exception:
                pass
        
        env_keys = [os.getenv("GEMINI_API_KEY"), os.getenv("GOOGLE_API_KEY")]
        for ek in env_keys:
            if ek and ek.strip() and ek.strip() not in keys:
                keys.append(ek.strip())
        return keys

    @classmethod
    def get_current_key(cls) -> Optional[str]:
        keys = cls.load_keys()
        if not keys:
            return None
        valid_keys = [k for k in keys if k not in cls._exhausted_keys]
        if not valid_keys:
            # If all were marked exhausted, reset to allow retry after cooldown
            cls._exhausted_keys.clear()
            valid_keys = keys
        idx = cls._current_index % len(valid_keys)
        return valid_keys[idx]

    @classmethod
    def mark_key_rate_limited(cls, key: str):
        print(f"[API_POOL] Key {key[:6]}... exceeded rate limit / quota (HTTP 429). Rotating to next key in pool...", flush=True)
        cls._exhausted_keys.add(key)
        cls._current_index += 1


import re
import hashlib
from collections import deque

MODERATION_LOG_FILE = ROOT_DIR / "spam_moderation_log.json"

# Authorized domains that are permitted in comments (Official Brand Assets)
AUTHORIZED_DOMAINS = [
    "automoviepro.com",
    "www.automoviepro.com",
    "assunnahpath.com",
    "www.assunnahpath.com",
    "facebook.com",
    "fb.com",
    "fb.me",
    "youtube.com",
    "youtu.be"
]

# Suspicious URL shorteners commonly used for scams and malicious redirects
SUSPICIOUS_SHORTENERS = [
    r"bit\.ly", r"tinyurl\.com", r"t\.me", r"wa\.me", r"telegram\.me",
    r"chat\.whatsapp\.com", r"is\.gd", r"cutt\.ly", r"rb\.gy", r"goo\.gl",
    r"ow\.ly", r"buff\.ly", r"adf\.ly", r"shorturl\.at", r"soo\.gd"
]

# Suspicious / Cheap TLDs often abused by automated link spammers
SPAM_TLDS = [
    r"\.xyz\b", r"\.top\b", r"\.site\b", r"\.club\b", r"\.vip\b", r"\.buzz\b",
    r"\.loan\b", r"\.fit\b", r"\.cam\b", r"\.tk\b", r"\.ml\b", r"\.ga\b",
    r"\.cf\b", r"\.gq\b", r"\.ru\b", r"\.fun\b", r"\.bid\b", r"\.click\b",
    r"\.live\b", r"\.stream\b", r"\.link\b"
]

# Malicious financial fraud, scam, phishing, and gambling keywords
SCAM_FRAUD_PATTERNS = [
    # English scam patterns
    r"earn\s+\$?[0-9]+\s*(?:daily|per day|hourly|weekly|a day)",
    r"crypto(?:currency)?\s*(?:trading|investment|expert|mining|profit|signals)",
    r"binary\s+options",
    r"forex\s+(?:trading|signals|investment|account)",
    r"double\s+your\s+(?:money|income|bitcoin|crypto)",
    r"guaranteed\s+(?:profit|return|income)",
    r"whatsapp\s+(?:me|number|chat|contact)",
    r"message\s+(?:me\s+on\s+)?telegram",
    r"dm\s+(?:me\s+)?(?:for\s+info|on\s+whatsapp|on\s+telegram)",
    r"investment\s+(?:scheme|platform|opportunity)",
    r"free\s+(?:giveaway|crypto|spins|bonus|money)",
    r"make\s+money\s+(?:online|fast|from\s+home)",
    r"recover\s+(?:hacked|stolen|lost)\s+(?:account|crypto|bitcoin|funds)",
    r"passive\s+income\s+click\s+here",
    # Bengali scam and fraud patterns
    r"ঘরে\s*বসে\s*(?:দৈনিক|প্রতিদিন|ইনকাম|টাকা\s*আয়)",
    r"ফ্রি\s*(?:টাকা|বোনাস|লটারি|গিভঅ্যাওয়ে)",
    r"টাকা\s*ডাবল",
    r"বিনিয়োগে\s*দ্বিগুণ",
    r"প্রতিদিন\s*[০-৯0-9]+(?:\s*-\s*[০-৯0-9]+)?\s*টাকা",
    r"টেলিগ্রামে\s*মেসেজ\s*দিন",
    r"হোয়াটসঅ্যাপে\s*(?:নক|মেসেজ)\s*দিন",
    r"টেলিগ্রাম\s*চ্যানেলে\s*জয়েন",
    r"অনলাইন\s*জুয়া",
    r"ক্যাসিনো",
    r"ক্রেডিট\s*কার্ড\s*ফ্রি",
    r"পাসওয়ার্ড\s*দিন",
    r"ওটিপি\s*পাঠান",
    r"বিকাশে\s*ফ্রি\s*টাকা",
    r"নগদে\s*ফ্রি\s*ক্যাশব্যাক"
]

# Slang, hate speech, vulgarity, and toxic harassment patterns
ABUSE_HATE_PATTERNS = [
    # English abusive / hate terms
    r"\b(?:idiot|stupid|scammer|fraudster|bastard|bitch|asshole|bullshit|scam page)\b",
    # Bengali abusive / vulgar / harassment terms
    r"(?:ভুয়া\s*পেজ|দালাল|চিটার|বাটপার|হারামি|শুয়োর|কুত্তা|গালি|লুচ্চা|চোর)"
]


class SpamShield:
    """
    OmniSocial Anti-Abuse & Spam Defense Sentinel.
    Enforces URL regex filters, malicious keyword detection, comment deduplication,
    and user frequency rate guarding.
    """
    _recent_comments = deque(maxlen=300) # stores {"hash", "user_id", "text", "time"}
    _user_timestamps = {}               # user_id -> list of timestamps
    _last_reply_time = 0.0

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Strips whitespace, emojis, and normalizes punctuation for deterministic matching."""
        if not text:
            return ""
        txt = text.lower()
        txt = re.sub(r"[^\w\s\u0980-\u09FF]", " ", txt)
        return " ".join(txt.split())

    @classmethod
    def detect_unauthorized_links(cls, text: str) -> Tuple[bool, List[str]]:
        """
        Detects standard, obfuscated, and shortener URLs, filtering against authorized domains.
        """
        detected_links = []
        if not text:
            return False, []

        # 1. Standard URLs (http, https, www)
        urls = re.findall(r"(?:https?://|www\.)[^\s/$.?#].[^\s]*", text, flags=re.IGNORECASE)
        for u in urls:
            is_authorized = any(ad in u.lower() for ad in AUTHORIZED_DOMAINS)
            if not is_authorized:
                detected_links.append(u)

        # 2. Suspicious Shorteners
        for shortener in SUSPICIOUS_SHORTENERS:
            matches = re.findall(rf"(?:https?://)?(?:[a-zA-Z0-9-]+\.)?{shortener}/[^\s]*", text, flags=re.IGNORECASE)
            for m in matches:
                if m not in detected_links:
                    detected_links.append(m)

        # 3. Spam TLDs
        for tld in SPAM_TLDS:
            matches = re.findall(rf"\b[a-zA-Z0-9-]{{2,}}{tld}(?:/[^\s]*)?", text, flags=re.IGNORECASE)
            for m in matches:
                if m not in detected_links:
                    detected_links.append(m)

        # 4. Obfuscated URLs (e.g. "site [dot] com", "bit(dot)ly", "t . me")
        obfuscated = re.findall(r"[a-zA-Z0-9_-]+\s*(?:\[dot\]|\(dot\)|\{dot\}|\s+dot\s+)\s*(?:com|net|org|xyz|io|me|info|tk|top|site)", text, flags=re.IGNORECASE)
        for ob in obfuscated:
            is_auth = any(ad.split(".")[0] in ob.lower() for ad in AUTHORIZED_DOMAINS)
            if not is_auth and ob not in detected_links:
                detected_links.append(ob)

        return (len(detected_links) > 0, detected_links)

    @classmethod
    def detect_malicious_content(cls, text: str) -> Tuple[bool, str, List[str]]:
        """
        Detects financial scams, phishing, spam keywords, and abusive hate speech.
        """
        matched_scam = []
        matched_abuse = []

        for p in SCAM_FRAUD_PATTERNS:
            m = re.findall(p, text, flags=re.IGNORECASE)
            if m:
                matched_scam.extend(m if isinstance(m[0], str) else [str(x) for x in m])

        for p in ABUSE_HATE_PATTERNS:
            m = re.findall(p, text, flags=re.IGNORECASE)
            if m:
                matched_abuse.extend(m if isinstance(m[0], str) else [str(x) for x in m])

        if matched_scam:
            return True, "SCAM_FRAUD", matched_scam
        if matched_abuse:
            return True, "ABUSIVE_HATE", matched_abuse
        return False, "CLEAN", []

    @classmethod
    def check_repetitive_dedup(cls, commenter_id: str, comment_text: str) -> Tuple[bool, str]:
        """
        Detects repetitive copy-paste comments across posts from the same commenter or bot swarm.
        """
        norm = cls.normalize_text(comment_text)
        if len(norm) < 6:
            return False, "SHORT_COMMENT"

        comment_hash = hashlib.md5(norm.encode("utf-8")).hexdigest()
        now = time.time()

        # Sliding window check (within 1800 seconds / 30 mins)
        same_hash_count = 0
        same_user_repeat = False

        for item in cls._recent_comments:
            if now - item["time"] > 1800:
                continue
            if item["hash"] == comment_hash:
                same_hash_count += 1
                if item["user_id"] == commenter_id:
                    same_user_repeat = True

        if same_user_repeat:
            return True, "DUPLICATE_FROM_USER"
        if same_hash_count >= 2:
            return True, "BOT_SWARM_DUPLICATE"

        # Record into cache
        cls._recent_comments.append({
            "hash": comment_hash,
            "user_id": commenter_id,
            "text": norm[:100],
            "time": now
        })
        return False, "UNIQUE"

    @classmethod
    def check_rate_limit(cls, commenter_id: str) -> Tuple[bool, str]:
        """
        Limits comments per commenter to maximum 3 comments per 10 minutes.
        """
        now = time.time()
        user_history = cls._user_timestamps.get(commenter_id, [])
        # Prune older than 600 seconds (10 mins)
        user_history = [t for t in user_history if now - t < 600]
        cls._user_timestamps[commenter_id] = user_history

        if len(user_history) >= 3:
            return True, f"RATE_LIMITED_USER ({len(user_history)} comments in 10m)"

        user_history.append(now)
        cls._user_timestamps[commenter_id] = user_history
        return False, "RATE_OK"

    @classmethod
    def evaluate_comment(
        cls,
        commenter_id: str,
        commenter_name: str,
        comment_text: str,
        post_id: str = ""
    ) -> Dict[str, Any]:
        """
        Evaluates an incoming comment against all 4 anti-abuse defense layers.
        """
        result = {
            "is_spam": False,
            "action": "ALLOW",
            "spam_type": "NONE",
            "confidence": 0.0,
            "matched_triggers": [],
            "risk_score": 0,
            "timestamp": datetime.now().isoformat()
        }

        # 1. Frequency Rate Limiting
        rate_limited, rate_reason = cls.check_rate_limit(commenter_id or commenter_name)
        if rate_limited:
            result.update({
                "is_spam": True,
                "action": "BLOCK_RATE_LIMIT",
                "spam_type": "FREQUENCY_FLOOD",
                "confidence": 1.0,
                "matched_triggers": [rate_reason],
                "risk_score": 90
            })
            cls.log_moderation_event(post_id, commenter_name, comment_text, result)
            return result

        # 2. Unauthorized Link / URL Regex Filter
        has_links, detected_urls = cls.detect_unauthorized_links(comment_text)
        if has_links:
            result.update({
                "is_spam": True,
                "action": "BLOCK_LINK_SPAM",
                "spam_type": "LINK_SPAMMER",
                "confidence": 0.98,
                "matched_triggers": detected_urls,
                "risk_score": 95
            })
            cls.log_moderation_event(post_id, commenter_name, comment_text, result)
            return result

        # 3. Malicious Keywords / Abuse / Hate Dictionaries
        has_malicious, cat, triggers = cls.detect_malicious_content(comment_text)
        if has_malicious:
            result.update({
                "is_spam": True,
                "action": f"BLOCK_{cat}",
                "spam_type": cat,
                "confidence": 0.92,
                "matched_triggers": triggers,
                "risk_score": 85 if cat == "SCAM_FRAUD" else 75
            })
            cls.log_moderation_event(post_id, commenter_name, comment_text, result)
            return result

        # 4. Repetitive Comment Deduplication
        is_repetitive, dedup_reason = cls.check_repetitive_dedup(commenter_id or commenter_name, comment_text)
        if is_repetitive:
            result.update({
                "is_spam": True,
                "action": "BLOCK_REPETITIVE",
                "spam_type": "REPETITIVE_BOT_SPAM",
                "confidence": 0.95,
                "matched_triggers": [dedup_reason],
                "risk_score": 80
            })
            cls.log_moderation_event(post_id, commenter_name, comment_text, result)
            return result

        return result

    @classmethod
    def log_moderation_event(cls, post_id: str, commenter_name: str, comment_text: str, evaluation: dict):
        """Records flagged comment into system moderation log."""
        try:
            records = []
            if MODERATION_LOG_FILE.exists():
                try:
                    with open(MODERATION_LOG_FILE, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except Exception:
                    records = []
            records.append({
                "timestamp": datetime.now().isoformat(),
                "post_id": post_id,
                "commenter": commenter_name,
                "comment_snippet": comment_text[:200],
                "action": evaluation.get("action"),
                "spam_type": evaluation.get("spam_type"),
                "triggers": evaluation.get("matched_triggers"),
                "risk_score": evaluation.get("risk_score")
            })
            # Keep last 500 moderation records
            records = records[-500:]
            from omni_social_hub import atomic_write_json
            atomic_write_json(MODERATION_LOG_FILE, records)
        except Exception:
            pass


class OmniCommentReplyAgent:
    """Intelligent Comment & Customer Inquiry Resolver."""

    @staticmethod
    def generate_reply(
        entity_id: str,
        post_context: str,
        commenter_name: str,
        user_comment: str,
        bypass_spam_shield: bool = False
    ) -> str:
        """
        Deeply analyzes the post content and customer question to create a perfect reply.
        Uses workspace LLM keys (Gemini / Grok / OpenRouter) from api_keys_pool with auto-failover on HTTP 429.
        Guarded by SpamShield to prevent wasting tokens or replying to malicious spammers.
        """
        # Anti-Spam & Anti-Abuse Shield Inspection
        if not bypass_spam_shield:
            moderation = SpamShield.evaluate_comment(
                commenter_id=commenter_name,
                commenter_name=commenter_name,
                comment_text=user_comment
            )
            if moderation.get("is_spam"):
                print(f"[SPAM_SHIELD] 🛡️ Blocked spam comment from '{commenter_name}'! Reason: {moderation.get('action')} | Triggers: {moderation.get('matched_triggers')}", flush=True)
                return ""  # Silently skip reply to prevent feeding trolls, spammers, and malicious links

        system_prompt = BRAND_PROMPTS.get(entity_id, "You are a professional social media manager. Reply politely in Bengali.")
        
        prompt = f"""
[POST CONTEXT]:
{post_context}

[USER NAME]: {commenter_name}
[USER COMMENT / QUESTION]:
{user_comment}

Please generate a deeply respectful, context-aware reply in Bengali:
"""
        keys_to_try = APIKeyPoolManager.load_keys()
        for _ in range(max(1, len(keys_to_try))):
            active_key = APIKeyPoolManager.get_current_key()
            if not active_key:
                break

            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={active_key}"
                data = {
                    "contents": [
                        {"role": "user", "parts": [{"text": system_prompt + "\n\n" + prompt}]}
                    ],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 300}
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text:
                        return text
            except urllib.error.HTTPError as he:
                if he.code in (429, 403):
                    APIKeyPoolManager.mark_key_rate_limited(active_key)
                    continue
                else:
                    break
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    APIKeyPoolManager.mark_key_rate_limited(active_key)
                    continue
                break

        # Intelligent Heuristic Fallback based on Entity and Question Keywords
        lower_q = user_comment.lower()
        if "automovie" in entity_id:
            if any(k in user_comment for k in ["দাম", "টাকা", "price", "কত"]):
                return f"ধন্যবাদ {commenter_name}! 🌟 AutoMovie Pro-এর লাইফটাইম লাইসেন্স এখন সীমিত সময়ের বিশেষ অফারে মাত্র ৳২,৯৯৮ (আজীবন ব্যবহার, কোনো মাসিক সাবস্ক্রিপশন নেই)। বিস্তারিত দেখতে বা সরাসরি অর্ডার করতে ভিজিট করুন: https://automoviepro.com অথবা আমাদের হটলাইনে যোগাযোগ করুন: +880 1684-355055।"
            elif any(k in user_comment for k in ["কিভাবে", "পেমেন্ট", "বিকাশ", "নগদ", "payment"]):
                return f"প্রিয় {commenter_name}, বিকাশ এজেন্ট (01756160993) অথবা নগদ এজেন্টে (01611-824811) ক্যাশ আউট করে লাস্ট ৩-৪ ডিজিট আমাদের ওয়েবসাইটে সাবমিট করলেই তৎক্ষণাৎ সফটওয়্যার ডাউনলোড ও লাইসেন্স পেয়ে যাবেন। সহায়তার জন্য WhatsApp: +880 1684-355055।"
            else:
                return f"ধন্যবাদ {commenter_name} আপনার মূল্যবান মন্তব্যের জন্য! 🚀 অটোমুভি প্রো দিয়ে কোনো অভিজ্ঞতা ছাড়াই ফুল অটোপাইলটে ফেসবুক ও ইউটিউবের ভিডিও বানাতে পারবেন। যেকোনো তথ্যের জন্য ইনবক্স করুন অথবা আমাদের অফিসিয়াল সাইট automoviepro.com দেখুন।"
        else:
            # As-Sunnah Path
            if any(k in user_comment for k in ["মাশাআল্লাহ", "আলহামদুলিল্লাহ", "জাযাকাল্লাহ", "আমিন"]):
                return f"ওয়ালাইকুম আসসালাম ওয়া রাহমাতুল্লাহ, প্রিয় {commenter_name} ভাই/বোন। জাযাকাল্লাহু খাইরান! আল্লাহ তাআলা আপনাকে উত্তম প্রতিদান দান করুন এবং আমাদের সকলকে সুন্নাহর পথে অবিচল রাখুন। 🤲"
            else:
                return f"আসসালামু আলাইকুম ওয়া রাহমাতুল্লাহ, প্রিয় {commenter_name}। আপনার সুন্দর ও মূল্যবান মন্তব্যের জন্য আন্তরিক ধন্যবাদ ও মুবারকবাদ। দ্বীনি সহিহ জ্ঞান ও আত্মিক প্রশান্তির জন্য আমাদের সাথেই থাকুন। 🕌"

    @staticmethod
    def log_and_record_reply(entity_id: str, post_id: str, user_name: str, user_comment: str, reply_text: str):
        from omni_social_hub import OmniSocialRegistry
        entity = OmniSocialRegistry.get_entity(entity_id)
        entity.append_comment_reply({
            "post_id": post_id,
            "commenter": user_name,
            "comment_text": user_comment,
            "reply_text": reply_text,
            "replied_at": datetime.now().isoformat()
        })


if __name__ == "__main__":
    # Test sample reply generation
    test_reply = OmniCommentReplyAgent.generate_reply(
        entity_id="automovie_pro_page",
        post_context="ইন্ডাস্ট্রিয়াল ভিডিও অটোমেশন লাইফটাইম ডিল মাত্র ৳২৯৯৮",
        commenter_name="তানভীর আহমেদ",
        user_comment="ভাই এই সফটওয়্যারটির প্যাকেজ মূল্য কত এবং কিভাবে কিনব?"
    )
    print("Sample AutoMovie Reply:\n", test_reply)
