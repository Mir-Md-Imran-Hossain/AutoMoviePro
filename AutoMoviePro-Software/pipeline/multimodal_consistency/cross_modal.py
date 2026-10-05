"""Cross-modal consistency: dialogue/visual/audio/subtitle (T004-C3)."""
from __future__ import annotations

import re
from typing import Any

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.contracts import SemanticIssue, SemanticIssueCode


def validate_audio_dialogue_identity(
    intent: SceneIntent,
    audio_meta: dict[str, Any],
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    if audio_meta.get("dialogue_id") and intent.dialogue_id:
        if str(audio_meta["dialogue_id"]).strip() != intent.dialogue_id.strip():
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH,
                    message="Audio dialogue_id does not match scene intent",
                    severity="CRITICAL",
                    evidence={"intent": intent.dialogue_id, "audio": audio_meta["dialogue_id"]},
                )
            )
    if audio_meta.get("scene_id") and intent.scene_id:
        if str(audio_meta["scene_id"]).strip() != str(intent.scene_id).strip():
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH,
                    message="Audio scene_id does not match scene intent",
                    severity="CRITICAL",
                    evidence={"intent": intent.scene_id, "audio": audio_meta["scene_id"]},
                )
            )
    return issues


def validate_dialogue_visual_consistency(
    intent: SceneIntent,
    visual_analysis: dict[str, Any],
    *,
    strict: bool = False,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    narr_kw = set(re.findall(r"[a-z]{3,}", intent.summary.lower()))
    vis_kw = set(re.findall(r"[a-z]{3,}", " ".join(visual_analysis.get("actions", []) + visual_analysis.get("objects", [])).lower()))
    if visual_analysis.get("description"):
        vis_kw |= set(re.findall(r"[a-z]{3,}", str(visual_analysis["description"]).lower()))

    if visual_analysis.get("wrong_actor"):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                message="Visual shows wrong actor",
                severity="CRITICAL",
                evidence={"expected_actors": intent.actors},
            )
        )

    if narr_kw and vis_kw and not (narr_kw & vis_kw):
        sev = "CRITICAL" if strict or visual_analysis.get("source") == "OFFLINE_TEST_ONLY" else "LOW"
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                message="Dialogue and visual share no semantic overlap",
                severity=sev,
                evidence={"narration_kw": sorted(narr_kw)[:8], "visual_kw": sorted(vis_kw)[:8]},
            )
        )

    if visual_analysis.get("contradiction"):
        issues.append(
            SemanticIssue(
                code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                message=str(visual_analysis["contradiction"]),
                severity="CRITICAL",
                evidence=visual_analysis,
            )
        )
    return issues


def validate_subtitle_dialogue(
    intent: SceneIntent,
    subtitle_meta: dict[str, Any],
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    if subtitle_meta.get("dialogue_id") and intent.dialogue_id:
        if str(subtitle_meta["dialogue_id"]).strip() != intent.dialogue_id.strip():
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_IDENTITY_MISMATCH,
                    message="Subtitle dialogue_id mismatch",
                    severity="CRITICAL",
                    evidence={"intent": intent.dialogue_id, "subtitle": subtitle_meta["dialogue_id"]},
                )
            )
    sub_text = str(subtitle_meta.get("text") or "").lower()
    narr = intent.summary.lower()
    if sub_text and narr:
        sub_kw = set(re.findall(r"[a-z]{3,}", sub_text))
        narr_kw = set(re.findall(r"[a-z]{3,}", narr))
        if sub_kw and narr_kw and not (sub_kw & narr_kw):
            issues.append(
                SemanticIssue(
                    code=SemanticIssueCode.DIALOGUE_VISUAL_CONTRADICTION,
                    message="Subtitle text diverges from dialogue meaning",
                    severity="HIGH",
                    evidence={"subtitle_preview": sub_text[:60], "dialogue_preview": narr[:60]},
                )
            )
    return issues
