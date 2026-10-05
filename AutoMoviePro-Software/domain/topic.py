"""Topic domain contracts."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from domain.common import TimestampedContract
from domain.enums import LifecycleStatus, ResearchStatus


class Topic(TimestampedContract):
    schema_version: str = "1.0.0"
    title: str
    normalized_title: Optional[str] = None
    niche: Optional[str] = None
    language_context: str = "en"
    content_type: str = "short"
    source: str = "manual"
    freshness: Optional[str] = None
    relevance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    seo_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    novelty_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    duplicate_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ranking: Optional[int] = Field(default=None, ge=0)
    research_status: ResearchStatus = ResearchStatus.REQUESTED
    lifecycle_status: LifecycleStatus = LifecycleStatus.CREATED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("title is required")
        return v.strip()
