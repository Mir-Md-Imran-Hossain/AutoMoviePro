"""Scene intent contract — canonical semantic source (T004-C3)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field, field_validator

from domain.common import TimestampedContract


class TemporalAction(TimestampedContract):
    schema_version: str = "1.0.0"
    action: str
    order: int = Field(ge=0)
    duration_sec: Optional[float] = Field(default=None, ge=0.0)
    relation: str = "sequential"  # sequential | simultaneous | follow


class SemanticEntity(TimestampedContract):
    """Grounded entity with explicit identity — prevents attribute misbinding."""

    schema_version: str = "1.0.0"
    entity_id: str
    entity_type: str = "object"  # actor | object | component | location | device
    label: str
    attributes: dict[str, str] = Field(default_factory=dict)
    parent_id: str = ""
    quantity: int = Field(default=1, ge=1)


class EntityRelation(TimestampedContract):
    schema_version: str = "1.0.0"
    relation_id: str
    source_id: str
    target_id: str
    relation_type: str  # owns | part_of | interacts_with | located_at | uses
    attributes: dict[str, str] = Field(default_factory=dict)


class AudioIntent(TimestampedContract):
    """Dialogue delivery intent. Voice identity ≠ emotional state (C05-Q)."""

    schema_version: str = "1.2.0"
    language: str = "en"
    # Stable voice identity (must not change merely because emotion changes)
    speaker_id: str = ""
    voice_identity_id: str = ""
    voice_profile: str = ""
    # Scene emotional state (independent of speaker identity)
    emotion: str = ""
    emotion_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    delivery: str = "neutral"
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pacing: str = ""  # e.g. measured | brisk — distinct from speech_rate
    emphasis: list[str] = Field(default_factory=list)
    pause_intent: list[dict[str, Any]] = Field(default_factory=list)
    pronunciation: list[str] = Field(default_factory=list)
    ambience_type: str = ""
    music_mood: str = ""
    duration_target_sec: Optional[float] = Field(default=None, ge=0.0)
    # Provider honesty — CAPABILITY_LIMITATION when TTS cannot honor a field
    capability_limitations: list[str] = Field(default_factory=list)


class LocalizationIntent(TimestampedContract):
    """Canonical localization intent — SceneIntent remains semantic source."""

    schema_version: str = "1.1.0"
    source_language: str = "en"
    target_language: str = ""
    preserve_events: bool = True
    semantic_events: list[str] = Field(default_factory=list)
    entity_bindings: list[str] = Field(default_factory=list)
    fact_bindings: list[dict[str, Any]] = Field(default_factory=list)
    speaker_id: str = ""
    emotion_intent: str = ""
    emotion_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    rtl: bool = False
    numeral_policy: str = "preserve_source_digits"
    unit_policy: str = "preserve_source_units"
    currency_policy: str = "preserve_source_currency"
    name_policy: str = "preserve_latin_proper_nouns"
    reading_speed_cps: float = Field(default=17.0, ge=5.0, le=40.0)
    max_chars_per_line: int = Field(default=42, ge=10, le=80)
    max_lines: int = Field(default=2, ge=1, le=3)
    line_break_policy: str = "semantic_phrase"
    revision_id: str = ""
    job_id: str = ""
    scene_id: str = ""
    dialogue_id: str = ""
    segment_id: str = ""


class SubtitleIntent(TimestampedContract):
    schema_version: str = "1.1.0"
    language: str = "en"
    cue_count: int = Field(default=0, ge=0)
    total_duration_sec: Optional[float] = Field(default=None, ge=0.0)
    audio_fingerprint: str = ""
    reading_speed_cps: float = Field(default=17.0, ge=5.0, le=40.0)
    max_chars_per_line: int = Field(default=42, ge=10, le=80)
    max_lines: int = Field(default=2, ge=1, le=3)
    rtl: bool = False
    dialogue_id: str = ""
    scene_id: str = ""
    segment_id: str = ""
    revision_id: str = ""


class SceneIntent(TimestampedContract):
    """
    Semantic intent for a single scene beat.
    Extends VisualPlan/Scene semantics without replacing Scene model.
    Canonical source for prompt compilation AND validation.
    """

    schema_version: str = "1.2.0"
    scene_id: str
    dialogue_id: str
    revision_id: str = ""
    script_id: str = ""
    summary: str = ""
    primary_action: str = ""
    secondary_actions: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    entities: list[SemanticEntity] = Field(default_factory=list)
    relations: list[EntityRelation] = Field(default_factory=list)
    location: str = ""
    environment: str = ""
    posture: str = ""
    state: str = ""
    interaction_surface: str = ""
    required_objects: list[str] = Field(default_factory=list)
    optional_objects: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    forbidden_objects: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    emotional_intent: str = ""
    visual_emphasis: str = ""
    action_order: list[TemporalAction] = Field(default_factory=list)
    continuity_expected: bool = True
    continuity_exception_reason: str = ""
    continuity_refs: dict[str, Any] = Field(default_factory=dict)
    narrative_change_allowed: bool = False
    audio_intent: Optional[AudioIntent] = None
    subtitle_intent: Optional[SubtitleIntent] = None
    localization_intent: Optional[LocalizationIntent] = None
    # AMP-004 Phase-07 creative production (additive; SceneIntent remains semantic authority)
    purpose: str = ""
    narrative_role: str = ""  # hook | setup | evidence | payoff | transition | close
    dialogue_intent: str = ""
    visual_intent: str = ""
    timing_intent: str = ""
    text_intent: str = ""
    transition_intent: str = "cut"
    shot_type: str = ""
    shot_purpose: str = ""
    camera_position: str = ""
    camera_motion: str = ""
    framing: str = ""
    focus_target: str = ""
    figurative_policy: str = "literal_unless_explicit"
    retention_role: str = ""
    information_units: list[str] = Field(default_factory=list)
    visualization_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # C05-V additive — Visual Intelligence / Image-First (does not replace ContinuityTracker)
    visual_bible_id: str = ""
    visual_bible_version: str = ""
    visual_mode: str = ""  # IMAGE | IMAGE_WITH_MOTION | VIDEO
    scene_visual_delta: dict[str, Any] = Field(default_factory=dict)
    localized_visual_text: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("scene_id", "dialogue_id")
    @classmethod
    def _non_empty_id(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("scene_id and dialogue_id are required")
        return v.strip()
