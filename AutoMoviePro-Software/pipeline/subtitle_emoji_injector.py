# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Subtitle Semantic Emoji Injector
================================================
Contextually maps spoken Bengali/English subtitle words to vibrant, high-retention
emojis. Preserves all Unicode diacritics and combining characters.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# Universal Semantic Emoji Rules across all niches
SEMANTIC_EMOJI_PATTERNS: List[Tuple[str, str]] = [
    # 1. Historical & Civilizational
    (r'(শহর|নগর|প্রাসাদ|সভ্যতা|মন্দির|ধ্বংসাবশেষ|প্রাচীন|পাথর|ভাস্কর্য|পিরামিড|সমাধি|ঐতিহাসিক|সিটাডেল|দুর্গ)', '🏛️'),
    # 2. Oceanic & Aquatic
    (r'(পানি|জল|সমুদ্র|মহাসাগর|নদী|তলদেশ|ডুব|জাহাজ|গভীর|অতলে|সুনামি)', '🌊'),
    # 3. Solar, Thermal & Nuclear Fusion
    (r'(সূর্য|আগুন|ফিউশন|তাপমাত্রা|জ্বল|শিখা|প্লাজমা|টোকামাক|সৌর|উত্তাপ)', '☀️'),
    # 4. Energy & Electricity
    (r'(বিদ্যুৎ|শক্তি|কারেন্ট|ভোল্টেজ|পাওয়ার|বিপ্লব|চার্জ|ব্যাটারি)', '⚡'),
    # 5. Science, Quantum & Laboratory
    (r'(বিজ্ঞান|গবেষক|ল্যাব|পরমাণু|কোয়ান্টাম|অণু|ইলেকট্রন|প্রযুক্তি|পরীক্ষা|থিউরি)', '⚛️'),
    # 6. Space, Cosmos & Astrophysics
    (r'(মহাকাশ|গ্রহ|নক্ষত্র|ব্ল্যাকহোল|চাঁদ|তারা|রকেট|গ্যালাক্সি|মহাজাগতিক)', '🚀'),
    # 7. Wealth, Economy & Money
    (r'(টাকা|অর্থনীতি|ব্যাংক|ডলার|মুদ্রা|সম্পদ|মুনাফা|মার্কেট|বাণিজ্য|স্বর্ণ)', '💰'),
    # 8. Mystery, Secrets & Discovery
    (r'(রহস্য|অজানা|গোপন|চিহ্ন|আবিষ্কার|তল্লাশি|সূত্র|উন্মোচন|কুয়াশা)', '🔍'),
    # 9. Danger, Hazard & Warning
    (r'(ভয়|বিপদ|সতর্ক|মৃত্যু|কঙ্কাল|ধ্বংস|ভূমিকম্প|ঝুঁকি|ভয়ঙ্কর)', '⚠️'),
    # 10. Intelligence, Mind & AI
    (r'(মানুষ|চিন্তা|মস্তিষ্ক|বুদ্ধি|এআই|রোবট|স্মৃতি|ধারণা)', '🧠'),
    # 11. Wonder & Magic
    (r'(চমক|বিস্ময়|জাদু|অদ্ভুত|অলৌকিক|চমকপ্রদ|আলো)', '✨'),
    # 12. Time & Eternity
    (r'(সময়|যুগ|শতবর্ষ|অতীত|ভবিষ্যৎ|মুহূর্ত|ঘড়ি)', '⏳'),
]


def _clean_word_preserving_unicode(word: str) -> str:
    """Strips punctuation while preserving all letters, marks (কার), and numbers."""
    return "".join(
        ch for ch in word.strip()
        if unicodedata.category(ch).startswith(('L', 'M', 'N'))
    )


def get_emoji_for_word(word: str) -> Optional[str]:
    """Returns a contextually matching emoji if the word matches a semantic pattern."""
    w_clean = _clean_word_preserving_unicode(word)
    if not w_clean:
        return None
    for pat, emoji in SEMANTIC_EMOJI_PATTERNS:
        if re.search(pat, w_clean, re.IGNORECASE):
            return emoji
    return None


def inject_semantic_emojis_to_text(text: str, max_emojis: int = 2) -> str:
    """
    Injects up to max_emojis contextually relevant emojis into a sentence without cluttering.
    Preserves exact word ordering and spacing.
    """
    words = text.split()
    output_words = []
    emojis_added = 0
    used_emojis = set()

    for w in words:
        output_words.append(w)
        if emojis_added < max_emojis:
            em = get_emoji_for_word(w)
            if em and em not in used_emojis:
                output_words.append(em)
                used_emojis.add(em)
                emojis_added += 1

    return " ".join(output_words)


def enrich_chunk_with_emojis(chunk: List[Dict[str, Any]], max_chunk_emojis: int = 1) -> List[Dict[str, Any]]:
    """
    Takes a word-timestamp chunk and attaches an emoji attribute to key conceptual words.
    """
    enriched = []
    emojis_added = 0

    for item in chunk:
        new_item = dict(item)
        word_str = item.get("word", "")
        if emojis_added < max_chunk_emojis:
            em = get_emoji_for_word(word_str)
            if em:
                new_item["emoji"] = em
                emojis_added += 1
            else:
                new_item["emoji"] = ""
        else:
            new_item["emoji"] = ""
        enriched.append(new_item)

    return enriched
