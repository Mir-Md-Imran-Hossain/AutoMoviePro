# -*- coding: utf-8 -*-
"""AutoMovie Pro — Central Topic Database (Phase 1 Industrial Implementation).

Module: pipeline.topic_database
Responsibilities:
1. Relational SQLite management for Topic Candidates, Approved Topics, Research Evidence,
   Duplicate Audit Logs, Validation Reports, and Retry History.
2. Thread-safe transactional isolation using BEGIN IMMEDIATE to guarantee zero race-conditions.
3. Cross-format (Shorts vs Longs) deduplication enforcement per channel.
4. Flexible multilingual storage without hardcoded English/Bengali requirements.
5. Permissive pre-ranking state (nullable TRS score until candidate ranking completes).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple

logger = logging.getLogger("AutoMoviePro.TopicDatabase")
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(asctime)s][TopicDatabase][%(levelname)s] %(message)s"))
    logger.addHandler(_ch)
    logger.setLevel(logging.INFO)

SOFTWARE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = SOFTWARE_ROOT / "data" / "intelligence" / "topic_registry.db"


class TopicDatabase:
    """Industrial Central SQLite Database for Topic Intelligence."""

    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._open_conns: List[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection with WAL mode and foreign keys enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None  # Explicit transaction management
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            self._local.conn = conn
            with self._conns_lock:
                self._open_conns.append(conn)
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides an exclusive/immediate transaction block for atomic operations."""
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def _init_db(self) -> None:
        """Initializes tables, indexes, and constraints if they do not exist."""
        with self.transaction() as conn:
            # 1. Candidates table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_candidates (
                candidate_id TEXT PRIMARY KEY,
                cycle_id TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                niche TEXT NOT NULL,
                video_format TEXT NOT NULL CHECK(video_format IN ('short', 'long')),
                title_primary TEXT NOT NULL,
                title_secondary TEXT,
                main_entity TEXT NOT NULL,
                story_angle TEXT NOT NULL,
                search_intent TEXT,
                trs_score REAL,  -- Nullable until candidate ranking completes
                selection_status TEXT NOT NULL CHECK(selection_status IN (
                    'PENDING', 'WINNER', 'REJECTED_LOW_SCORE', 'REJECTED_DUPLICATE', 'REJECTED_POLICY'
                )),
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. Approved Topic Registry table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_registry (
                topic_id TEXT PRIMARY KEY,
                candidate_id TEXT UNIQUE NOT NULL,
                channel_id INTEGER NOT NULL,
                niche TEXT NOT NULL,
                video_format TEXT NOT NULL CHECK(video_format IN ('short', 'long')),
                normalized_signature TEXT NOT NULL,
                title_primary TEXT NOT NULL,
                title_secondary TEXT,
                main_entity TEXT,
                story_angle TEXT,
                primary_keyword TEXT,
                seo_metadata_json TEXT NOT NULL,
                trs_score REAL NOT NULL,
                mqs_score REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('approved', 'in_production', 'published', 'archived')),
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES topic_candidates(candidate_id),
                CONSTRAINT uq_channel_format_sig UNIQUE (channel_id, video_format, normalized_signature)
            );
            """)

            # 3. Research Evidence table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS research_evidence (
                evidence_id TEXT PRIMARY KEY,
                candidate_id TEXT,
                source TEXT NOT NULL,
                query TEXT NOT NULL,
                country TEXT NOT NULL,
                language TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                is_verified INTEGER NOT NULL CHECK(is_verified IN (0, 1)),
                payload_json TEXT NOT NULL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES topic_candidates(candidate_id) ON DELETE CASCADE
            );
            """)

            # 4. Duplicate Audit Log table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_audit_log (
                audit_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                matched_topic_id TEXT,
                matched_title TEXT,
                exact_match INTEGER NOT NULL CHECK(exact_match IN (0, 1)),
                token_similarity REAL NOT NULL,
                entity_collision INTEGER NOT NULL CHECK(entity_collision IN (0, 1)),
                angle_divergence REAL NOT NULL,
                decision_status TEXT NOT NULL CHECK(decision_status IN ('UNIQUE', 'RELATED_DIFFERENT_ANGLE', 'DUPLICATE')),
                layer_triggered TEXT NOT NULL,
                details_json TEXT,
                audited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES topic_candidates(candidate_id) ON DELETE CASCADE
            );
            """)

            # 5. Validation Reports table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS validation_reports (
                report_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                mqs_score REAL NOT NULL,
                fact_score REAL NOT NULL,
                policy_safe INTEGER NOT NULL CHECK(policy_safe IN (0, 1)),
                verdict TEXT NOT NULL CHECK(verdict IN ('APPROVED', 'RETRY', 'FAILED')),
                issues_json TEXT,
                feedback_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES topic_candidates(candidate_id) ON DELETE CASCADE
            );
            """)

            # 6. Retry History table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS retry_history (
                retry_id TEXT PRIMARY KEY,
                cycle_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                rejected_candidate_id TEXT,
                rejection_reason TEXT NOT NULL,
                prompt_adjustments TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Critical Performance Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reg_sig ON topic_registry(normalized_signature);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reg_ch_fmt ON topic_registry(channel_id, video_format);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cand_cycle ON topic_candidates(cycle_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cand_ch ON topic_candidates(channel_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_cand ON research_evidence(candidate_id);")

        logger.info("TopicDatabase schema initialized at %s", self.db_path)

    # -------------------------------------------------------------
    # Candidate Management
    # -------------------------------------------------------------
    def record_candidate(
        self,
        *,
        candidate_id: str,
        cycle_id: str,
        channel_id: int,
        niche: str,
        video_format: str,
        title_primary: str,
        main_entity: str,
        story_angle: str,
        title_secondary: Optional[str] = None,
        search_intent: Optional[str] = None,
        trs_score: Optional[float] = None,
        selection_status: str = "PENDING",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Inserts a generated candidate topic record."""
        fmt = str(video_format).lower().strip()
        if fmt not in ("short", "long"):
            raise ValueError(f"Invalid video_format: '{video_format}'. Must be 'short' or 'long'.")

        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self.transaction() as conn:
            conn.execute("""
            INSERT INTO topic_candidates (
                candidate_id, cycle_id, channel_id, niche, video_format,
                title_primary, title_secondary, main_entity, story_angle,
                search_intent, trs_score, selection_status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                candidate_id, cycle_id, int(channel_id), niche.strip(), fmt,
                title_primary.strip(), (title_secondary or "").strip() or None,
                main_entity.strip(), story_angle.strip(),
                (search_intent or "").strip() or None,
                trs_score, selection_status, meta_json
            ))
        return {"candidate_id": candidate_id, "status": selection_status}

    def update_candidate_ranking(
        self,
        candidate_id: str,
        trs_score: float,
        selection_status: str
    ) -> bool:
        """Updates ranking score and status after multi-candidate evaluation."""
        with self.transaction() as conn:
            cursor = conn.execute("""
            UPDATE topic_candidates
            SET trs_score = ?, selection_status = ?
            WHERE candidate_id = ?;
            """, (float(trs_score), selection_status, candidate_id))
            return cursor.rowcount > 0

    # -------------------------------------------------------------
    # Evidence & Audit Logging
    # -------------------------------------------------------------
    def record_evidence(
        self,
        *,
        evidence_id: str,
        candidate_id: Optional[str],
        source: str,
        query: str,
        country: str,
        language: str,
        evidence_type: str,
        confidence: float,
        is_verified: bool,
        payload: Dict[str, Any],
    ) -> str:
        """Stores market & trend evidence metadata."""
        with self.transaction() as conn:
            conn.execute("""
            INSERT INTO research_evidence (
                evidence_id, candidate_id, source, query, country, language,
                evidence_type, confidence, is_verified, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                evidence_id, candidate_id, source, query, country, language,
                evidence_type, float(confidence), 1 if is_verified else 0,
                json.dumps(payload, ensure_ascii=False)
            ))
        return evidence_id

    def log_duplicate_audit(
        self,
        *,
        audit_id: str,
        candidate_id: str,
        decision_status: str,
        layer_triggered: str,
        exact_match: bool = False,
        token_similarity: float = 0.0,
        entity_collision: bool = False,
        angle_divergence: float = 1.0,
        matched_topic_id: Optional[str] = None,
        matched_title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Logs layer-by-layer duplicate audit decisions."""
        with self.transaction() as conn:
            conn.execute("""
            INSERT INTO duplicate_audit_log (
                audit_id, candidate_id, matched_topic_id, matched_title,
                exact_match, token_similarity, entity_collision, angle_divergence,
                decision_status, layer_triggered, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                audit_id, candidate_id, matched_topic_id, matched_title,
                1 if exact_match else 0, float(token_similarity),
                1 if entity_collision else 0, float(angle_divergence),
                decision_status, layer_triggered,
                json.dumps(details or {}, ensure_ascii=False)
            ))
        return audit_id

    def record_validation_report(
        self,
        *,
        report_id: str,
        candidate_id: str,
        attempt_number: int,
        mqs_score: float,
        fact_score: float,
        policy_safe: bool,
        verdict: str,
        issues: Optional[List[str]] = None,
        feedback_notes: str = "",
    ) -> str:
        """Records independent validator 11-point report."""
        with self.transaction() as conn:
            conn.execute("""
            INSERT INTO validation_reports (
                report_id, candidate_id, attempt_number, mqs_score,
                fact_score, policy_safe, verdict, issues_json, feedback_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                report_id, candidate_id, int(attempt_number), float(mqs_score),
                float(fact_score), 1 if policy_safe else 0, verdict,
                json.dumps(issues or [], ensure_ascii=False), feedback_notes
            ))
        return report_id

    # -------------------------------------------------------------
    # Topic Approval & Registry (Transactional Guard)
    # -------------------------------------------------------------
    def approve_topic(
        self,
        *,
        topic_id: str,
        candidate_id: str,
        channel_id: int,
        niche: str,
        video_format: str,
        normalized_signature: str,
        title_primary: str,
        primary_keyword: str,
        seo_metadata: Dict[str, Any],
        trs_score: float,
        mqs_score: float,
        title_secondary: Optional[str] = None,
        main_entity: Optional[str] = None,
        story_angle: Optional[str] = None,
        status: str = "approved",
    ) -> Dict[str, Any]:
        """Atomically approves and locks a topic in topic_registry.
        
        Raises:
            sqlite3.IntegrityError: If (channel_id, video_format, normalized_signature) or
                                   candidate_id already exists.
        """
        fmt = str(video_format).lower().strip()
        seo_json = json.dumps(seo_metadata, ensure_ascii=False)

        with self.transaction() as conn:
            # 1. Update candidate status to WINNER
            conn.execute("""
            UPDATE topic_candidates
            SET selection_status = 'WINNER'
            WHERE candidate_id = ?;
            """, (candidate_id,))

            # If main_entity or story_angle not passed, try to fetch from candidate
            m_entity = main_entity
            s_angle = story_angle
            if not m_entity or not s_angle:
                row = conn.execute(
                    "SELECT main_entity, story_angle FROM topic_candidates WHERE candidate_id = ?",
                    (candidate_id,)
                ).fetchone()
                if row:
                    m_entity = m_entity or row["main_entity"]
                    s_angle = s_angle or row["story_angle"]

            # 2. Insert into topic_registry with unique signature protection
            conn.execute("""
            INSERT INTO topic_registry (
                topic_id, candidate_id, channel_id, niche, video_format,
                normalized_signature, title_primary, title_secondary,
                main_entity, story_angle,
                primary_keyword, seo_metadata_json, trs_score, mqs_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                topic_id, candidate_id, int(channel_id), niche.strip(), fmt,
                normalized_signature.strip(), title_primary.strip(),
                (title_secondary or "").strip() or None,
                (m_entity or "").strip() or None,
                (s_angle or "").strip() or None,
                primary_keyword.strip(), seo_json,
                float(trs_score), float(mqs_score), status
            ))

        logger.info("Topic %s atomically approved for channel %d (%s)", topic_id, channel_id, fmt)
        return {
            "ok": True,
            "topic_id": topic_id,
            "channel_id": channel_id,
            "status": status,
            "normalized_signature": normalized_signature
        }

    # -------------------------------------------------------------
    # Query & Duplicate History Scanning
    # -------------------------------------------------------------
    def get_registered_topics_for_channel(
        self,
        channel_id: int,
        video_format: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches approved topics for a channel. If video_format is None, returns both Shorts and Longs."""
        conn = self._get_connection()
        if video_format:
            cursor = conn.execute("""
            SELECT * FROM topic_registry
            WHERE channel_id = ? AND video_format = ?
            ORDER BY approved_at DESC;
            """, (int(channel_id), str(video_format).lower().strip()))
        else:
            cursor = conn.execute("""
            SELECT * FROM topic_registry
            WHERE channel_id = ?
            ORDER BY approved_at DESC;
            """, (int(channel_id),))

        return [dict(row) for row in cursor.fetchall()]

    def get_all_registered_topics(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Returns all approved topics across all channels."""
        conn = self._get_connection()
        cursor = conn.execute("""
        SELECT * FROM topic_registry
        ORDER BY approved_at DESC LIMIT ?;
        """, (int(limit),))
        return [dict(row) for row in cursor.fetchall()]

    def is_exact_signature_registered(
        self,
        channel_id: int,
        normalized_signature: str,
        video_format: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Checks if a normalized signature already exists in registry for channel.
        If video_format is specified, checks that format; otherwise checks both formats.
        """
        conn = self._get_connection()
        sig = normalized_signature.strip()
        if video_format:
            cursor = conn.execute("""
            SELECT topic_id, title_primary FROM topic_registry
            WHERE channel_id = ? AND video_format = ? AND normalized_signature = ?
            LIMIT 1;
            """, (int(channel_id), str(video_format).lower().strip(), sig))
        else:
            cursor = conn.execute("""
            SELECT topic_id, title_primary FROM topic_registry
            WHERE channel_id = ? AND normalized_signature = ?
            LIMIT 1;
            """, (int(channel_id), sig))

        row = cursor.fetchone()
        if row:
            return True, row["title_primary"]
        return False, None

    def close(self) -> None:
        """Closes all active database connections across threads."""
        with self._conns_lock:
            for conn in self._open_conns:
                try:
                    conn.close()
                except Exception:
                    pass
            self._open_conns.clear()
        if hasattr(self._local, "conn"):
            self._local.conn = None


def get_topic_database(db_path: Optional[Path] = None) -> TopicDatabase:
    """Convenience factory function."""
    return TopicDatabase(db_path=db_path)
