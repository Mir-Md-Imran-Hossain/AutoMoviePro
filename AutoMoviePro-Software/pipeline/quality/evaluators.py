"""Deterministic creative quality evaluators (BUILD-04F)."""
from __future__ import annotations

import os
import re
from typing import Any, Optional, Sequence

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
from pipeline.quality.thresholds import (
    DEFAULT_MAX_DIALOGUE_SEC,
    DEFAULT_MIN_DIALOGUE_SEC,
    DIMENSION_WEIGHTS,
    PASS_SCORE_THRESHOLD,
    REPAIR_SCORE_THRESHOLD,
)


def _issue(
    *,
    issue_id: str,
    stage: str,
    severity: IssueSeverity,
    category: str,
    subject_id: str,
    description: str,
    evidence: dict[str, Any],
    repair_scope: RepairScope,
    action: str = "repair",
) -> QualityIssue:
    return QualityIssue(
        issue_id=issue_id,
        stage=stage,
        severity=severity,
        category=category,
        subject_id=subject_id,
        description=description,
        evidence=evidence,
        repair_scope=repair_scope,
        recommended_action=action,
    )


def _score_from_issues(dimensions: dict[str, float], issues: Sequence[QualityIssue]) -> float:
    if not dimensions:
        return 0.0
    # Score only dimensions that were actually evaluated. Missing dimensions must not
    # silently default to 0.5 and drag issue-free results into REPAIR_REQUIRED
    # (C11 FINAL job2270: visual dims PASS-quality but full-table default fill → 0.58).
    present = {k: float(v) for k, v in dimensions.items() if k in DIMENSION_WEIGHTS}
    if not present:
        return 0.0
    weight_sum = sum(DIMENSION_WEIGHTS[k] for k in present)
    if weight_sum <= 0:
        return 0.0
    weighted = sum(present[k] * DIMENSION_WEIGHTS[k] for k in present) / weight_sum
    penalty = sum(
        0.15 if i.severity == IssueSeverity.CRITICAL else
        0.08 if i.severity == IssueSeverity.HIGH else
        0.04 if i.severity == IssueSeverity.MEDIUM else 0.01
        for i in issues
    )
    return max(0.0, min(1.0, weighted - penalty))


def _verdict_from(score: float, issues: Sequence[QualityIssue]) -> QualityVerdict:
    if any(i.severity == IssueSeverity.CRITICAL for i in issues):
        scopes = {i.repair_scope for i in issues if i.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH)}
        if RepairScope.SCRIPT in scopes or RepairScope.SCRIPT_SECTION in scopes:
            return QualityVerdict.REGENERATE_REQUIRED
        return QualityVerdict.REPAIR_REQUIRED
    if any(i.category == "EVIDENCE_INSUFFICIENT" for i in issues):
        return QualityVerdict.UNKNOWN
    # Issues are authoritative. A low dimension score with zero issues must not
    # force regenerate/repair (seen on visual stage ~0.48 → REGENERATE with []).
    if not issues:
        return QualityVerdict.PASS
    if score >= PASS_SCORE_THRESHOLD:
        high_sev = {IssueSeverity.CRITICAL, IssueSeverity.HIGH}
        if not any(i.severity in high_sev for i in issues):
            return QualityVerdict.PASS
        return QualityVerdict.REPAIR_REQUIRED
    if score >= REPAIR_SCORE_THRESHOLD:
        return QualityVerdict.REPAIR_REQUIRED
    return QualityVerdict.REGENERATE_REQUIRED


