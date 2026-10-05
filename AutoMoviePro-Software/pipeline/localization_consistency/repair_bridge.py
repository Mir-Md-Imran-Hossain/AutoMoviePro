"""BUILD-04F repair mapping for localization/subtitle/text (AMP-004 Phase-06)."""
from __future__ import annotations

from typing import Optional

from pipeline.localization_consistency.gate import allow_loc_repair_cycle, record_loc_repair_cycle
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


def scope_for_loc_issue(issue: str) -> RepairScope:
    i = (issue or "").lower()
    if "subtitle" in i or "reading_speed" in i or "line_" in i:
        return RepairScope.SUBTITLE
    if "overflow" in i or "safe_area" in i or "collision" in i or "layout" in i:
        return RepairScope.TEXT_LAYOUT
    if "glyph" in i or "font" in i or "rtl" in i:
        return RepairScope.TEXT_RENDER
    if "audio" in i:
        return RepairScope.AUDIO_ASSET
    if "render" in i or "composite" in i:
        return RepairScope.RENDER
    return RepairScope.LOCALIZATION


def plan_localization_repair(
    *,
    issues: list[str],
    subject_id: str = "loc",
    attempt: int = 1,
    old_fingerprint: str = "",
    work_dir=None,
) -> Optional[RepairPlan]:
    if not issues:
        return None
    if work_dir is not None and not allow_loc_repair_cycle(work_dir):
        return None
    q_issues = [
        QualityIssue(
            issue_id=f"loc-{i[:40]}",
            stage="localization",
            severity=IssueSeverity.CRITICAL,
            category="localization",
            subject_id=subject_id,
            description=i,
            repair_scope=scope_for_loc_issue(i),
            recommended_action="repair_minimal_localization_scope",
        )
        for i in issues
    ]
    quality = CreativeQualityResult(
        subject="localization",
        subject_id=subject_id,
        stage="localization",
        verdict=QualityVerdict.REPAIR_REQUIRED,
        score=0.25,
        dimensions={QualityDimension.SUBTITLE_ALIGNMENT.value: 0.25},
        issues=q_issues,
        repair_scope=scope_for_loc_issue(issues[0]),
        recommended_action="repair_minimal_localization_scope",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=old_fingerprint,
    )
    plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)
    if plan and work_dir is not None:
        record_loc_repair_cycle(work_dir, outcome="repair_planned", scope=plan.repair_scope.value)
    return plan
