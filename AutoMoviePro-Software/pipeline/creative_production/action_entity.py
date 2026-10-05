"""Action atomicity and entity/attribute ownership (AMP-004 Phase-07).

Prevents HOLD(phone)+DESCRIBE(camera) from becoming TRANSFORM(phone→camera).
Reuses SemanticEntity / infer_phone_camera_entities — does not replace SceneIntent.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from domain.scene_intent import SceneIntent, SemanticEntity
from pipeline.creative_production.contract import ActionAtom

INCOMPATIBLE_SIMULTANEOUS = {
    frozenset({"sit", "stand"}),
    frozenset({"sitting", "standing"}),
    frozenset({"eat", "drink"}),
    frozenset({"open", "close"}),
    frozenset({"walk", "sit"}),
}

TRANSFORM_PATTERNS = (
    r"\btransforms?\s+into\b",
    r"\bbecomes?\s+a\s+(?:giant\s+)?camera\b",
    r"\bturns?\s+into\b",
    r"\bmorphs?\s+into\b",
)

PHONE_CAMERA_ATTR = re.compile(
    r"\b(iphone|smartphone|mobile phone|phone).{0,40}camera\b|\bcamera.{0,40}(iphone|smartphone|phone)\b",
    re.I,
)


def parse_action_atoms(text: str, *, subject: str = "", location: str = "", posture: str = "") -> list[ActionAtom]:
    low = (text or "").lower()
    atoms: list[ActionAtom] = []
    verb_obj = [
        ("hold", r"\b(holds?|holding)\b", r"\b(phone|smartphone|iphone|cup|mug|knife|biscuit)\b"),
        ("open", r"\b(opens?|opening)\b", r"\b(door|window|box|app)\b"),
        ("close", r"\b(closes?|closing)\b", r"\b(door|window|box)\b"),
        ("sit", r"\b(sits?|sitting|seated)\b", r"\b(chair|floor|sofa|bench)\b"),
        ("stand", r"\b(stands?|standing)\b", r""),
        ("eat", r"\b(eats?|eating)\b", r"\b(biscuit|food|bread|meal)\b"),
        ("drink", r"\b(drinks?|drinking)\b", r"\b(tea|coffee|water|cup)\b"),
        ("walk", r"\b(walks?|walking)\b", r""),
        ("look", r"\b(looks?|looking)\b", r""),
        ("cut", r"\b(cuts?|cutting)\b", r""),
        ("describe", r"\b(quality|improved|better|feature|spec)\b", r"\b(camera|sensor|lens|battery)\b"),
        # Require contiguous morph phrasing — do NOT treat documentary metaphor
        # "transforms the Moon from X into Y" as an unexplained object morph.
        (
            "transform",
            r"\b(transforms?\s+into|becomes?\s+a\b|turns?\s+into|morphs?\s+into)\b",
            r"",
        ),
    ]
    for verb, vpat, opat in verb_obj:
        if re.search(vpat, low):
            obj = ""
            if opat:
                m = re.search(opat, low)
                if m:
                    obj = m.group(0)
            atoms.append(
                ActionAtom(
                    subject=subject or "subject",
                    verb=verb,
                    object=obj,
                    location=location,
                    posture=posture,
                    relation="sequential",
                )
            )
    return atoms


def validate_action_atomicity(atoms: list[ActionAtom]) -> dict[str, Any]:
    issues: list[str] = []
    simultaneous = [a for a in atoms if a.relation == "simultaneous"]
    verbs = {a.verb.lower() for a in simultaneous} or {a.verb.lower() for a in atoms if a.relation == "simultaneous"}
    # If caller marked simultaneous, check pairs; also detect sit+stand in same beat without sequential order
    all_verbs = [a.verb.lower() for a in atoms]
    if "transform" in all_verbs and ("hold" in all_verbs or "describe" in all_verbs):
        issues.append("incompatible_transform_with_hold_or_describe")
    if "sit" in all_verbs and "stand" in all_verbs:
        sit_a = next(a for a in atoms if a.verb == "sit")
        stand_a = next(a for a in atoms if a.verb == "stand")
        if sit_a.relation == "simultaneous" or stand_a.relation == "simultaneous":
            issues.append("incompatible_simultaneous_sit_stand")
    pair = frozenset(v for v in all_verbs if v in ("eat", "drink"))
    if pair in INCOMPATIBLE_SIMULTANEOUS or pair == frozenset({"eat", "drink"}):
        # sequential eat then drink is allowed if relation sequential and order differs
        eat_i = next((i for i, a in enumerate(atoms) if a.verb == "eat"), None)
        drink_i = next((i for i, a in enumerate(atoms) if a.verb == "drink"), None)
        if eat_i is not None and drink_i is not None:
            if atoms[eat_i].relation == "simultaneous" or atoms[drink_i].relation == "simultaneous":
                issues.append("incompatible_simultaneous_eat_drink")
    for a in atoms:
        if a.verb == "transform":
            issues.append("unexplained_transformation")
    return {
        "status": "BLOCK" if issues else "PASS",
        "issues": issues,
        "atoms": [a.to_dict() for a in atoms],
        "method": "DETERMINISTIC",
    }


def validate_entity_attribute_ownership(
    *,
    narration: str,
    visual_text: str = "",
    intent: Optional[SceneIntent] = None,
    entities: Optional[list[SemanticEntity]] = None,
) -> dict[str, Any]:
    issues: list[str] = []
    combined = f"{narration} {visual_text}"
    vis = (visual_text or "").lower()
    ents = list(entities or (intent.entities if intent else []))
    # Smartphone/camera class
    if PHONE_CAMERA_ATTR.search(narration or "") or (
        intent and any("phone" in (e.label or "").lower() for e in ents)
    ):
        if any(re.search(p, vis) for p in TRANSFORM_PATTERNS):
            issues.append("smartphone_transforms_into_camera")
        if re.search(r"\bgiant\s+camera\b|\bstandalone\s+camera\b|\bexternal\s+dslr\b", vis):
            issues.append("camera_module_rendered_as_separate_device")
    # Attribute owned by wrong entity: knife sharpness → knife becomes sword, etc.
    if re.search(r"\bsharpness\b", (narration or "").lower()) and re.search(
        r"\btransforms?\s+into\b", vis
    ):
        issues.append("attribute_literalized_as_transformation")
    if intent:
        for ent in intent.entities:
            if ent.entity_type == "component" and ent.parent_id:
                if ent.label.lower() in vis and not any(
                    p.label.lower() in vis or p.entity_id == ent.parent_id
                    for p in intent.entities
                    if p.entity_id == ent.parent_id
                ):
                    # visual may omit parent name; only block transform language
                    pass
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def validate_physical_plausibility_heuristic(
    *,
    atoms: list[ActionAtom],
    posture: str = "",
    location: str = "",
) -> dict[str, Any]:
    """Honest: no CV. Impossible combos BLOCK; uncertain → UNKNOWN/HEURISTIC."""
    issues: list[str] = []
    classification = "HEURISTIC"
    post = (posture or "").lower()
    loc = (location or "").lower()
    verbs = {a.verb for a in atoms}
    if "sit" in verbs and "floor" in loc and "chair" in post:
        issues.append("posture_location_contradiction")
    if "sit" in verbs and "floor" in " ".join(a.object for a in atoms) and "chair" in post:
        issues.append("seat_surface_contradiction")
    if not atoms and not posture:
        return {
            "status": "UNKNOWN",
            "issues": ["physical_plausibility_unobserved"],
            "classification": "UNKNOWN",
            "method": "HEURISTIC",
        }
    status = "BLOCK" if any("contradiction" in i for i in issues) else "PASS"
    return {
        "status": status,
        "issues": issues,
        "classification": classification,
        "method": "HEURISTIC",
    }


def smartphone_camera_negative_constraints() -> list[str]:
    return [
        "DO NOT transform smartphone into standalone camera",
        "DO NOT show phone morphing into a giant camera",
        "DO NOT replace the phone with a cinema/DSLR body",
        "camera quality is an ATTRIBUTE of the phone, not a new object",
    ]
