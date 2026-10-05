"""BUILD-04F repair mapping for creative production failures. No second repair engine."""
from __future__ import annotations

from typing import Any, Optional

from pipeline.creative_production.gate import allow_creative_repair_cycle, record_creative_repair_cycle
from pipeline.quality.contracts import (
    EVALUATOR_VERSION,
    RULE_VERSION,
    CreativeQualityResult,
    IssueSeverity,
    QualityDimension,
    QualityIssue,
    QualityVerdict,
    RepairScope,
)
from pipeline.quality.repair_planner import RepairPlan, plan_repair


def scope_for_creative_issue(issue: str) -> RepairScope:
    i = (issue or "").lower()
    if "hook" in i or "script" in i or "repetition" in i or "clickbait" in i or "title" in i:
        return RepairScope.SCRIPT_SECTION if "hook" in i or "title" in i else RepairScope.SCRIPT
    if "transition" in i:
        return RepairScope.RENDER
    if "music" in i:
        return RepairScope.MUSIC_ASSET
    if "sfx" in i:
        return RepairScope.SFX_ASSET
    if "visual" in i or "camera" in i or "shot" in i or "metaphor" in i or "smartphone" in i or "transform" in i:
        return RepairScope.VISUAL_PLAN
    if "dialogue" in i or "pacing" in i:
        return RepairScope.DIALOGUE
    return RepairScope.SCENE


def plan_creative_production_repair(
    *,
    issues: list[str],
    subject_id: str = "creative",
    attempt: int = 1,
    old_fingerprint: str = "",
    work_dir=None,
) -> Optional[RepairPlan]:
    if not issues:
        return None
    if work_dir is not None and not allow_creative_repair_cycle(work_dir):
        return None
    q_issues = [
        QualityIssue(
            issue_id=f"cr-{i[:40]}",
            stage="creative_production",
            severity=IssueSeverity.CRITICAL,
            category="creative_production",
            subject_id=subject_id,
            description=i,
            repair_scope=scope_for_creative_issue(i),
            recommended_action="repair_minimal_creative_scope",
        )
        for i in issues
    ]
    quality = CreativeQualityResult(
        subject="creative_production",
        subject_id=subject_id,
        stage="creative",
        verdict=QualityVerdict.REPAIR_REQUIRED,
        score=0.25,
        dimensions={QualityDimension.SCRIPT_STRUCTURE.value: 0.25},
        issues=q_issues,
        repair_scope=scope_for_creative_issue(issues[0]),
        recommended_action="repair_minimal_creative_scope",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=old_fingerprint,
    )
    plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)
    if plan and work_dir is not None:
        record_creative_repair_cycle(work_dir, outcome="repair_planned", scope=plan.repair_scope.value)
    return plan
