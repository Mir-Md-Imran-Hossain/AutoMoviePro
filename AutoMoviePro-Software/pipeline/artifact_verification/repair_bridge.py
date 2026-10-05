"""BUILD-04F repair integration for artifact verification failures (AMP-004 Phase-04).

Does NOT create a second repair engine.
"""
from __future__ import annotations

from typing import Any, Optional

from pipeline.artifact_verification.contracts import ArtifactObservation, MediaType, ObservationStatus
from pipeline.artifact_verification.gate import allow_another_repair_cycle, record_verify_cycle
from pipeline.quality.contracts import (
    CreativeQualityResult,
    IssueSeverity,
    QualityDimension,
    QualityIssue,
    QualityVerdict,
    RepairScope,
    EVALUATOR_VERSION,
    RULE_VERSION,
)
from pipeline.quality.repair_planner import RepairPlan, plan_repair


def _scope_for_observation(obs: ArtifactObservation) -> RepairScope:
    mt = obs.media_type
    if mt == MediaType.COMPOSITE or obs.layer == "E":
        return RepairScope.RENDER
    if mt == MediaType.AUDIO:
        return RepairScope.AUDIO_ASSET
    if mt == MediaType.SUBTITLE:
        return RepairScope.SUBTITLE
    if mt in (MediaType.VIDEO, MediaType.IMAGE, MediaType.THUMBNAIL):
        return RepairScope.VISUAL_ASSET
    return RepairScope.SCENE


def observation_to_quality(obs: ArtifactObservation) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    if obs.observation_status == ObservationStatus.FAIL or obs.technical_status == ObservationStatus.FAIL:
        for msg in obs.issues or ["artifact_fail"]:
            issues.append(
                QualityIssue(
                    issue_id=f"art-{obs.artifact_id}-{msg}"[:80],
                    stage="artifact",
                    severity=IssueSeverity.CRITICAL,
                    category="artifact_verification",
                    subject_id=obs.scene_id or obs.artifact_id,
                    description=msg,
                    evidence=dict(obs.evidence),
                    repair_scope=_scope_for_observation(obs),
                    recommended_action="regenerate_minimal_scope",
                )
            )
    # UNKNOWN semantic alone must NOT auto-trigger expensive regeneration
    verdict = QualityVerdict.PASS
    if issues:
        verdict = QualityVerdict.REPAIR_REQUIRED
    elif obs.observation_status == ObservationStatus.UNKNOWN:
        verdict = QualityVerdict.UNKNOWN

    return CreativeQualityResult(
        subject="artifact_verification",
        subject_id=obs.scene_id or obs.artifact_id,
        stage="artifact",
        verdict=verdict,
        score=0.2 if issues else (0.5 if verdict == QualityVerdict.UNKNOWN else 0.9),
        dimensions={QualityDimension.TECHNICAL_MEDIA_QUALITY.value: 0.2 if issues else 0.9},
        issues=issues,
        evidence={
            "artifact_fingerprint": obs.artifact_fingerprint,
            "semantic_status": obs.semantic_status.value,
            "technical_status": obs.technical_status.value,
        },
        repair_scope=_scope_for_observation(obs) if issues else None,
        recommended_action="regenerate_minimal_scope" if issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=obs.artifact_fingerprint,
    )


def plan_artifact_repair(
    obs: ArtifactObservation,
    *,
    attempt: int = 1,
    work_dir=None,
) -> Optional[RepairPlan]:
    """Smallest repair scope; UNKNOWN semantic → no auto-regen; cycle-limited."""
    if work_dir is not None and not allow_another_repair_cycle(work_dir):
        return None
    quality = observation_to_quality(obs)
    if quality.verdict == QualityVerdict.UNKNOWN:
        # Policy: do not automatically regenerate on semantic UNKNOWN alone
        return None
    plan = plan_repair(
        quality,
        attempt=attempt,
        old_fingerprint=obs.artifact_fingerprint,
        revision_counter=attempt,
    )
    if plan and work_dir is not None:
        record_verify_cycle(work_dir, outcome="repair_planned", repair_scope=plan.repair_scope.value)
    return plan


def may_regenerate_artifact(
    *,
    prior_observation: Optional[ArtifactObservation],
    current_fingerprint: str = "",
) -> bool:
    """Reuse valid artifacts — do not regenerate if fingerprint + verification remain valid."""
    if prior_observation is None:
        return True
    if prior_observation.technical_status == ObservationStatus.PASS:
        if current_fingerprint and prior_observation.artifact_fingerprint == current_fingerprint:
            return False
        if not current_fingerprint and prior_observation.artifact_fingerprint:
            return False
    return True
