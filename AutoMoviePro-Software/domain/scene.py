"""Scene and plan contracts (visual/audio/subtitle plans)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from domain.common import TimestampedContract


class VisualEvidence(TimestampedContract):
    schema_version: str = "1.0.0"
    must_show: list[str] = Field(default_factory=list)
    should_show: list[str] = Field(default_factory=list)
    must_not_show: list[str] = Field(default_factory=list)


class ShotPlan(TimestampedContract):
    schema_version: str = "1.0.0"
    subject: str
    action: str
    environment: str
    camera: str = "slow push-in, stable documentary"
    lighting: str = "natural cinematic grade"
    composition: str = "subject-centered, readable silhouette"
    motion: Optional[str] = None
    style: Optional[str] = None
    negative_constraints: list[str] = Field(default_factory=list)
    # AMP-004 Phase-07 — explicit shot purpose (camera string remains compatible)
    shot_type: str = ""  # close-up | medium | wide | ots | top-down
    camera_position: str = ""
    camera_motion: str = ""
    framing: str = ""
    focus: str = ""
    duration_sec: Optional[float] = Field(default=None, ge=0.0)
    purpose: str = ""


class VisualPlan(TimestampedContract):
    schema_version: str = "1.0.0"
    scene_id: str
    dialogue_id: Optional[str] = None
    evidence: VisualEvidence = Field(default_factory=VisualEvidence)
    shot: ShotPlan
    provider: Optional[str] = None
    prompt_reference: Optional[str] = None
    prompt_hash: Optional[str] = None
    continuity: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioPlan(TimestampedContract):
    """Canonical per-scene audio plan (dialogue + sound design). Schema 1.1.0 AMP-004 P05."""

    schema_version: str = "1.1.0"
    scene_id: str
    dialogue_id: Optional[str] = None
    segment_id: Optional[str] = None
    revision_id: Optional[str] = None
    language: str = "en"
    speaker_id: Optional[str] = None
    voice_profile: Optional[str] = None
    emotion: Optional[str] = None
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    delivery_style: Optional[str] = None
    speech_rate: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    speed: Optional[float] = None
    pause_hints: list[float] = Field(default_factory=list)
    pause_intent: list[dict[str, Any]] = Field(default_factory=list)
    pronunciation: list[str] = Field(default_factory=list)
    # Sound design (purposeful — empty means none planned)
    ambience: Optional[dict[str, Any]] = None
    sfx_events: list[dict[str, Any]] = Field(default_factory=list)
    music: Optional[dict[str, Any]] = None
    ducking: Optional[dict[str, Any]] = None
    mix_priority: dict[str, int] = Field(
        default_factory=lambda: {"dialogue": 1, "sfx": 2, "ambience": 3, "music": 4}
    )
    loudness_policy: str = "dialogue_primary_v1"
    provider: Optional[str] = None
    generation_reference: Optional[str] = None
    duration_target_sec: Optional[float] = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubtitleCue(TimestampedContract):
    schema_version: str = "1.0.0"
    scene_id: str
    dialogue_id: Optional[str] = None
    cue_id: str
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    text: str
    language: str = "en"

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start_time")
        if start is not None and v < start:
            raise ValueError("end_time must be >= start_time")
        return v


class SubtitlePlan(TimestampedContract):
    schema_version: str = "1.0.0"
    scene_id: str
    language: str = "en"
    cues: list[SubtitleCue] = Field(default_factory=list)


class Scene(TimestampedContract):
    schema_version: str = "1.0.0"
    script_id: Optional[str] = None
    scene_index: int = Field(ge=0)
    legacy_scene_id: Optional[int] = None
    element: str = "beat"
    claim_id: Optional[str] = None
    dialogue_id: Optional[str] = None
    primary_claim: Optional[str] = None
    visual_plan: Optional[VisualPlan] = None
    audio_plan: Optional[AudioPlan] = None
    subtitle_plan: Optional[SubtitlePlan] = None
    duration_target_sec: Optional[float] = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("element")
    @classmethod
    def _element_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("element is required")
        return v.strip()
