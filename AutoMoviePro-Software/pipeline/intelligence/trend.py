"""Trend intelligence — evidence required (BUILD-04G-H)."""
from __future__ import annotations

import math
import time
from typing import Any

from pipeline.intelligence.contracts import TrendClass

SCORING_SIGNAL_VERSION = "1.0.0"
FRESHNESS_HALF_LIFE_SEC = 86400 * 14
SEO_HEURISTIC_SOURCE = "local_heuristic_v1"
TREND_SIGNAL_SOURCE = "metadata_heuristic"


def normalize_score_component(value: float | None, *, default: float = 0.5) -> float:
    """Clamp score inputs to [0,1] with safe fallback for invalid numerics."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return max(0.0, min(1.0, v))


def freshness_from_timestamps(
    *,
    discovered_at: float | None = None,
    researched_at: float | None = None,
    now: float | None = None,
) -> float | None:
    """Derive freshness from timestamps — newer → higher score."""
    ts = researched_at if researched_at is not None else discovered_at
    if ts is None:
        return None
    try:
        age = max(0.0, float(now if now is not None else time.time()) - float(ts))
    except (TypeError, ValueError):
        return None
    return round(math.exp(-age / FRESHNESS_HALF_LIFE_SEC * math.log(2)), 4)


def resolve_freshness_score(metadata: dict[str, Any], *, now: float | None = None) -> float:
    """Prefer explicit freshness; else compute from discovered_at / researched_at."""
    if metadata.get("freshness") is not None:
        return normalize_score_component(metadata.get("freshness"))
    prov = metadata.get("provenance") or {}
    computed = freshness_from_timestamps(
        discovered_at=prov.get("discovered_at") or metadata.get("discovered_at"),
        researched_at=metadata.get("researched_at"),
        now=now,
    )
    if computed is not None:
        return computed
    return 0.5


def scoring_rule_fingerprint() -> str:
    from pipeline.idempotency.fingerprint import hash_text
    payload = f"{SCORING_SIGNAL_VERSION}|{FRESHNESS_HALF_LIFE_SEC}|{SEO_HEURISTIC_SOURCE}"
    return hash_text(payload)[:16]


def classify_trend_from_signals(
    *,
    trend_score: float | None = None,
    freshness: float | None = None,
    evergreen_verified: bool = False,
    seasonal: bool = False,
    event_driven: bool = False,
    trend_evidence: str = "",
    source_count: int = 0,
) -> TrendClass:
    has_evidence = trend_evidence not in ("", "UNAVAILABLE", "UNVERIFIED") or source_count >= 2
    if not has_evidence and trend_score is None and freshness is None:
        return TrendClass.TREND_SIGNAL_UNAVAILABLE
    if evergreen_verified:
        return TrendClass.EVERGREEN
    if seasonal and has_evidence:
        return TrendClass.SEASONAL
    if event_driven and has_evidence:
        return TrendClass.EVENT_DRIVEN
    ts = float(trend_score or 0)
    fr = float(freshness or 0)
    if has_evidence and ts >= 0.7:
        return TrendClass.TRENDING
    if has_evidence and fr >= 0.6:
        return TrendClass.FRESH
    if ts <= 0.1 and fr <= 0.3:
        return TrendClass.LOW_RECENCY
    return TrendClass.TREND_SIGNAL_UNAVAILABLE


def apply_trend_decay(trend_class: TrendClass, *, age_days: float, evergreen: bool = False) -> TrendClass:
    if evergreen and trend_class == TrendClass.EVERGREEN:
        return TrendClass.EVERGREEN
    if age_days > 14 and trend_class == TrendClass.TRENDING:
        return TrendClass.LOW_RECENCY
    if age_days > 7 and trend_class == TrendClass.FRESH:
        return TrendClass.LOW_RECENCY
    return trend_class


def seo_heuristic_score(title: str, niche: str = "") -> float:
    """Heuristic only — NOT search volume or real SEO evidence."""
    words = [w for w in title.split() if w]
    if not words:
        return 0.0
    clarity = min(1.0, len(words) / 10.0)
    specificity = min(1.0, 0.5 + len(set(words)) * 0.05)
    niche_fit = 0.7 if niche and niche.lower() in title.lower() else 0.5
    return round((clarity * 0.35 + specificity * 0.35 + niche_fit * 0.30), 4)


# Backward compat alias — documented as heuristic
seo_score = seo_heuristic_score


def content_gap_score(topic: str, historical: list[str]) -> float:
    if not historical:
        return 0.7
    from pipeline.intelligence.normalization import canonical_topic_key, jaccard_similarity

    cand_key = canonical_topic_key(topic)
    for h in historical:
        if cand_key and cand_key == canonical_topic_key(h):
            return 0.05
    sims = [jaccard_similarity(topic, h) for h in historical if h]
    if not sims:
        return 0.7
    max_sim = max(sims)
    return round(max(0.1, 1.0 - max_sim), 4)
