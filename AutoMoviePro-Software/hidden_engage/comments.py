"""
Human-like comment generation: topic-aware, occasional typo, then edit.
"""
from __future__ import annotations

import logging
import random
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SAFE_TEMPLATES = [
    "Really nice video!",
    "Loved this one",
    "Great work, keep it up",
    "This was interesting",
    "দারুণ ভিডিও",
    "ভালো লেগেছে",
    "সুন্দর হয়েছে",
    "Informative, thanks",
    "Nice edit",
    "Awesome content",
]


def _simple_topic_comment(title: str, description: str = "") -> str:
    blob = f"{title} {description}".strip().lower()
    if any(k in blob for k in ("ancient", "civilization", "egypt", "rome", "pyramid", "history")):
        return random.choice(
            [
                "History like this always fascinates me",
                "Ancient stories never get old",
                "Love learning about old civilizations",
                "পুরনো ইতিহাস বেশ ভালো লাগলো",
            ]
        )
    if any(k in blob for k in ("review", "gadget", "phone", "unbox")):
        return random.choice(
            [
                "Helpful review, thanks",
                "Clear explanation",
                "Good points in this one",
            ]
        )
    if title.strip():
        short = re.sub(r"\s+", " ", title.strip())[:48]
        return random.choice(
            [
                f"Nice take on {short}",
                "Really enjoyed this",
                "সুন্দর হয়েছে",
                "Great video",
            ]
        )
    return random.choice(SAFE_TEMPLATES)


def generate_comment(title: str = "", description: str = "", *, lang_hint: str = "") -> str:
    """Try LLM briefly; fall back to templates. Always returns short human comment."""
    prompt = (
        "Write ONE short casual social-media comment (max 12 words) about this video. "
        "Sound like a real viewer, not a bot. No hashtags, no emojis spam, no links.\n"
        f"Title: {title[:200]}\n"
        f"Description: {description[:300]}\n"
        f"Language hint: {lang_hint or 'mix English/Bangla ok'}\n"
        "Reply with only the comment text."
    )
    try:
        from pipeline.llm_router import chat_text

        res = chat_text(prompt, purpose="agent", json_mode=False)
        text = (res.get("text") or "").strip().strip('"').strip("'")
        text = re.sub(r"\s+", " ", text)
        if 2 <= len(text) <= 120 and "http" not in text.lower():
            return text
    except Exception as exc:
        logger.debug("comment llm skip: %s", exc)
    return _simple_topic_comment(title, description)


def inject_typo(text: str) -> Tuple[str, str]:
    """
    Returns (typo_version, corrected_version).
    Sometimes swaps adjacent letters or drops one character.
    """
    corrected = text
    if len(text) < 5 or random.random() > 0.55:
        return text, corrected
    chars = list(text)
    # Prefer letter positions
    letter_idxs = [i for i, c in enumerate(chars) if c.isalpha()]
    if len(letter_idxs) < 2:
        return text, corrected
    mode = random.choice(["swap", "drop", "double"])
    if mode == "swap" and len(letter_idxs) >= 2:
        i = random.choice(letter_idxs[:-1])
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif mode == "drop":
        i = random.choice(letter_idxs)
        chars.pop(i)
    else:
        i = random.choice(letter_idxs)
        chars.insert(i, chars[i])
    typo = "".join(chars)
    if typo == corrected:
        return text, corrected
    return typo, corrected


def prepare_comment(item: Dict[str, Any]) -> Dict[str, Any]:
    base = generate_comment(
        title=item.get("title") or "",
        description=item.get("description") or "",
    )
    with_typo, fixed = inject_typo(base)
    will_edit = with_typo != fixed
    return {
        "text": with_typo,
        "corrected": fixed,
        "will_edit": will_edit,
        "source": "llm_or_template",
    }
