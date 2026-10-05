"""Research domain contracts."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from domain.common import TimestampedContract
from domain.enums import EvidenceStatus, ResearchStatus, Verdict


class ResearchEvidence(TimestampedContract):
    schema_version: str = "1.0.0"
    topic_id: str
    claim: str
    source: str = "unknown"
    source_url: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    raw_excerpt: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("claim")
    @classmethod
    def _claim_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("claim is required")
        return v.strip()


class TopicResearch(TimestampedContract):
    schema_version: str = "1.0.0"
    topic_id: str
    status: ResearchStatus = ResearchStatus.REQUESTED
    query: Optional[str] = None
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    verdict: Verdict = Verdict.UNKNOWN
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
