"""Deterministic semantic validators — heuristic, honestly labeled (T004-C3)."""
from __future__ import annotations

import re
from typing import Optional

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.contracts import (
    SemanticIssue,
    SemanticIssueCode,
    VisualAnalysisMetadata,
)

# Mutually exclusive action pairs (heuristic)
_CONFLICT_PAIRS = [
    ({"drink", "drinking"}, {"eat", "eating"}),
    ({"drink", "drinking"}, {"cut", "cutting"}),
    ({"sit", "sitting"}, {"stand", "standing"}),
    ({"sit", "sitting"}, {"walk", "walking"}),
]

_SINGLE_ACTION_PRIMARIES = {"drink", "drinking", "eat", "eating", "cut", "cutting"}


def _norm_list(items: list[str]) -> set[str]:
    out: set[str] = set()
    for it in items:
        for tok in re.findall(r"[a-z0-9]{3,}", (it or "").lower()):
            out.add(tok)
    return out


def validate_action_consistency(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    detected = _norm_list(analysis.actions)
    if analysis.description:
        detected |= _norm_list(re.findall(r"[a-z]{3,}", analysis.description.lower()))

    primary_tokens = _norm_list([intent.primary_action])
    allowed = primary_tokens | _norm_list(intent.optional_objects) | _norm_list(intent.actors)
    forbidden = _norm_list(intent.forbidden_actions)

    unexpected = detected - allowed - _norm_list(intent.optional_objects)
    if primary_tokens & _SINGLE_ACTION_PRIMARIES and len(detected) > 2:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.MULTI_ACTION_OVERLOAD,
                message="Multiple high-salience actions detected for single-action scene intent.",
                severity="HIGH",
                evidence={"detected": sorted(detected), "primary": intent.primary_action},
            )
        )

    for det in unexpected:
        if det in forbidden:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.UNEXPECTED_ACTION,
                    message=f"Forbidden action detected: {det}",
                    severity="CRITICAL",
                    evidence={"action": det, "primary": intent.primary_action},
                )
            )
        elif primary_tokens and det not in primary_tokens:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.UNEXPECTED_ACTION,
                    message=f"Unexpected action relative to primary intent: {det}",
                    severity="HIGH",
                    evidence={"action": det, "primary": intent.primary_action},
                )
            )

    det_set = set(detected)
    for a, b in _CONFLICT_PAIRS:
        if det_set & a and det_set & b:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.CONFLICTING_ACTION,
                    message="Conflicting simultaneous actions detected.",
                    severity="CRITICAL",
                    evidence={"group_a": sorted(det_set & a), "group_b": sorted(det_set & b)},
                )
            )

    return issues


def validate_object_consistency(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    detected = _norm_list(analysis.objects)
    if analysis.description:
        detected |= _norm_list(re.findall(r"[a-z]{3,}", analysis.description.lower()))

    required = _norm_list(intent.required_objects)
    forbidden = _norm_list(intent.forbidden_objects)

    for req in required:
        if req and req not in detected and not any(req in d for d in detected):
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.MISSING_REQUIRED_OBJECT,
                    message=f"Required object not present in analysis metadata: {req}",
                    severity="HIGH",
                    evidence={"required": req, "detected": sorted(detected)},
                )
            )

    for det in detected:
        if det in forbidden:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.FORBIDDEN_OBJECT,
                    message=f"Forbidden object detected: {det}",
                    severity="CRITICAL",
                    evidence={"object": det},
                )
            )
        elif det in {"knife", "biscuit", "gun", "phone"} and det not in required and det not in _norm_list(intent.optional_objects):
            if intent.primary_action and det not in _norm_list([intent.primary_action]):
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.UNEXPECTED_OBJECT,
                        message=f"Unexpected high-salience object: {det}",
                        severity="MEDIUM",
                        evidence={"object": det, "primary": intent.primary_action},
                    )
                )

    return issues


