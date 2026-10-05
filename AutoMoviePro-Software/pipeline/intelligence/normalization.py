"""Topic normalization — multilingual (BUILD-04G-H)."""
from __future__ import annotations

import re
import unicodedata

TOPIC_STOPWORDS = {
    "the", "a", "an", "why", "what", "how", "did", "does", "do", "is", "are",
    "was", "were", "to", "of", "in", "on", "for", "and", "or", "today",
    # Bengali common stopwords
    "কেন", "কি", "কী", "হয়", "হয়", "এবং", "আজ",
}

# Unicode script ranges preserved — do not strip meaningful chars
_SCRIPT_RANGES = (
    r"\u0980-\u09FF",  # Bengali
    r"\u0600-\u06FF",  # Arabic
    r"\u0900-\u097F",  # Devanagari
    r"\u0400-\u04FF",  # Cyrillic
    r"\u4E00-\u9FFF",  # CJK
    r"\u3040-\u30FF",  # Hiragana/Katakana
    r"\uAC00-\uD7AF",  # Hangul
)


def normalize_topic_text(text: str) -> str:
    """Normalize whitespace, punctuation, case — preserve semantic tokens across scripts."""
    raw = unicodedata.normalize("NFKC", (text or "").strip())
    raw = raw.replace("?", " ").replace("!", " ").replace(".", " ")
    allowed = r"\w\s'\-" + "".join(_SCRIPT_RANGES)
    raw = re.sub(rf"[^{allowed}]", " ", raw, flags=re.UNICODE)
    raw = re.sub(r"\s+", " ", raw).strip().lower()
    return raw


def canonical_topic_key(text: str) -> str:
    norm = normalize_topic_text(text)
    tokens = [t for t in norm.split() if t and t not in TOPIC_STOPWORDS]
    return " ".join(tokens)


def token_set(text: str) -> set[str]:
    return set(canonical_topic_key(text).split())


def jaccard_similarity(a: str, b: str) -> float:
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def normalize_research_query(query: str) -> str:
    q = normalize_topic_text(query)
    return q[:200]
