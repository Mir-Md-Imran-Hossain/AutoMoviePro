"""Production continuity wiring — ContinuityTracker into validated scene handoff (AMP-004 P03).

Does NOT create a second continuity engine.
Applies PRE-generation constraints → SceneIntent → prompt compiler → handoff dicts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.multimodal_consistency.prompt_validator import validate_prompt_contradiction
from pipeline.visual_semantic.continuity import (
    ContinuityConstraints,
    ContinuityError,
    ContinuityTracker,
)
from pipeline.visual_semantic.contracts import SemanticIssue
from pipeline.visual_semantic.scene_intent import build_scene_intent_from_dialogue, intent_fingerprint

logger = logging.getLogger(__name__)


class ContinuityPromptBlocked(RuntimeError):
    """Prompt contradicts SceneIntent / continuity — must not generate."""

    def __init__(self, message: str, *, issues: Optional[list[SemanticIssue]] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


def _intent_from_handoff(scene: dict[str, Any], *, scene_index: int) -> SceneIntent:
    # C05-S / C05-TRS-PW: prefer projected SceneIntent over legacy niche visual prompts
    c05s_intent = scene.get("c05s_scene_intent")
    if isinstance(c05s_intent, dict) and c05s_intent:
        try:
            intent = SceneIntent.model_validate(c05s_intent)
            narr = str(scene.get("narration") or "").strip()
            if narr and not (intent.dialogue_intent or "").strip():
                intent.dialogue_intent = narr
            if narr and not (intent.summary or "").strip():
                intent.summary = narr[:200]
            return intent
        except Exception as exc:
            logger.debug("c05s_scene_intent validate failed — falling back: %s", exc)

    narr = str(scene.get("narration") or "").strip()
    dialogue_id = str(scene.get("dialogue_id") or f"dlg-{scene_index}").strip()
    scene_id = str(scene.get("canonical_scene_id") or scene.get("scene_id") or scene_index)
    shot = {}
    cont = dict(scene.get("continuity") or {})
    if scene.get("subject"):
        shot["subject"] = scene["subject"]
    if scene.get("environment"):
        shot["environment"] = scene["environment"]
    # Narrative change markers on handoff
    narrative_change = bool(scene.get("narrative_change_allowed") or cont.get("narrative_change_allowed"))
    continuity_expected = scene.get("continuity_expected")
    if continuity_expected is None:
        continuity_expected = cont.get("continuity_expected", True)

    # When C05-S marked canonical, do not feed LEGACY niche prompts into intent emphasis
    if str(scene.get("visual_direction_source") or "").upper() == "C05-S":
        visual_for_intent = str(
            scene.get("c05s_compiled_positive")
            or scene.get("visual_implication")
            or narr
            or ""
        )
    else:
        visual_for_intent = str(scene.get("visual_prompt") or scene.get("exact_ai_video_prompt") or "")

    intent = build_scene_intent_from_dialogue(
        scene_id=str(scene_id),
        dialogue_id=dialogue_id,
        narration=narr,
        script_id=str(scene.get("script_id") or ""),
        visual_prompt=visual_for_intent,
        shot=shot,
        continuity=cont,
        continuity_expected=bool(continuity_expected),
        narrative_change_allowed=narrative_change,
        emotional_intent=str(scene.get("emotional_intent") or ""),
    )
    if scene.get("revision_id"):
        intent.revision_id = str(scene["revision_id"])
    if scene.get("posture"):
        intent.posture = str(scene["posture"])
    if scene.get("location"):
        intent.location = str(scene["location"])
        intent.environment = intent.environment or intent.location
    if scene.get("forbidden_objects"):
        intent.forbidden_objects = list(scene["forbidden_objects"])
    if scene.get("required_objects"):
        for o in scene["required_objects"]:
            if o not in intent.required_objects:
                intent.required_objects.append(str(o))
    if scene.get("actors"):
        intent.actors = [str(a) for a in scene["actors"]]
    return intent


def prepare_scene_with_continuity(
    tracker: ContinuityTracker,
    scene: dict[str, Any],
    *,
    scene_index: int,
    block_on_critical: bool = True,
) -> dict[str, Any]:
    """
    PRE-generation: constraints → intent → compile → contradiction check → handoff fields.
    First scene initializes tracker; subsequent scenes inherit structured constraints.
    """
    out = dict(scene)
    intent = _intent_from_handoff(out, scene_index=scene_index)
    constraints: Optional[ContinuityConstraints] = None

    if scene_index == 0 or tracker.state is None:
        tracker.initialize_from_intent(intent)
        out["continuity_initialized"] = True
    else:
        if intent.continuity_expected and not intent.narrative_change_allowed and tracker.state is None:
            raise ContinuityError(
                f"scene[{scene_index}]: mandatory continuity state missing",
            )
        # Mark whether location was explicit before merge (prevention of unexplained jumps)
        if (intent.location or "").strip():
            meta = dict(intent.metadata or {})
            meta["explicit_location"] = True
            intent.metadata = meta
        constraints = tracker.build_constraints_for_next(intent)
        pre_issues = tracker.validate_pre_generation(intent, constraints)
        critical = [i for i in pre_issues if i.severity == "CRITICAL"]
        if critical and block_on_critical:
            raise ContinuityError(
                f"scene[{scene_index}]: continuity pre-generation blocked: {critical[0].message}",
                issues=critical,
            )
        intent = tracker.apply_constraints_to_intent(intent, constraints)
        # Re-check impossible actions after merge
        post_issues = tracker.validate_pre_generation(intent, constraints)
        critical2 = [i for i in post_issues if i.severity == "CRITICAL"]
        if critical2 and block_on_critical:
            raise ContinuityError(
                f"scene[{scene_index}]: continuity pre-generation blocked: {critical2[0].message}",
                issues=critical2,
            )
        out["continuity_constraints"] = constraints.to_dict()
        out["continuity_fingerprint"] = constraints.source_fingerprint
        from pipeline.visual_semantic.contracts import VisualAnalysisMetadata

        tracker.update_from_intent(
            intent,
            VisualAnalysisMetadata(
                source="HEURISTIC",
                actions=[intent.primary_action] if intent.primary_action else [],
                objects=list(intent.required_objects),
                location=intent.location,
                posture=intent.posture,
                description=intent.summary,
                dialogue_id=intent.dialogue_id,
            ),
        )

    from pipeline.creative_production.prompt_policy import enrich_scene_intent

    intent = enrich_scene_intent(intent, scene=out, scene_index=scene_index)

    compiled = compile_provider_prompt(intent)
    prompt_issues = validate_prompt_contradiction(intent, compiled)
    critical_prompt = [i for i in prompt_issues if i.severity == "CRITICAL"]
    if critical_prompt and block_on_critical:
        raise ContinuityPromptBlocked(
            f"scene[{scene_index}]: prompt contradicts continuity/intent: {critical_prompt[0].message}",
            issues=critical_prompt,
        )

    out["visual_prompt"] = compiled.positive
    out["exact_ai_video_prompt"] = compiled.positive
    out["compiled_negative_prompt"] = compiled.negative
    # C05-GA: final authoritative compile supersedes intermediate C05-S stamp
    if out.get("c05s_compiled_positive") and out["c05s_compiled_positive"] != compiled.positive:
        out["c05s_intermediate_compiled_positive"] = out.get("c05s_compiled_positive")
    out["canonical_compiled_positive"] = compiled.positive
    out["prompt_authority"] = "ContinuityTracker+prompt_compiler"
    out["scene_intent_fingerprint"] = compiled.intent_fingerprint or intent_fingerprint(intent)
    out["continuity_refs"] = dict(intent.continuity_refs)
    out["dialogue_id"] = intent.dialogue_id
    out["canonical_scene_id"] = out.get("canonical_scene_id") or intent.scene_id
    out["script_id"] = out.get("script_id") or intent.script_id
    out["_continuity_applied"] = True
    out["shared_scene_identity"] = {
        "scene_id": intent.scene_id,
        "dialogue_id": intent.dialogue_id,
        "revision_id": intent.revision_id,
        "intent_fingerprint": out["scene_intent_fingerprint"],
        "continuity_fingerprint": (tracker.state.fingerprint if tracker.state else ""),
    }
    return out


def apply_production_continuity(
    work_dir: Path,
    handoff_scenes: list[dict[str, Any]],
    *,
    job_id: str = "",
    block_on_critical: bool = True,
) -> list[dict[str, Any]]:
    """
    Production entry: apply ContinuityTracker across all validated handoff scenes.
    Persists CONTINUITY_STATE.json for recovery / retry / provenance.
    """
    work_dir = Path(work_dir)
    tracker = ContinuityTracker.load(work_dir) or ContinuityTracker()
    # Fresh job with existing empty history for new validation pass: if handoff longer than history, keep state only if recovering mid-job
    if tracker.state and tracker._history and len(tracker._history) >= len(handoff_scenes):
        # Recovery: already applied — re-load fresh for deterministic rebuild
        tracker = ContinuityTracker()

    prepared: list[dict[str, Any]] = []
    for i, sc in enumerate(handoff_scenes):
        if not isinstance(sc, dict):
            raise ContinuityError(f"scene[{i}]: handoff must be dict")
        prepared.append(
            prepare_scene_with_continuity(
                tracker, sc, scene_index=i, block_on_critical=block_on_critical
            )
        )
    tracker.persist(work_dir)
    logger.info(
        "production continuity applied job=%s scenes=%s fp=%s",
        job_id or work_dir.name,
        len(prepared),
        tracker.state.fingerprint if tracker.state else "",
    )
    return prepared
