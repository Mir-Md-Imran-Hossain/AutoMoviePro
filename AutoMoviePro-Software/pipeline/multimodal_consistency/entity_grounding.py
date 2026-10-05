"""Entity / attribute / relation grounding validators (T004-C3)."""
from __future__ import annotations

import re
from typing import Any

from domain.scene_intent import SceneIntent, SemanticEntity
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode


def _norm_set(items: list[str]) -> set[str]:
    out: set[str] = set()
    for it in items:
        for tok in re.findall(r"[a-z0-9]{3,}", (it or "").lower()):
            out.add(tok)
    return out


def validate_entity_grounding(
    intent: SceneIntent,
    analysis: dict[str, Any],
    *,
    strict: bool = False,
) -> list[SemanticIssue]:
    """Detect entity substitution, attribute misbinding, relation confusion."""
    issues: list[SemanticIssue] = []
    detected_entities = [str(x).lower() for x in (analysis.get("entities") or analysis.get("objects") or [])]
    detected_set = _norm_set(detected_entities)

    # Expected entity labels from intent
    expected_labels = {e.label.lower(): e for e in intent.entities}
    for req in intent.required_objects:
        if req.lower() not in detected_set and not any(req.lower() in d for d in detected_set):
            if strict or analysis.get("source") == "OFFLINE_TEST_ONLY":
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.MISSING_REQUIRED_OBJECT,
                        message=f"Expected entity/object missing: {req}",
                        severity="HIGH",
                        evidence={"required": req, "detected": detected_entities},
                    )
                )

    # Entity substitution: canonical label absent but substitute present
    substitute = str(analysis.get("substituted_entity") or "").lower()
    if substitute and intent.entities:
        primary = intent.entities[0].label.lower()
        if substitute != primary and substitute in detected_set and primary not in detected_set:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.UNEXPECTED_OBJECT,
                    message=f"Entity substitution detected: expected {primary}, got {substitute}",
                    severity="CRITICAL" if strict else "HIGH",
                    evidence={"expected": primary, "substitute": substitute},
                )
            )

    # Component ownership: mobile phone camera must not become separate giant camera
    for ent in intent.entities:
        if ent.parent_id:
            parent = next((e for e in intent.entities if e.entity_id == ent.parent_id), None)
            if parent and ent.entity_type == "component":
                parent_label = parent.label.lower()
                comp_label = ent.label.lower()
                if comp_label in detected_set and parent_label not in detected_set:
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.UNEXPECTED_OBJECT,
                            message=(
                                f"Component '{comp_label}' detected without parent '{parent_label}' "
                                "(relation confusion — e.g. phone camera → separate camera)"
                            ),
                            severity="CRITICAL",
                            evidence={"component": comp_label, "parent": parent_label},
                        )
                    )
                if analysis.get("component_as_separate_object"):
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.UNEXPECTED_OBJECT,
                            message="Component incorrectly rendered as separate top-level object",
                            severity="CRITICAL",
                            evidence={"entity_id": ent.entity_id, "parent_id": ent.parent_id},
                        )
                    )

    # Attribute misbinding
    for ent in intent.entities:
        bound = analysis.get("attributes") or {}
        if isinstance(bound, dict):
            for attr_key, attr_val in ent.attributes.items():
                detected_val = str(bound.get(attr_key) or bound.get(ent.entity_id, {}).get(attr_key) or "")
                wrong_entity = str(bound.get(f"{attr_key}_entity") or "")
                if detected_val and wrong_entity and wrong_entity.lower() != ent.entity_id.lower():
                    issues.append(
                        SemanticIssue(
                            code=SemanticIssueCode.UNEXPECTED_OBJECT,
                            message=f"Attribute '{attr_key}' bound to wrong entity '{wrong_entity}'",
                            severity="CRITICAL",
                            evidence={"attribute": attr_key, "expected_entity": ent.entity_id, "bound_to": wrong_entity},
                        )
                    )

    # Relation confusion
    declared_rels = {(r.source_id, r.target_id, r.relation_type) for r in intent.relations}
    for rel in analysis.get("relations") or []:
        if not isinstance(rel, dict):
            continue
        key = (rel.get("source_id", ""), rel.get("target_id", ""), rel.get("relation_type", ""))
        if declared_rels and key not in declared_rels and rel.get("relation_type") not in ("located_at",):
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.UNEXPECTED_OBJECT,
                    message="Unexpected entity relation in analysis metadata",
                    severity="MEDIUM",
                    evidence={"relation": rel},
                )
            )

    return issues


def infer_phone_camera_entities(narration: str, shot_subject: str = "") -> tuple[list[SemanticEntity], list]:
    """Heuristic entity inference for mobile-phone-camera grounding."""
    from domain.scene_intent import EntityRelation

    text = f"{narration} {shot_subject}".lower()
    entities: list[SemanticEntity] = []
    relations: list[EntityRelation] = []
    if "phone" in text and "camera" in text:
        entities.append(
            SemanticEntity(
                entity_id="MOBILE_PHONE_01",
                entity_type="device",
                label="mobile phone",
                attributes={"form_factor": "handheld"},
            )
        )
        entities.append(
            SemanticEntity(
                entity_id="CAMERA_MODULE_01",
                entity_type="component",
                label="phone camera module",
                parent_id="MOBILE_PHONE_01",
                attributes={"low_light_performance": "enabled"},
            )
        )
        relations.append(
            EntityRelation(
                relation_id="REL_PHONE_CAMERA",
                source_id="MOBILE_PHONE_01",
                target_id="CAMERA_MODULE_01",
                relation_type="part_of",
            )
        )
    return entities, relations
