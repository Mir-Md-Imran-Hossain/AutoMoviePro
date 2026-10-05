"""Multimodal consistency gate — canonical SceneIntent → validation layers (T004-C3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.idempotency.visual_validation import validate_visual_asset
from pipeline.multimodal_consistency.cross_modal import (
    validate_audio_dialogue_identity,
    validate_dialogue_visual_consistency,
    validate_subtitle_dialogue,
)
from pipeline.multimodal_consistency.entity_grounding import validate_entity_grounding
from pipeline.multimodal_consistency.evaluator_adapter import get_evaluator
from pipeline.multimodal_consistency.industrial_status import (
    ConfidenceLevel,
    IndustrialValidationReport,
    LayerResult,
    LayerStatus,
    ValidationLayer,
    aggregate_final_status,
)
from pipeline.multimodal_consistency.localization_semantic import validate_localization_semantics
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.multimodal_consistency.prompt_validator import validate_prompt_contradiction
from pipeline.multimodal_consistency.timeline import validate_timeline_consistency
from pipeline.visual_semantic.continuity import ContinuityTracker
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode, VisualAnalysisMetadata
from pipeline.visual_semantic.scene_intent import intent_fingerprint


def _layer_from_issues(
    layer: ValidationLayer,
    issues: list[SemanticIssue],
    *,
    confidence: ConfidenceLevel,
    strict: bool,
    blocking_severities: frozenset[str] = frozenset({"CRITICAL", "HIGH"}),
) -> LayerResult:
    critical = [i for i in issues if i.severity in blocking_severities and i.code != SemanticIssueCode.HEURISTIC_ONLY]
    if critical:
        status = LayerStatus.BLOCKED
    elif any(i.severity in ("MEDIUM", "LOW") for i in issues if i.code != SemanticIssueCode.HEURISTIC_ONLY):
        status = LayerStatus.PARTIAL
    elif issues and all(i.code == SemanticIssueCode.HEURISTIC_ONLY for i in issues):
        status = LayerStatus.PASS
    elif issues:
        status = LayerStatus.PARTIAL if not strict else LayerStatus.PASS
    else:
        status = LayerStatus.PASS
    return LayerResult(
        layer=layer,
        status=status,
        confidence=confidence,
        issues=[i.to_dict() for i in issues],
    )


def run_multimodal_consistency_gate(
    intent: SceneIntent,
    *,
    asset_path: str = "",
    analysis_fixture: Optional[dict[str, Any]] = None,
    provider_prompt: str = "",
    negative_prompt: str = "",
    audio_meta: Optional[dict[str, Any]] = None,
    subtitle_meta: Optional[dict[str, Any]] = None,
    localized: Optional[dict[str, Any]] = None,
    audio_duration_sec: float = 0.0,
    subtitle_duration_sec: float = 0.0,
    visual_duration_sec: float = 0.0,
    scene_duration_sec: float = 0.0,
    request_dialogue_id: str = "",
    continuity: Optional[ContinuityTracker] = None,
    strict: bool = False,
    skip_technical: bool = False,
) -> IndustrialValidationReport:
    """
    Industrial multimodal boundary — single semantic source controls generation + validation.
    """
    from pipeline.visual_semantic.boundary import analysis_from_fixture, run_visual_semantic_gate

    compiled = compile_provider_prompt(intent)
    confidence = ConfidenceLevel.OFFLINE_TEST_ONLY if analysis_fixture else ConfidenceLevel.HEURISTIC
    if strict and analysis_fixture:
        strict = True

    layers: list[LayerResult] = []

    # PROMPT layer — before provider execution
    prompt_issues = validate_prompt_contradiction(
        intent,
        compiled,
        provider_prompt=provider_prompt,
        negative_prompt=negative_prompt,
    )
    layers.append(_layer_from_issues(ValidationLayer.PROMPT, prompt_issues, confidence=confidence, strict=strict))

    # TECHNICAL layer
    tech_issues: list[SemanticIssue] = []
    if asset_path and not skip_technical:
        ok, reason = validate_visual_asset(asset_path, mode="video")
        if not ok:
            tech_issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.TECHNICAL_INVALID,
                    message=f"Technical validation failed: {reason}",
                    severity="CRITICAL",
                    evidence={"path": asset_path, "reason": reason},
                )
            )
    tech_status = LayerStatus.BLOCKED if tech_issues else LayerStatus.PASS
    layers.append(
        LayerResult(
            layer=ValidationLayer.TECHNICAL,
            status=tech_status,
            confidence=confidence,
            issues=[i.to_dict() for i in tech_issues],
        )
    )

    # Analysis metadata
    if analysis_fixture is not None:
        analysis = analysis_from_fixture(analysis_fixture)
        strict = True
        confidence = ConfidenceLevel.OFFLINE_TEST_ONLY
    else:
        evaluator = get_evaluator(fixture=analysis_fixture, strict=strict)
        eval_result = evaluator.analyze_visual(intent, asset_path)
        raw = eval_result.visual_analysis
        analysis = VisualAnalysisMetadata(
            source=eval_result.source,
            actions=[str(x) for x in (raw.get("actions") or [])],
            objects=[str(x) for x in (raw.get("objects") or raw.get("entities") or [])],
            location=str(raw.get("location") or ""),
            posture=str(raw.get("posture") or ""),
            simultaneous_actions=bool(raw.get("simultaneous_actions", False)),
            description=str(raw.get("description") or intent.visual_emphasis or ""),
            dialogue_id=str(raw.get("dialogue_id") or intent.dialogue_id),
        )

    analysis_dict = analysis.to_dict()
    analysis_dict.update({k: v for k, v in (analysis_fixture or {}).items() if k not in analysis_dict})

    # SEMANTIC layer — entity grounding + visual semantic validators
    entity_issues = validate_entity_grounding(intent, analysis_dict, strict=strict)
    sem_result = run_visual_semantic_gate(
        intent,
        analysis,
        request_dialogue_id=request_dialogue_id or intent.dialogue_id,
        continuity=continuity,
        strict=strict,
    )
    semantic_issues = entity_issues + [i for i in sem_result.issues if i not in entity_issues]
    sem_status = LayerStatus.BLOCKED if sem_result.blocked else (
        LayerStatus.PARTIAL if sem_result.status.value == "SEMANTIC_PARTIAL" else LayerStatus.PASS
    )
    layers.append(
        LayerResult(
            layer=ValidationLayer.SEMANTIC,
            status=sem_status,
            confidence=confidence,
            issues=[i.to_dict() for i in semantic_issues],
        )
    )

    # CROSS_MODAL layer
    cross_issues: list[SemanticIssue] = []
    if audio_meta:
        cross_issues.extend(validate_audio_dialogue_identity(intent, audio_meta))
    cross_issues.extend(
        validate_dialogue_visual_consistency(intent, analysis_dict, strict=strict)
    )
    if subtitle_meta:
        cross_issues.extend(validate_subtitle_dialogue(intent, subtitle_meta))
    cross_issues.extend(
        validate_timeline_consistency(
            intent,
            audio_duration_sec=audio_duration_sec,
            subtitle_duration_sec=subtitle_duration_sec,
            visual_duration_sec=visual_duration_sec,
            scene_duration_sec=scene_duration_sec or (intent.audio_intent.duration_target_sec if intent.audio_intent else 0.0),
        )
    )
    layers.append(_layer_from_issues(ValidationLayer.CROSS_MODAL, cross_issues, confidence=confidence, strict=strict))

    # CONTINUITY layer
    cont_issues: list[SemanticIssue] = []
    if continuity is not None:
        cont_issues.extend(continuity.validate_continuity(intent, analysis))
    layers.append(_layer_from_issues(ValidationLayer.CONTINUITY, cont_issues, confidence=confidence, strict=strict))

    # LOCALIZATION layer
    loc_issues: list[SemanticIssue] = []
    if localized:
        loc_issues.extend(validate_localization_semantics(intent, localized))
    loc_status = LayerStatus.PASS if not localized else (
        LayerStatus.BLOCKED if any(i.severity == "CRITICAL" for i in loc_issues) else LayerStatus.PASS
    )
    layers.append(
        LayerResult(
            layer=ValidationLayer.LOCALIZATION,
            status=loc_status,
            confidence=confidence,
            issues=[i.to_dict() for i in loc_issues],
        )
    )

    if continuity is not None and sem_status != LayerStatus.BLOCKED:
        continuity.update_from_intent(intent, analysis)

    final = aggregate_final_status(layers)
    if tech_status == LayerStatus.BLOCKED:
        final = LayerStatus.BLOCKED

    return IndustrialValidationReport(
        scene_id=intent.scene_id,
        dialogue_id=intent.dialogue_id,
        revision_id=intent.revision_id,
        intent_fingerprint=intent_fingerprint(intent),
        layers=layers,
        final_status=final,
        metadata={
            "compiled_prompt_fingerprint": compiled.intent_fingerprint,
            "analysis_source": analysis.source,
            "strict": strict,
            "confidence": confidence.value,
        },
    )


def multimodal_gate_for_spec(
    *,
    asset_path: Path,
    narration_hint: str,
    visual_prompt: str,
    scene_id: str,
    dialogue_id: str,
    script_id: str = "",
    revision_id: str = "",
    analysis_fixture: Optional[dict[str, Any]] = None,
    continuity: Optional[ContinuityTracker] = None,
    skip: bool = False,
    strict: bool = False,
    audio_meta: Optional[dict[str, Any]] = None,
    subtitle_meta: Optional[dict[str, Any]] = None,
    localized: Optional[dict[str, Any]] = None,
) -> IndustrialValidationReport:
    """Production helper — build SceneIntent from dialogue + run multimodal gate."""
    if skip:
        return IndustrialValidationReport(
            scene_id=str(scene_id),
            dialogue_id=dialogue_id,
            final_status=LayerStatus.UNKNOWN,
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
    intent.revision_id = revision_id

    compiled = compile_provider_prompt(intent)
    return run_multimodal_consistency_gate(
        intent,
        asset_path=str(asset_path),
        analysis_fixture=analysis_fixture,
        provider_prompt=visual_prompt or compiled.positive,
        negative_prompt=compiled.negative,
        audio_meta=audio_meta,
        subtitle_meta=subtitle_meta,
        localized=localized,
        request_dialogue_id=dialogue_id,
        continuity=continuity,
        strict=strict or analysis_fixture is not None,
    )
