"""Idempotent repair execution tracking (BUILD-04F)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.idempotency.states import IdempotencyState
from pipeline.quality.contracts import RULE_VERSION, EVALUATOR_VERSION
from pipeline.quality.repair_planner import RepairPlan

logger = logging.getLogger(__name__)

RepairFn = Callable[[], dict[str, Any]]


@dataclass
class RepairExecutionResult:
    success: bool
    action: str = ""
    fingerprint: str = ""
    revision_id: str = ""
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)


def compute_repair_fingerprint(
    *,
    job_id: str,
    plan: RepairPlan,
    issue_fingerprint: str,
) -> str:
    return compute_fingerprint(
        job_id=job_id,
        stage="quality_repair",
        entity_id=f"repair-{plan.repair_scope.value}-{plan.subject_id}",
        contract_version="1.0.0",
        provider="repair_planner",
        model=EVALUATOR_VERSION,
        inputs={
            "repair_scope": plan.repair_scope.value,
            "subject_id": plan.subject_id,
            "issue_ids": sorted(plan.issue_ids),
            "old_fingerprint": plan.old_fingerprint,
            "issue_fingerprint": issue_fingerprint,
            "rule_version": RULE_VERSION,
        },
    )


def execute_repair_request(
    work_dir: Path,
    *,
    job_id: str,
    plan: RepairPlan,
    issue_fingerprint: str,
    repair_fn: RepairFn,
) -> RepairExecutionResult:
    work_dir = Path(work_dir)
    fingerprint = compute_repair_fingerprint(job_id=job_id, plan=plan, issue_fingerprint=issue_fingerprint)
    executor = IdempotentExecutor(work_dir)
    inv = {"n": 0}

    def _execute() -> dict[str, Any]:
        inv["n"] += 1
        out = repair_fn()
        out.setdefault("revision_id", plan.revision_id)
        return out

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        if not out.get("success", True):
            return False, "repair_failed"
        return True, "ok"

    def _persist(out: dict[str, Any]) -> str:
        log = work_dir / "quality_repairs" / f"{fingerprint[:20]}.json"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({**out, "plan": plan.to_dict(), "fingerprint": fingerprint}, indent=2), encoding="utf-8")
        return str(log)

    result = executor.execute(
        job_id=job_id,
        stage="quality_repair",
        entity_id=f"repair-{plan.subject_id}",
        inputs={"scope": plan.repair_scope.value, "attempt": plan.attempt},
        provider="repair_planner",
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    return RepairExecutionResult(
        success=result.action in ("execute", "reuse"),
        action=result.action,
        fingerprint=fingerprint,
        revision_id=plan.revision_id,
        provider_invocations=0 if result.action == "reuse" else inv["n"],
        metrics=result.metrics,
    )
