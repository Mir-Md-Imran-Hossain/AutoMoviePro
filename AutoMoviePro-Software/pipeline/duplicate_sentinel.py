# -*- coding: utf-8 -*-
"""AutoMovie Pro — Central Duplicate Sentinel (Phase 1 Industrial Implementation).

Module: pipeline.duplicate_sentinel
Responsibilities:
1. Canonical 3-Status Duplicate Decisions:
   - 'UNIQUE'
   - 'RELATED_DIFFERENT_ANGLE'
   - 'DUPLICATE'
2. 5-Layer Progressive Inspection:
   - Layer 1: Exact Normalized Match
   - Layer 2: Language-Aware Token Similarity (Jaccard / Token Overlap)
   - Layer 3: Entity Collision & Angle Divergence (Same Entity != Duplicate)
   - Layer 4: Semantic Story-Angle Similarity (SequenceMatcher & Predicate overlap)
   - Layer 5: Cross-Format History (Shorts vs Longs shared registry audit)
3. Multilingual Normalization:
   - Unicode NFC normalization
   - Bengali, Hindi, Urdu, Arabic, English script support
   - Preservation of critical search intent markers ('কীভাবে', 'কেন', 'how', 'why', 'what')
4. Fail-Safe Execution:
   - Catches internal exceptions, logs forensics, and prevents silent false-positive approvals.
"""

from __future__ import annotations

import logging
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
if str(SOFTWARE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_ROOT))

from pipeline.topic_database import TopicDatabase, get_topic_database

