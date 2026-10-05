"""Topic scoring dimensions and weights (BUILD-04G)."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from pipeline.channel_dna import ChannelDNA, from_channel_row
from pipeline.intelligence.contracts import (
    ChannelProfile,
    ContentFormat,
    DuplicateResult,
    DuplicateVerdict,
    TopicCandidate,
    TopicScoreResult,
    TrendClass,
)
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.trend import (
    content_gap_score,
    normalize_score_component,
    resolve_freshness_score,
    seo_heuristic_score,
)
from pipeline.topic_scoring import score_topic

DIMENSION_WEIGHTS: dict[str, float] = {
    "CHANNEL_RELEVANCE": 0.17,
    "AUDIENCE_VALUE": 0.08,
    "RECENCY": 0.08,
    "TREND_SIGNAL": 0.08,
    "SEARCH_INTENT": 0.08,
    "SEO_HEURISTIC_SCORE": 0.08,
    "EVIDENCE_AVAILABILITY": 0.09,
    "CONTENT_GAP": 0.08,
    "NOVELTY": 0.08,
    "FORMAT_FIT": 0.08,
    "PRODUCTION_FEASIBILITY": 0.05,
    "DUPLICATE_RISK": 0.05,
}

PASS_THRESHOLD = 0.45


def classify_trend(candidate: dict[str, Any]) -> TrendClass:
    from pipeline.intelligence.trend import classify_trend_from_signals
    return classify_trend_from_signals(
        trend_score=candidate.get("trend_score"),
        freshness=candidate.get("freshness"),
        evergreen_verified=bool(candidate.get("evergreen_verified")),
        seasonal=bool(candidate.get("seasonal")),
        event_driven=bool(candidate.get("event_driven")),
        trend_evidence=str(candidate.get("trend_evidence") or ""),
        source_count=int(candidate.get("source_count") or 0),
    )


def channel_profile_from_row(channel: dict[str, Any]) -> ChannelProfile:
    dna = from_channel_row(channel)
    return ChannelProfile(
        channel_id=int(channel.get("id") or 0),
        channel_name=str(channel.get("youtube_name") or channel.get("facebook_name") or ""),
        niche=str(channel.get("niche") or dna.niche or ""),
        sub_niche=str(dna.sub_niche or ""),
        audience_profile=str(dna.audience or "general"),
        language=str(channel.get("language") or dna.language or "en"),
        target_region=str(dna.country or ""),
        forbidden_topics=list(dna.forbidden_topics or []),
        preferred_topics=list(dna.preferred_topics or []),
    )


def score_candidate(
    candidate: TopicCandidate,
    profile: ChannelProfile,
    *,
    dna: Optional[ChannelDNA] = None,
    existing_topics: Sequence[str] = (),
    duplicate_result: Optional[DuplicateResult] = None,
    evidence_count: int = 0,
    content_gap_score: float = 0.5,
) -> TopicScoreResult:
    dna = dna or from_channel_row({"id": profile.channel_id, "niche": profile.niche})
    title = candidate.title or candidate.canonical_topic

    # Hard blocks
    for bad in profile.forbidden_topics:
        if bad and bad.lower() in title.lower():
            return TopicScoreResult(
                topic_id=candidate.topic_id,
                total_score=0.0,
                hard_blocked=True,
                block_reason="FORBIDDEN",
                rejection_reason="FORBIDDEN",
                evidence={"forbidden_match": bad},
            )

    dup = duplicate_result or analyze_duplicate(
        title,
        existing_topics,
        candidate_revision_id=candidate.revision_id,
        allow_intentional_revision=bool(candidate.metadata.get("intentional_revision")),
    )
    if dup.verdict == DuplicateVerdict.DUPLICATE:
        return TopicScoreResult(
            topic_id=candidate.topic_id,
            total_score=0.0,
            hard_blocked=True,
            block_reason="DUPLICATE",
            duplicate=dup,
            rejection_reason="DUPLICATE",
        )
    if dup.verdict == DuplicateVerdict.UNKNOWN:
        return TopicScoreResult(
            topic_id=candidate.topic_id,
            total_score=0.0,
            hard_blocked=True,
            block_reason="DUPLICATE_UNKNOWN",
            duplicate=dup,
            rejection_reason="INVALID",
        )

    legacy = score_topic(
        title,
        dna,
        trend_score=normalize_score_component(candidate.metadata.get("trend_score"), default=0.0),
        trend_evidence=str(candidate.metadata.get("trend_evidence") or "UNVERIFIED"),
        source_count=int(candidate.metadata.get("source_count") or 0),
        freshness=resolve_freshness_score(candidate.metadata),
        is_duplicate=dup.verdict == DuplicateVerdict.DUPLICATE,
        is_recent_repeat=dup.verdict == DuplicateVerdict.POSSIBLE_DUPLICATE,
        evergreen_verified=bool(candidate.metadata.get("evergreen_verified")),
    )

    gap_value = normalize_score_component(content_gap_score, default=0.5)
    dims: dict[str, float] = {
        "CHANNEL_RELEVANCE": normalize_score_component(legacy.get("components", {}).get("channel_fit"), default=0.5),
        "AUDIENCE_VALUE": normalize_score_component(legacy.get("components", {}).get("audience_fit"), default=0.5),
        "RECENCY": normalize_score_component(legacy.get("components", {}).get("freshness"), default=0.5),
        "TREND_SIGNAL": normalize_score_component(legacy.get("components", {}).get("trend"), default=0.0),
        "SEARCH_INTENT": min(1.0, len(title.split()) / 12.0),
        "SEO_HEURISTIC_SCORE": min(1.0, 0.4 + seo_heuristic_score(title, profile.niche) * 0.6),
        "EVIDENCE_AVAILABILITY": min(1.0, evidence_count / 5.0),
        "CONTENT_GAP": gap_value,
        "NOVELTY": 0.3 if dup.verdict == DuplicateVerdict.POSSIBLE_DUPLICATE else 0.85,
        "FORMAT_FIT": 0.9 if candidate.format == ContentFormat.SHORT else 0.85,
        "PRODUCTION_FEASIBILITY": 0.8,
        "DUPLICATE_RISK": 0.1 if dup.verdict == DuplicateVerdict.UNIQUE else 0.6,
    }
    total = sum(dims[k] * DIMENSION_WEIGHTS[k] for k in DIMENSION_WEIGHTS)
    if dup.verdict == DuplicateVerdict.POSSIBLE_DUPLICATE:
        total *= 0.7

    trend = classify_trend(candidate.metadata)
    passed = total >= PASS_THRESHOLD and not legacy.get("penalties", {}).get("duplicate")
    reason = ""
    if passed:
        reason = "Strong channel relevance; no duplicate; acceptable score"
    elif total < PASS_THRESHOLD:
        reason = "LOW_SCORE"

    return TopicScoreResult(
        topic_id=candidate.topic_id,
        total_score=round(total, 4),
        dimensions=dims,
        duplicate=dup,
        trend_class=trend,
        selection_reason=reason if passed else "",
        rejection_reason="" if passed else (reason or "LOW_SCORE"),
        evidence={"legacy_score": legacy, "weights": DIMENSION_WEIGHTS},
    )
