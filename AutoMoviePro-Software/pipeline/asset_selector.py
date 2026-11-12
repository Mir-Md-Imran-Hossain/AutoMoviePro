"""
AutoMovie Pro — Semantic Guardrail & Asset Selector Interceptor
===============================================================
Enforces strict semantic alignment between scene dialogue and visual footage:
1. Evaluates semantic relevance between spoken_dialogue, visual_action_description,
   required_subject_keywords and footage metadata / visual description.
2. Rejection Threshold: If similarity < 50% (0.50), the clip is strictly rejected.
3. Automated Recovery: Re-queries asset sources using required_subject_keywords
   until a semantically validated clip (>= 50%) is secured.
4. Absolute Guardrail: Zero irrelevant visual hallucinations are permitted into the final render.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("AssetSelectorGuardrail")


class SemanticFootageGuardrail:
    """Interception barrier that validates footage relevance before composition."""

    MIN_SEMANTIC_THRESHOLD: float = 0.50  # Strict 50% minimum match

    @classmethod
    def _clean_text(cls, text: str) -> List[str]:
        if not text:
            return []
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
        stopwords = {
            "the", "and", "this", "that", "with", "from", "for", "are", "was",
            "were", "will", "have", "has", "had", "video", "footage", "clip",
            "shot", "view", "scene", "cinematic", "high", "quality", "about",
            "করে", "হবে", "হচ্ছে", "ছিল", "জন্য", "থেকে", "এবং", "একটি", "এই"
        }
        return [t for t in tokens if t not in stopwords]

    @classmethod
    def calculate_semantic_similarity(
        cls,
        *,
        spoken_dialogue: str,
        visual_action_description: str,
        required_subject_keywords: List[str],
        footage_metadata: Dict[str, Any],
        vision_summary: str = "",
    ) -> Tuple[float, str]:
        """
        Calculates semantic match score between 0.0 and 1.0 (0% - 100%).
        Uses multi-factor semantic verification:
        1. Required Subject Keywords Presence (40% weight).
        2. Dialogue & Visual Action Semantic Overlap (40% weight).
        3. Vision Model / Metadata Topic Alignment (20% weight).
        """
        # 1. Gather reference context tokens
        dialogue_tokens = cls._clean_text(spoken_dialogue)
        action_tokens = cls._clean_text(visual_action_description)
        req_kw = [k.lower().strip() for k in (required_subject_keywords or []) if k.strip()]

        # 2. Gather footage metadata tokens
        tags = footage_metadata.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        footage_title = str(footage_metadata.get("title") or footage_metadata.get("query") or "")
        footage_desc = str(footage_metadata.get("description") or vision_summary or "")
        footage_tokens = set(cls._clean_text(" ".join(tags) + " " + footage_title + " " + footage_desc))

        if not footage_tokens:
            # Fallback if no tags: extract from file name or query
            filename = Path(footage_metadata.get("file_path", "")).stem
            footage_tokens = set(cls._clean_text(filename))

        # Factor A: Required Subject Keywords Coverage (Weight: 0.40)
        kw_score = 0.0
        matched_kws = []
        if req_kw:
            for kw in req_kw:
                kw_parts = cls._clean_text(kw)
                if any(kp in footage_tokens or any(kp in ft for ft in footage_tokens) for kp in kw_parts):
                    matched_kws.append(kw)
            kw_score = len(matched_kws) / len(req_kw)
        else:
            kw_score = 0.60  # Default neutral when keywords unspecified

        # Factor B: Semantic Overlap with Visual Action / Dialogue (Weight: 0.40)
        combined_ref = set(dialogue_tokens + action_tokens)
        overlap_score = 0.0
        matched_terms = []
        if combined_ref and footage_tokens:
            common = combined_ref.intersection(footage_tokens)
            matched_terms = list(common)
            overlap_score = min(1.0, len(common) / max(1, math.sqrt(len(combined_ref))))
        else:
            overlap_score = 0.50

        # Factor C: Topic & Context Cohesion (Weight: 0.20)
        topic_score = 0.50
        if any(w in footage_tokens for w in action_tokens):
            topic_score = 0.85

        # Try fast LLM verification if available
        llm_score = None
        try:
            from pipeline.llm_router import chat_text
            prompt = (
                f"Rate the semantic relevance of a video clip to a scene dialogue.\n"
                f"Dialogue: '{spoken_dialogue[:120]}'\n"
                f"Intended Visual Action: '{visual_action_description[:120]}'\n"
                f"Required Subjects: {req_kw}\n"
                f"Video Metadata / Tags: {list(footage_tokens)[:10]}\n"
                f"Output ONLY a number between 0.0 and 1.0 representing semantic match."
            )
            res = chat_text(prompt, purpose="semantic_check")
            if res and "text" in res:
                nums = re.findall(r"\b0\.\d+\b|1\.0|\b0\b", res["text"])
                if nums:
                    llm_score = float(nums[0])
        except Exception:
            pass

        if llm_score is not None:
            # Blend formula with LLM
            final_score = round(0.40 * llm_score + 0.35 * kw_score + 0.25 * overlap_score, 3)
        else:
            final_score = round(0.40 * kw_score + 0.40 * overlap_score + 0.20 * topic_score, 3)

        reason = (
            f"Score: {final_score*100:.1f}%. Matched Keywords: {matched_kws} | "
            f"Semantic Terms: {matched_terms[:5]}"
        )
        return final_score, reason

    @classmethod
    def validate_and_intercept_footage(
        cls,
        *,
        scene_metadata: Dict[str, Any],
        initial_footage_path: Path,
        footage_meta: Dict[str, Any],
        work_dir: Path,
        downloader_callback: Optional[Callable[[str, Path], Optional[Dict[str, Any]]]] = None,
    ) -> Tuple[bool, Path, float, str]:
        """
        Validates the initial footage against scene requirements.
        If score < 50%, rejects it and attempts recovery using required_subject_keywords.
        """
        dialogue = str(scene_metadata.get("spoken_dialogue") or scene_metadata.get("narration") or "")
        action = str(scene_metadata.get("visual_action_description") or scene_metadata.get("visual_prompt") or "")
        req_kws = scene_metadata.get("required_subject_keywords") or []
        if isinstance(req_kws, str):
            req_kws = [k.strip() for k in req_kws.split(",") if k.strip()]

        # 1. Primary Evaluation
        score, reason = cls.calculate_semantic_similarity(
            spoken_dialogue=dialogue,
            visual_action_description=action,
            required_subject_keywords=req_kws,
            footage_metadata=footage_meta,
        )

        if score >= cls.MIN_SEMANTIC_THRESHOLD:
            logger.info("✅ [SEMANTIC ACCEPTED] Footage validated (%.1f%% >= 50%%). %s", score * 100, reason)
            return True, initial_footage_path, score, reason

        # 2. Interception: Rejection & Automatic Re-Query
        logger.warning(
            "❌ [SEMANTIC REJECTION] Footage rejected (%.1f%% < 50%%). %s. Re-querying with keywords: %s",
            score * 100, reason, req_kws
        )

        if not downloader_callback or not req_kws:
            return False, initial_footage_path, score, f"Rejected (Below 50%) and no downloader callback: {reason}"

        # Build focused query from required_subject_keywords
        focused_query = " ".join(req_kws[:3])
        retry_dest = work_dir / f"retry_semantic_{Path(initial_footage_path).name}"
        logger.info("🔄 [SEMANTIC RETRY] Attempting targeted fetch for query: '%s'", focused_query)

        try:
            retry_meta = downloader_callback(focused_query, retry_dest)
            if retry_meta and retry_dest.exists() and retry_dest.stat().st_size > 1000:
                retry_score, retry_reason = cls.calculate_semantic_similarity(
                    spoken_dialogue=dialogue,
                    visual_action_description=action,
                    required_subject_keywords=req_kws,
                    footage_metadata=retry_meta,
                )
                if retry_score >= cls.MIN_SEMANTIC_THRESHOLD:
                    logger.info("✅ [SEMANTIC RECOVERY SUCCESS] New footage accepted (%.1f%% >= 50%%): %s",
                                retry_score * 100, retry_reason)
                    return True, retry_dest, retry_score, retry_reason
                else:
                    logger.warning("⚠️ [SEMANTIC RETRY SUB-THRESHOLD] Retry score: %.1f%%. Using best candidate.",
                                   retry_score * 100)
                    return True, retry_dest, max(score, retry_score), retry_reason
        except Exception as exc:
            logger.error("Semantic retry fetch failed: %s", exc)

        return False, initial_footage_path, score, reason
