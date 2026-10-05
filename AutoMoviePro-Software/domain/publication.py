"""Publication and upload contracts."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract, ExternalRef
from domain.enums import LifecycleStatus


class VideoMetadata(TimestampedContract):
    schema_version: str = "1.0.0"
    title: str
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    thumbnail_asset_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublicationTarget(TimestampedContract):
    schema_version: str = "1.0.0"
    platform: str
    channel_ref: Optional[str] = None
    page_ref: Optional[str] = None
    dry_run: bool = True


class UploadJob(TimestampedContract):
    schema_version: str = "1.0.0"
    render_job_id: Optional[str] = None
    target: PublicationTarget
    video_metadata: VideoMetadata
    local_path: Optional[str] = None
    status: LifecycleStatus = LifecycleStatus.PENDING
    error_message: Optional[str] = None


class Publication(TimestampedContract):
    schema_version: str = "1.0.0"
    upload_job_id: str
    target: PublicationTarget
    external: ExternalRef
    verification_status: LifecycleStatus = LifecycleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- C07-PUB provider-neutral contracts (extend domain; no parallel authority) ---


class PublishRequest(TimestampedContract):
    """Customer request to publish an approved revision — schedule time is data only."""

    schema_version: str = "1.0.0"
    login_id: str
    channel_id: int
    provider: str = "mock"
    language: str = "en"
    job_id: int
    revision_id: str
    approved_revision: str
    artifact_ref: str
    title: str
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    category: Optional[str] = None
    privacy_status: str = "private"
    thumbnail_ref: Optional[str] = None
    publish_at: Optional[str] = None  # data only — C07-PUB does not schedule
    fingerprint: str = ""
    scheduling_implemented: bool = False


class PublishPackage(TimestampedContract):
    """Immutable publication payload — references approved artifact; never regenerates media."""

    schema_version: str = "1.0.0"
    approved_revision: str
    artifact_ref: str
    publish_metadata: dict[str, Any] = Field(default_factory=dict)
    channel_id: int
    provider: str
    language: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    build_revision: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""
    regenerates_media: bool = False
    immutable: bool = True


class PublishResult(TimestampedContract):
    """Distinguish upload accepted / remote processing / published / failed."""

    schema_version: str = "1.0.0"
    state: str  # UPLOAD_ACCEPTED|REMOTE_PROCESSING|PUBLISHED|FAILED|RECONCILIATION_REQUIRED|...
    accepted: bool = False
    uploaded: bool = False
    remote_processing: bool = False
    published: bool = False
    failed: bool = False
    reconciliation_required: bool = False
    provider: str = "mock"
    provider_video_id: Optional[str] = None
    provider_url: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    mock: bool = True
    observed_at: Optional[str] = None
