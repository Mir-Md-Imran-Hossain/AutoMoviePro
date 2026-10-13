"""Visual subject policy — stop gratuitous faces on product/tool videos.

Problem (live pkg 003 ChatGPT): every shot forced a young-male portrait even when
the VO said \"open Custom Instructions / Save button\". Random faces killed meaning.

Policy
------
  presenter   → talking-head / reaction OK (hook, salam, CTA)
  product_ui  → ChatGPT/settings/screen ONLY — no face, no portrait
  hands_ui    → hands + screen OK, face cropped out
  broll       → environment / abstract — no forced character

Inference uses niche + narration + optional script visual_subject field.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

SUBJECT_PRESENTER = "presenter"
SUBJECT_PRODUCT_UI = "product_ui"
SUBJECT_HANDS_UI = "hands_ui"
SUBJECT_BROLL = "broll"

_PRODUCT_NICHE = re.compile(
    r"\b("
    r"chatgpt|gpt|openai|gemini|claude|copilot|midjourney|"
    r"software|app|saas|ui|ux|dashboard|settings|productivity|"
    r"laptop|browser|website|tool|hack|prompt|custom instructions?"
    r")\b",
    re.I,
)

_UI_ACTION = re.compile(
    r"\b("
    r"click|open|tap|press|save|paste|copy|type|scroll|menu|button|"
    r"settings?|custom instructions?|chat|prompt|box|screen|interface|"
    r"laptop|browser|dashboard|panel|sidebar|dropdown|toggle|"
    r"অ্যাসাইনমেন্ট|ক্লিক|সেভ|কপি|পেস্ট|ল্যাপটপ|স্ক্রিন|বাটন|সেটিং"
    r")\b",
    re.I,
)

_PRESENTER_CUE = re.compile(
    r"\b("
    r"hey everyone|listen|assalam|salam|subscribe|like|share|comment|"
    r"look at me|i will show|today i|welcome|"
    r"শোনো|আসসালাম|সাবস্ক্রাইব|লাইক|শেয়ার|কমেন্ট|দেখাবো|আজকে"
    r")\b",
    re.I,
)

_FACE_WORDS = re.compile(
    r"\b(face|portrait|selfie|looking (?:straight )?at camera|close-?up of (?:a )?(?:young )?(?:man|woman|male|female)|"
    r"facial|hoodie.*expression|intense focused expression)\b",
    re.I,
)


_NON_PRESENTER_BN = (
    "রোবট", "রোবটিক্স", "হিউম্যানয়েড", "যন্ত্র", "যন্ত্রপাতি", "অটোমেশন",
    "কৃত্রিম বুদ্ধিমত্তা", "এআই", "টুল", "সফটওয়্যার", "টেক", "টিপস",
    "মহাকাশ", "নক্ষত্র", "গ্রহ", "গ্যালাক্সি", "রহস্য", "পৃথিবী",
    "বিজ্ঞান", "পদার্থবিজ্ঞান", "কোয়ান্টাম", "ইতিহাস", "প্রাচীন", "প্রাণী",
    "জীবজগৎ", "বন্যপ্রাণী", "প্রকৃতি", "কারখানা", "চিকিৎসা", "মেডিসিন",
    "আবিষ্কার", "তথ্য", "টপ", "টাকা", "অনলাইন", "টিউটোরিয়াল", "গাইড"
)

_NON_PRESENTER_TOPIC = re.compile(
    r"\b("
    r"robot|robotics|humanoid|automation|autonomous|space|galaxy|planet|universe|"
    r"science|physics|nature|wildlife|animal|animals|ancient|machinery|"
    r"engineering|factory|automotive|discovery|future|cyber|mystery|history|"
    r"ai|tools|software|technology|tech|tutorial|guide|facts|tips|hacks|coding|"
    r"medicine|biology|quantum|gadgets|top|top10|"
    r"রোবট|মহাকাশ|বিজ্ঞান|ইতিহাস|প্রাণী|অটোমেশন|ফ্যাক্টস|রহস্য|তথ্য"
    r")\b",
    re.I,
)


def is_product_or_tool_niche(niche: str = "", topic: str = "") -> bool:
    blob = f"{niche} {topic}"
    return bool(_PRODUCT_NICHE.search(blob))


def is_non_presenter_topic(niche: str = "", topic: str = "") -> bool:
    blob = f"{niche} {topic}"
    blob_low = blob.lower()
    if any(kw in blob for kw in _NON_PRESENTER_BN):
        return True
    return bool(_NON_PRESENTER_TOPIC.search(blob_low))


def infer_visual_subject(
    *,
    narration: str = "",
    niche: str = "",
    topic: str = "",
    scene: Optional[Dict[str, Any]] = None,
    shot_number: int = 0,
    total_shots: int = 0,
) -> str:
    """Decide what the frame should prioritize."""
    sc = scene or {}
    explicit = str(
        sc.get("visual_subject")
        or sc.get("source_visual_subject")
        or sc.get("subject_type")
        or ""
    ).strip().lower()

    narr = narration or str(
        sc.get("source_voiceover_script") or sc.get("voiceover_script") or ""
    )
    productish = is_product_or_tool_niche(niche, topic) or bool(_PRODUCT_NICHE.search(narr))
    topic_driven = is_non_presenter_topic(niche, topic) or bool(_NON_PRESENTER_TOPIC.search(narr)) or any(kw in narr for kw in _NON_PRESENTER_BN)

    if explicit in (
        SUBJECT_PRESENTER,
        SUBJECT_PRODUCT_UI,
        SUBJECT_HANDS_UI,
        SUBJECT_BROLL,
        "ui",
        "screen",
        "product",
        "person",
        "character",
    ):
        if explicit in ("ui", "screen", "product", SUBJECT_PRODUCT_UI):
            if topic_driven and not productish:
                return SUBJECT_BROLL
            return SUBJECT_PRODUCT_UI
        if explicit in ("person", "character", SUBJECT_PRESENTER):
            # If the topic is non-presenter documentary, or any middle/late shot: strictly NO presenter
            if topic_driven or shot_number > 1:
                return SUBJECT_PRODUCT_UI if productish else SUBJECT_BROLL
            return SUBJECT_PRESENTER
        return explicit

    # Presenter hook / CTA: allowed on Shot 1-2 or final shot for personal/product videos (strictly blocked on pure documentaries)
    pure_documentary = topic_driven and not productish
    if _PRESENTER_CUE.search(narr) and not pure_documentary and (shot_number <= 2 or (total_shots and shot_number >= total_shots)):
        return SUBJECT_PRESENTER

    if _UI_ACTION.search(narr) and productish:
        if re.search(r"\b(hand|typing|keyboard|কপি|পেস্ট|টাইপ)\b", narr, re.I):
            return SUBJECT_HANDS_UI
        return SUBJECT_PRODUCT_UI

    if productish:
        return SUBJECT_PRODUCT_UI

    if topic_driven:
        # Robotics, nature, science, tech documentary: prioritize topic visuals (B-ROLL)
        return SUBJECT_BROLL

    # Default to B-ROLL (cinematic topic scene) instead of forcing presenter portraits
    return SUBJECT_BROLL


def character_allowed(subject: str) -> bool:
    return subject == SUBJECT_PRESENTER


def strip_face_language(text: str) -> str:
    """Remove positive presenter/portrait/face directives from a visual prompt string cleanly,
    WITHOUT corrupting negative constraints or 'NO human face' clauses."""
    t = text or ""
    # Protect negative / forbidden directives so they are never mutilated
    neg_placeholders = {}

    def _protect_neg(m):
        key = f"__NEG_PROT_{len(neg_placeholders)}__"
        neg_placeholders[key] = m.group(0)
        return key

    # Match negative clauses: NO human face, no portrait, FORBIDDEN: ..., NEGATIVE: ...
    t = re.sub(
        r"(?i)\b(?:NO|STRICTLY NO|NEVER|FORBIDDEN:?|NEGATIVE:?)\s+[^.,;\n]{3,120}",
        _protect_neg,
        t,
    )

    # Now strip positive character/presenter directives
    t = _FACE_WORDS.sub(" ", t)
    t = re.sub(
        r"(?i)\b(?:male|female)?\s*presenter\b[^.,;]{0,60}",
        " ",
        t,
    )
    t = re.sub(
        r"(?i)\b(?:28-year-old|25-year-old|bangladeshi male|young man|young woman|light stubble|short black hair|dark navy t-shirt|hoodie|warm natural smile|small wave|looking into lens|looking at camera|facing camera|talking head)\b[^.,;]{0,60}",
        " ",
        t,
    )
    t = re.sub(
        r"(?i)\b(?:young )?(?:bangladeshi )?(?:male|female|man|woman)\b[^.,;]{0,80}",
        " ",
        t,
    )
    # Clean up broken punctuation, isolated words, and orphaned commas
    t = re.sub(r"\b(?:plain|consistent character and wardrobe|consistent facial structure and wardrobe)\b", " ", t, flags=re.I)
    t = re.sub(r"[,;]\s*[,;]+", ", ", t)
    t = re.sub(r"^\s*[,;.\s]+", "", t)
    t = re.sub(r"[,;\s]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;")

    # Restore protected negative directives
    for k, v in neg_placeholders.items():
        t = t.replace(k, v)

    return t


def product_ui_subject_block(narration: str = "", *, product_hint: str = "") -> str:
    """Hard subject lock for screen-first shots."""
    cues = []
    low = (narration or "").lower()
    hint = (product_hint or "").strip() or "software"
    if "custom instruction" in low or "কাস্টম" in low:
        cues.append(f"{hint} Custom Instructions settings panel full-screen")
    if "save" in low or "সেভ" in low:
        cues.append(f"Save button highlighted on {hint} settings UI")
    if "paste" in low or "copy" in low or "কপি" in low or "পেস্ট" in low:
        cues.append(f"text being pasted into {hint} instructions box")
    if "laptop" in low or "ল্যাপটপ" in low:
        cues.append(f"laptop screen showing {hint} web app, no face")
    if not cues:
        cues.append(f"{hint} web UI / settings / app screen, crisp readable panels")
    return (
        "SUBJECT LOCK (PRODUCT UI — NO HUMAN FACE): "
        + "; ".join(cues)
        + ". FORBIDDEN: portrait, selfie, random person face, talking head, "
        "stock-photo young man/woman looking at camera."
    )


def hands_ui_subject_block() -> str:
    return (
        "SUBJECT LOCK (HANDS + SCREEN ONLY): adult hands on keyboard/trackpad over "
        "screen or device UI. Crop face out of frame entirely. No portrait."
    )


def negative_for_subject(subject: str, topic: str = "") -> str:
    if subject != SUBJECT_PRESENTER or is_non_presenter_topic(topic=topic):
        return (
            "female robot, female robot face, gynoid, woman robot face, female android, doll face, "
            "mannequin face, robot face close-up, talking head, female portrait, cyborg woman, sexy robot, "
            "feminine robot, uncanny valley face, anime robot face, breasts, cleavage, erotic robot, "
            "human face, woman face, male face, presenter face, stock model looking at camera, "
            "beauty close-up, selfie, dark underexposed shadows, pitch black background, murky dark lighting, "
            "low resolution artifacts, blurry textures, watermark, logo, text, unreadable newspaper, messy surreal artifacts"
        )
    return ""


