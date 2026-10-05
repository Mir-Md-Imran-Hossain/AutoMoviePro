"""Canonical status and verdict vocabulary (BUILD-01)."""
from __future__ import annotations

from enum import Enum


class LifecycleStatus(str, Enum):
    """Canonical domain lifecycle states (normalized from legacy strings)."""

    CREATED = "created"
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PROCESSING = "processing"
    COMPLETED = "completed"
    READY = "ready"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    VERIFIED = "verified"
    SKIPPED = "skipped"


class JobState(str, Enum):
    """Formal job FSM states — aligned with pipeline/job_fsm.py STATES."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SCRIPTING = "SCRIPTING"
    GENERATING = "GENERATING"
    VERIFYING = "VERIFYING"
    ASSEMBLING = "ASSEMBLING"
    READY = "READY"
    UPLOADING = "UPLOADING"
    PUBLISHED = "PUBLISHED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNCERTAIN = "UNCERTAIN"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"


class ResearchStatus(str, Enum):
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    THUMBNAIL = "thumbnail"
    INTRO = "intro"
    LOGO = "logo"


class ErrorCategory(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    QUOTA_ERROR = "QUOTA_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    MEDIA_ERROR = "MEDIA_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    STATE_ERROR = "STATE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


# Legacy alias map → canonical JobState
PHASE_TO_JOB_STATE: dict[str, JobState] = {
    "starting": JobState.CREATED,
    "generate_short": JobState.GENERATING,
    "generate_long": JobState.GENERATING,
    "scene": JobState.GENERATING,
    "localize": JobState.ASSEMBLING,
    "package": JobState.ASSEMBLING,
    "upload": JobState.UPLOADING,
    "waiting_comments": JobState.PUBLISHED,
    "comment_check": JobState.VERIFIED,
    "failed": JobState.FAILED,
    "cancelled": JobState.CANCELLED,
    "complete": JobState.VERIFIED,
    "ready": JobState.READY,
}
