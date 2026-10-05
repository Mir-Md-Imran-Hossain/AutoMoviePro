"""Shared contract primitives for BUILD-01 canonical domain layer."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")


def parse_schema_version(version: str) -> tuple[int, int, int]:
    """Parse semantic version into (major, minor, patch)."""
    if not SCHEMA_VERSION_PATTERN.match(version or ""):
        raise ValueError(f"invalid schema_version: {version!r}")
    parts = version.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return major, minor, patch


def schema_versions_compatible(stored: str, expected: str) -> bool:
    """Major version must match; minor/patch may differ within same major."""
    try:
        s_major, _, _ = parse_schema_version(stored)
        e_major, _, _ = parse_schema_version(expected)
    except ValueError:
        return False
    return s_major == e_major


class SchemaVersionMismatchError(ValueError):
    """Raised when persisted contract schema_version is incompatible."""

    def __init__(self, stored: str, expected: str, model_name: str = "Contract") -> None:
        super().__init__(
            f"{model_name} schema_version mismatch: stored={stored!r} expected major={expected!r}"
        )
        self.stored = stored
        self.expected = expected
        self.model_name = model_name


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    """Internal canonical identifier (UUID4 string)."""
    return str(uuid4())


class ContractBase(BaseModel):
    """Base for versioned, serializable domain contracts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    schema_version: str = Field(default="1.0.0", description="Semantic contract version")
    id: str = Field(default_factory=new_id, description="Internal canonical ID")

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, v: str) -> str:
        if not SCHEMA_VERSION_PATTERN.match(v or ""):
            raise ValueError(f"invalid schema_version: {v!r}")
        return v

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id must be non-empty")
        try:
            UUID(v)
        except ValueError as exc:
            raise ValueError(f"id must be a valid UUID string: {v!r}") from exc
        return v

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "ContractBase":
        stored = str(data.get("schema_version") or cls.model_fields["schema_version"].default)
        expected = str(cls.model_fields["schema_version"].default)
        if not schema_versions_compatible(stored, expected):
            raise SchemaVersionMismatchError(stored, expected, cls.__name__)
        return cls.model_validate(data)


class TimestampedContract(ContractBase):
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> Any:
        if v is None or isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class ExternalRef(BaseModel):
    """Separate internal ID from external provider identifiers."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    external_id: str
    label: Optional[str] = None