def validate_location_posture(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    exp_loc = (intent.location or intent.environment or "").lower().strip()
    det_loc = (analysis.location or "").lower().strip()
    if exp_loc and det_loc and exp_loc not in det_loc and det_loc not in exp_loc:
        # chair vs floor style mismatch
        chair_terms = {"chair", "seat", "seated"}
        floor_terms = {"floor", "ground", "carpet"}
        exp_chair = any(t in exp_loc for t in chair_terms)
        det_floor = any(t in det_loc for t in floor_terms)
        if exp_chair and det_floor:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.LOCATION_MISMATCH,
                    message="Location contradicts expected seated-on-chair context.",
                    severity="HIGH",
                    evidence={"expected": exp_loc, "detected": det_loc},
                )
            )
        elif exp_loc.split()[0] not in det_loc:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.LOCATION_MISMATCH,
                    message="Location mismatch between intent and analysis metadata.",
                    severity="MEDIUM",
                    evidence={"expected": exp_loc, "detected": det_loc},
                )
            )

    exp_posture = (intent.posture or "").lower().strip()
    det_posture = (analysis.posture or "").lower().strip()
    if exp_posture and det_posture and exp_posture not in det_posture and det_posture not in exp_posture:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.POSTURE_MISMATCH,
                message="Posture mismatch between intent and analysis metadata.",
                severity="HIGH",
                evidence={"expected": exp_posture, "detected": det_posture},
            )
        )

    return issues


def validate_dialogue_alignment(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    request_dialogue_id: str = "",
    strict: bool = False,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    if request_dialogue_id and intent.dialogue_id and request_dialogue_id.strip() != intent.dialogue_id.strip():
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH,
                message="Visual request dialogue_id does not match scene intent dialogue_id.",
                severity="CRITICAL",
                evidence={"intent": intent.dialogue_id, "request": request_dialogue_id},
            )
        )
    if analysis.dialogue_id and intent.dialogue_id and analysis.dialogue_id.strip() != intent.dialogue_id.strip():
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH,
                message="Analysis metadata dialogue_id does not match scene intent.",
                severity="CRITICAL",
                evidence={"intent": intent.dialogue_id, "analysis": analysis.dialogue_id},
            )
        )

    narr_kw = _norm_list(re.findall(r"[a-z]{3,}", intent.summary.lower()))
    vis_kw = _norm_list(analysis.actions + analysis.objects)
    if analysis.description:
        vis_kw |= _norm_list(re.findall(r"[a-z]{3,}", analysis.description.lower()))
    if narr_kw and vis_kw and not (narr_kw & vis_kw):
        sev = "HIGH" if strict or analysis.source == "OFFLINE_TEST_ONLY" else "LOW"
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                message="Dialogue meaning and visual analysis metadata share no semantic overlap.",
                severity=sev,
                evidence={"narration_keywords": sorted(narr_kw)[:8], "visual_keywords": sorted(vis_kw)[:8]},
            )
        )
    return issues


def validate_temporal_order(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    if len(intent.action_order) >= 2 and analysis.simultaneous_actions:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.TEMPORAL_CONTRADICTION,
                message="Sequential action order required but analysis indicates simultaneous actions.",
                severity="HIGH",
                evidence={
                    "expected_order": [a.action for a in intent.action_order],
                    "simultaneous": True,
                },
            )
        )
    return issues


def validate_robotic_signals(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    prior_descriptions: Optional[list[str]] = None,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    prior = prior_descriptions or []
    desc = (analysis.description or "").strip().lower()
    if desc and prior.count(desc) >= 2:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.REPEATED_PATTERN,
                message="Repeated identical visual composition pattern detected across scenes.",
                severity="MEDIUM",
                evidence={"description": desc[:80], "repeat_count": prior.count(desc) + 1},
            )
        )
    return issues


def run_semantic_validators(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    request_dialogue_id: str = "",
    prior_descriptions: Optional[list[str]] = None,
    strict: bool = False,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    issues.extend(validate_action_consistency(intent, analysis))
    issues.extend(validate_object_consistency(intent, analysis))
    issues.extend(validate_location_posture(intent, analysis))
    issues.extend(validate_dialogue_alignment(intent, analysis, request_dialogue_id=request_dialogue_id, strict=strict))
    issues.extend(validate_temporal_order(intent, analysis))
    issues.extend(validate_robotic_signals(intent, analysis, prior_descriptions=prior_descriptions))
    if analysis.source in ("HEURISTIC", "OFFLINE_TEST_ONLY"):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.HEURISTIC_ONLY,
                message=f"Semantic check used {analysis.source} metadata — not computer vision.",
                severity="INFO",
                evidence={"source": analysis.source},
            )
        )
    return issues
