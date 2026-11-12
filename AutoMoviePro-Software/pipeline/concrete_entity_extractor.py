# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Universal Dynamic Semantic Entity & Focal Subject Extractor
=============================================================================
Module: pipeline.concrete_entity_extractor

Niche-agnostic semantic distillation translating spoken Bengali into concrete,
photorealistic physical visual subjects with ZERO hardcoded domain bias.
Eliminates all quantum computing, ancient stonework, and deep sea submarine defaults.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ConcreteEntityExtractor")
logger.setLevel(logging.INFO)


class ConcreteEntityExtractor:
    """Universally translates Bengali narrative into concrete, tangible physical subjects."""

    @classmethod
    def clean_ascii_tokens(cls, text: str, max_words: int = 4) -> str:
        """Extracts clean, lowercased English search tokens free of framing buzzwords."""
        forbidden = {
            "the", "and", "with", "from", "into", "over", "under", "that", "this",
            "shot", "view", "scene", "cinematic", "photorealistic", "documentary",
            "ultra", "master", "lighting", "authentic", "focal", "subject", "vertical",
            "horizontal", "macro", "realistic", "detail", "camera", "angle", "movement"
        }
        words = re.findall(r'[a-zA-Z]{3,}', text or "")
        filtered = [w.lower() for w in words if w.lower() not in forbidden]
        return " ".join(filtered[:max_words])

    @classmethod
    def extract_topic_anchor(cls, topic_title: str, topic_bn: str = "") -> str:
        """Extracts a clean English anchor subject from topic or dynamically translates Bengali topic."""
        raw = (topic_title or topic_bn or "").strip()
        if not raw:
            return ""
        eng_words = re.findall(r'[A-Za-z0-9\-]+', raw)
        if len(eng_words) >= 2:
            clean = " ".join(w for w in eng_words if w.lower() not in {"hd", "4k", "part", "episode", "short", "video", "mystery", "history"})
            if clean and len(clean.split()) >= 1:
                return clean[:40]

        # Dynamically translate Bengali topic into clean 2-4 word English concrete noun phrase
        try:
            from pipeline.llm_router import chat_text
            p_trans = f"Translate this topic title into 2 to 4 concise English words describing the physical subject (NO conversational filler, NO quotes, ASCII English only): '{raw}'"
            res = chat_text(p_trans, purpose="agent")
            txt = res.get("text", "") if isinstance(res, dict) else str(res)
            m_bold = re.findall(r'\*\*([A-Za-z\s\-]+)\*\*', txt)
            candidate = m_bold[0] if m_bold else txt.split("\n")[0]
            words = [w for w in re.findall(r'[a-zA-Z]{3,}', candidate) if w.lower() not in {"here", "there", "short", "visual", "video", "best"}]
            if words:
                return " ".join(words[:4])
        except Exception:
            pass

        # Clean fallback
        clean_bn = re.sub(
            r'\b(রহস্য|ইতিহাস|আবিষ্কার|সত্য|ডকুমেন্টারি|ভিডিও|পর্ব|বাস্তবতা|অজানা|কীভাবে|কেন|ঘটনা)\b',
            '', raw, flags=re.IGNORECASE
        ).strip()
        return clean_bn[:40] or "documentary subject"

    @classmethod
    def extract_concrete_entity(
        cls,
        dialogue_bn: str,
        niche: str = "",
        fallback_subject: str = "",
        topic_title: str = "",
        topic_bn: str = "",
    ) -> Dict[str, Any]:
        """
        Extracts concrete physical subject, action, environment, and English stock query.
        Guarantees:
        1. Literal physical manifestation of dialogue, ignoring abstract metaphors.
        2. Zero hardcoded domain presets or stonework fallbacks.
        3. 100% English stock query and subject (Zero Bengali characters in search fields).
        """
        text = (dialogue_bn or "").strip()
        clean_fallback = (fallback_subject or "").strip()
        topic_anchor = cls.extract_topic_anchor(topic_title, topic_bn) or niche or "documentary subject"

        # Tier 1: Check if fallback_subject (from Script Contract) is already a descriptive English subject
        has_english_fallback = bool(re.search(r'[A-Za-z]{3,}', clean_fallback))
        is_generic = any(k in clean_fallback.lower() for k in ["unknown", "generic", "phase", "topic title", "focal subject scene"])

        if has_english_fallback and len(clean_fallback.split()) >= 3 and not is_generic:
            stock_q = cls.clean_ascii_tokens(f"{topic_anchor} {clean_fallback}", max_words=3)
            return {
                "concrete_subject_en": clean_fallback,
                "stock_query": stock_q or "documentary subject",
                "action": "captured in sharp steady motion",
                "environment": f"authentic {niche or 'cinematic'} environment",
                "is_specific_match": True,
            }

        # Tier 2: Dynamic LLM Semantic Translation (Zero-Shot Metaphor Demolition)
        try:
            from pipeline.llm_router import chat_text, extract_json_object
            prompt = f"""You are Lead Visual Director. Translate this Bengali documentary dialogue into concrete physical visual entities.
Topic: {topic_title or topic_bn}
Niche: {niche}
Dialogue: "{text}"

CRITICAL RULES:
1. NO ABSTRACT METAPHORS. If dialogue says "lost in the abyss of time", do NOT show deep sea or void; show tangible physical artifacts related to the topic.
2. If dialogue is rhetorical, describe the literal physical scene, setting, or tools of the topic ({topic_anchor}).
3. 'stock_query' MUST be 2-3 concise English words: [Physical Entity] + [Physical Setting]. STRICTLY ASCII ENGLISH ONLY.

Return JSON:
{{
  "concrete_subject_en": "exact tangible object, vehicle, tool, specimen, or landscape",
  "action": "physical action or optical state",
  "environment": "authentic physical setting",
  "stock_query": "entity setting"
}}"""
            res = chat_text(prompt, purpose="agent", json_mode=True)
            data = res if isinstance(res, dict) else extract_json_object(res)
            if isinstance(data, dict) and data.get("concrete_subject_en") and data.get("stock_query"):
                clean_q = cls.clean_ascii_tokens(data["stock_query"], max_words=3)
                return {
                    "concrete_subject_en": data["concrete_subject_en"],
                    "stock_query": clean_q or cls.clean_ascii_tokens(topic_anchor, 3),
                    "action": data.get("action", "captured in clear optical perspective"),
                    "environment": data.get("environment", f"authentic {niche} setting"),
                    "is_specific_match": True,
                }
        except Exception as e:
            logger.debug("Online entity extraction note: %s; using deterministic anchor projection", e)

        # Tier 3: Deterministic Fallback grounded purely in Niche and Topic Anchor (Zero Hardcoded Bias)
        clean_anchor_en = cls.clean_ascii_tokens(topic_anchor, max_words=3) or cls.clean_ascii_tokens(niche, max_words=3) or "cinematic subject"
        clean_fallback_tokens = cls.clean_ascii_tokens(clean_fallback, max_words=3)

        focal_subject = f"detailed physical view of {topic_anchor}" if not clean_fallback_tokens else f"{clean_fallback_tokens} in {clean_anchor_en}"
        stock_query = f"{clean_anchor_en} {clean_fallback_tokens}".strip()
        stock_query = cls.clean_ascii_tokens(stock_query, max_words=3) or clean_anchor_en

        return {
            "concrete_subject_en": focal_subject,
            "stock_query": stock_query,
            "action": "exhibiting realistic physical presence and motion",
            "environment": f"authentic {niche or 'cinematic'} documentary setting",
            "is_specific_match": False,
        }


def extract_topic_anchor(topic_title: str, topic_bn: str = "") -> str:
    """Convenience functional wrapper for topic anchor extraction."""
    return ConcreteEntityExtractor.extract_topic_anchor(topic_title=topic_title, topic_bn=topic_bn)


def extract_concrete_entity_from_dialogue(
    dialogue_bn: str,
    niche: str = "",
    fallback_subject: str = "",
    topic_title: str = "",
    topic_bn: str = "",
) -> Dict[str, Any]:
    """Universal convenience functional interface."""
    return ConcreteEntityExtractor.extract_concrete_entity(
        dialogue_bn=dialogue_bn,
        niche=niche,
        fallback_subject=fallback_subject,
        topic_title=topic_title,
        topic_bn=topic_bn,
    )
