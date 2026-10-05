"""Media asset contracts with provenance."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract, ExternalRef
from domain.enums import AssetType


class Provenance(TimestampedContract):
    schema_version: str = "1.0.0"
    job_id: Optional[str] = None
    contract_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_hash: Optional[str] = None
    input_hash: Optional[str] = None
    generation_id: Optional[str] = None
    seed: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaAsset(TimestampedContract):
    schema_version: str = "1.0.0"
    asset_type: AssetType
    scene_id: Optional[str] = None
    source: str = "generated"
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    duration_sec: Optional[float] = Field(default=None, ge=0.0)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    codec: Optional[str] = None
    language: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)
    external_refs: list[ExternalRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualAsset(MediaAsset):
    asset_type: AssetType = AssetType.VIDEO


class AudioAsset(MediaAsset):
    asset_type: AssetType = AssetType.AUDIO


class ImageAsset(MediaAsset):
    asset_type: AssetType = AssetType.IMAGE


class VideoAsset(MediaAsset):
    asset_type: AssetType = AssetType.VIDEO


class ThumbnailAsset(MediaAsset):
    asset_type: AssetType = AssetType.THUMBNAIL
