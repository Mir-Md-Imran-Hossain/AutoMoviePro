"""Visual semantic validation boundary — technical + semantic (T004-C3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.idempotency.visual_validation import validate_visual_asset
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.contracts import (
    SemanticIssueCode,
    SemanticValidationStatus,
    VisualAnalysisMetadata,
    VisualSemanticResult,
)
from pipeline.visual_semantic.scene_intent import intent_fingerprint
from pipeline.visual_semantic.validators import run_semantic_validators


def build_heuristic_analysis(
    *,
    visual_prompt: str = "",
    visual_description: str = "",
    dialogue_id: str = "",
) -> VisualAnalysisMetadata:
    """HEURISTIC metadata derived from prompt/description — not computer vision."""
    import re

    text = f"{visual_prompt} {visual_description}".lower()
    actions: list[str] = []
    for pat, label in (
        (r"\b(drinks?|drinking)\b", "drinking"),
        (r"\b(eats?|eating)\b", "eating"),
        (r"\b(cuts?|cutting)\b", "cutting"),
        (r"\b(sits?|sitting|seated)\b", "sitting"),
        (r"\b(walks?|walking)\b", "walking"),
    ):
        if re.search(pat, text):
            actions.append(label)
    objects = re.findall(r"\b(tea|cup|mug|biscuit|knife|vegetable|vegetables|chair|floor|plate)\b", text)
    location = ""
    if "chair" in text:
        location = "chair"
    elif "floor" in text:
        location = "floor"
    posture = ""
    if "sitting" in text or "seated" in text:
        posture = "sitting on chair"
    elif "floor" in text:
        posture = "sitting on floor"
    return VisualAnalysisMetadata(
        source="HEURISTIC",
        actions=actions,
        objects=list(dict.fromkeys(objects)),
        location=location,
        posture=posture,
        simultaneous_actions=len(actions) > 1,
        description=visual_description or visual_prompt,
        dialogue_id=dialogue_id,
    )


def analysis_from_fixture(data: dict[str, Any]) -> VisualAnalysisMetadata:
    """OFFLINE_TEST_ONLY fixture adapter."""
    return VisualAnalysisMetadata(
        source="OFFLINE_TEST_ONLY",
        actions=[str(x) for x in (data.get("actions") or [])],
        objects=[str(x) for x in (data.get("objects") or [])],
        location=str(data.get("location") or ""),
        posture=str(data.get("posture") or ""),
        simultaneous_actions=bool(data.get("simultaneous_actions", False)),
        description=str(data.get("description") or ""),
        dialogue_id=str(data.get("dialogue_id") or ""),
    )


def run_visual_semantic_gate(
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    request_dialogue_id: str = "",
    continuity: Optional[ContinuityTracker] = None,
    strict: bool = False,
) -> VisualSemanticResult:
    """Run semantic validators + optional continuity checks."""
    issues = run_semantic_validators(
        intent,
        analysis,
        request_dialogue_id=request_dialogue_id,
        prior_descriptions=continuity.prior_descriptions if continuity else None,
        strict=strict,
    )
    if continuity is not None:
        issues.extend(continuity.validate_continuity(intent, analysis))

    blocking_codes = {SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH, SemanticIssueCode.TECHNICAL_INVALID}
    if strict or analysis.source == "OFFLINE_TEST_ONLY":
        blocking_codes = {
            c for c in SemanticIssueCode if c != SemanticIssueCode.HEURISTIC_ONLY
        }

    blocking = [
        i
        for i in issues
        if i.code != SemanticIssueCode.HEURISTIC_ONLY
        and i.code in blocking_codes
        and i.severity in ("CRITICAL", "HIGH")
    ]
    info_only = all(i.code == SemanticIssueCode.HEURISTIC_ONLY for i in issues)

    if blocking:
        status = SemanticValidationStatus.SEMANTIC_BLOCKED
        semantic_ok = False
    elif issues and not info_only:
        status = SemanticValidationStatus.SEMANTIC_PARTIAL
        semantic_ok = not strict
    elif issues:
        status = SemanticValidationStatus.SEMANTIC_PASS
        semantic_ok = True
    else:
        status = SemanticValidationStatus.SEMANTIC_PASS
        semantic_ok = True

    return VisualSemanticResult(
        status=status,
        technical_ok=True,
        semantic_ok=semantic_ok,
        issues=issues,
        heuristic_only=analysis.source in ("HEURISTIC", "OFFLINE_TEST_ONLY"),
        intent_fingerprint=intent_fingerprint(intent),
        dialogue_id=intent.dialogue_id,
        scene_id=intent.scene_id,
        metadata={"analysis_source": analysis.source, "strict": strict},
    )


def validate_visual_complete(
    asset_path: str,
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    mode: str = "video",
    request_dialogue_id: str = "",
    continuity: Optional[ContinuityTracker] = None,
    strict: bool = False,
) -> VisualSemanticResult:
    """
    Combined technical + semantic validation.
    Does NOT claim SEMANTIC_PASS when only technical checks ran.
    """
    tech_ok, tech_reason = validate_visual_asset(asset_path, mode=mode)
    if not tech_ok:
        from pipeline.visual_semantic.contracts import SemanticIssue

        return VisualSemanticResult(
            status=SemanticValidationStatus.SEMANTIC_BLOCKED,
            technical_ok=False,
            semantic_ok=False,
            issues=[
                SemanticIssue(
                    code=SemanticIssueCode.TECHNICAL_INVALID,
                    message=f"Technical validation failed: {tech_reason}",
                    severity="CRITICAL",
                    evidence={"path": asset_path, "reason": tech_reason},
                )
            ],
            intent_fingerprint=intent_fingerprint(intent),
            dialogue_id=intent.dialogue_id,
            scene_id=intent.scene_id,
        )

    sem = run_visual_semantic_gate(
        intent,
        analysis,
        request_dialogue_id=request_dialogue_id,
        continuity=continuity,
        strict=strict,
    )
    sem.technical_ok = True
    if sem.status == SemanticValidationStatus.SEMANTIC_PASS:
        sem.status = SemanticValidationStatus.SEMANTIC_PASS
    elif sem.blocked:
        sem.status = SemanticValidationStatus.SEMANTIC_BLOCKED
    else:
        sem.status = SemanticValidationStatus.SEMANTIC_PARTIAL
    return sem


def semantic_gate_for_spec(
    *,
    asset_path: Path,
    narration_hint: str,
    visual_prompt: str,
    scene_id: str,
    dialogue_id: str,
    script_id: str = "",
    analysis_fixture: Optional[dict[str, Any]] = None,
    continuity: Optional[ContinuityTracker] = None,
    skip: bool = False,
    strict: bool = False,
) -> VisualSemanticResult:
    """Production helper — build intent from shared dialogue source + run gate."""
    if skip:
        return VisualSemanticResult(
            status=SemanticValidationStatus.UNKNOWN,
            technical_ok=True,
            semantic_ok=True,
            metadata={"skipped": True},
        )

    from pipeline.visual_semantic.scene_intent import build_scene_intent_from_dialogue

    intent = build_scene_intent_from_dialogue(
        scene_id=str(scene_id),
        dialogue_id=dialogue_id,
        narration=narration_hint,
        script_id=script_id,
        visual_prompt=visual_prompt,
    )
    if analysis_fixture is not None:
        analysis = analysis_from_fixture(analysis_fixture)
        strict = True
    else:
        analysis = build_heuristic_analysis(
            visual_prompt=visual_prompt,
            visual_description=visual_prompt,
            dialogue_id=dialogue_id,
        )

    result = validate_visual_complete(
        str(asset_path),
        intent,
        analysis,
        request_dialogue_id=dialogue_id,
        continuity=continuity,
        strict=strict,
    )
    if continuity is not None and result.semantic_ok:
        continuity.update_from_intent(intent, analysis)
    return result
