"""Orchestrator integration boundary (BUILD-02) — incremental, non-rewrite."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import DATA_DIR
from pipeline.contract_wiring.core import CONTRACT_LAYER_VERSION, StageWireResult
from pipeline.contract_wiring.trace import PipelineTrace, wire_pipeline_from_plan

logger = logging.getLogger("pipeline.contract_wiring.orchestrator")

TRACE_DIR = Path(DATA_DIR) / "contract_traces"


def enrich_queue_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach contract layer metadata to orchestrator queue payloads."""
    out = dict(payload or {})
    meta = dict(out.get("contract_meta") or {})
    meta["contract_layer"] = CONTRACT_LAYER_VERSION
    meta["wiring"] = "build02"
    out["contract_meta"] = meta
    return out


def persist_trace(trace: PipelineTrace) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{trace.job_id}.json"
    path.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    return path


def on_stage_complete(result: StageWireResult[Any], *, queue_job_id: Optional[str] = None) -> None:
    """Log + optional trace fragment for orchestrator-adjacent stages."""
    logger.info(
        "orchestrator_bridge stage=%s queue_job=%s passed=%s job_id=%s",
        result.stage,
        queue_job_id or "-",
        result.passed,
        result.context.job_id,
    )


def wire_plan_for_queue(
    plan: dict[str, Any],
    *,
    job_id: str,
    research_notes: str = "",
    persist: bool = True,
) -> PipelineTrace:
    """Wire canonical contracts for a queued production plan (offline validation)."""
    trace = wire_pipeline_from_plan(plan, job_id=job_id, research_notes=research_notes)
    if persist:
        persist_trace(trace)
    return trace
