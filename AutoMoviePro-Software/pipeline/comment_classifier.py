"""Comment classifier — simple path avoids LLM for cheap categories."""
from __future__ import annotations

import re
from typing import Any, Dict


def classify_comment(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return {"category": "UNKNOWN", "needs_llm": False, "confidence": 0.2}

    if re.search(r"(https?://|www\.|\bsubscribe\b|crypto|forex|onlyfans)", low):
        return {"category": "SPAM", "needs_llm": False, "confidence": 0.9}
    if re.search(r"\b(kill|suicide|slur_placeholder)\b", low):
        return {"category": "TOXIC", "needs_llm": False, "confidence": 0.7}
    if "?" in t or re.search(r"\b(how|what|why|when|where|which|price|cost|available)\b", low):
        if re.search(r"\b(price|cost|how much|tk|usd|\$)\b", low):
            return {"category": "PRICE", "needs_llm": False, "confidence": 0.75}
        if re.search(r"\b(available|stock|buy|where can)\b", low):
            return {"category": "AVAILABILITY", "needs_llm": False, "confidence": 0.7}
        return {"category": "QUESTION", "needs_llm": False, "confidence": 0.65}
    if re.search(r"\b(love|amazing|great|awesome|best|thanks|thank you|🔥|❤️)\b", low):
        return {"category": "PRAISE", "needs_llm": False, "confidence": 0.7}
    if re.search(r"\b(wrong|incorrect|fake|lie|mistake)\b", low):
        return {"category": "CORRECTION", "needs_llm": True, "confidence": 0.55}
    if re.search(r"\b(hate|terrible|worst|scam|garbage)\b", low):
        return {"category": "NEGATIVE", "needs_llm": True, "confidence": 0.6}
    if len(t.split()) <= 6:
        return {"category": "OPINION", "needs_llm": False, "confidence": 0.5}
    return {"category": "UNKNOWN", "needs_llm": True, "confidence": 0.4}
