"""Render domain contracts (BUILD-02)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract
from domain.enums import LifecycleStatus, Verdict
from domain.validation import ValidationResult


class RenderArtifact(TimestampedContract):
    schema_version: str = "1.0.0"
    scene_id: Optional[str] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    duration_sec: Optional[float] = Field(default=None, ge=0.0)
    codec: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RenderManifest(TimestampedContract):
    schema_version: str = "1.0.0"
    job_id: str
    artifacts: list[RenderArtifact] = Field(default_factory=list)
    output_path: Optional[str] = None
    validation: Optional[ValidationResult] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RenderJob(TimestampedContract):
    schema_version: str = "1.0.0"
    pipeline_job_id: Optional[str] = None
    entity_id: Optional[str] = None
    status: LifecycleStatus = LifecycleStatus.PENDING
    manifest: Optional[RenderManifest] = None
    verdict: Verdict = Verdict.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)
