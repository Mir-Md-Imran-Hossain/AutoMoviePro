"""BUILD-04F repair mapping for rendering integrity. No second repair engine."""
from __future__ import annotations

from typing import Any, Optional

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
from pipeline.rendering_integrity.gate import allow_render_integrity_repair_cycle, record_render_integrity_repair_cycle


def scope_for_render_issue(issue: str) -> RepairScope:
    i = (issue or "").lower()
    if "vmaf" in i or "perceptual" in i:
        return RepairScope.RENDER
    if "subtitle" in i or "text" in i or "glyph" in i or "rtl" in i:
        return RepairScope.TEXT_RENDER
    if "audio" in i and "video" not in i:
        return RepairScope.AUDIO_ASSET
    if "filter" in i or "stream" in i or "geometry" in i or "fps" in i or "duration" in i:
        return RepairScope.RENDER
    if "vfx" in i or "transition" in i:
        return RepairScope.RENDER
    if "timeline" in i or "overlap" in i or "gap" in i:
        return RepairScope.RENDER
    return RepairScope.FINAL_VIDEO


def recommended_action_for_render_issue(issue: str) -> str:
    i = (issue or "").lower()
    if "vmaf_low" in i or ("vmaf" in i and "low" in i) or "perceptual:vmaf_low" in i:
        return "reencode_higher_crf_or_replace_low_quality_source_asset"
    if "subtitle" in i or "text" in i:
        return "repair_text_render_or_burnin"
    return "repair_render_contract_or_remux"


def plan_perceptual_vmaf_repair(
    *,
    issues: list[str],
    subject_id: str = "perceptual_vmaf",
    attempt: int = 1,
    old_fingerprint: str = "",
    work_dir=None,
) -> Optional[RepairPlan]:
    """Targeted repair when libvmaf reports low perceptual quality (not semantic)."""
    vmaf_issues = [i for i in (issues or []) if "vmaf" in str(i).lower() or "perceptual" in str(i).lower()]
    if not vmaf_issues:
        return None
    return plan_rendering_integrity_repair(
        issues=vmaf_issues,
        subject_id=subject_id,
        attempt=attempt,
        old_fingerprint=old_fingerprint,
        work_dir=work_dir,
    )


def plan_rendering_integrity_repair(
    *,
    issues: list[str],
    subject_id: str = "render",
    attempt: int = 1,
    old_fingerprint: str = "",
    work_dir=None,
) -> Optional[RepairPlan]:
    if not issues:
        return None
    if work_dir is not None and not allow_render_integrity_repair_cycle(work_dir):
        return None
    q_issues = [
        QualityIssue(
            issue_id=f"ri-{i[:40]}",
            stage="rendering_integrity",
            severity=IssueSeverity.CRITICAL,
            category="rendering_integrity",
            subject_id=subject_id,
            description=i,
            repair_scope=scope_for_render_issue(i),
            recommended_action=recommended_action_for_render_issue(i),
        )
        for i in issues
    ]
    primary = issues[0]
    quality = CreativeQualityResult(
        subject="rendering_integrity",
        subject_id=subject_id,
        stage="render",
        verdict=QualityVerdict.REPAIR_REQUIRED,
        score=0.25,
        dimensions={QualityDimension.TECHNICAL_MEDIA_QUALITY.value: 0.25},
        issues=q_issues,
        repair_scope=scope_for_render_issue(primary),
        recommended_action=recommended_action_for_render_issue(primary),
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=old_fingerprint,
    )
    plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)
    if plan and work_dir is not None:
        record_render_integrity_repair_cycle(work_dir, outcome="repair_planned", scope=plan.repair_scope.value)
    return plan
