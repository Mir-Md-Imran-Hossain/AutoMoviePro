"""Channel and user domain stubs (existing DB-backed, canonical shape only)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract


class Channel(TimestampedContract):
    schema_version: str = "1.0.0"
    legacy_db_id: Optional[int] = None
    youtube_name: Optional[str] = None
    facebook_name: Optional[str] = None
    niche: Optional[str] = None
    niche_id: Optional[int] = None
    enabled: bool = True
    languages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(TimestampedContract):
    schema_version: str = "1.0.0"
    login_id: Optional[str] = None
    api_base_url: Optional[str] = None
    customer_ref: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
