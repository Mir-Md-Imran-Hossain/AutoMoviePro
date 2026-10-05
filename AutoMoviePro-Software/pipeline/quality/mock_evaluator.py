"""Mock quality evaluator (BUILD-04F)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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
from pipeline.quality.evaluators import evaluate_script_quality, evaluate_scene_visual_alignment


class MockQualityBehavior(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REPAIR = "repair"
    REGENERATE = "regenerate"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    WEAK_HOOK = "weak_hook"
    WRONG_VISUAL = "wrong_visual"
    WRONG_EMOTION = "wrong_emotion"
    SUBTITLE_MISMATCH = "subtitle_mismatch"
    CROSS_MODAL = "cross_modal"
    FACT_CONTRADICTION = "fact_contradiction"
    STATIC_MOTION = "static_motion"


@dataclass
class MockQualityEvaluator:
    behavior: MockQualityBehavior = MockQualityBehavior.PASS
    invocation_count: int = field(default=0, init=False)

    def reset(self) -> None:
        self.invocation_count = 0

    def evaluate(self, *, context: dict[str, Any]) -> CreativeQualityResult:
        self.invocation_count += 1
        stage = str(context.get("stage") or "final")
        subject_id = str(context.get("subject_id") or "job-1")

        if self.behavior == MockQualityBehavior.UNKNOWN:
            return CreativeQualityResult(
                subject=stage, subject_id=subject_id, stage=stage,
                verdict=QualityVerdict.UNKNOWN, score=0.0,
                evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
            )
        if self.behavior == MockQualityBehavior.BLOCKED:
            return CreativeQualityResult(
                subject=stage, subject_id=subject_id, stage=stage,
                verdict=QualityVerdict.BLOCKED, score=0.0,
                issues=[QualityIssue(
                    issue_id="blocked", stage=stage, severity=IssueSeverity.CRITICAL,
                    category="BLOCKED", subject_id=subject_id,
                    description="Evaluation blocked — insufficient evidence.",
                    repair_scope=RepairScope.SCENE,
                )],
                evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
            )
        if self.behavior == MockQualityBehavior.WEAK_HOOK:
            plan = context.get("plan") or {"topic": "test", "scenes": [{"narration": "Hey guys welcome back to my channel"}]}
            return evaluate_script_quality(subject_id=subject_id, plan=plan)
        if self.behavior == MockQualityBehavior.WRONG_VISUAL:
            return evaluate_scene_visual_alignment(
                scene_id=subject_id,
                narration="The spacecraft enters the atmosphere at high speed.",
                visual_prompt="busy urban street with traffic and pedestrians downtown",
                visual_query="city street",
                requires_motion=True,
                motion_detected=False,
            )
        if self.behavior == MockQualityBehavior.WRONG_EMOTION:
            from pipeline.quality.evaluators import evaluate_audio_quality
            return evaluate_audio_quality(
                subject_id=subject_id,
                narration_semantics="This is a serious warning about critical system failure.",
                delivery_style="cheerful",
            )
        if self.behavior == MockQualityBehavior.SUBTITLE_MISMATCH:
            from pipeline.quality.evaluators import evaluate_subtitle_creative
            return evaluate_subtitle_creative(
                subject_id=subject_id,
                subtitle_text="Completely different words here",
                dialogue_text="Original dialogue about spacecraft launch",
                structural_pass=True,
            )
        if self.behavior == MockQualityBehavior.CROSS_MODAL:
            from pipeline.quality.evaluators import evaluate_cross_modal
            return evaluate_cross_modal(
                subject_id=subject_id,
                script_cues={"time_of_day": "night"},
                visual_cues={"time_of_day": "daytime"},
            )
        if self.behavior == MockQualityBehavior.FACT_CONTRADICTION:
            plan = context.get("plan") or {
                "topic": "History",
                "scenes": [{"narration": "Event happened in 1999", "fact_gate": {"verdict": "FAIL", "allowed": False}}],
            }
            return evaluate_script_quality(subject_id=subject_id, plan=plan)
        if self.behavior == MockQualityBehavior.REPAIR:
            return CreativeQualityResult(
                subject=stage, subject_id=subject_id, stage=stage,
                verdict=QualityVerdict.REPAIR_REQUIRED, score=0.65,
                dimensions={QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value: 0.5},
                issues=[QualityIssue(
                    issue_id="repair-needed", stage=stage, severity=IssueSeverity.MEDIUM,
                    category="VISUAL_ALIGNMENT", subject_id=subject_id,
                    description="Targeted repair needed.", repair_scope=RepairScope.VISUAL_ASSET,
                )],
                repair_scope=RepairScope.VISUAL_ASSET,
                evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
            )
        if self.behavior == MockQualityBehavior.REGENERATE:
            return CreativeQualityResult(
                subject=stage, subject_id=subject_id, stage=stage,
                verdict=QualityVerdict.REGENERATE_REQUIRED, score=0.3,
                evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
            )
        if self.behavior == MockQualityBehavior.FAIL:
            return CreativeQualityResult(
                subject=stage, subject_id=subject_id, stage=stage,
                verdict=QualityVerdict.REGENERATE_REQUIRED, score=0.2,
                issues=[QualityIssue(
                    issue_id="fail", stage=stage, severity=IssueSeverity.CRITICAL,
                    category="QUALITY_FAIL", subject_id=subject_id,
                    description="Mock failure.", repair_scope=RepairScope.SCENE,
                )],
                evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
            )
        return CreativeQualityResult(
            subject=stage, subject_id=subject_id, stage=stage,
            verdict=QualityVerdict.PASS, score=0.92,
            dimensions={d.value: 0.9 for d in QualityDimension},
            evaluator_version=EVALUATOR_VERSION, rule_version=RULE_VERSION,
        )


_GLOBAL = MockQualityEvaluator()


def get_mock_quality_evaluator() -> MockQualityEvaluator:
    return _GLOBAL


def reset_mock_quality_evaluator() -> None:
    _GLOBAL.reset()
