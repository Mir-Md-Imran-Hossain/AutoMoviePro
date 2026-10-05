"""Script and dialogue contracts."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict, Field, field_validator

from domain.common import TimestampedContract, new_id


class Dialogue(TimestampedContract):
    schema_version: str = "1.0.0"
    script_id: str
    scene_id: str
    element: str = "beat"
    text: str
    claim_id: Optional[str] = None
    language: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _text_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("dialogue text is required")
        return v.strip()


class ScriptPlanBeat(TimestampedContract):
    """Canonical semantic beat inside ScriptPlan — NOT a visual generation prompt."""

    # Industrial retention / montage fields may appear on beats from director repair;
    # ignore unknown extras so production-plan validation does not hard-fail.
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0.0"
    beat_id: str
    order: int = Field(default=0, ge=0)
    section_role: str = ""  # hook | context | development | reveal | payoff | ending | cta
    narration: str = ""
    speaker: str = "Narrator"
    emotion: str = ""
    emotion_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    action_intent: str = ""
    entity_refs: list[str] = Field(default_factory=list)
    location_ref: str = ""
    temporal_context: str = ""
    continuity_deps: list[str] = Field(default_factory=list)
    visual_implication: str = ""  # semantic EXPECTED visual — not provider prompt
    claim_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    estimated_duration_sec: float = Field(default=4.0, ge=0.0)
    # Industrial retention spine (from niche_director / script_quality)
    retention_role: str = ""
    open_loop: str = ""
    payoff_for: str = ""
    emotional_intent: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScriptPlan(TimestampedContract):
    """Canonical script planning boundary (C05-TRS).

    Owns narrative meaning only. Does NOT own provider-specific visual prompts.
    Legacy niche_director fields visual_prompt / exact_ai_video_prompt are
    LEGACY/DEPRECATED compatibility payloads — not canonical ScriptPlan ownership.
    """

    # Retention/montage enrichments may attach non-canonical keys (blueprint, scenes).
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0.0"
    topic_id: str = ""
    topic: str
    format: str = "LONG"  # LONG | SHORT
    language: str = "en"
    target_duration_sec: float = Field(default=60.0, ge=0.0)
    hook: str = ""
    narrative_structure: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    beats: list[ScriptPlanBeat] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    fact_pack_id: str = ""
    ending: str = ""
    payoff: str = ""
    cta: str = ""
    estimated_duration_sec: float = Field(default=0.0, ge=0.0)
    # Legacy compatibility (non-canonical ownership)
    legacy_visual_prompts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def _topic_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("topic is required")
        return v.strip()


class ScriptSection(TimestampedContract):
    schema_version: str = "1.0.0"
    script_id: str
    section_key: str
    title: Optional[str] = None
    dialogues: list[Dialogue] = Field(default_factory=list)
    order: int = Field(default=0, ge=0)


class Script(TimestampedContract):
    schema_version: str = "1.0.0"
    topic_id: Optional[str] = None
    fact_pack_id: Optional[str] = None
    title: str
    language: str = "en"
    sections: list[ScriptSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("title is required")
        return v.strip()

    def add_dialogue(self, *, element: str, text: str, claim_id: Optional[str] = None) -> Dialogue:
        dlg = Dialogue(
            script_id=self.id,
            scene_id=new_id(),
            element=element,
            text=text,
            claim_id=claim_id,
            language=self.language,
        )
        section = ScriptSection(
            script_id=self.id,
            section_key=element,
            dialogues=[dlg],
            order=len(self.sections),
        )
        self.sections.append(section)
        return dlg
