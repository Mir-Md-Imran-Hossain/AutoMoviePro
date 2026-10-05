"""Audio/visual/subtitle timeline consistency (T004-C3)."""
from __future__ import annotations

from typing import Any

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode


def validate_timeline_consistency(
    intent: SceneIntent,
    *,
    audio_duration_sec: float = 0.0,
    subtitle_duration_sec: float = 0.0,
    visual_duration_sec: float = 0.0,
    scene_duration_sec: float = 0.0,
    tolerance_sec: float = 1.5,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    target = scene_duration_sec or (
        (intent.audio_intent.duration_target_sec if intent.audio_intent else None) or 0.0
    )
    target = float(target or 0.0)

    def _check(a: float, b: float, label: str) -> None:
        if a > 0 and b > 0 and abs(a - b) > tolerance_sec:
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.TEMPORAL_CONTRADICTION,
                    message=f"Timeline mismatch: {label}",
                    severity="HIGH",
                    evidence={"a": a, "b": b, "tolerance": tolerance_sec},
                )
            )

    if audio_duration_sec > 0 and subtitle_duration_sec > 0:
        _check(audio_duration_sec, subtitle_duration_sec, "audio vs subtitle duration")
    if audio_duration_sec > 0 and visual_duration_sec > 0:
        _check(audio_duration_sec, visual_duration_sec, "audio vs visual duration")
    if target > 0 and audio_duration_sec > 0:
        _check(target, audio_duration_sec, "scene target vs audio duration")

    cue_count = subtitle_meta_cue_count(intent)
    sub_dur = subtitle_duration_sec or (
        intent.subtitle_intent.total_duration_sec if intent.subtitle_intent else 0.0
    )
    if cue_count > 0 and sub_dur <= 0:
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.TEMPORAL_CONTRADICTION,
                message="Subtitle cues declared but duration missing",
                severity="MEDIUM",
                evidence={"cue_count": cue_count},
            )
        )
    return issues


def subtitle_meta_cue_count(intent: SceneIntent) -> int:
    if intent.subtitle_intent:
        return int(intent.subtitle_intent.cue_count or 0)
    return 0
