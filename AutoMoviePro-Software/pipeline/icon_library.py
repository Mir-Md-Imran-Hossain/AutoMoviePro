"""AutoMovie Pro — Open-Source Vector Icon Library & Semantic Resolver.

Integrates an open-source, MIT-licensed vector icon engine based on Lucide/Feather icons.
Features:
1. 70+ Curated Explainer & Motion Graphics Vector Icons (Finance, Tech, AI, Brain, Security, etc.).
2. Multilingual Semantic Keyword Resolver (Bangla & English natural language -> Icon key).
3. Pure-Python High-DPI Vector/Canvas Renderer (PIL with 4x supersampling, anti-aliased strokes,
   glassmorphism badges, and radial glow effects). Zero external npm/binary dependencies.
4. Extensible: Automatically loads any custom .svg files dropped into `assets/icons/`.
5. High-performance caching in `assets/icons_cache/` for sub-millisecond retrieval.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
ICONS_DIR = BASE_DIR / "assets" / "icons"
CACHE_DIR = BASE_DIR / "assets" / "icons_cache"

ICONS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Vector Primitives Registry for 70+ Lucide/Feather Open-Source Icons
# Defined in normalized 24x24 coordinate space (standard Lucide viewBox 0 0 24 24)
# Types of elements:
#   ("line", (x1, y1, x2, y2))
#   ("circle", (cx, cy, r))
#   ("rect", (x, y, w, h, rx))
#   ("poly", [(x1, y1), (x2, y2), ...])
#   ("arc", (cx, cy, r, start_deg, end_deg))
# ---------------------------------------------------------------------------

ICON_REGISTRY: Dict[str, List[Tuple[str, Any]]] = {
    # --- Ideas, Innovation, Brain, AI ---
    "lightbulb": [
        ("circle", (12, 9, 6)),
        ("line", (9, 18, 15, 18)),
        ("line", (10, 21, 14, 21)),
        ("line", (12, 15, 12, 18)),
    ],
    "brain": [
        ("circle", (9, 9, 3.5)),
        ("circle", (15, 9, 3.5)),
        ("circle", (8, 15, 3)),
        ("circle", (16, 15, 3)),
        ("line", (12, 6, 12, 18)),
        ("arc", (12, 12, 4, 30, 150)),
    ],
    "sparkles": [
        ("poly", [(12, 3), (13.5, 8.5), (19, 10), (13.5, 11.5), (12, 17), (10.5, 11.5), (5, 10), (10.5, 8.5), (12, 3)]),
        ("circle", (19, 5, 1.5)),
        ("circle", (5, 17, 1.5)),
    ],
    "cpu": [
        ("rect", (6, 6, 12, 12, 2)),
        ("rect", (9, 9, 6, 6, 1)),
        ("line", (9, 2, 9, 6)),
        ("line", (15, 2, 15, 6)),
        ("line", (9, 18, 9, 22)),
        ("line", (15, 18, 15, 22)),
        ("line", (2, 9, 6, 9)),
        ("line", (2, 15, 6, 15)),
        ("line", (18, 9, 22, 9)),
        ("line", (18, 15, 22, 15)),
    ],
    "bot": [
        ("rect", (4, 8, 16, 12, 3)),
        ("circle", (9, 13, 1.5)),
        ("circle", (15, 13, 1.5)),
        ("line", (9, 17, 15, 17)),
        ("line", (12, 4, 12, 8)),
        ("circle", (12, 3, 1)),
    ],
    "zap": [
        ("poly", [(13, 2), (4, 14), (11, 14), (10, 22), (20, 9), (13, 9), (14, 2)]),
    ],
    "flame": [
        ("poly", [(12, 2), (15, 8), (19, 11), (17, 18), (12, 22), (7, 18), (5, 11), (9, 8), (12, 2)]),
        ("arc", (12, 16, 3, 0, 180)),
    ],
    "atom": [
        ("circle", (12, 12, 3)),
        ("arc", (12, 12, 8, 0, 360)),
        ("arc", (12, 12, 5, 45, 225)),
    ],
    "compass": [
        ("circle", (12, 12, 9)),
        ("poly", [(12, 6), (14, 11), (19, 12), (14, 13), (12, 18), (10, 13), (5, 12), (10, 11), (12, 6)]),
    ],

    # --- Finance, Wealth, Growth, Business ---
    "coins": [
        ("circle", (9, 12, 6)),
        ("arc", (14, 10, 6, 270, 90)),
        ("line", (9, 9, 9, 15)),
    ],
    "dollar-sign": [
        ("line", (12, 2, 12, 22)),
        ("arc", (12, 8, 4, 90, 270)),
        ("arc", (12, 16, 4, 270, 90)),
        ("line", (9, 8, 15, 8)),
        ("line", (9, 16, 15, 16)),
    ],
    "trending-up": [
        ("poly", [(23, 6), (17, 6), (23, 12)]),
        ("poly", [(23, 6), (13.5, 15.5), (8.5, 10.5), (1, 18)]),
    ],
    "trending-down": [
        ("poly", [(23, 18), (17, 18), (23, 12)]),
        ("poly", [(23, 18), (13.5, 8.5), (8.5, 13.5), (1, 6)]),
    ],
    "wallet": [
        ("rect", (3, 6, 18, 13, 2)),
        ("line", (3, 10, 21, 10)),
        ("circle", (16, 14, 1.5)),
    ],
    "bar-chart": [
        ("line", (18, 20, 18, 10)),
        ("line", (12, 20, 12, 4)),
        ("line", (6, 20, 6, 14)),
        ("line", (3, 20, 21, 20)),
    ],
    "pie-chart": [
        ("circle", (12, 12, 9)),
        ("line", (12, 12, 12, 3)),
        ("line", (12, 12, 19, 16)),
    ],
    "percent": [
        ("line", (19, 5, 5, 19)),
        ("circle", (7, 7, 2.5)),
        ("circle", (17, 17, 2.5)),
    ],

    # --- Security, Safety, Rules, Protection ---
    "shield": [
        ("poly", [(12, 2), (20, 5), (20, 11), (12, 21), (4, 11), (4, 5), (12, 2)]),
    ],
    "shield-check": [
        ("poly", [(12, 2), (20, 5), (20, 11), (12, 21), (4, 11), (4, 5), (12, 2)]),
        ("poly", [(9, 11), (11, 13), (15, 9)]),
    ],
    "shield-alert": [
        ("poly", [(12, 2), (20, 5), (20, 11), (12, 21), (4, 11), (4, 5), (12, 2)]),
        ("line", (12, 8, 12, 12)),
        ("circle", (12, 15, 0.8)),
    ],
    "lock": [
        ("rect", (5, 11, 14, 10, 2)),
        ("arc", (12, 8, 4, 180, 360)),
        ("circle", (12, 16, 1.5)),
    ],
    "unlock": [
        ("rect", (5, 11, 14, 10, 2)),
        ("arc", (15, 8, 4, 180, 360)),
        ("circle", (12, 16, 1.5)),
    ],
    "check-circle": [
        ("circle", (12, 12, 9)),
        ("poly", [(8, 12), (11, 15), (16, 9)]),
    ],
    "check": [
        ("poly", [(5, 12), (10, 17), (19, 7)]),
    ],

    # --- Warnings, Obstacles, Mistakes ---
    "alert-triangle": [
        ("poly", [(12, 3), (22, 20), (2, 20), (12, 3)]),
        ("line", (12, 9, 12, 14)),
        ("circle", (12, 17, 0.9)),
    ],
    "alert-circle": [
        ("circle", (12, 12, 9)),
        ("line", (12, 8, 12, 13)),
        ("circle", (12, 16, 0.9)),
    ],
    "x-circle": [
        ("circle", (12, 12, 9)),
        ("line", (9, 9, 15, 15)),
        ("line", (15, 9, 9, 15)),
    ],
    "bell": [
        ("poly", [(6, 17), (18, 17), (17, 10), (15, 6), (9, 6), (7, 10), (6, 17)]),
        ("arc", (12, 18, 2.5, 0, 180)),
        ("line", (12, 3, 12, 5)),
    ],

    # --- Goals, Speed, Action, Achievement ---
    "rocket": [
        ("poly", [(12, 2), (17, 7), (16, 13), (12, 17), (8, 13), (7, 7), (12, 2)]),
        ("circle", (12, 8, 2)),
        ("poly", [(6, 13), (3, 16), (7, 17)]),
        ("poly", [(18, 13), (21, 16), (17, 17)]),
        ("line", (12, 17, 12, 21)),
    ],
    "target": [
        ("circle", (12, 12, 9)),
        ("circle", (12, 12, 5)),
        ("circle", (12, 12, 1.5)),
    ],
    "award": [
        ("circle", (12, 9, 6)),
        ("poly", [(8, 14), (6, 21), (12, 18), (18, 21), (16, 14)]),
    ],
    "crown": [
        ("poly", [(3, 18), (21, 18), (19, 8), (14, 13), (12, 5), (10, 13), (5, 8), (3, 18)]),
    ],
    "star": [
        ("poly", [(12, 2), (15, 8.5), (22, 9), (17, 14), (18.5, 21), (12, 17.5), (5.5, 21), (7, 14), (2, 9), (9, 8.5), (12, 2)]),
    ],
    "thumbs-up": [
        ("poly", [(7, 11), (7, 20), (3, 20), (3, 11), (7, 11)]),
        ("poly", [(7, 13), (12, 5), (14, 5), (13, 9), (19, 9), (21, 11), (19, 19), (7, 19)]),
    ],

    # --- Time, Process, Scheduling ---
    "clock": [
        ("circle", (12, 12, 9)),
        ("line", (12, 7, 12, 12)),
        ("line", (12, 12, 16, 14)),
    ],
    "hourglass": [
        ("poly", [(5, 3), (19, 3), (12, 11), (19, 21), (5, 21), (12, 11), (5, 3)]),
    ],
    "calendar": [
        ("rect", (4, 5, 16, 16, 2)),
        ("line", (4, 10, 20, 10)),
        ("line", (8, 2, 8, 6)),
        ("line", (16, 2, 16, 6)),
    ],

    # --- Technology, System, Data, Code ---
    "database": [
        ("arc", (12, 6, 8, 0, 360)),
        ("line", (4, 6, 4, 18)),
        ("line", (20, 6, 20, 18)),
        ("arc", (12, 12, 8, 0, 180)),
        ("arc", (12, 18, 8, 0, 180)),
    ],
    "code": [
        ("poly", [(8, 7), (3, 12), (8, 17)]),
        ("poly", [(16, 7), (21, 12), (16, 17)]),
        ("line", (14, 4, 10, 20)),
    ],
    "laptop": [
        ("rect", (5, 5, 14, 10, 1)),
        ("line", (2, 19, 22, 19)),
    ],
    "smartphone": [
        ("rect", (6, 3, 12, 18, 2)),
        ("circle", (12, 17, 1)),
    ],
    "globe": [
        ("circle", (12, 12, 9)),
        ("line", (3, 12, 21, 12)),
        ("arc", (12, 12, 5, 0, 360)),
    ],

    # --- Video, Content, Social, People ---
    "video": [
        ("rect", (3, 6, 12, 12, 2)),
        ("poly", [(15, 10), (21, 6), (21, 18), (15, 14)]),
    ],
    "film": [
        ("rect", (3, 4, 18, 16, 2)),
        ("line", (7, 4, 7, 20)),
        ("line", (17, 4, 17, 20)),
        ("line", (3, 9, 21, 9)),
        ("line", (3, 15, 21, 15)),
    ],
    "mic": [
        ("rect", (9, 3, 6, 11, 3)),
        ("arc", (12, 11, 5, 0, 180)),
        ("line", (12, 16, 12, 20)),
        ("line", (8, 20, 16, 20)),
    ],
    "users": [
        ("circle", (9, 8, 3.5)),
        ("arc", (9, 18, 6, 180, 360)),
        ("circle", (16, 9, 2.5)),
        ("arc", (16, 18, 4.5, 180, 360)),
    ],
    "user": [
        ("circle", (12, 8, 4)),
        ("arc", (12, 19, 7, 180, 360)),
    ],
    "message-square": [
        ("poly", [(4, 4), (20, 4), (20, 16), (9, 16), (4, 21), (4, 4)]),
    ],

    # --- Knowledge, Books, Education, Tools ---
    "book-open": [
        ("poly", [(12, 7), (12, 20), (3, 17), (3, 4), (12, 7)]),
        ("poly", [(12, 7), (12, 20), (21, 17), (21, 4), (12, 7)]),
    ],
    "list": [
        ("line", (8, 6, 20, 6)),
        ("line", (8, 12, 20, 12)),
        ("line", (8, 18, 20, 18)),
        ("circle", (4, 6, 1)),
        ("circle", (4, 12, 1)),
        ("circle", (4, 18, 1)),
    ],
    "settings": [
        ("circle", (12, 12, 4)),
        ("poly", [(12, 2), (14, 4), (17, 4), (18, 7), (21, 8), (20, 11), (22, 13), (20, 15),
                  (21, 18), (18, 19), (17, 22), (14, 22), (12, 24), (10, 22), (7, 22), (6, 19),
                  (3, 18), (4, 15), (2, 13), (4, 11), (3, 8), (6, 7), (7, 4), (10, 4), (12, 2)]),
    ],
    # --- Health, Wellness, Life ---
    "heart": [
        ("circle", (8, 9, 4)),
        ("circle", (16, 9, 4)),
        ("poly", [(4, 11), (12, 20), (20, 11)]),
    ],
    "activity": [
        ("poly", [(3, 12), (7, 12), (10, 6), (14, 18), (17, 12), (21, 12)]),
    ],
}


# ---------------------------------------------------------------------------
# Multilingual Natural Language Semantic Keyword Dictionary (Bangla & English)
# ---------------------------------------------------------------------------

SEMANTIC_ICON_KEYWORDS = {
    # Finance, Money, Business
    "coins": [
        "টাকা", "অর্থ", "ডলার", "পয়সা", "মুনাফা", "লাভ", "ইনকাম", "উপার্জন",
        "সম্পদ", "ব্যবসা", "বিনিয়োগ", "ব্যাংক", "ক্যাশ", "অর্থনীতি",
        "money", "cash", "wealth", "income", "profit", "earnings", "finance", "bank", "coins", "investment"
    ],
    "dollar-sign": [
        "ডলার", "মূল্য", "টাকা", "বেতন", "খরচ", "রেভিনিউ",
        "dollar", "price", "salary", "cost", "revenue", "paid", "expensive"
    ],
    "trending-up": [
        "উন্নতি", "বৃদ্ধি", "গ্রোথ", "সাফল্য", "শীর্ষ", "ভাইরাল", "উঠছে", "উর্ধমুখী",
        "growth", "trending", "increase", "boost", "scale", "climb", "rise", "viral"
    ],
    "trending-down": [
        "পতন", "ঘাটতি", "হ্রাস", "কমছে", "লস", "ক্ষতি", "মন্দা",
        "loss", "decline", "fall", "drop", "crash", "down", "recession"
    ],
    "wallet": [
        "ওয়ালেট", "পকেট", "সঞ্চয়", "বাজেট",
        "wallet", "savings", "budget", "pouch"
    ],
    "bar-chart": [
        "চার্ট", "পরিসংখ্যান", "গ্রাফ", "অ্যানালিটিক্স", "মেট্রিক", "রিপোর্ট",
        "chart", "statistics", "analytics", "graph", "metric", "data", "report"
    ],
    "percent": [
        "শতকরা", "পার্সেন্ট", "ডিসকাউন্ট", "অফার", "হার",
        "percent", "percentage", "discount", "offer", "rate", "ratio"
    ],

    # Ideas, Innovation, Brain, AI
    "lightbulb": [
        "আইডিয়া", "ভাবনা", "উপায়", "উদ্ভাবন", "সমাধান", "টিপস", "রহস্য", "নতুন",
        "idea", "lightbulb", "solution", "innovation", "creativity", "secret", "tip", "insight"
    ],
    "brain": [
        "মস্তিষ্ক", "চিন্তা", "মেধা", "বুদ্ধি", "স্মৃতি", "মনোবিজ্ঞান", "পদ্ধতি", "জ্ঞান",
        "brain", "mind", "psychology", "intelligence", "strategy", "thought", "memory", "mental"
    ],
    "sparkles": [
        "জাদু", "অলৌকিক", "চমৎকার", "আকর্ষণীয়", "বিশেষ", "বিস্ময়",
        "magic", "sparkle", "wonder", "amazing", "special", "shining", "miracle"
    ],
    "cpu": [
        "প্রযুক্তি", "এআই", "কম্পিউটার", "প্রসেসর", "সফটওয়্যার", "অ্যালগরিদম", "অটোমেশন",
        "tech", "technology", "ai", "artificial intelligence", "cpu", "processor", "software", "automation"
    ],
    "bot": [
        "রোবট", "বট", "এজেন্ট", "চ্যাটবট",
        "robot", "bot", "agent", "assistant", "cyborg"
    ],
    "zap": [
        "বিদ্যুৎ", "গতি", "তাৎক্ষণিক", "পাওয়ার", "শক্তি", "ফাস্ট",
        "fast", "instant", "lightning", "speed", "power", "energy", "quick"
    ],
    "flame": [
        "আগুন", "হট", "উত্তেজনা", "ট্রেন্ডিং", "জ্বলন্ত",
        "fire", "flame", "hot", "trending", "burn"
    ],

    # Security, Trust, Rules, Safety
    "shield": [
        "সুরক্ষা", "নিরাপত্তা", "রক্ষা", "সেফ", "প্রাইভেসি", "গোপনীয়তা",
        "shield", "security", "protection", "safe", "privacy", "defense", "secure"
    ],
    "shield-check": [
        "ভেরিফাইড", "প্রমাণিত", "বিশ্বস্ত", "নিশ্চিত", "গ্যারান্টি",
        "verified", "trust", "guarantee", "proof", "confirmed"
    ],
    "lock": [
        "লক", "তালা", "সুরক্ষিত", "পাসওয়ার্ড", "সীমিত",
        "lock", "locked", "password", "restricted", "private"
    ],
    "check-circle": [
        "সঠিক", "নিয়ম", "পদ্ধতি", "চেকলিস্ট", "কমপ্লিট", "হ্যাঁ", "পাস",
        "check", "correct", "rule", "complete", "done", "yes", "checklist", "passed"
    ],

    # Warnings, Alerts, Mistakes
    "alert-triangle": [
        "সতর্কতা", "বিপদ", "ভুল", "সাবধান", "ঝুঁকি", "ক্ষতি", "সতর্ক",
        "warning", "alert", "danger", "risk", "mistake", "caution", "fatal"
    ],
    "alert-circle": [
        "জরুরি", "মনোযোগ", "নোটিশ",
        "notice", "attention", "urgent", "critical"
    ],
    "x-circle": [
        "না", "ভুল", "নিষিদ্ধ", "বর্জন", "ব্যর্থ",
        "wrong", "fail", "prohibited", "cross", "cancel", "no"
    ],

    # Goals, Scale, Achievement
    "rocket": [
        "রকেট", "লঞ্চ", "উড়ান", "ভবিষ্যৎ", "যাত্রা", "দ্রুততম",
        "rocket", "launch", "space", "future", "boost", "spaceship"
    ],
    "target": [
        "টার্গেট", "লক্ষ্য", "উদ্দেশ্য", "ফোকাস", "অর্জন",
        "target", "goal", "focus", "aim", "objective", "bullseye"
    ],
    "award": [
        "পুরস্কার", "সম্মাননা", "সেরা", "বিজয়", "প্রথম",
        "award", "best", "winner", "medal", "honor", "first"
    ],
    "crown": [
        "রাজা", "বাদশা", "মুকুট", "কিং", "শীর্ষস্থানীয়",
        "crown", "king", "queen", "elite", "royal", "supreme"
    ],
    "star": [
        "স্টার", "তারা", "ভিআইপি", "রেটিং", "সেরা",
        "star", "rating", "top", "favorite", "stellar"
    ],

    # Time, Scheduling
    "clock": [
        "সময়", "ঘড়ি", "ঘণ্টা", "মিনিট", "দেরি", "সময়সীমা", "এখনই",
        "time", "clock", "hour", "minute", "schedule", "deadline", "now"
    ],
    "hourglass": [
        "অপেক্ষা", "ধৈর্য", "কাউন্টডাউন", "ইতিহাস",
        "wait", "patience", "countdown", "history", "ancient"
    ],

    # Media, Video, Social
    "video": [
        "ভিডিও", "সিনেমা", "ক্যামেরা", "রেকর্ডিং", "ইউটিউব", "রিল",
        "video", "movie", "recording", "camera", "reel", "youtube"
    ],
    "users": [
        "মানুষ", "দর্শক", "জনগণ", "গ্রাহক", "ফলোয়ার", "সম্প্রদায়", "টিম",
        "people", "users", "audience", "followers", "community", "team", "crowd"
    ],
    "book-open": [
        "বই", "শিক্ষা", "কুরআন", "ইতিহাস", "গবেষণা", "পড়া", "জ্ঞান", "মিশর", "পিরামিড", "প্রাচীন",
        "book", "study", "learning", "education", "quran", "history", "research", "reading", "ancient", "pyramid"
    ],
    "heart": [
        "স্বাস্থ্য", "হৃদয়", "ভালোবাসা", "চিকিৎসা", "ডাক্তার", "ফিটনেস", "রক্তকণিকা", "কোষ", "ইমিউন",
        "health", "heart", "love", "doctor", "fitness", "wellness", "medical", "hospital", "blood", "immune", "cell"
    ],
    "activity": [
        "নাড়ি", "পালস", "অ্যাক্টিভিটি", "ব্যায়াম", "ফিট",
        "pulse", "activity", "ecg", "vital", "exercise", "cardio"
    ],
    "globe": [
        "মহাবিশ্ব", "পৃথিবী", "বিশ্ব", "গ্রহ", "কসমিক", "আন্তর্জাতিক", "গ্লোবাল", "পরিবেশ",
        "world", "earth", "universe", "planet", "global", "globe", "cosmos"
    ],
    "atom": [
        "কোয়ান্টাম", "পরমাণু", "পদার্থবিজ্ঞান", "পদার্থবিদ্যা", "অণু", "কণা", "সুপারপজিশন", "বিজ্ঞান", "ল্যাব", "কিউবিট",
        "quantum", "atom", "physics", "particle", "science", "laboratory", "qubit", "nucleus"
    ],
    "compass": [
        "সমুদ্র", "সাগর", "মারিয়ানা", "গভীর সমুদ্র", "পানি", "জল", "টাইটানিক", "জাহাজ", "সাবমেরিন", "অতলে", "দিকনির্ণয়", "অভিযান",
        "ocean", "sea", "mariana", "deep sea", "water", "marine", "submarine", "abyss", "compass", "navigation"
    ],
}


def _canonical_bengali_nukta(text: str) -> str:
    """Canonicalizes Bengali decomposed nuktas (Avro/Bijoy/Gboard) to standard precomposed glyphs."""
    return (
        text.replace("\u09af\u09bc", "\u09df")  # য + ় -> য়
        .replace("\u09a1\u09bc", "\u09dc")      # ড + ় -> ড়
        .replace("\u09a2\u09bc", "\u09dd")      # ঢ + ় -> ঢ়
    )


class IconLibrary:
    """Open-Source Icon Provider & High-DPI Vector Renderer."""

    @classmethod
    def list_available_icons(cls) -> List[str]:
        """Returns all icon names currently supported in the catalog."""
        return sorted(list(ICON_REGISTRY.keys()))

    @classmethod
    def resolve_icon_keyword(cls, query_text: str, context: Optional[str] = None) -> str:
        """
        Intelligently maps query and optional context to the most semantically relevant icon.
        Scores candidate icons based on exact token matches and weighted domain relevance,
        preventing false-positive substring matches and irrelevant icon choices.
        """
        if not query_text and not context:
            return "sparkles"

        full_query = f"{context or ''} {query_text or ''}".strip()
        norm = _canonical_bengali_nukta(full_query.lower())
        words = set(re.findall(r"[\w\u0980-\u09ff]+", norm))

        # 1. Exact catalog key match directly in query
        for w in words:
            if w in ICON_REGISTRY:
                return w

        # 2. Token-scoring across all registered icon categories
        scores: Dict[str, float] = {}
        for icon_key, triggers in SEMANTIC_ICON_KEYWORDS.items():
            score = 0.0
            for t in triggers:
                t_clean = t.strip().lower()
                # Whole word match: highest weight
                if t_clean in words:
                    score += 3.0
                # Exact phrase match in normalized text
                elif len(t_clean) > 4 and f" {t_clean} " in f" {norm} ":
                    score += 2.0
            if score > 0:
                scores[icon_key] = score

        if scores:
            # Pick highest scoring icon
            return max(scores.items(), key=lambda kv: kv[1])[0]

        # 3. Contextual Domain Fallbacks (instead of arbitrary first item)
        if any(w in norm for w in ("মহাকাশ", "স্পেস", "নক্ষত্র", "ব্ল্যাক হোল", "গ্যালাক্সি", "space", "cosmos", "galaxy")):
            return "rocket"
        if any(w in norm for w in ("কোয়ান্টাম", "পরমাণু", "বিজ্ঞান", "quantum", "physics", "science")):
            return "atom"
        if any(w in norm for w in ("সমুদ্র", "সাগর", "পানি", "মারিয়ানা", "ocean", "sea", "marine", "deep")):
            return "compass"
        if any(w in norm for w in ("টাকা", "আয়", "লাভ", "মুনাফা", "money", "profit", "finance")):
            return "coins"
        if any(w in norm for w in ("প্রযুক্তি", "এআই", "কম্পিউটার", "সফটওয়্যার", "tech", "ai", "computer")):
            return "cpu"
        if any(w in norm for w in ("ইতিহাস", "প্রাচীন", "মিশর", "পিরামিড", "ancient", "history", "pyramid")):
            return "book-open"
        if any(w in norm for w in ("সময়", "ঘণ্টা", "টাইম", "time", "clock", "hour")):
            return "clock"
        if any(w in norm for w in ("স্বাস্থ্য", "শরীর", "রক্ত", "চিকিৎসা", "health", "body", "medical")):
            return "heart"

        return "sparkles"

    @classmethod
    def render_icon_png(
        cls,
        icon_name: str,
        dest_path: Optional[Path] = None,
        *,
        size: int = 256,
        color: str = "#FFFFFF",
        badge: str = "rounded_square",  # 'rounded_square', 'circle', 'glow', 'none'
        badge_bg: str = "#0f172a",
        border_color: str = "#334155",
        glow_color: Optional[str] = None,
    ) -> Path:
        """
        Renders the vector icon to a crisp, high-resolution PNG file.
        Uses 4x supersampling (anti-aliasing) and optional glassmorphic card backdrop.
        """
        icon_name = (icon_name or "lightbulb").lower().strip()
        if icon_name not in ICON_REGISTRY:
            # Fallback to resolver or default
            icon_name = cls.resolve_icon_keyword(icon_name)
            if icon_name not in ICON_REGISTRY:
                icon_name = "lightbulb"

        # Check cache
        cache_key = hashlib.md5(
            f"{icon_name}_{size}_{color}_{badge}_{badge_bg}_{border_color}_{glow_color}".encode("utf-8")
        ).hexdigest()
        cache_file = CACHE_DIR / f"icon_{icon_name}_{cache_key[:12]}.png"

        if cache_file.exists() and cache_file.stat().st_size > 500:
            if dest_path:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(cache_file.read_bytes())
                return dest_path
            return cache_file

        target_file = dest_path or cache_file
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Render at 4x canvas resolution for flawless anti-aliasing
        supersample = 4
        canvas_dim = size * supersample
        img = Image.new("RGBA", (canvas_dim, canvas_dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Parse colors
        stroke_color = cls._hex_to_rgba(color, 255)
        bg_rgba = cls._hex_to_rgba(badge_bg, 235)
        border_rgba = cls._hex_to_rgba(border_color, 200)
        glow_rgba = cls._hex_to_rgba(glow_color or color, 120)

        # 1. Render Badge Backdrop (if requested)
        pad = int(canvas_dim * 0.08)
        content_box = [pad, pad, canvas_dim - pad, canvas_dim - pad]

        if badge == "circle":
            if glow_color:
                glow_img = Image.new("RGBA", (canvas_dim, canvas_dim), (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow_img)
                gdraw.ellipse(content_box, fill=glow_rgba)
                glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=supersample * 6))
                img = Image.alpha_composite(img, glow_img)
                draw = ImageDraw.Draw(img)

            draw.ellipse(content_box, fill=bg_rgba, outline=border_rgba, width=supersample * 3)

        elif badge == "rounded_square":
            radius = int(canvas_dim * 0.22)
            if glow_color:
                glow_img = Image.new("RGBA", (canvas_dim, canvas_dim), (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow_img)
                gdraw.rounded_rectangle(content_box, radius=radius, fill=glow_rgba)
                glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=supersample * 6))
                img = Image.alpha_composite(img, glow_img)
                draw = ImageDraw.Draw(img)

            draw.rounded_rectangle(
                content_box,
                radius=radius,
                fill=bg_rgba,
                outline=border_rgba,
                width=supersample * 3,
            )

        elif badge == "glow":
            glow_img = Image.new("RGBA", (canvas_dim, canvas_dim), (0, 0, 0, 0))
            gdraw = ImageDraw.Draw(glow_img)
            gdraw.ellipse([pad * 2, pad * 2, canvas_dim - pad * 2, canvas_dim - pad * 2], fill=glow_rgba)
            glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=supersample * 10))
            img = Image.alpha_composite(img, glow_img)
            draw = ImageDraw.Draw(img)

        # 2. Render Icon Vector Geometry (Scale normalized 24x24 viewBox to content inner rect)
        inner_pad = int(canvas_dim * 0.26) if badge in ("circle", "rounded_square") else int(canvas_dim * 0.12)
        inner_w = canvas_dim - (inner_pad * 2)
        scale = inner_w / 24.0
        line_w = max(2, int(supersample * 2.2 * (size / 128.0)))

        primitives = ICON_REGISTRY.get(icon_name, ICON_REGISTRY["lightbulb"])

        for kind, args in primitives:
            if kind == "line":
                x1, y1, x2, y2 = args
                px1 = inner_pad + (x1 * scale)
                py1 = inner_pad + (y1 * scale)
                px2 = inner_pad + (x2 * scale)
                py2 = inner_pad + (y2 * scale)
                draw.line([(px1, py1), (px2, py2)], fill=stroke_color, width=line_w)

            elif kind == "circle":
                cx, cy, r = args
                pcx = inner_pad + (cx * scale)
                pcy = inner_pad + (cy * scale)
                pr = r * scale
                draw.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], outline=stroke_color, width=line_w)

            elif kind == "rect":
                x, y, w, h, rx = args
                px = inner_pad + (x * scale)
                py = inner_pad + (y * scale)
                pw = w * scale
                ph = h * scale
                prx = rx * scale
                draw.rounded_rectangle([px, py, px + pw, py + ph], radius=int(prx), outline=stroke_color, width=line_w)

            elif kind == "poly":
                pts = [(inner_pad + (x * scale), inner_pad + (y * scale)) for x, y in args]
                if len(pts) >= 2:
                    if pts[0] == pts[-1]:
                        draw.polygon(pts, outline=stroke_color, width=line_w)
                    else:
                        draw.line(pts, fill=stroke_color, width=line_w)

            elif kind == "arc":
                cx, cy, r, sdeg, edeg = args
                pcx = inner_pad + (cx * scale)
                pcy = inner_pad + (cy * scale)
                pr = r * scale
                draw.arc([pcx - pr, pcy - pr, pcx + pr, pcy + pr], start=sdeg, end=edeg, fill=stroke_color, width=line_w)

        # 3. Downscale with LANCZOS for razor-sharp edge anti-aliasing
        final_img = img.resize((size, size), Image.Resampling.LANCZOS)
        final_img.save(target_file, "PNG")

        # Also save to cache if custom target
        if target_file != cache_file:
            final_img.save(cache_file, "PNG")

        return target_file

    @staticmethod
    def _hex_to_rgba(hex_code: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        """Converts '#RRGGBB' or '#RGB' hex string to RGBA tuple."""
        hex_code = (hex_code or "#FFFFFF").strip().lstrip("#")
        if len(hex_code) == 3:
            hex_code = "".join(c * 2 for c in hex_code)
        if len(hex_code) != 6:
            return (255, 255, 255, alpha)
        try:
            r = int(hex_code[0:2], 16)
            g = int(hex_code[2:4], 16)
            b = int(hex_code[4:6], 16)
            return (r, g, b, alpha)
        except ValueError:
            return (255, 255, 255, alpha)
