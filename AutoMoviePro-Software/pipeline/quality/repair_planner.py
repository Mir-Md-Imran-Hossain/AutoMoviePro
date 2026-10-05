"""Targeted repair planning (BUILD-04F)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.quality.contracts import CreativeQualityResult, QualityIssue, QualityVerdict, RepairScope
from pipeline.quality.thresholds import DEFAULT_MAX_REPAIR_ATTEMPTS, DEFAULT_MAX_SCENE_REPAIRS, DEFAULT_MAX_SCRIPT_REPAIRS


@dataclass
class RepairPlan:
    repair_scope: RepairScope
    subject_id: str
    issue_ids: list[str] = field(default_factory=list)
    attempt: int = 1
    max_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    old_fingerprint: str = ""
    revision_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""
    escalate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_scope": self.repair_scope.value,
            "subject_id": self.subject_id,
            "issue_ids": list(self.issue_ids),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "old_fingerprint": self.old_fingerprint,
            "revision_id": self.revision_id,
            "evidence": dict(self.evidence),
            "recommended_action": self.recommended_action,
            "escalate": self.escalate,
        }


SCOPE_PRIORITY = [
    RepairScope.DIALOGUE,
    RepairScope.SCRIPT_SECTION,
    RepairScope.VISUAL_PLAN,
    RepairScope.VISUAL_ASSET,
    RepairScope.AUDIO_PLAN,
    RepairScope.AUDIO_ASSET,
    RepairScope.SFX_ASSET,
    RepairScope.MUSIC_ASSET,
    RepairScope.AUDIO_MIX,
    RepairScope.SUBTITLE,
    RepairScope.LOCALIZATION,
    RepairScope.TEXT_LAYOUT,
    RepairScope.TEXT_RENDER,
    RepairScope.RENDER,
    RepairScope.SCENE,
    RepairScope.SCRIPT,
    RepairScope.FINAL_VIDEO,
]


def plan_repair(
    result: CreativeQualityResult,
    *,
    attempt: int = 1,
    old_fingerprint: str = "",
    revision_counter: int = 1,
) -> Optional[RepairPlan]:
    if result.verdict == QualityVerdict.PASS:
        return None
    if result.verdict == QualityVerdict.UNKNOWN:
        return None
    if result.verdict == QualityVerdict.BLOCKED:
        return None

    issues = result.issues
    if not issues and result.repair_scope:
        scope = result.repair_scope
        subject = result.subject_id
    else:
        # Smallest valid scope from highest-severity issue
        sorted_issues = sorted(
            issues,
            key=lambda i: (i.severity.value, SCOPE_PRIORITY.index(i.repair_scope) if i.repair_scope in SCOPE_PRIORITY else 99),
        )
        if not sorted_issues:
            return None
        primary = sorted_issues[0]
        scope = primary.repair_scope
        subject = primary.subject_id or result.subject_id

    max_attempts = DEFAULT_MAX_SCENE_REPAIRS if scope in (
        RepairScope.SCENE, RepairScope.VISUAL_ASSET, RepairScope.VISUAL_PLAN
    ) else DEFAULT_MAX_SCRIPT_REPAIRS if scope in (RepairScope.SCRIPT, RepairScope.SCRIPT_SECTION, RepairScope.DIALOGUE) else DEFAULT_MAX_REPAIR_ATTEMPTS

    escalate = attempt >= max_attempts
    revision_id = f"r{revision_counter + attempt:03d}"

    return RepairPlan(
        repair_scope=scope,
        subject_id=subject,
        issue_ids=[i.issue_id for i in issues[:5]],
        attempt=attempt,
        max_attempts=max_attempts,
        old_fingerprint=old_fingerprint,
        revision_id=revision_id,
        evidence={i.issue_id: i.evidence for i in issues[:3]},
        recommended_action=issues[0].recommended_action if issues else result.recommended_action,
        escalate=escalate,
    )


def should_regenerate_broadly(plans: list[RepairPlan]) -> bool:
    """True only when evidence shows script-level root cause."""
    script_scopes = {RepairScope.SCRIPT, RepairScope.SCRIPT_SECTION}
    return len(plans) > 3 and sum(1 for p in plans if p.repair_scope in script_scopes) >= 2
