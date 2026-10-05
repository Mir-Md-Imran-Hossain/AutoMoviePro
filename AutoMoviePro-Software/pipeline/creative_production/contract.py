"""Canonical creative production contracts (AMP-004 Phase-07).

SceneIntent remains the semantic authority. This plan answers WHY
each scene exists and binds hook/retention/shot purpose without a
second quality-score engine.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from pipeline.idempotency.fingerprint import hash_text

NARRATIVE_ROLES = (
    "hook",
    "setup",
    "evidence",
    "payoff",
    "transition",
    "close",
)

SHOT_TYPES = (
    "close-up",
    "medium",
    "wide",
    "over-the-shoulder",
    "top-down",
    "establishing",
)

ROLE_SHOT_DEFAULTS: dict[str, tuple[str, str]] = {
    "hook": ("close-up", "pattern_interrupt"),
    "setup": ("medium", "establish_subject"),
    "evidence": ("medium", "show_claimed_subject"),
    "payoff": ("medium", "deliver_payoff"),
    "transition": ("wide", "bridge_scenes"),
    "close": ("medium", "resolve"),
}


@dataclass
class ActionAtom:
    subject: str
    verb: str
    object: str = ""
    instrument: str = ""
    location: str = ""
    posture: str = ""
    state: str = ""
    relation: str = "sequential"  # sequential | simultaneous

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HookContract:
    text: str
    purpose: str = "curiosity"
    generic: bool = False
    clickbait: bool = False
    unsupported_claim: bool = False
    topic_aligned: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenePurpose:
    scene_id: str
    purpose: str
    narrative_role: str
    dialogue_intent: str = ""
    visual_intent: str = ""
    emotion_intent: str = ""
    continuity_constraints: dict[str, Any] = field(default_factory=dict)
    timing_intent: str = ""
    audio_intent: str = ""
    text_intent: str = ""
    transition_intent: str = "cut"
    shot_type: str = ""
    shot_purpose: str = ""
    information_units: list[str] = field(default_factory=list)
    dialogue_id: str = ""
    retention_role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CreativeProductionPlan:
    """Job-level creative production contract — not a competing quality score."""

    job_id: str
    topic: str
    niche: str = ""
    audience: str = ""
    story_purpose: str = ""
    information_objective: str = ""
    emotional_objective: str = ""
    pacing_purpose: str = "natural_spoken"
    sound_purpose: str = "dialogue_primary"
    retention_purpose: str = "curiosity_then_payoff"
    hook: Optional[HookContract] = None
    scenes: list[ScenePurpose] = field(default_factory=list)
    title: str = ""
    thumbnail_claim: str = ""
    revision_id: str = ""
    plan_fingerprint: str = ""
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "topic": self.topic,
            "niche": self.niche,
            "audience": self.audience,
            "story_purpose": self.story_purpose,
            "information_objective": self.information_objective,
            "emotional_objective": self.emotional_objective,
            "pacing_purpose": self.pacing_purpose,
            "sound_purpose": self.sound_purpose,
            "retention_purpose": self.retention_purpose,
            "hook": self.hook.to_dict() if self.hook else None,
            "scenes": [s.to_dict() for s in self.scenes],
            "title": self.title,
            "thumbnail_claim": self.thumbnail_claim,
            "revision_id": self.revision_id,
            "plan_fingerprint": self.plan_fingerprint,
            "schema_version": self.schema_version,
        }


def creative_plan_fingerprint(plan: CreativeProductionPlan | dict[str, Any]) -> str:
    data = plan.to_dict() if isinstance(plan, CreativeProductionPlan) else dict(plan)
    data.pop("plan_fingerprint", None)
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hash_text(payload)[:24]


def _scene_id_of(row: dict[str, Any], index: int) -> str:
    return str(row.get("canonical_scene_id") or row.get("scene_id") or f"scene-{index}")


def _narration_of(row: dict[str, Any]) -> str:
    return str(row.get("narration") or row.get("dialogue") or "").strip()


def default_narrative_role(index: int, total: int) -> str:
    if index == 0:
        return "hook"
    if total <= 1:
        return "hook"
    if index == total - 1:
        return "close"
    if index == 1:
        return "setup"
    if index == 2:
        return "evidence"
    return "payoff" if index % 2 == 1 else "evidence"


def build_creative_production_plan(
    *,
    job_id: str,
    plan: Optional[dict[str, Any]] = None,
    scenes: Optional[list[dict[str, Any]]] = None,
    audience: str = "",
    revision_id: str = "",
) -> CreativeProductionPlan:
    src = dict(plan or {})
    rows = list(scenes if scenes is not None else (src.get("scenes") or []))
    topic = str(src.get("topic") or src.get("title") or "").strip()
    title = str(src.get("title") or topic)
    niche = str(src.get("niche") or src.get("style_family") or "")
    hook_text = ""
    if rows:
        hook_text = _narration_of(rows[0] if isinstance(rows[0], dict) else {})
    purposes: list[ScenePurpose] = []
    n = len(rows)
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        role = str(row.get("narrative_role") or row.get("retention", {}).get("role") or "")
        if not role:
            role = default_narrative_role(i, n)
        if role == "pattern_interrupt":
            role = "hook"
        elif role in ("curiosity_gap", "curiosity"):
            role = "setup"
        elif role in ("first_payoff",):
            role = "payoff"
        shot_type, shot_purpose = ROLE_SHOT_DEFAULTS.get(role, ("medium", "serve_scene_purpose"))
        if row.get("shot_type"):
            shot_type = str(row["shot_type"])
        if row.get("shot_purpose"):
            shot_purpose = str(row["shot_purpose"])
        narr = _narration_of(row)
        purpose = str(row.get("purpose") or "").strip()
        if not purpose:
            purpose = f"{role}: {narr[:80]}" if narr else ""
        purposes.append(
            ScenePurpose(
                scene_id=_scene_id_of(row, i),
                dialogue_id=str(row.get("dialogue_id") or ""),
                purpose=purpose,
                narrative_role=role,
                dialogue_intent=str(row.get("dialogue_intent") or narr[:160]),
                visual_intent=str(row.get("visual_intent") or row.get("visual_prompt") or "")[:200],
                emotion_intent=str(row.get("emotional_intent") or row.get("emotion_intent") or ""),
                continuity_constraints=dict(row.get("continuity_constraints") or row.get("continuity") or {}),
                timing_intent=str(row.get("timing_intent") or ""),
                audio_intent=str(row.get("audio_intent") or ""),
                text_intent=str(row.get("text_intent") or ""),
                transition_intent=str(row.get("transition_intent") or "cut"),
                shot_type=shot_type,
                shot_purpose=shot_purpose,
                information_units=[t for t in narr.split(".") if t.strip()][:6],
                retention_role=str((row.get("retention") or {}).get("role") or role),
            )
        )
    cpp = CreativeProductionPlan(
        job_id=job_id,
        topic=topic,
        niche=niche,
        audience=audience or str(src.get("audience") or ""),
        story_purpose=str(src.get("story_purpose") or src.get("intent") or topic),
        information_objective=str(src.get("information_objective") or topic),
        emotional_objective=str(src.get("emotional_objective") or ""),
        hook=HookContract(text=hook_text, purpose="open_with_specific_claim") if hook_text else None,
        scenes=purposes,
        title=title,
        thumbnail_claim=str(src.get("thumbnail_claim") or title),
        revision_id=revision_id,
    )
    cpp.plan_fingerprint = creative_plan_fingerprint(cpp)
    return cpp
