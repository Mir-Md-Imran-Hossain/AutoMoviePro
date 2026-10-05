"""Intelligence layer contracts (BUILD-04G)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ContentFormat(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TopicLifecycleStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    NORMALIZED = "NORMALIZED"
    CHECKING_DUPLICATE = "CHECKING_DUPLICATE"
    RESEARCHING = "RESEARCHING"
    EVALUATED = "EVALUATED"
    RANKED = "RANKED"
    RESERVED = "RESERVED"
    SELECTED = "SELECTED"
    CONSUMED = "CONSUMED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


class DuplicateVerdict(str, Enum):
    UNIQUE = "UNIQUE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class TrendClass(str, Enum):
    TRENDING = "TRENDING"
    FRESH = "FRESH"
    EVERGREEN = "EVERGREEN"
    SEASONAL = "SEASONAL"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    LOW_RECENCY = "LOW_RECENCY"
    TREND_SIGNAL_UNAVAILABLE = "TREND_SIGNAL_UNAVAILABLE"


class EvidenceClass(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    SUPPORTING = "SUPPORTING"
    WEAK = "WEAK"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class RejectionReason(str, Enum):
    DUPLICATE = "DUPLICATE"
    LOW_RELEVANCE = "LOW_RELEVANCE"
    LOW_EVIDENCE = "LOW_EVIDENCE"
    FORBIDDEN = "FORBIDDEN"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    EXPIRED = "EXPIRED"
    LOW_SCORE = "LOW_SCORE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    INVALID = "INVALID"


INTELLIGENCE_CONTRACT_VERSION = "1.0.0"
PROMPT_VERSION = "1.0.0"
EVALUATOR_VERSION = "1.0.0"
DEFAULT_RESERVE_MIN = 5


@dataclass
class ChannelProfile:
    channel_id: int
    platform: str = "youtube"
    channel_name: str = ""
    niche: str = ""
    sub_niche: str = ""
    audience_profile: str = "general"
    language: str = "en"
    target_region: str = ""
    content_style: str = ""
    long_video_strategy: str = "depth"
    short_video_strategy: str = "immediacy"
    forbidden_topics: list[str] = field(default_factory=list)
    preferred_topics: list[str] = field(default_factory=list)
    evergreen_preferences: bool = True
    trend_preferences: bool = True
    publication_frequency: str = "daily"

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "platform": self.platform,
            "channel_name": self.channel_name,
            "niche": self.niche,
            "sub_niche": self.sub_niche,
            "audience_profile": self.audience_profile,
            "language": self.language,
            "target_region": self.target_region,
            "content_style": self.content_style,
            "long_video_strategy": self.long_video_strategy,
            "short_video_strategy": self.short_video_strategy,
            "forbidden_topics": list(self.forbidden_topics),
            "preferred_topics": list(self.preferred_topics),
            "evergreen_preferences": self.evergreen_preferences,
            "trend_preferences": self.trend_preferences,
            "publication_frequency": self.publication_frequency,
        }


@dataclass
class TopicCandidate:
    title: str
    canonical_topic: str
    format: ContentFormat
    channel_id: int
    niche: str = ""
    angle: str = ""
    audience: str = ""
    source: str = "discovery"
    revision_id: str = "r001"
    topic_id: str = ""
    language: str = "en"
    target_duration_sec: int = 0
    novelty_reason: str = ""
    relevance_reason: str = ""
    evidence_need: str = ""
    confidence: float = 0.5
    status: TopicLifecycleStatus = TopicLifecycleStatus.DISCOVERED
    # C05-TRS additive (optional; prefer metadata when absent in older payloads)
    research_status: str = ""
    evidence_status: str = ""
    eligibility_status: str = ""
    intelligence_fingerprint: str = ""
    research_capability: str = ""  # LOCAL_FACTPACK | EXTERNAL_LIVE | MOCK
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "canonical_topic": self.canonical_topic,
            "format": self.format.value,
            "channel_id": self.channel_id,
            "niche": self.niche,
            "angle": self.angle,
            "audience": self.audience,
            "source": self.source,
            "revision_id": self.revision_id,
            "topic_id": self.topic_id,
            "language": self.language,
            "target_duration_sec": self.target_duration_sec,
            "novelty_reason": self.novelty_reason,
            "relevance_reason": self.relevance_reason,
            "evidence_need": self.evidence_need,
            "confidence": round(float(self.confidence), 4),
            "status": self.status.value,
            "research_status": self.research_status,
            "evidence_status": self.evidence_status,
            "eligibility_status": self.eligibility_status,
            "intelligence_fingerprint": self.intelligence_fingerprint,
            "research_capability": self.research_capability,
            "metadata": dict(self.metadata),
        }


@dataclass
class DuplicateResult:
    verdict: DuplicateVerdict
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    comparison_target: str = ""
    layer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "confidence": round(float(self.confidence), 4),
            "evidence": dict(self.evidence),
            "comparison_target": self.comparison_target,
            "layer": self.layer,
        }


@dataclass
class TopicScoreResult:
    topic_id: str
    total_score: float
    dimensions: dict[str, float] = field(default_factory=dict)
    hard_blocked: bool = False
    block_reason: str = ""
    duplicate: Optional[DuplicateResult] = None
    trend_class: TrendClass = TrendClass.TREND_SIGNAL_UNAVAILABLE
    ranking_position: int = 0
    selection_reason: str = ""
    rejection_reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "total_score": round(float(self.total_score), 4),
            "dimensions": {k: round(float(v), 4) for k, v in self.dimensions.items()},
            "hard_blocked": self.hard_blocked,
            "block_reason": self.block_reason,
            "duplicate": self.duplicate.to_dict() if self.duplicate else None,
            "trend_class": self.trend_class.value,
            "ranking_position": self.ranking_position,
            "selection_reason": self.selection_reason,
            "rejection_reason": self.rejection_reason,
            "evidence": dict(self.evidence),
        }


@dataclass
class ResearchRequest:
    topic_id: str
    canonical_topic: str
    query: str
    language: str = "en"
    region: str = ""
    time_window: str = "7d"
    provider: str = "local"
    model: str = "research-v1"
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "canonical_topic": self.canonical_topic,
            "query": self.query,
            "language": self.language,
            "region": self.region,
            "time_window": self.time_window,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


@dataclass
class ApiCostMetrics:
    request_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retries: int = 0
    avoided_calls: int = 0
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "retries": self.retries,
            "avoided_calls": self.avoided_calls,
            "provider": self.provider,
        }
