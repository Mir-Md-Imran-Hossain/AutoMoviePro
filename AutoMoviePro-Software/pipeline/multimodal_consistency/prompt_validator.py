"""Prompt contradiction detection before provider execution (T004-C3)."""
from __future__ import annotations

import re
from typing import Any

from domain.scene_intent import SceneIntent
from pipeline.multimodal_consistency.prompt_compiler import CompiledPrompt
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def validate_prompt_contradiction(
    intent: SceneIntent,
    compiled: CompiledPrompt,
    *,
    provider_prompt: str = "",
    negative_prompt: str = "",
) -> list[SemanticIssue]:
    """Block when compiled/provider prompt contradicts canonical intent."""
    issues: list[SemanticIssue] = []
    combined = f"{provider_prompt or compiled.positive} {negative_prompt or compiled.negative}".lower()
    combined_tokens = _tokens(combined)

    # Forbidden objects/actions must not appear in positive provider prompt (not negative list).
    # Multi-word phrases require full phrase match — token intersection alone false-positives
    # (e.g. "broadcast camera" vs legitimate "phone camera").
    pos_text = (provider_prompt or compiled.positive).lower()
    pos_tokens = _tokens(pos_text)
    for forbidden in intent.forbidden_objects + intent.forbidden_actions:
        f = (forbidden or "").strip().lower()
        if not f:
            continue
        if " " in f:
            hit = f in pos_text
        else:
            ft = _tokens(f)
            hit = bool(ft) and ft <= pos_tokens
        if hit:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.FORBIDDEN_OBJECT,
                    message=f"Prompt contains forbidden element: {forbidden}",
                    severity="CRITICAL",
                    evidence={"forbidden": forbidden},
                )
            )

    # Canonical smartphone vs DSLR contradiction — positive prompt only
    canonical_device = "smartphone" if any("phone" in e.label.lower() for e in intent.entities) else ""
    pos_only = _tokens(provider_prompt or compiled.positive)
    if canonical_device and any(t in pos_only for t in ("dslr", "professional", "broadcast", "cinema")):
        if "external" in intent.negative_constraints or any(
            "external" in nc.lower() or "dslr" in nc.lower() for nc in intent.negative_constraints
        ):
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                    message="Prompt contradicts canonical device: smartphone vs external/pro DSLR camera",
                    severity="CRITICAL",
                    evidence={"canonical": canonical_device, "prompt_tokens": sorted(combined_tokens)[:12]},
                )
            )

    # Posture contradiction
    if intent.posture:
        posture = intent.posture.lower()
        if "sitting" in posture or "seated" in posture:
            if "standing" in pos_tokens and "sitting" not in pos_tokens:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.POSTURE_MISMATCH,
                        message="Prompt contradicts canonical posture (seated vs standing)",
                        severity="CRITICAL",
                        evidence={"canonical_posture": intent.posture},
                    )
                )

    # Required elements omitted from compiled prompt (token-wise, not literal phrase)
    for req in intent.required_objects:
        req_tokens = _tokens(req)
        if req_tokens and not req_tokens <= _tokens(compiled.positive):
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.MISSING_REQUIRED_OBJECT,
                    message=f"Required element missing from compiled prompt: {req}",
                    severity="HIGH",
                    evidence={"required": req},
                )
            )

    # Entity relationship preservation in prompt
    for ent in intent.entities:
        if ent.parent_id and ent.label.lower() not in combined:
            parent = next((e for e in intent.entities if e.entity_id == ent.parent_id), None)
            if parent and parent.label.lower() not in combined:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.UNEXPECTED_OBJECT,
                        message="Prompt flattened critical entity relationship",
                        severity="HIGH",
                        evidence={"entity": ent.entity_id, "parent": ent.parent_id},
                    )
                )

    # Continuity constraints vs positive prompt (AMP-004 Phase-03)
    refs = intent.continuity_refs or {}
    constraints = refs.get("continuity_constraints") if isinstance(refs.get("continuity_constraints"), dict) else {}
    req_loc = str(constraints.get("required_location") or "")
    if req_loc and pos_tokens:
        loc_tokens = _tokens(req_loc)
        # If prompt asserts a clearly different place keyword
        for other in ("beach", "forest", "stadium", "airport"):
            if other in pos_tokens and other not in loc_tokens and loc_tokens:
                issues.append(
                    SemanticIssue(
                        code=SemanticIssueCode.CONTINUITY_BREAK,
                        message=f"Prompt location contradicts continuity required location ({req_loc})",
                        severity="CRITICAL",
                        evidence={"required_location": req_loc, "prompt_token": other},
                    )
                )
                break

    req_char = str(constraints.get("required_character") or "")
    if req_char and intent.actors:
        # actors already validated in pre-gen; ensure positive prompt doesn't name a replacement celebrity pattern
        if "different person" in (provider_prompt or compiled.positive).lower():
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.CONTINUITY_BREAK,
                    message="Prompt requests different person against continuity character constraint",
                    severity="CRITICAL",
                    evidence={"required_character": req_char},
                )
            )

    return issues
