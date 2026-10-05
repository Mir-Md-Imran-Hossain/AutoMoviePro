"""Enrich SceneIntent for canonical prompt compiler — no second prompt engine."""
from __future__ import annotations

from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.creative_production.action_entity import (
    parse_action_atoms,
    smartphone_camera_negative_constraints,
    validate_entity_attribute_ownership,
)
from pipeline.creative_production.camera import controlled_variation_for_role
from pipeline.creative_production.contract import default_narrative_role
from pipeline.creative_production.metaphor import detect_figurative_language, figurative_negative_constraints
from pipeline.multimodal_consistency.entity_grounding import infer_phone_camera_entities


def _merge_negatives(intent: SceneIntent, extras: list[str]) -> None:
    seen = {n.strip() for n in intent.negative_constraints if n.strip()}
    for n in extras:
        n = (n or "").strip()
        if n and n not in seen:
            intent.negative_constraints.append(n)
            seen.add(n)


def enrich_scene_intent(
    intent: SceneIntent,
    *,
    scene: Optional[dict[str, Any]] = None,
    scene_index: int = 0,
    scene_count: int = 1,
    prior_shot_type: str = "",
) -> SceneIntent:
    """Attach purpose, shot reason, ownership negatives, metaphor policy."""
    row = dict(scene or {})
    narr = str(row.get("narration") or intent.summary or "")
    role = str(row.get("narrative_role") or intent.narrative_role or "")
    if not role:
        role = default_narrative_role(scene_index, scene_count)
    intent.narrative_role = role
    if not intent.purpose:
        intent.purpose = str(row.get("purpose") or "").strip() or f"{role}: {(narr or intent.summary)[:80]}"
    intent.dialogue_intent = intent.dialogue_intent or narr[:160]
    intent.visual_intent = intent.visual_intent or str(row.get("visual_intent") or "")[:200]
    intent.retention_role = intent.retention_role or str((row.get("retention") or {}).get("role") or role)
    intent.transition_intent = intent.transition_intent or str(row.get("transition_intent") or "cut")
    intent.figurative_policy = intent.figurative_policy or "literal_unless_explicit"

    var = controlled_variation_for_role(role, prior_shot=prior_shot_type)
    if not intent.shot_type:
        intent.shot_type = str(row.get("shot_type") or var["shot_type"])
    if not intent.shot_purpose:
        intent.shot_purpose = str(row.get("shot_purpose") or var["shot_purpose"])
    if not intent.camera_motion:
        intent.camera_motion = var.get("camera_motion") or "stable"

    # Phone/camera ownership
    if not intent.entities:
        ents, rels = infer_phone_camera_entities(narr, " ".join(intent.actors))
        if ents:
            intent.entities = ents
            intent.relations = list(intent.relations) + list(rels)
    if any("phone" in (e.label or "").lower() for e in intent.entities) or (
        "phone" in narr.lower() and "camera" in narr.lower()
    ):
        _merge_negatives(intent, smartphone_camera_negative_constraints())
        intent.visualization_policy["attribute_ownership"] = "phone.has.camera_quality"

    hits = detect_figurative_language(narr)
    if hits:
        intent.visualization_policy["figurative"] = hits
        _merge_negatives(intent, figurative_negative_constraints(hits))

    # High-retention rules: Scene 1 (0-3s) must start with intense suspense/curiosity
    if scene_index == 0:
        intent.retention_role = "curiosity_hook_0_3s"
        intent.visualization_policy["hook_policy"] = "immediate_suspense_no_intro"
        _merge_negatives(
            intent,
            [
                "NO slow introductory preamble",
                "NO generic greetings before the hook",
                "NO low-energy start",
                "NO delayed visual action",
            ],
        )

    # Subtitle retention policy
    intent.visualization_policy["subtitle_retention"] = "bold_keyword_accent_highlight"

    _merge_negatives(
        intent,
        [
            "DO NOT introduce unrelated objects",
            "DO NOT duplicate hands",
            "DO NOT change seated posture without transition",
            "DO NOT change clothing unless intentional",
            "DO NOT visually literalize metaphors unless explicitly requested",
            "WHAT THE SUBJECT IS DOING must not be replaced by WHAT IS BEING DESCRIBED",
        ],
    )

    atoms = parse_action_atoms(narr, subject=(intent.actors[0] if intent.actors else ""), location=intent.location, posture=intent.posture)
    intent.metadata = dict(intent.metadata or {})
    intent.metadata["action_atoms"] = [a.to_dict() for a in atoms]
    intent.metadata["scene_purpose"] = intent.purpose
    intent.metadata["retention_hook"] = (scene_index == 0)
    intent.metadata["subtitle_accent_enabled"] = True
    own = validate_entity_attribute_ownership(narration=narr, visual_text=intent.visual_intent, intent=intent)
    intent.metadata["ownership_preflight"] = own
    return intent

