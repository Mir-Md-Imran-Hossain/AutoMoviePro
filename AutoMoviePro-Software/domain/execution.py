"""Job, checkpoint, and execution contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract, utc_now
from domain.enums import JobState
from domain.errors import AppError


class Checkpoint(TimestampedContract):
    schema_version: str = "1.0.0"
    job_id: str
    stage: str
    state: JobState
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    checkpoint_version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Job(TimestampedContract):
    schema_version: str = "1.0.0"
    job_type: str = "video_generation"
    entity_id: Optional[str] = None
    channel_id: Optional[int] = None
    status: JobState = JobState.CREATED
    attempt: int = Field(default=0, ge=0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[AppError] = None
    checkpoint_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobAttempt(TimestampedContract):
    schema_version: str = "1.0.0"
    job_id: str
    attempt_number: int = Field(ge=1)
    status: JobState
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    error: Optional[AppError] = None