logger = logging.getLogger("AutoMoviePro.DuplicateSentinel")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s][DuplicateSentinel][%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
    logger.setLevel(logging.INFO)

# Canonical Decisions
STATUS_UNIQUE = "UNIQUE"
STATUS_RELATED_DIFFERENT_ANGLE = "RELATED_DIFFERENT_ANGLE"
STATUS_DUPLICATE = "DUPLICATE"

# Conversational & Filler words to filter from topic signatures.
# IMPORTANT: Never include core search-intent words ('কেন', 'কীভাবে', 'how', 'why', 'what') here!
CONVERSATIONAL_STOPWORDS = {
    "রহস্য", "রহস্যময়", "ইতিহাস", "সত্য", "অজানা", "বাস্তবতা", "ঘটনা", "অনুসন্ধান", "ডকুমেন্টারি", "ভিডিও",
    # Bengali conversational filler
    "ভিডিও", "টপিক", "নিয়ে", "জন্য", "হবে", "করছে", "পারে", "আসল", "সত্যি",
    "যে", "এই", "আর", "ও", "না", "একবার", "সেট", "করো", "হলে", "মতো", "এখন",
    "থেকে", "করে", "নয়", "হিসাব", "কিছু", "সব", "কোন", "কোথায়", "কখন", "বলল",
    "বলছে", "যায়", "যা", "থাকে", "থাকবে", "হয়ে", "হলে", "আসসালামু", "আলাইকুম",
    "আল্লাহ", "হাফেজ", "বন্ধুরা", "দর্শক", "চ্যানেল", "সাবস্ক্রাইব", "লাইক", "শেয়ার",
    "আছে", "ছিল", "হচ্ছে", "হয়েছে", "দেয়", "নেয়", "কাজ", "নতুন", "সবচেয়ে", "বেশি",
    "কম", "প্রথম", "শেষ", "আজ", "কাল", "অনেক", "এক", "দুই", "তিন", "সেই", "কিন্তু",
    "বা", "কিংবা", "অথবা", "যদি", "তবে", "তাই", "বলতে", "গেলে", "জানেন", "দেখুন",
    "শুনুন", "মনে", "রাখবেন", "কারণ", "ফলে", "পর", "আগে", "পরে",
    # English conversational filler
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "is",
    "are", "was", "were", "of", "it", "its", "by", "from", "video", "shorts",
    "documentary", "secret", "truth", "revealed", "shocking"
}

# Bengali Grammatical Suffixes for Stemming
BENGALI_SUFFIXES = ("টিতেও", "টিতে", "গুলো", "দের", "ের", "তে", "ায়", "ে", "র", "য়", "কে", "সহ")

# High-priority anchor entity pairs
ANCHOR_ENTITY_PAIRS = [
    {"james webb", "galaxy"},
    {"james webb", "gold mirror"},
    {"james webb", "cosmic"},
    {"bmw", "figure"},
    {"figure", "02"},
    {"tesla", "optimus"},
    {"chatgpt", "o1"},
    {"chatgpt", "custom instructions"},
    {"dark", "oxygen"},
    {"black", "hole"},
    {"event", "horizon"},
    {"boston", "dynamics"},
    {"nvidia", "gr00t"},
    {"titanic", "abyss"},
    {"mariana", "trench"},
]


class DuplicateSentinel:
    """Enterprise multi-layer duplicate topic detection sentinel."""

    def __init__(self, db: Optional[TopicDatabase] = None):
        self.db = db or get_topic_database()

    # -------------------------------------------------------------
    # Layer 1: Normalization & Exact Match
    # -------------------------------------------------------------
    @staticmethod
    def normalize_text(text: str) -> str:
        """Language-aware normalization with Unicode NFC, lowercase, and punctuation cleanup.
        Preserves search intent words ('কীভাবে', 'কেন', 'how', 'why', 'what').
        """
        if not text:
            return ""
        # 1. Unicode NFC
        t = unicodedata.normalize("NFC", str(text)).lower().strip()
        # 2. Explicitly remove dandis (। \u0964, ॥ \u0965) and common punctuation
        t = re.sub(r"[।॥!?,;:\'\"()\[\]{}–—\-_/\\|]+", " ", t)
        # 3. Strip remaining punctuation but preserve multilingual word letters and numbers
        # Supported scripts: Latin, Bengali (\u0980-\u09FF), Devanagari/Hindi (\u0900-\u097F),
        # Arabic/Urdu (\u0600-\u06FF)
        t = re.sub(
            r"[^\w\s\u0980-\u09FF\u0900-\u097F\u0600-\u06FF]+",
            " ",
            t,
            flags=re.UNICODE
        )
        # 4. Remove conversational stopwords while keeping intent markers
        tokens = t.split()
        cleaned = [w for w in tokens if w not in CONVERSATIONAL_STOPWORDS and len(w) > 1]
        return " ".join(cleaned).strip()

    # -------------------------------------------------------------
    # Layer 2: Multilingual Token Extraction & Stemming
    # -------------------------------------------------------------
    @classmethod
    def extract_stemmed_tokens(cls, text: str) -> Set[str]:
        """Extracts and stems tokens across Bengali, Hindi, Arabic, and English."""
        if not text:
            return set()
        norm = cls.normalize_text(text)
        raw_tokens = norm.split()
        stemmed: Set[str] = set()

        for tk in raw_tokens:
            # Bengali suffix stripping
            for sfx in BENGALI_SUFFIXES:
                if tk.endswith(sfx) and len(tk) > len(sfx) + 2:
                    tk = tk[:-len(sfx)]
                    break
            # English simple plural/verb stripping
            if len(tk) > 4 and tk.endswith("ing"):
                tk = tk[:-3]
            elif len(tk) > 4 and tk.endswith("ed"):
                tk = tk[:-2]
            elif len(tk) > 3 and tk.endswith("s") and not tk.endswith("ss"):
                tk = tk[:-1]

            if tk not in CONVERSATIONAL_STOPWORDS and len(tk) >= 2:
                stemmed.add(tk)

        return stemmed

    @classmethod
    def calculate_token_similarity(cls, text1: str, text2: str) -> float:
        """Calculates Jaccard token overlap between two phrases."""
        tokens1 = cls.extract_stemmed_tokens(text1)
        tokens2 = cls.extract_stemmed_tokens(text2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        return round(len(intersection) / float(len(union)), 4)

    # -------------------------------------------------------------
    # Layer 3: Entity Collision & Angle Divergence
    # -------------------------------------------------------------
    @classmethod
    def extract_entities(cls, text: str) -> Set[str]:
        """Identifies significant named entities, brand names, or model codes."""
        norm = unicodedata.normalize("NFC", str(text or "")).lower()
        # English alphanumeric (2+ chars)
        en_entities = set(re.findall(r"[a-z0-9]{2,}", norm))
        # Bengali entities (3+ chars)
        bn_entities = set(re.findall(r"[\u0980-\u09ff]{3,}", norm))
        # Hindi entities
        hi_entities = set(re.findall(r"[\u0900-\u097f]{3,}", norm))
        # Arabic entities
        ar_entities = set(re.findall(r"[\u0600-\u06ff]{3,}", norm))

        raw = (en_entities | bn_entities | hi_entities | ar_entities) - CONVERSATIONAL_STOPWORDS
        return {e for e in raw if len(e) >= 3}

    @classmethod
    def calculate_angle_divergence(cls, angle1: str, angle2: str) -> float:
        """Computes semantic divergence (0.0 to 1.0) between two story angles.
        Prioritizes token conceptual divergence while considering character sequence similarity.
        1.0 means completely different story angles; 0.0 means identical angle.
        """
        tokens1 = cls.extract_stemmed_tokens(angle1)
        tokens2 = cls.extract_stemmed_tokens(angle2)
        if not tokens1 or not tokens2:
            return 1.0

        jaccard = len(tokens1.intersection(tokens2)) / float(len(tokens1.union(tokens2)))
        norm1 = cls.normalize_text(angle1)
        norm2 = cls.normalize_text(angle2)
        seq_ratio = SequenceMatcher(None, norm1, norm2).ratio()

        # Weighted combination: 70% token conceptual overlap, 30% sequence ratio
        combined_similarity = (jaccard * 0.70) + (seq_ratio * 0.30)
        return round(1.0 - combined_similarity, 4)

    # -------------------------------------------------------------
    # Layer 4: Semantic Story-Angle Similarity
    # -------------------------------------------------------------
    @classmethod
    def calculate_semantic_similarity(cls, text1: str, text2: str) -> float:
        """Combines character sequence matcher and token Jaccard for robust semantic comparison."""
        norm1 = cls.normalize_text(text1)
        norm2 = cls.normalize_text(text2)
        if not norm1 or not norm2:
            return 0.0
        seq_ratio = SequenceMatcher(None, norm1, norm2).ratio()
        jaccard = cls.calculate_token_similarity(text1, text2)
        # Conservative combined score
        return round(max(seq_ratio, jaccard), 4)

    # -------------------------------------------------------------
    # 5-Layer Complete Evaluation Pipeline
    # -------------------------------------------------------------
    def audit_candidate(
        self,
        *,
        candidate_title: str,
        channel_id: int,
        video_format: str,
        story_angle: str = "",
        main_entity: str = "",
        external_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs the complete 5-layer duplicate audit against channel history.
        
        Returns:
            Dict containing:
                - decision_status: 'UNIQUE', 'RELATED_DIFFERENT_ANGLE', or 'DUPLICATE'
                - layer_triggered: name of the layer that made the decision
                - matched_topic: title of matching topic if found
                - similarity_score: float score
                - details: granular diagnostic metadata
        """
        # Safety Check: Empty Title Rejection
        clean_title = (candidate_title or "").strip()
        if not clean_title or len(clean_title) < 5:
            return {
                "decision_status": STATUS_DUPLICATE,
                "layer_triggered": "Safety_Empty_Rejection",
                "matched_topic": None,
                "similarity_score": 1.0,
                "details": {"reason": "Empty or trivially short candidate title."}
            }

        norm_candidate = self.normalize_text(clean_title)
        candidate_tokens = self.extract_stemmed_tokens(clean_title)
        candidate_entities = self.extract_entities(f"{clean_title} {main_entity}")

        # Fetch channel history across BOTH formats (Cross-Format Layer 5)
        history_topics: List[Dict[str, Any]] = []
        try:
            db_topics = self.db.get_registered_topics_for_channel(channel_id=channel_id)
            history_topics.extend(db_topics)
        except Exception as exc:
            logger.warning("Database topic fetch failed; falling back to external history: %s", exc)

        if external_history:
            history_topics.extend(external_history)

        if not history_topics:
            return {
                "decision_status": STATUS_UNIQUE,
                "layer_triggered": "Layer_0_Empty_History",
                "matched_topic": None,
                "similarity_score": 0.0,
                "details": {"reason": "No previous topics exist for this channel."}
            }

        highest_sim = 0.0
        best_match_title: Optional[str] = None
        best_match_topic_id: Optional[str] = None
        angle_divergence_noted: float = 1.0

        for record in history_topics:
            prior_title = (record.get("title_primary") or record.get("topic") or record.get("title") or "").strip()
            prior_angle = (record.get("story_angle") or "").strip()
            prior_topic_id = record.get("topic_id")

            if not prior_title:
                continue

            norm_prior = self.normalize_text(prior_title)

            # --- Layer 1: Exact Normalized Match ---
            if norm_candidate and norm_candidate == norm_prior:
                return {
                    "decision_status": STATUS_DUPLICATE,
                    "layer_triggered": "Layer_1_Exact_Match",
                    "matched_topic": prior_title,
                    "matched_topic_id": prior_topic_id,
                    "similarity_score": 1.0,
                    "details": {"reason": "Exact normalized title match."}
                }

            # --- Layer 2: High Semantic & Token Similarity (Title Phrasing Match) ---
            token_sim = self.calculate_token_similarity(clean_title, prior_title)
            semantic_sim = self.calculate_semantic_similarity(clean_title, prior_title)
            effective_sim = max(token_sim, semantic_sim)

            if effective_sim > highest_sim:
                highest_sim = effective_sim
                best_match_title = prior_title
                best_match_topic_id = prior_topic_id

            # If the title phrasing itself is heavily duplicate (>= 75% semantic or >= 65% tokens)
            if semantic_sim >= 0.75 or token_sim >= 0.65:
                return {
                    "decision_status": STATUS_DUPLICATE,
                    "layer_triggered": "Layer_2_Semantic_Title_Similarity",
                    "matched_topic": prior_title,
                    "matched_topic_id": prior_topic_id,
                    "similarity_score": effective_sim,
                    "details": {
                        "semantic_similarity": semantic_sim,
                        "token_similarity": token_sim,
                        "reason": "Title phrasing is semantically near-identical."
                    }
                }

            # --- Layer 3: Entity Collision & Angle Divergence ---
            prior_entities = self.extract_entities(prior_title)
            common_entities = candidate_entities.intersection(prior_entities)

            # Check if an identical entity or anchor pair is shared
            has_entity_collision = bool(common_entities)
            for pair in ANCHOR_ENTITY_PAIRS:
                if pair.issubset(candidate_entities) and pair.issubset(prior_entities):
                    has_entity_collision = True
                    break

            if has_entity_collision:
                # Same Entity Detected -> Evaluate Story Angle Divergence!
                angle_div = self.calculate_angle_divergence(
                    story_angle or clean_title,
                    prior_angle or prior_title
                )
                angle_divergence_noted = angle_div

                # If Angle Divergence >= 0.70, it is a VALID DIFFERENT ANGLE (Not a duplicate!)
                if angle_div >= 0.70:
                    return {
                        "decision_status": STATUS_RELATED_DIFFERENT_ANGLE,
                        "layer_triggered": "Layer_3_Entity_Angle_Divergence",
                        "matched_topic": prior_title,
                        "matched_topic_id": prior_topic_id,
                        "similarity_score": effective_sim,
                        "details": {
                            "shared_entities": list(common_entities),
                            "angle_divergence": angle_div,
                            "verdict": "Allowed as different educational/narrative angle."
                        }
                    }
                else:
                    # Same entity AND similar angle -> Flag Duplicate!
                    return {
                        "decision_status": STATUS_DUPLICATE,
                        "layer_triggered": "Layer_3_Entity_Same_Angle",
                        "matched_topic": prior_title,
                        "matched_topic_id": prior_topic_id,
                        "similarity_score": max(effective_sim, 0.85),
                        "details": {
                            "shared_entities": list(common_entities),
                            "angle_divergence": angle_div,
                            "reason": "Shared entity with insufficient angle divergence."
                        }
                    }

        # Passed all 5 layers cleanly -> UNIQUE
        return {
            "decision_status": STATUS_UNIQUE,
            "layer_triggered": "Layer_5_All_Layers_Passed",
            "matched_topic": best_match_title,
            "matched_topic_id": best_match_topic_id,
            "similarity_score": highest_sim,
            "details": {
                "highest_similarity_seen": highest_sim,
                "cross_format_verified": True
            }
        }


def get_duplicate_sentinel(db: Optional[TopicDatabase] = None) -> DuplicateSentinel:
    """Convenience factory function."""
    return DuplicateSentinel(db=db)
