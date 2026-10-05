"""Localization contracts."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from domain.common import TimestampedContract


class VoiceProfile(TimestampedContract):
    schema_version: str = "1.0.0"
    language: str
    provider: Optional[str] = None
    voice_name: Optional[str] = None
    gender_hint: Optional[str] = None
    voice_register: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalizedDialogue(TimestampedContract):
    schema_version: str = "1.1.0"
    source_dialogue_id: str
    target_language: str
    text: str
    adaptation_status: str = "draft"
    voice_profile_id: Optional[str] = None
    localization_version: str = "1.1.0"
    source_language: str = "en"
    job_id: str = ""
    scene_id: str = ""
    segment_id: str = ""
    revision_id: str = ""
    speaker_id: str = ""
    entity_bindings: list[str] = Field(default_factory=list)
    fact_bindings: list[dict[str, Any]] = Field(default_factory=list)
    emotion_intent: str = ""
    source_text_hash: str = ""
    localized_text_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Localization(TimestampedContract):
    schema_version: str = "1.1.0"
    source_language: str
    target_language: str
    source_dialogue_id: str
    localized_dialogue: LocalizedDialogue
    voice_profile: Optional[VoiceProfile] = None
    cultural_adaptation_status: str = "none"
    job_id: str = ""
    scene_id: str = ""
    segment_id: str = ""
    revision_id: str = ""
    contract_fingerprint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
