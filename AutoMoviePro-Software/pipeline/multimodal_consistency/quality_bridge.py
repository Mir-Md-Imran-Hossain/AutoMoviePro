"""Feed multimodal consistency signals into BUILD-04F quality/repair (T004-C3)."""
from __future__ import annotations

from typing import Optional

from pipeline.multimodal_consistency.industrial_status import IndustrialValidationReport, LayerStatus, ValidationLayer
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
from pipeline.quality.thresholds import DEFAULT_MAX_SCENE_REPAIRS


def multimodal_report_to_quality(
    report: IndustrialValidationReport,
    *,
    subject_id: str = "",
) -> CreativeQualityResult:
    """Convert IndustrialValidationReport to BUILD-04F CreativeQualityResult."""
    issues: list[QualityIssue] = []
    sid = subject_id or report.scene_id or "scene-unknown"
    for layer in report.layers:
        for raw in layer.issues:
            sev_str = str(raw.get("severity") or "HIGH").upper()
            sev = IssueSeverity.HIGH
            if sev_str == "CRITICAL":
                sev = IssueSeverity.CRITICAL
            elif sev_str == "MEDIUM":
                sev = IssueSeverity.MEDIUM
            elif sev_str == "LOW":
                sev = IssueSeverity.LOW
            elif sev_str == "INFO":
                sev = IssueSeverity.INFO
            code = str(raw.get("code") or "semantic")
            issues.append(
                QualityIssue(
                    issue_id=f"mm-{layer.layer.value}-{code}-{sid}",
                    stage="multimodal",
                    severity=sev,
                    category=code,
                    subject_id=sid,
                    description=str(raw.get("message") or code),
                    evidence=dict(raw.get("evidence") or {}),
                    repair_scope=RepairScope.VISUAL_ASSET,
                    recommended_action="regenerate_visual",
                )
            )

    if report.blocked:
        verdict = QualityVerdict.REPAIR_REQUIRED
        score = 0.2
    elif report.final_status == LayerStatus.PARTIAL:
        verdict = QualityVerdict.REPAIR_REQUIRED
        score = 0.55
    elif report.passed:
        verdict = QualityVerdict.PASS
        score = 0.9
    else:
        verdict = QualityVerdict.UNKNOWN
        score = 0.5

    dims = {
        QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value: score,
        "multimodal_consistency": score,
    }
    return CreativeQualityResult(
        subject="multimodal_consistency",
        subject_id=sid,
        stage="visual",
        verdict=verdict,
        score=score,
        dimensions=dims,
        issues=issues,
        evidence={"intent_fingerprint": report.intent_fingerprint, "layers": [l.to_dict() for l in report.layers]},
        repair_scope=RepairScope.VISUAL_ASSET if issues else None,
        recommended_action="regenerate_visual" if issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=report.intent_fingerprint,
    )


def plan_multimodal_repair(
    report: IndustrialValidationReport,
    *,
    attempt: int = 1,
    old_fingerprint: str = "",
) -> Optional[RepairPlan]:
    quality = multimodal_report_to_quality(report)
    if attempt > DEFAULT_MAX_SCENE_REPAIRS:
        plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint)
        if plan:
            plan.escalate = True
        return plan
    return plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)
