"""Orchestrator idempotency bridge (BUILD-03) — surgical hook."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.executor import IdempotentExecutor, IdempotentResult
from pipeline.idempotency.metrics import IdempotencyMetrics
from pipeline.idempotency.resume_resolver import ResumePlan, ResumeResolver

logger = logging.getLogger("pipeline.idempotency.bridge")

BUILD03_LAYER_VERSION = "build03-1.0.0"


def enrich_payload_with_idempotency(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Attach BUILD-03 metadata to queue payloads (non-breaking)."""
    out = dict(payload or {})
    meta = dict(out.get("idempotency_meta") or {})
    meta["layer"] = BUILD03_LAYER_VERSION
    meta["enabled"] = True
    out["idempotency_meta"] = meta
    return out


def resolve_resume(work_dir: Path, job_id: str) -> ResumePlan:
    resolver = ResumeResolver(work_dir)
    plan = resolver.resolve(job_id)
    logger.info(
        "resume job=%s from=%s completed=%s",
        job_id,
        plan.resume_from,
        plan.completed_stages,
    )
    return plan


def get_executor(work_dir: Path) -> IdempotentExecutor:
    return IdempotentExecutor(work_dir)


def metrics_snapshot(work_dir: Path) -> dict[str, int]:
    ex = get_executor(work_dir)
    return IdempotencyMetrics.from_store(ex.store).to_dict()