def _keywords(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", (text or "").lower()))


def evaluate_script_quality(
    *,
    subject_id: str,
    plan: dict[str, Any],
    fact_pack: Optional[dict[str, Any]] = None,
) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    dims: dict[str, float] = {}
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    narrations = [str(s.get("narration") or "") for s in scenes]
    full_text = " ".join(narrations).strip()
    topic = str(plan.get("topic") or "")

    # Hook (first scene / opening)
    hook_text = narrations[0] if narrations else full_text[:200]
    hook_kw = _keywords(hook_text)
    topic_kw = _keywords(topic)
    hook_overlap = len(hook_kw & topic_kw) / max(1, len(topic_kw)) if topic_kw else 0.5
    generic_hooks = ("hey guys", "welcome back", "in today's video", "without further ado")
    if any(h in hook_text.lower() for h in generic_hooks):
        issues.append(_issue(
            issue_id="hook-generic-filler",
            stage="script",
            severity=IssueSeverity.HIGH,
            category="HOOK_WEAK",
            subject_id=subject_id,
            description="Opening contains generic filler instead of immediate topic relevance.",
            evidence={"hook_text": hook_text[:120], "matched": "generic_opener"},
            repair_scope=RepairScope.SCRIPT_SECTION,
            action="rewrite_hook",
        ))
        dims[QualityDimension.HOOK_STRENGTH.value] = 0.35
    elif hook_overlap < 0.1 and topic_kw:
        issues.append(_issue(
            issue_id="hook-topic-mismatch",
            stage="script",
            severity=IssueSeverity.HIGH,
            category="HOOK_WEAK",
            subject_id=subject_id,
            description="Opening lacks clear topic alignment — blocking for rewrite.",
            evidence={"hook_text": hook_text[:120], "topic": topic, "overlap": hook_overlap},
            repair_scope=RepairScope.SCRIPT_SECTION,
            action="rewrite_hook",
        ))
        dims[QualityDimension.HOOK_STRENGTH.value] = 0.35
    else:
        dims[QualityDimension.HOOK_STRENGTH.value] = 0.85

    # Opening attention (deterministic structural gate)
    try:
        from pipeline.creative_production.script_quality import score_opening_attention

        opening = score_opening_attention(hook_text, topic=topic)
        if opening.get("status") == "BLOCK":
            issues.append(_issue(
                issue_id="opening-attention-weak",
                stage="script",
                severity=IssueSeverity.HIGH,
                category="HOOK_WEAK",
                subject_id=subject_id,
                description="Opening fails attention-retention structural checks.",
                evidence=opening,
                repair_scope=RepairScope.SCRIPT_SECTION,
                action="rewrite_hook",
            ))
            dims[QualityDimension.HOOK_STRENGTH.value] = min(
                float(dims.get(QualityDimension.HOOK_STRENGTH.value, 0.5)),
                float(opening.get("score") or 0.4),
            )
    except Exception:
        pass

    # Naturalness via robot_detector
    try:
        from pipeline.robot_detector import robot_score
        robot = robot_score(narrations)
        dims[QualityDimension.DIALOGUE_NATURALNESS.value] = 1.0 - float(robot.get("score") or 0.5)
        if not robot.get("passed", True):
            issues.append(_issue(
                issue_id="dialogue-robot-like",
                stage="script",
                severity=IssueSeverity.HIGH,
                category="NATURALNESS",
                subject_id=subject_id,
                description="Dialogue exhibits repetitive or generic AI-like phrasing patterns.",
                evidence={"robot_issues": robot.get("issues"), "score": robot.get("score")},
                repair_scope=RepairScope.DIALOGUE,
                action="rewrite_dialogue",
            ))
    except Exception:
        dims[QualityDimension.DIALOGUE_NATURALNESS.value] = 0.7

    # Retention structure — scene progression diversity
    if len(scenes) >= 3:
        unique_starts = len({tuple(n.split()[:3]) if n.split() else () for n in narrations if n})
        prog = unique_starts / max(1, len(scenes))
        dims[QualityDimension.RETENTION_STRUCTURE.value] = min(1.0, 0.4 + prog * 0.6)
        if prog < 0.5:
            issues.append(_issue(
                issue_id="retention-repetitive",
                stage="script",
                severity=IssueSeverity.MEDIUM,
                category="RETENTION_WEAK",
                subject_id=subject_id,
                description="Script middle sections lack meaningful progression.",
                evidence={"scene_count": len(scenes), "unique_openers": unique_starts},
                repair_scope=RepairScope.SCRIPT_SECTION,
            ))
    else:
        dims[QualityDimension.RETENTION_STRUCTURE.value] = 0.75

    # Dialogue duration window 7–9s (short-form spoken beats)
    min_dur = float(os.environ.get("AMP_MIN_DIALOGUE_SEC", DEFAULT_MIN_DIALOGUE_SEC))
    max_dur = float(os.environ.get("AMP_MAX_DIALOGUE_SEC", DEFAULT_MAX_DIALOGUE_SEC))
    for i, narr in enumerate(narrations):
        try:
            from pipeline.dialogue_sync import estimate_spoken_seconds
            est = float(estimate_spoken_seconds(narr) or 0)
        except Exception:
            est = len(narr.split()) / 2.5
        # Soft band: slight overrun is common for documentary beats after TTS timing.
        # Hard HIGH only for clear overruns (not 0.08s past a razor threshold).
        if est > max_dur + 2.0:
            issues.append(_issue(
                issue_id=f"dialogue-too-long-{i}",
                stage="script",
                severity=IssueSeverity.HIGH,
                category="DIALOGUE_DURATION",
                subject_id=f"scene-{i:02d}",
                description=f"Dialogue estimated {est:.1f}s exceeds configured max {max_dur:.1f}s.",
                evidence={"estimated_sec": est, "max_sec": max_dur, "text_preview": narr[:80]},
                repair_scope=RepairScope.DIALOGUE,
                action="segment_or_rewrite",
            ))
        elif est > max_dur + 0.5:
            issues.append(_issue(
                issue_id=f"dialogue-soft-long-{i}",
                stage="script",
                severity=IssueSeverity.LOW,
                category="DIALOGUE_DURATION",
                subject_id=f"scene-{i:02d}",
                description=f"Dialogue estimated {est:.1f}s slightly over max {max_dur:.1f}s (soft).",
                evidence={"estimated_sec": est, "max_sec": max_dur, "text_preview": narr[:80], "soft": True},
                repair_scope=RepairScope.DIALOGUE,
                action="optional_trim",
            ))
        elif est > 0 and est < min_dur - 0.75:
            issues.append(_issue(
                issue_id=f"dialogue-too-short-{i}",
                stage="script",
                severity=IssueSeverity.MEDIUM,
                category="DIALOGUE_DURATION",
                subject_id=f"scene-{i:02d}",
                description=f"Dialogue estimated {est:.1f}s below target min {min_dur:.1f}s (want ~7–9s beats).",
                evidence={"estimated_sec": est, "min_sec": min_dur, "text_preview": narr[:80]},
                repair_scope=RepairScope.DIALOGUE,
                action="expand_or_merge",
            ))
        # Adjacent dialogue continuity (lexical bridge)
        if i > 0 and narrations[i - 1]:
            prev_kw = set(re.findall(r"[a-z0-9]{4,}", narrations[i - 1].lower()))
            cur_kw = set(re.findall(r"[a-z0-9]{4,}", narr.lower()))
            if prev_kw and cur_kw and len(prev_kw & cur_kw) == 0 and len(cur_kw) >= 4:
                issues.append(_issue(
                    issue_id=f"dialogue-bridge-weak-{i}",
                    stage="script",
                    severity=IssueSeverity.LOW,
                    category="DIALOGUE_CONTINUITY",
                    subject_id=f"scene-{i:02d}",
                    description="Adjacent dialogues share no content keywords — possible story jump.",
                    evidence={"prev_preview": narrations[i - 1][:60], "cur_preview": narr[:60]},
                    repair_scope=RepairScope.SCRIPT_SECTION,
                    action="rewrite_bridge",
                ))

    # Factual evidence from plan fact_gate
    unknown_claims = 0
    contradictions = 0
    for i, sc in enumerate(scenes):
        gate = sc.get("fact_gate") or {}
        if gate.get("verdict") == "UNKNOWN":
            unknown_claims += 1
        if gate.get("verdict") == "FAIL" or gate.get("allowed") is False:
            contradictions += 1
            issues.append(_issue(
                issue_id=f"fact-contradiction-{i}",
                stage="script",
                severity=IssueSeverity.CRITICAL,
                category="FACTUAL_SUPPORT",
                subject_id=f"scene-{i:02d}",
                description="Script claim contradicts available FactPack evidence.",
                evidence={"fact_gate": gate, "narration_preview": str(sc.get("narration") or "")[:100]},
                repair_scope=RepairScope.DIALOGUE,
            ))
    if unknown_claims and not fact_pack:
        issues.append(_issue(
            issue_id="fact-evidence-insufficient",
            stage="script",
            severity=IssueSeverity.MEDIUM,
            category="EVIDENCE_INSUFFICIENT",
            subject_id=subject_id,
            description="Claims could not be verified against available FactPack evidence.",
            evidence={"unknown_claim_count": unknown_claims},
            repair_scope=RepairScope.SCRIPT,
        ))
    dims[QualityDimension.FACTUAL_COHERENCE.value] = max(0.0, 1.0 - 0.2 * contradictions - 0.05 * unknown_claims)
    dims[QualityDimension.SCRIPT_STRUCTURE.value] = 0.8 if len(scenes) >= 2 else 0.5
    dims[QualityDimension.CONTENT_RELEVANCE.value] = 0.85 if topic_kw and hook_kw & topic_kw else 0.6

    score = _score_from_issues(dims, issues)
    verdict = _verdict_from(score, issues)
    repair_scope = issues[0].repair_scope if issues else None
    return CreativeQualityResult(
        subject="script",
        subject_id=subject_id,
        stage="script",
        verdict=verdict,
        score=score,
        dimensions=dims,
        issues=issues,
        evidence={"topic": topic, "scene_count": len(scenes)},
        repair_scope=repair_scope,
        recommended_action=issues[0].recommended_action if issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )


def evaluate_scene_visual_alignment(
    *,
    scene_id: str,
    narration: str,
    visual_prompt: str = "",
    visual_query: str = "",
    visual_description: str = "",
    requires_motion: bool = False,
    is_static_intentional: bool = False,
    motion_detected: bool = True,
) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    dims: dict[str, float] = {}
    narr_kw = _keywords(narration)
    vis_text = " ".join([visual_prompt, visual_query, visual_description]).lower()
    vis_kw = _keywords(vis_text)

    overlap = len(narr_kw & vis_kw) / max(1, min(len(narr_kw), 8)) if narr_kw else 0.0
    dims[QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value] = min(1.0, 0.3 + overlap * 0.7)

    # Detect obvious mismatch: space/launch vs urban street
    space_terms = {"spacecraft", "atmosphere", "launch", "orbit", "rocket", "space"}
    urban_terms = {"street", "city", "urban", "traffic", "sidewalk", "downtown"}
    narr_space = bool(narr_kw & space_terms)
    vis_urban = bool(vis_kw & urban_terms)
    if narr_space and vis_urban and overlap < 0.15:
        issues.append(_issue(
            issue_id=f"visual-mismatch-{scene_id}",
            stage="visual",
            severity=IssueSeverity.CRITICAL,
            category="VISUAL_ALIGNMENT",
            subject_id=scene_id,
            description=(
                "Dialogue references spacecraft/launch context but visual asset "
                "contains unrelated urban street imagery."
            ),
            evidence={
                "narration_preview": narration[:120],
                "visual_preview": vis_text[:120],
                "overlap": overlap,
            },
            repair_scope=RepairScope.VISUAL_ASSET,
            action="regenerate_visual",
        ))
        dims[QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value] = 0.15
    elif overlap < 0.05 and narr_kw and vis_kw:
        issues.append(_issue(
            issue_id=f"visual-weak-align-{scene_id}",
            stage="visual",
            severity=IssueSeverity.LOW,
            category="VISUAL_ALIGNMENT",
            subject_id=scene_id,
            description="Visual plan has weak semantic overlap with dialogue meaning.",
            evidence={"overlap": overlap, "narration_keywords": list(narr_kw)[:8], "visual_keywords": list(vis_kw)[:8]},
            repair_scope=RepairScope.VISUAL_PLAN,
        ))

    if not vis_text.strip():
        issues.append(_issue(
            issue_id=f"visual-plan-empty-{scene_id}",
            stage="visual",
            severity=IssueSeverity.HIGH,
            category="VISUAL_PLAN",
            subject_id=scene_id,
            description="Visual prompt missing essential subject/action/environment.",
            evidence={},
            repair_scope=RepairScope.VISUAL_PLAN,
        ))
        dims[QualityDimension.VISUAL_QUALITY.value] = 0.3
    else:
        dims[QualityDimension.VISUAL_QUALITY.value] = 0.75

    if requires_motion and not motion_detected and not is_static_intentional:
        issues.append(_issue(
            issue_id=f"visual-motion-fail-{scene_id}",
            stage="visual",
            severity=IssueSeverity.HIGH,
            category="VISUAL_MOTION",
            subject_id=scene_id,
            description="Scene requires motion but output is effectively static.",
            evidence={"requires_motion": True, "motion_detected": False},
            repair_scope=RepairScope.VISUAL_ASSET,
        ))
        dims[QualityDimension.VISUAL_QUALITY.value] = min(dims.get(QualityDimension.VISUAL_QUALITY.value, 0.75), 0.4)

    dims[QualityDimension.SCENE_COHERENCE.value] = dims.get(QualityDimension.VISUAL_DIALOGUE_ALIGNMENT.value, 0.5)
    score = _score_from_issues(dims, issues)
    return CreativeQualityResult(
        subject="scene",
        subject_id=scene_id,
        stage="visual",
        verdict=_verdict_from(score, issues),
        score=score,
        dimensions=dims,
        issues=issues,
        evidence={"overlap": overlap},
        repair_scope=issues[0].repair_scope if issues else None,
        recommended_action=issues[0].recommended_action if issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )


def evaluate_audio_quality(
    *,
    subject_id: str,
    emotion_tag: str = "",
    narration_semantics: str = "",
    delivery_style: str = "neutral",
    gate_results: Optional[list[dict[str, Any]]] = None,
) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    dims: dict[str, float] = {QualityDimension.AUDIO_QUALITY.value: 0.85}
    gates = gate_results or []
    for g in gates:
        if not g.get("passed", True):
            issues.append(_issue(
                issue_id=f"audio-gate-{g.get('check', 'unknown')}",
                stage="audio",
                severity=IssueSeverity.HIGH,
                category="AUDIO_TECHNICAL",
                subject_id=subject_id,
                description=f"Audio gate failed: {g.get('check')}",
                evidence={"gate": g},
                repair_scope=RepairScope.AUDIO_ASSET,
            ))
            dims[QualityDimension.AUDIO_QUALITY.value] = 0.4

    # Emotion alignment heuristic
    serious_terms = {"warning", "danger", "critical", "serious", "caution", "death", "fail"}
    cheerful_delivery = delivery_style.lower() in ("cheerful", "happy", "excited", "upbeat")
    narr_lower = narration_semantics.lower()
    if any(t in narr_lower for t in serious_terms) and cheerful_delivery:
        issues.append(_issue(
            issue_id=f"emotion-mismatch-{subject_id}",
            stage="audio",
            severity=IssueSeverity.HIGH,
            category="EMOTION_MISMATCH",
            subject_id=subject_id,
            description="Serious dialogue semantics paired with cheerful delivery style.",
            evidence={"semantics_preview": narration_semantics[:80], "delivery": delivery_style, "emotion_tag": emotion_tag},
            repair_scope=RepairScope.AUDIO_PLAN,
        ))
        dims[QualityDimension.EMOTION_ALIGNMENT.value] = 0.3
    else:
        dims[QualityDimension.EMOTION_ALIGNMENT.value] = 0.85
    dims[QualityDimension.VOICE_CONSISTENCY.value] = 0.8

    score = _score_from_issues(dims, issues)
    return CreativeQualityResult(
        subject="audio",
        subject_id=subject_id,
        stage="audio",
        verdict=_verdict_from(score, issues),
        score=score,
        dimensions=dims,
        issues=issues,
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )


def evaluate_subtitle_creative(
    *,
    subject_id: str,
    subtitle_text: str,
    dialogue_text: str,
    structural_pass: bool = True,
) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    dims: dict[str, float] = {}
    if not structural_pass:
        issues.append(_issue(
            issue_id="subtitle-structural-fail",
            stage="subtitle",
            severity=IssueSeverity.CRITICAL,
            category="SUBTITLE_STRUCTURAL",
            subject_id=subject_id,
            description="BUILD-04E structural validation failed.",
            evidence={},
            repair_scope=RepairScope.SUBTITLE,
        ))
        dims[QualityDimension.SUBTITLE_ALIGNMENT.value] = 0.2
    else:
        dims[QualityDimension.SUBTITLE_ALIGNMENT.value] = 0.9

    lines = [ln for ln in (subtitle_text or "").splitlines() if ln.strip() and "-->" not in ln and not ln.strip().isdigit()]
    if any(len(ln) > 84 for ln in lines):
        issues.append(_issue(
            issue_id="subtitle-line-too-long",
            stage="subtitle",
            severity=IssueSeverity.LOW,
            category="SUBTITLE_READABILITY",
            subject_id=subject_id,
            description="Subtitle lines exceed readable length.",
            evidence={"max_line_len": max((len(ln) for ln in lines), default=0)},
            repair_scope=RepairScope.SUBTITLE,
        ))
    if dialogue_text and subtitle_text and _keywords(dialogue_text) and not (_keywords(dialogue_text) & _keywords(subtitle_text)):
        issues.append(_issue(
            issue_id="subtitle-text-mismatch",
            stage="subtitle",
            severity=IssueSeverity.CRITICAL,
            category="SUBTITLE_MISMATCH",
            subject_id=subject_id,
            description="Subtitle text does not match dialogue content.",
            evidence={"dialogue_preview": dialogue_text[:60], "subtitle_preview": subtitle_text[:60]},
            repair_scope=RepairScope.SUBTITLE,
        ))
        dims[QualityDimension.SUBTITLE_ALIGNMENT.value] = 0.1

    score = _score_from_issues(dims, issues)
    return CreativeQualityResult(
        subject="subtitle",
        subject_id=subject_id,
        stage="subtitle",
        verdict=_verdict_from(score, issues),
        score=score,
        dimensions=dims,
        issues=issues,
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )


def evaluate_cross_modal(
    *,
    subject_id: str,
    script_cues: dict[str, str],
    visual_cues: dict[str, str],
) -> CreativeQualityResult:
    issues: list[QualityIssue] = []
    dims: dict[str, float] = {QualityDimension.CROSS_MODAL_CONSISTENCY.value: 0.85}
    s_time = script_cues.get("time_of_day", "").lower()
    v_time = visual_cues.get("time_of_day", "").lower()
    if s_time and v_time and s_time != v_time:
        issues.append(_issue(
            issue_id="cross-modal-time",
            stage="cross_modal",
            severity=IssueSeverity.CRITICAL,
            category="CROSS_MODAL",
            subject_id=subject_id,
            description=f"Script indicates {s_time} but visual indicates {v_time}.",
            evidence={"script_time": s_time, "visual_time": v_time},
            repair_scope=RepairScope.VISUAL_ASSET,
        ))
        dims[QualityDimension.CROSS_MODAL_CONSISTENCY.value] = 0.2
    score = _score_from_issues(dims, issues)
    return CreativeQualityResult(
        subject="cross_modal",
        subject_id=subject_id,
        stage="cross_modal",
        verdict=_verdict_from(score, issues),
        score=score,
        dimensions=dims,
        issues=issues,
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )


def aggregate_quality_results(
    results: Sequence[CreativeQualityResult],
    *,
    subject_id: str,
    stage: str = "final",
) -> CreativeQualityResult:
    all_issues: list[QualityIssue] = []
    all_dims: dict[str, float] = {}
    for r in results:
        all_issues.extend(r.issues)
        for k, v in r.dimensions.items():
            all_dims[k] = min(all_dims.get(k, 1.0), v) if k in all_dims else v

    if any(r.verdict == QualityVerdict.UNKNOWN for r in results):
        overall = QualityVerdict.UNKNOWN
    elif any(r.verdict == QualityVerdict.BLOCKED for r in results):
        overall = QualityVerdict.BLOCKED
    elif any(r.verdict == QualityVerdict.REGENERATE_REQUIRED for r in results):
        overall = QualityVerdict.REGENERATE_REQUIRED
    elif any(r.verdict == QualityVerdict.REPAIR_REQUIRED for r in results):
        overall = QualityVerdict.REPAIR_REQUIRED
    elif all(r.verdict == QualityVerdict.PASS for r in results):
        overall = QualityVerdict.PASS
    else:
        overall = QualityVerdict.REPAIR_REQUIRED

    score = _score_from_issues(all_dims, all_issues) if all_dims else (
        sum(r.score for r in results) / max(1, len(results))
    )
    repair_scope = None
    for i in all_issues:
        if i.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH):
            repair_scope = i.repair_scope
            break

    return CreativeQualityResult(
        subject="aggregate",
        subject_id=subject_id,
        stage=stage,
        verdict=overall,
        score=score,
        dimensions=all_dims,
        issues=all_issues,
        evidence={"evaluated_stages": [r.stage for r in results]},
        repair_scope=repair_scope,
        recommended_action=all_issues[0].recommended_action if all_issues else "",
        evaluator_version=EVALUATOR_VERSION,
        rule_version=RULE_VERSION,
    )
