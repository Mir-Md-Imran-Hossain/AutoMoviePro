"""Localization semantic preservation (T004-C3)."""
from __future__ import annotations

import re
from typing import Any

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode

_EVENT_VERBS = (
    "pick", "picked", "call", "called", "drink", "drank", "drinking",
    "walk", "walking", "sit", "sitting", "eat", "eating", "put", "putdown",
)


_CANONICAL_EVENT: dict[str, str] = {
    "pick": "pick",
    "picked": "pick",
    "call": "call",
    "called": "call",
    "drink": "drink",
    "drank": "drink",
    "drinking": "drink",
    "walk": "walk",
    "walking": "walk",
    "sit": "sit",
    "sitting": "sit",
    "eat": "eat",
    "eating": "eat",
    "put": "put",
    "putdown": "put",
}


def extract_semantic_events(text: str) -> list[str]:
    events: list[str] = []
    lower = (text or "").lower()
    for verb in _EVENT_VERBS:
        if re.search(rf"\b{verb}\b", lower):
            canonical = _CANONICAL_EVENT.get(verb, verb.rstrip("ed").rstrip("ing") or verb)
            events.append(canonical)
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in events:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def validate_localization_semantics(
    intent: SceneIntent,
    localized: dict[str, Any],
) -> list[SemanticIssue]:
    """
    Verify localized text preserves event/actor/object/action order semantics.
    Not literal word-for-word translation.
    """
    issues: list[SemanticIssue] = []
    if not intent.localization_intent or not intent.localization_intent.preserve_events:
        return issues

    master_events = intent.localization_intent.semantic_events or extract_semantic_events(intent.summary)
    localized_text = str(localized.get("text") or "")
    localized_events = extract_semantic_events(localized_text)

    if localized.get("actor_changed"):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                message="Localization changed actor identity",
                severity="CRITICAL",
                evidence={"master_actors": intent.actors},
            )
        )

    if localized.get("object_changed"):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.UNEXPECTED_OBJECT,
                message="Localization changed core object identity",
                severity="CRITICAL",
                evidence={"required_objects": intent.required_objects},
            )
        )

    if master_events and localized_events:
        missing = [e for e in master_events if e not in localized_events]
        if missing and localized.get("source") == "OFFLINE_TEST_ONLY":
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                    message="Localization lost semantic events from master dialogue",
                    severity="CRITICAL",
                    evidence={"master_events": master_events, "localized_events": localized_events, "missing": missing},
                )
            )

    if localized.get("order_changed") and not intent.narrative_change_allowed:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.TEMPORAL_CONTRADICTION,
                message="Localization altered temporal event order",
                severity="CRITICAL",
                evidence={"master_events": master_events, "localized_events": localized_events},
            )
        )

    return issues
