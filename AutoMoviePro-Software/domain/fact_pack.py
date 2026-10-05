"""FactPack canonical contract — bridge research → script."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from domain.common import TimestampedContract
from domain.enums import EvidenceStatus, Verdict


class FactClaim(TimestampedContract):
    schema_version: str = "1.0.0"
    claim_id: str
    claim: str
    evidence: str = "UNVERIFIED"
    source: str = "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness: str = "UNVERIFIED"
    evidence_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    restrictions: list[str] = Field(default_factory=list)

    @field_validator("claim_id")
    @classmethod
    def _claim_id_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("claim_id is required")
        return v.strip()


class FactPack(TimestampedContract):
    schema_version: str = "1.0.0"
    topic_id: Optional[str] = None
    topic_title: str
    claims: list[FactClaim] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    verdict: Verdict = Verdict.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic_title")
    @classmethod
    def _topic_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("topic_title is required")
        return v.strip()

    def classify_claim(self, claim: FactClaim) -> EvidenceStatus:
        if claim.evidence_status != EvidenceStatus.UNVERIFIED:
            return claim.evidence_status
        if claim.confidence >= 0.75 and claim.evidence not in ("UNVERIFIED", "research_notes"):
            return EvidenceStatus.VERIFIED
        if claim.confidence >= 0.4:
            return EvidenceStatus.UNCERTAIN
        return EvidenceStatus.UNSUPPORTED
