"""BUILD-04F targeted repair integration for semantic visual failures."""
from __future__ import annotations

from typing import Any, Optional

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
from pipeline.quality.repair_runtime import RepairExecutionResult, execute_repair_request
from pipeline.quality.thresholds import DEFAULT_MAX_SCENE_REPAIRS
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode, VisualSemanticResult


def semantic_result_to_quality(
    sem: VisualSemanticResult,
    *,
    subject_id: str = "",
) -> CreativeQualityResult:
    """Convert semantic validation result to BUILD-04F CreativeQualityResult."""
    issues: list[QualityIssue] = []
    sid = subject_id or sem.scene_id or "scene-unknown"
    for si in sem.issues:
        if si.code == SemanticIssueCode.HEURISTIC_ONLY:
            continue
        sev = IssueSeverity.HIGH
        if si.severity == "CRITICAL":
            sev = IssueSeverity.CRITICAL
        elif si.severity == "MEDIUM":
            sev = IssueSeverity.MEDIUM
        elif si.severity == "LOW":
            sev = IssueSeverity.LOW
        elif si.severity == "INFO":
            sev = IssueSeverity.INFO
        issues.append(
            QualityIssue(
                issue_id=f"sem-{si.code.value}-{sid}",
                stage="visual",
                severity=sev,
                category=si.code.value,
                subject_id=sid,
                description=si.message,
                evidence=dict(si.evidence),
                # Continuity post-gen failures → smallest visual/scene scope (BUILD-04F);
                # do NOT escalate to SCRIPT unless planner dependency graph requires it.
                repair_scope=(
                    RepairScope.SCENE
                    if si.code == SemanticIssueCode.CONTINUITY_BREAK
                    else RepairScope.VISUAL_ASSET
                ),
                recommended_action=(
                    "regenerate_visual_with_continuity"
                    if si.code == SemanticIssueCode.CONTINUITY_BREAK
                    else "regenerate_visual"
                ),
            )
        )

    if sem.blocked:
        verdict = QualityVerdict.REPAIR_REQUIRED
        score = 0.25
    elif sem.status.value == "SEMANTIC_PARTIAL":
        verdict = QualityVerdict.REPAIR_REQUIRED
        score = 0.55
    elif sem.semantic_ok:
        verdict = QualityVerdict.PASS
        score = 0.9
    else:
        verdict = QualityVerdict.UNKNOWN
        score = 0.5

    return CreativeQualityResult(
        subject="visual_semantic",
        subject_id=sid,
        stage="visual",
        verdict=verdict,
        score=score,
        dimensions={QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value: score},
        issues=issues,
        evidence={"intent_fingerprint": sem.intent_fingerprint},
        repair_scope=RepairScope.VISUAL_ASSET if issues else None,
        recommended_action="regenerate_visual" if issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
        artifact_fingerprint=sem.intent_fingerprint,
    )


def plan_semantic_repair(
    sem: VisualSemanticResult,
    *,
    attempt: int = 1,
    old_fingerprint: str = "",
) -> Optional[RepairPlan]:
    quality = semantic_result_to_quality(sem)
    if attempt > DEFAULT_MAX_SCENE_REPAIRS:
        plan = plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint)
        if plan:
            plan.escalate = True
        return plan
    return plan_repair(quality, attempt=attempt, old_fingerprint=old_fingerprint, revision_counter=attempt)


def execute_semantic_repair(
    work_dir,
    *,
    job_id: str,
    plan: RepairPlan,
    repair_fn,
) -> RepairExecutionResult:
    """
    Targeted visual/scene repair — BUILD-04F only.

    Must NOT wipe CONTINUITY_STATE.json or reset valid upstream continuity;
    ContinuityTracker.load(work_dir) remains authoritative across retries.
    """
    from pathlib import Path

    issue_fp = plan.old_fingerprint or plan.revision_id
    return execute_repair_request(
        Path(work_dir),
        job_id=job_id,
        plan=plan,
        issue_fingerprint=issue_fp,
        repair_fn=repair_fn,
    )
