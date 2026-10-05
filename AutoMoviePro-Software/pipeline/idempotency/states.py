"""Idempotency request states (BUILD-03)."""
from __future__ import annotations

from enum import Enum


class IdempotencyState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RESERVED = "RESERVED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"
