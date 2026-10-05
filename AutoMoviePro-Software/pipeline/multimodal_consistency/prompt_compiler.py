"""Deterministic prompt compiler from canonical SceneIntent (T004-C3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.scene_intent import SceneIntent


def _continuity_section(intent: SceneIntent) -> str:
    refs = intent.continuity_refs or {}
    constraints = refs.get("continuity_constraints")
    if isinstance(constraints, dict):
        parts = []
        for key in (
            "required_character",
            "required_wardrobe",
            "required_location",
            "required_posture",
            "required_held_object",
        ):
            if constraints.get(key):
                parts.append(f"{key}={constraints[key]}")
        if constraints.get("required"):
            parts.append("REQUIRED=" + ";".join(constraints["required"]))
        if constraints.get("spatial_required"):
            parts.append("SPATIAL=" + ";".join(constraints["spatial_required"]))
        if constraints.get("temporal_notes"):
            parts.append("TEMPORAL=" + ";".join(constraints["temporal_notes"]))
        if parts:
            return " | ".join(parts)
    # Fallback structured refs (not raw dict dump alone)
    bits = []
    for k in ("wardrobe", "held_object", "prior_scene_id", "prior_fingerprint", "lighting", "camera_language"):
        if refs.get(k):
            bits.append(f"{k}={refs[k]}")
    return " | ".join(bits) if bits else ""


@dataclass
class CompiledPrompt:
    positive: str
    negative: str
    sections: dict[str, str] = field(default_factory=dict)
    intent_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "sections": dict(self.sections),
            "intent_fingerprint": self.intent_fingerprint,
        }


def compile_provider_prompt(intent: SceneIntent) -> CompiledPrompt:
    """
    Structured prompt compiler — prompt is NOT source of truth.
    Derives exclusively from canonical SceneIntent.
    """
    from pipeline.visual_semantic.scene_intent import intent_fingerprint

    entity_lines = []
    for ent in intent.entities:
        line = f"{ent.entity_id}:{ent.label}"
        if ent.parent_id:
            line += f" (part_of {ent.parent_id})"
        if ent.attributes:
            attrs = ", ".join(f"{k}={v}" for k, v in ent.attributes.items())
            line += f" [{attrs}]"
        entity_lines.append(line)

    rel_lines = []
    label_by_id = {e.entity_id: e.label for e in intent.entities}
    for r in intent.relations:
        attrs = dict(r.attributes or {})
        canon = str(attrs.get("c05s_relation") or r.relation_type or "").strip()
        src_label = label_by_id.get(r.source_id) or r.source_id
        tgt_label = label_by_id.get(r.target_id) or r.target_id
        try:
            from pipeline.story_visual_direction import render_relation_prompt_phrase

            rel_lines.append(
                render_relation_prompt_phrase(
                    source_label=src_label,
                    relation_type=canon,
                    target_label=tgt_label,
                )
            )
        except Exception:
            # Fail-open to structured form without semantic collapse
            rel_lines.append(f"{src_label} {canon} {tgt_label}")

    action_lines = [intent.primary_action] + list(intent.secondary_actions)
    temporal = " → ".join(a.action for a in sorted(intent.action_order, key=lambda x: x.order))

    described = (intent.visual_emphasis or intent.dialogue_intent or "")[:180]
    fig = ""
    if isinstance(intent.visualization_policy, dict) and intent.visualization_policy.get("figurative"):
        fig = str(intent.visualization_policy.get("figurative"))[:240]
    shot_cam = " ".join(
        x for x in (intent.shot_type, intent.shot_purpose, intent.camera_motion, intent.framing) if x
    )
    bible_bits = []
    if intent.visual_bible_id:
        bible_bits.append(f"id={intent.visual_bible_id}")
    if intent.visual_bible_version:
        bible_bits.append(f"ver={intent.visual_bible_version}")
    delta = intent.scene_visual_delta or {}
    delta_bits = [f"{k}={v}" for k, v in delta.items() if v not in (None, "", [], {})]
    loc_text = []
    for item in intent.localized_visual_text or []:
        if isinstance(item, dict) and item.get("text"):
            loc_text.append(
                f"[LOCALIZED_VISUAL_TEXT lang={item.get('language') or '?'}]{item.get('text')}"
            )
    sections = {
        "SCENE_PURPOSE": intent.purpose or intent.narrative_role,
        "NARRATIVE_ROLE": intent.narrative_role,
        "VISUAL_BIBLE": " ".join(bible_bits),
        "VISUAL_MODE": (intent.visual_mode or "").strip().upper(),
        "SCENE_VISUAL_DELTA": "; ".join(delta_bits),
        "LOCALIZED_VISUAL_TEXT": "; ".join(loc_text),
        "SUBJECT_ENTITIES": "; ".join(entity_lines) or "; ".join(intent.actors) or intent.summary[:80],
        "ATTRIBUTES": ", ".join(
            f"{e.entity_id}.{k}={v}" for e in intent.entities for k, v in e.attributes.items()
        ),
        "ATTRIBUTE_OWNERSHIP": str((intent.visualization_policy or {}).get("attribute_ownership") or ""),
        "RELATIONSHIPS": "; ".join(rel_lines),
        "ACTION": "; ".join(a for a in action_lines if a),
        "SUBJECT_IS_DOING": intent.primary_action,
        "WHAT_IS_BEING_DESCRIBED": described,
        "TEMPORAL_ORDER": temporal,
        "ENVIRONMENT": intent.environment or intent.location,
        "CAMERA": shot_cam or str((intent.continuity_refs or {}).get("camera_language") or ""),
        "SHOT_PURPOSE": f"{intent.shot_type} {intent.shot_purpose}".strip(),
        "LIGHTING": str((intent.continuity_refs or {}).get("lighting") or ""),
        "STYLE": str((intent.metadata or {}).get("style") or ""),
        "EMOTION": intent.emotional_intent or str((intent.continuity_refs or {}).get("emotional_state") or ""),
        "AUDIO_CONTEXT": (
            f"lang={intent.audio_intent.language} emotion={intent.audio_intent.emotion}"
            if intent.audio_intent
            else ""
        ),
        "POSTURE_STATE": f"{intent.posture} {intent.state}".strip(),
        "CONTINUITY": _continuity_section(intent),
        "TRANSITION": intent.transition_intent,
        "FIGURATIVE_POLICY": intent.figurative_policy + ((" " + fig) if fig else ""),
        "REQUIRED": ", ".join(intent.required_objects),
        "FORBIDDEN": ", ".join(intent.forbidden_objects + intent.forbidden_actions),
        "NEGATIVE_CONSTRAINTS": ", ".join(intent.negative_constraints),
        "PROHIBITED_TRANSFORMATIONS": ", ".join(
            n for n in intent.negative_constraints if "transform" in n.lower() or "morph" in n.lower()
        ),
    }

    positive_parts = [
        f"{k}: {v}"
        for k, v in sections.items()
        if v and k not in ("FORBIDDEN", "NEGATIVE_CONSTRAINTS")
    ]
    positive = "\n".join(positive_parts)
    negative = ", ".join(
        list(intent.forbidden_objects)
        + list(intent.forbidden_actions)
        + list(intent.negative_constraints)
    )

    return CompiledPrompt(
        positive=positive,
        negative=negative,
        sections=sections,
        intent_fingerprint=intent_fingerprint(intent),
    )
