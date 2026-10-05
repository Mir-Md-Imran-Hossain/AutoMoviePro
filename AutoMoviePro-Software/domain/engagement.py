"""Engagement domain contracts (BUILD-02)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract, ExternalRef
from domain.enums import LifecycleStatus


class EngagementAction(TimestampedContract):
    schema_version: str = "1.0.0"
    action_type: str
    platform: str
    target_url: Optional[str] = None
    status: LifecycleStatus = LifecycleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class Comment(TimestampedContract):
    schema_version: str = "1.0.0"
    publication_id: Optional[str] = None
    external: Optional[ExternalRef] = None
    author: Optional[str] = None
    text: str
    language: str = "en"
    status: LifecycleStatus = LifecycleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class Reply(TimestampedContract):
    schema_version: str = "1.0.0"
    comment_id: str
    text: str
    status: LifecycleStatus = LifecycleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(TimestampedContract):
    schema_version: str = "1.0.0"
    platform: str
    thread_id: Optional[str] = None
    text: str
    status: LifecycleStatus = LifecycleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)
