"""Quality evaluation runtime with cache + idempotency (BUILD-04F)."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_text
from pipeline.idempotency.states import IdempotencyState
from pipeline.quality.contracts import CreativeQualityResult, EVALUATOR_VERSION, RULE_VERSION
from pipeline.quality.fingerprint import compute_quality_fingerprint, normalized_quality_inputs
from pipeline.quality.provenance import load_quality_provenance, save_quality_provenance

logger = logging.getLogger(__name__)

EvaluatorFn = Callable[[dict[str, Any]], CreativeQualityResult]


@dataclass
class QualityEvaluationResult:
    success: bool
    result: Optional[CreativeQualityResult] = None
    action: str = ""
    fingerprint: str = ""
    from_cache: bool = False
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED


def execute_quality_evaluation(
    work_dir: Path,
    *,
    job_id: str,
    subject_id: str,
    stage: str,
    artifact_fingerprint: str,
    context: dict[str, Any],
    evaluator_fn: Optional[EvaluatorFn] = None,
    use_mock: bool = False,
    mock_evaluator=None,
    report_path: Optional[Path] = None,
) -> QualityEvaluationResult:
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    report_path = report_path or (work_dir / "quality_reports" / f"{stage}_{subject_id}.json")
    normalized_inputs = normalized_quality_inputs(
        artifact_fingerprint=artifact_fingerprint,
        stage=stage,
    )
    fingerprint = compute_quality_fingerprint(
        job_id=job_id,
        subject_id=subject_id,
        stage=stage,
        artifact_fingerprint=artifact_fingerprint,
    )
    executor = IdempotentExecutor(work_dir)
    inv = {"n": 0}

    def _evaluate() -> dict[str, Any]:
        inv["n"] += 1
        ctx = {**context, "subject_id": subject_id, "stage": stage, "job_id": job_id}
        if evaluator_fn:
            result = evaluator_fn(ctx)
        elif use_mock:
            me = mock_evaluator
            if me is None:
                from pipeline.quality.mock_evaluator import get_mock_quality_evaluator
                me = get_mock_quality_evaluator()
            result = me.evaluate(context=ctx)
        else:
            from pipeline.quality.orchestrator import evaluate_stage
            result = evaluate_stage(ctx)
        result.artifact_fingerprint = artifact_fingerprint
        report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = report_path.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, report_path)
        return {"report_path": str(report_path), "result": result.to_dict(), "verdict": result.verdict.value}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        if not out.get("result"):
            return False, "empty_result"
        verdict = str(out.get("verdict") or "")
        if verdict == "UNKNOWN":
            return True, "unknown_ok"
        return True, "ok"

    def _persist(out: dict[str, Any]) -> str:
        result = CreativeQualityResult.from_dict(out["result"])
        save_quality_provenance(work_dir, result=result, fingerprint=fingerprint)
        return str(out.get("report_path") or "")

    existing = executor.store.get(fingerprint)
    if existing and existing.request_state == IdempotencyState.SUCCEEDED and existing.result_reference:
        if Path(existing.result_reference).is_file():
            try:
                data = json.loads(Path(existing.result_reference).read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("verdict"):
                    result = CreativeQualityResult.from_dict(data)
                    return QualityEvaluationResult(
                        success=True,
                        result=result,
                        action="reuse",
                        fingerprint=existing.fingerprint,
                        from_cache=True,
                        state=IdempotencyState.SUCCEEDED,
                    )
            except Exception:
                pass

    exec_result = executor.execute(
        job_id=job_id,
        stage="quality",
        entity_id=f"cq-{stage}-{subject_id}",
        inputs=normalized_inputs,
        provider="quality_evaluator",
        model=EVALUATOR_VERSION,
        execute_fn=_evaluate,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    result = None
    ref = exec_result.result_reference
    if ref and Path(ref).is_file():
        try:
            result = CreativeQualityResult.from_dict(json.loads(Path(ref).read_text(encoding="utf-8")))
        except Exception:
            pass

    return QualityEvaluationResult(
        success=exec_result.action in ("execute", "reuse"),
        result=result,
        action=exec_result.action,
        fingerprint=exec_result.fingerprint or fingerprint,
        from_cache=exec_result.action == "reuse",
        metrics=exec_result.metrics,
        state=exec_result.state,
    )
