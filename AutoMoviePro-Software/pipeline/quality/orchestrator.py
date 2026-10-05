"""Quality gate orchestrator (BUILD-04F)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.fingerprint import hash_artifact, hash_text
from pipeline.quality.contracts import CreativeQualityResult, QualityVerdict
from pipeline.quality.evaluators import (
    aggregate_quality_results,
    evaluate_audio_quality,
    evaluate_cross_modal,
    evaluate_scene_visual_alignment,
    evaluate_script_quality,
    evaluate_subtitle_creative,
)
from pipeline.quality.repair_planner import plan_repair

logger = logging.getLogger(__name__)


def evaluate_stage(context: dict[str, Any]) -> CreativeQualityResult:
    stage = str(context.get("stage") or "final")
    subject_id = str(context.get("subject_id") or "job")
    if stage == "script":
        return evaluate_script_quality(subject_id=subject_id, plan=context.get("plan") or {}, fact_pack=context.get("fact_pack"))
    if stage == "visual":
        return evaluate_scene_visual_alignment(
            scene_id=subject_id,
            narration=str(context.get("narration") or ""),
            visual_prompt=str(context.get("visual_prompt") or ""),
            visual_query=str(context.get("visual_query") or ""),
            visual_description=str(context.get("visual_description") or ""),
            requires_motion=bool(context.get("requires_motion")),
            is_static_intentional=bool(context.get("is_static_intentional")),
            motion_detected=bool(context.get("motion_detected", True)),
        )
    if stage == "audio":
        return evaluate_audio_quality(
            subject_id=subject_id,
            emotion_tag=str(context.get("emotion_tag") or ""),
            narration_semantics=str(context.get("narration_semantics") or ""),
            delivery_style=str(context.get("delivery_style") or "neutral"),
            gate_results=context.get("gate_results"),
        )
    if stage == "subtitle":
        return evaluate_subtitle_creative(
            subject_id=subject_id,
            subtitle_text=str(context.get("subtitle_text") or ""),
            dialogue_text=str(context.get("dialogue_text") or ""),
            structural_pass=bool(context.get("structural_pass", True)),
        )
    if stage == "cross_modal":
        return evaluate_cross_modal(
            subject_id=subject_id,
            script_cues=dict(context.get("script_cues") or {}),
            visual_cues=dict(context.get("visual_cues") or {}),
        )
    return CreativeQualityResult(
        subject=stage, subject_id=subject_id, stage=stage,
        verdict=QualityVerdict.PASS, score=0.9,
    )


def quality_gate_orchestrator(
    work_dir: Path,
    *,
    job_id: str,
    plan: dict[str, Any],
    technical_ship: Optional[dict[str, Any]] = None,
    scene_results: Optional[list[CreativeQualityResult]] = None,
    use_mock: bool = False,
    mock_evaluator=None,
) -> dict[str, Any]:
    """
    Full creative quality pipeline for a job work directory.
    Reuses BUILD-04E structural results and MASTER_SHIP_GATE as evidence.
    """
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    results: list[CreativeQualityResult] = []

    # 1. Script quality
    from pipeline.quality.runtime import execute_quality_evaluation

    plan_fp = hash_text(json.dumps(plan, sort_keys=True, default=str))[:32]
    script_ctx = {"plan": plan, "fact_pack": plan.get("fact_pack")}
    sr = execute_quality_evaluation(
        work_dir, job_id=job_id, subject_id=job_id, stage="script",
        artifact_fingerprint=plan_fp, context=script_ctx,
        use_mock=use_mock, mock_evaluator=mock_evaluator,
    )
    if sr.result:
        results.append(sr.result)

    # 2. Per-scene evaluation from plan
    if scene_results:
        results.extend(scene_results)
    else:
        for i, sc in enumerate(plan.get("scenes") or []):
            if not isinstance(sc, dict):
                continue
            sid = f"scene-{i:02d}"
            narr = str(sc.get("narration") or "")
            vprompt = str(sc.get("visual_prompt") or sc.get("exact_ai_video_prompt") or "")
            vquery = str(sc.get("visual_query") or "")
            if not narr:
                continue
            if not vprompt and not vquery:
                continue  # no visual intent metadata — skip creative visual gate
            ctx = {
                "narration": narr,
                "visual_prompt": vprompt,
                "visual_query": vquery,
                "requires_motion": bool(sc.get("requires_motion", True)),
                "motion_detected": sc.get("motion_detected", True) is not False,
            }
            sc_fp = hash_text(f"{sid}:{narr}:{ctx['visual_prompt']}")[:32]
            vr = execute_quality_evaluation(
                work_dir, job_id=job_id, subject_id=sid, stage="visual",
                artifact_fingerprint=sc_fp, context=ctx,
                use_mock=use_mock, mock_evaluator=mock_evaluator,
            )
            if vr.result:
                results.append(vr.result)

    # 3. Technical media quality from ship gate (reuse, do not duplicate)
    tech_pass = True
    if technical_ship:
        tech_pass = bool(technical_ship.get("ok")) and not bool(technical_ship.get("unshippable"))
        if not tech_pass:
            from pipeline.quality.contracts import IssueSeverity, QualityIssue, RepairScope
            results.append(CreativeQualityResult(
                subject="technical", subject_id=job_id, stage="technical",
                verdict=QualityVerdict.REPAIR_REQUIRED, score=0.4,
                issues=[QualityIssue(
                    issue_id="technical-ship-fail", stage="technical",
                    severity=IssueSeverity.CRITICAL, category="TECHNICAL_MEDIA",
                    subject_id=job_id,
                    description="Technical ship gate failed.",
                    evidence={"ship": technical_ship},
                    repair_scope=RepairScope.RENDER,
                )],
            ))

    # 4. Aggregate
    final = aggregate_quality_results(results, subject_id=job_id, stage="final")

    # 5. Repair plan for primary failure
    repair = plan_repair(final)

    report = {
        "overall_verdict": final.verdict.value,
        "overall_score": final.score,
        "publishable": final.verdict == QualityVerdict.PASS and tech_pass,
        "dimensions": final.dimensions,
        "issues": [i.to_dict() for i in final.issues],
        "evidence": final.evidence,
        "confidence": final.confidence,
        "repair_scope": final.repair_scope.value if final.repair_scope else "",
        "repair_plan": repair.to_dict() if repair else None,
        "evaluator_version": final.evaluator_version,
        "rule_version": final.rule_version,
        "dependency_fingerprints": {"plan": plan_fp},
        "stage_results": [r.to_dict() for r in results],
    }

    out = work_dir / "quality_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = work_dir / "CREATIVE_QUALITY_GATE.json"
    gate.write_text(json.dumps({"ok": report["publishable"], **report}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def artifact_fingerprint_for_path(path: Path) -> str:
    if path.is_file():
        return hash_artifact(str(path))[:32]
    return hash_text(str(path))[:32]
