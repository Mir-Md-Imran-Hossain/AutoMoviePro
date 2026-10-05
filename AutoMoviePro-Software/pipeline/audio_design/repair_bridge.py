"""BUILD-04F repair mapping for audio design failures (AMP-004 Phase-05)."""
from __future__ import annotations

from typing import Any, Optional

from pipeline.audio_design.gate import allow_audio_repair_cycle, record_audio_repair_cycle
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


def scope_for_audio_issue(issue: str) -> RepairScope:
    i = (issue or "").lower()
    if "sfx" in i:
        return RepairScope.SFX_ASSET
    if "music" in i:
        return RepairScope.MUSIC_ASSET
    if "mix" in i or "duck" in i or "clipping" in i or "loudness" in i:
        return RepairScope.AUDIO_MIX
    if "subtitle" in i:
        return RepairScope.SUBTITLE
    if "render" in i or "final" in i:
        return RepairScope.RENDER
    return RepairScope.AUDIO_ASSET


def plan_audio_design_repair(
    *,
    issues: list[str],
    subject_id: str = "audio",
    attempt: int = 1,
    old_fingerprint: str = "",
    work_dir=None,
) -> Optional[RepairPlan]:
    if not issues:
        return None
    if work_dir is not None and not allow_audio_repair_cycle(work_dir):
        return None
    # UNKNOWN-only must not auto-regenerate — caller should not pass unknown-as-fail
    q_issues = [
        QualityIssue(
            issue_id=f"aud-{i[:40]}",
            stage="audio",
            severity=IssueSeverity.CRITICAL,
            category="audio_design",
            subject_id=subject_id,
            description=i,
            repair_scope=scope_for_audio_issue(i),
            recommended_action="regenerate_minimal_audio_scope",
        )
        for i in issues
    ]
    quality = CreativeQualityResult(
        subject="audio_design",
        subject_id=subject_id,
        stage="audio",
        verdict=QualityVerdict.REPAIR_REQUIRED,
        score=0.25,
        dimensions={QualityDimension.AUDIO_QUALITY.value: 0.25},
        issues=q_issues,
        repair_scope=scope_for_audio_issue(issues[0]),
        recommended_action="regenerate_minimal_audio_scope",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=old_fingerprint,
    )
    plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)
    if plan and work_dir is not None:
        record_audio_repair_cycle(work_dir, outcome="repair_planned", scope=plan.repair_scope.value)
    return plan
