"""Intelligence layer package (BUILD-04G)."""
from pipeline.intelligence.contracts import (
    ApiCostMetrics,
    ChannelProfile,
    ContentFormat,
    DuplicateResult,
    DuplicateVerdict,
    EvidenceClass,
    RejectionReason,
    ResearchRequest,
    TopicCandidate,
    TopicLifecycleStatus,
    TopicScoreResult,
    TrendClass,
)
from pipeline.intelligence.orchestrator import (
    refresh_topic_intelligence,
    run_topic_intelligence,
    select_topic_for_production,
)
from pipeline.intelligence.bridge import enrich_channel_topic, intelligence_duplicate_check, pick_topic_from_reserve

__all__ = [
    "ApiCostMetrics",
    "ChannelProfile",
    "ContentFormat",
    "DuplicateResult",
    "DuplicateVerdict",
    "EvidenceClass",
    "RejectionReason",
    "ResearchRequest",
    "TopicCandidate",
    "TopicLifecycleStatus",
    "TopicScoreResult",
    "TrendClass",
    "refresh_topic_intelligence",
    "run_topic_intelligence",
    "select_topic_for_production",
    "enrich_channel_topic",
    "intelligence_duplicate_check",
    "pick_topic_from_reserve",
]
