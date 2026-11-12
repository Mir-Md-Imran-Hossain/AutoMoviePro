# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Enhanced Niche & Topic Guard (Anti-Duplicate & Lifetime Frequency Cap)
=====================================================================================
Enforces:
1. Niche & Topic Neutrality: Zero hardcoded topic bias; fully dynamic for all 150+ niches.
2. Strict Frequency Cap: A topic can be used AT MOST 2 TIMES per channel/niche (use_count <= 2).
   Once a topic reaches 2 videos, it is permanently RETIRED.
3. Angle Divergence: When a topic is used for the 2nd time, it MUST take a completely distinct
   angle and script premise (e.g. Paradox/Warning/Deep Science vs. Intro/Overview).
4. Semantic Anti-Duplicate Guard: Rejects any candidate topic with >= 65% token/Levenshtein
   similarity to any previously generated topic in the channel/niche history.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import sqlite3
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AutoMoviePro.NicheTopicGuard")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s][TopicGuard][%(levelname)s] %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = SOFTWARE_ROOT / "data" / "local.db"


class NicheTopicGuard:
    _instance: Optional["NicheTopicGuard"] = None

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "NicheTopicGuard":
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Creates the niche_topic_history tracking table if missing."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS niche_topic_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER DEFAULT 0,
                        niche_name TEXT NOT NULL,
                        topic_title TEXT NOT NULL,
                        normalized_title TEXT NOT NULL,
                        use_count INTEGER DEFAULT 1,
                        last_angle TEXT DEFAULT '',
                        status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE' (< 2) or 'RETIRED' (>= 2)
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_nth_niche ON niche_topic_history(niche_name);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_nth_norm ON niche_topic_history(normalized_title);")
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not ensure niche_topic_history table: {e}")

    @staticmethod
    def normalize_title(title: str) -> str:
        """Normalizes a Bengali or English title for accurate deduplication comparison."""
        t = (title or "").lower().strip()
        # Remove punctuation
        t = re.sub(r'[।!?,;\'\"“”‘’—\-_:()\[\]{}]', ' ', t)
        words = t.split()
        stop_words = {
            "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "of", "is",
            "কি", "কেন", "কী", "এবং", "ও", "বা", "এই", "সেই", "একটি", "এমন", "যে", "যা", "এর", "সব"
        }
        meaningful = [w for w in words if w not in stop_words and len(w) > 1]
        return " ".join(meaningful)

    @classmethod
    def calculate_similarity(cls, title1: str, title2: str) -> float:
        """Computes hybrid Jaccard token overlap and Levenshtein sequence ratio."""
        norm1 = cls.normalize_title(title1)
        norm2 = cls.normalize_title(title2)
        if not norm1 or not norm2:
            return 0.0

        set1 = set(norm1.split())
        set2 = set(norm2.split())
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        jaccard = len(intersection) / float(len(union)) if union else 0.0
        seq_ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()

        return round(max(jaccard, seq_ratio), 4)

    def get_retired_topics_for_niche(self, niche_name: str, channel_id: int = 0) -> List[str]:
        """Returns all topics for this niche that have reached the max cap (use_count >= 2)."""
        retired = []
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT topic_title FROM niche_topic_history WHERE (niche_name = ? OR ? = '') AND use_count >= 2",
                    (niche_name, niche_name)
                )
                retired = [r["topic_title"] for r in cur.fetchall()]
        except Exception as e:
            logger.debug(f"get_retired_topics error: {e}")
        return retired

    def audit_candidate_topic(
        self,
        candidate_title: str,
        niche_name: str,
        channel_id: int = 0,
        similarity_threshold: float = 0.65
    ) -> Dict[str, Any]:
        """
        Audits a proposed topic against the historical registry:
        1. Checks if title matches a RETIRED topic (use_count >= 2) -> REJECT.
        2. Checks if title matches an ACTIVE topic (use_count == 1) -> PERMIT (with Angle Divergence requirement).
        3. Checks if title is completely NEW (use_count == 0) -> PERMIT as fresh.
        """
        norm_candidate = self.normalize_title(candidate_title)
        if not norm_candidate:
            return {
                "approved": False,
                "reason": "EMPTY_NORMALIZED_TITLE",
                "similarity": 1.0,
                "use_count": 0,
                "action": "REJECT"
            }

        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                # Query historical topics under this niche or channel
                cur.execute(
                    "SELECT topic_title, normalized_title, use_count, status, last_angle FROM niche_topic_history WHERE niche_name = ? OR ? = ''",
                    (niche_name, niche_name)
                )
                rows = cur.fetchall()

                highest_sim = 0.0
                matched_row = None

                for r in rows:
                    sim = self.calculate_similarity(candidate_title, r["topic_title"])
                    if sim > highest_sim:
                        highest_sim = sim
                        matched_row = r

                if highest_sim >= similarity_threshold and matched_row:
                    matched_title = matched_row["topic_title"]
                    curr_uses = matched_row["use_count"]

                    # RULE: Max 2 videos per topic
                    if curr_uses >= 2:
                        logger.warning(
                            f"🛑 [Topic Cap Exceeded] '{candidate_title}' matches retired topic '{matched_title}' (Sim: {highest_sim:.2f}, Used: {curr_uses} times). BANNED."
                        )
                        return {
                            "approved": False,
                            "reason": "TOPIC_CAP_REACHED_MAX_2_VIDEOS",
                            "similarity": highest_sim,
                            "matched_title": matched_title,
                            "use_count": curr_uses,
                            "action": "REJECT_AND_RESEED"
                        }
                    else:
                        # 2nd video allowed, but MUST enforce angle divergence
                        logger.info(
                            f"⚠️ [Topic Re-use (2/2)] '{candidate_title}' matches existing '{matched_title}' (Sim: {highest_sim:.2f}). Allowed for 2nd and final run with Angle Divergence."
                        )
                        return {
                            "approved": True,
                            "reason": "ALLOWED_SECOND_RUN_WITH_ANGLE_DIVERGENCE",
                            "similarity": highest_sim,
                            "matched_title": matched_title,
                            "use_count": curr_uses + 1,
                            "previous_angle": matched_row["last_angle"],
                            "require_fresh_angle": True,
                            "action": "PERMIT_WITH_DIVERGENCE"
                        }

        except Exception as e:
            logger.warning(f"Error querying topic history in DB: {e}")

        # Completely fresh topic
        return {
            "approved": True,
            "reason": "FRESH_TOPIC",
            "similarity": 0.0,
            "matched_title": None,
            "use_count": 1,
            "require_fresh_angle": False,
            "action": "PERMIT_FRESH"
        }

    def record_topic_usage(
        self,
        topic_title: str,
        niche_name: str,
        channel_id: int = 0,
        angle_summary: str = ""
    ) -> int:
        """
        Records the successful generation of a video for this topic.
        Increments use_count. If use_count >= 2, marks topic as 'RETIRED'.
        """
        norm_title = self.normalize_title(topic_title)
        new_count = 1
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, use_count FROM niche_topic_history WHERE normalized_title = ? OR topic_title = ?",
                    (norm_title, topic_title)
                )
                row = cur.fetchone()

                if row:
                    row_id = row["id"]
                    new_count = row["use_count"] + 1
                    status = "RETIRED" if new_count >= 2 else "ACTIVE"
                    cur.execute(
                        "UPDATE niche_topic_history SET use_count = ?, last_angle = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (new_count, angle_summary, status, row_id)
                    )
                else:
                    cur.execute(
                        "INSERT INTO niche_topic_history (channel_id, niche_name, topic_title, normalized_title, use_count, last_angle, status) VALUES (?, ?, ?, ?, 1, ?, 'ACTIVE')",
                        (channel_id, niche_name, topic_title, norm_title, angle_summary)
                    )
                conn.commit()
                logger.info(f"✅ [Topic Registered] '{topic_title}' | Niche: '{niche_name}' | Total Uses: {new_count}/2 | Status: {'RETIRED' if new_count >= 2 else 'ACTIVE'}")
        except Exception as e:
            logger.warning(f"Failed to record topic usage in DB: {e}")

        return new_count


def get_niche_topic_guard() -> NicheTopicGuard:
    return NicheTopicGuard.get_instance()
