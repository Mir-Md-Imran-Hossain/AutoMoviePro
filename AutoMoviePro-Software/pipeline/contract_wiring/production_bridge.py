"""Production path contract wiring bridge (AMP-003 TASK-002)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.contract_wiring.orphans import detect_orphans
from pipeline.contract_wiring.trace import PipelineTrace, wire_pipeline_from_plan

logger = logging.getLogger("pipeline.contract_wiring.production")

CANONICAL_STAGE_ORDER: tuple[str, ...] = (
    "topic",
    "research",
    "factpack",
    "script",
    "scene",
    "visual",
    "audio",
    "subtitle",
    "render",
    "metadata",
    "thumbnail",
    "upload",
    "publication",
)


class ProductionWiringError(RuntimeError):
    """Raised when production contract wiring fails."""

    def __init__(self, trace: PipelineTrace) -> None:
        self.trace = trace
        stage = trace.stopped_at or "unknown"
        detail = ";".join(trace.errors) if trace.errors else "validation_failed"
        super().__init__(f"contract_wiring_blocked:{stage}:{detail}")


def stage_order_valid(executed: list[str]) -> bool:
    """Verify stages executed in canonical order (per-scene media stages may repeat)."""
    if not executed:
        return False
    rank = {name: i for i, name in enumerate(CANONICAL_STAGE_ORDER)}
    normalized: list[str] = []
    i = 0
    while i < len(executed):
        stage = executed[i]
        if stage in ("visual", "audio", "subtitle"):
            normalized.append("scene_media")
            while i < len(executed) and executed[i] in ("visual", "audio", "subtitle"):
                i += 1
            continue
        normalized.append(stage)
        i += 1
    media_rank = rank["visual"]
    last = -1
    for stage in normalized:
        pos = media_rank if stage == "scene_media" else rank.get(stage, -1)
        if pos < 0 or pos < last:
            return False
        last = pos
    return True


def persist_work_trace(work_dir: Path, trace: PipelineTrace) -> Path:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "CONTRACT_WIRING_TRACE.json"
    path.write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    return path


def load_work_trace(work_dir: Path) -> Optional[dict[str, Any]]:
    path = Path(work_dir) / "CONTRACT_WIRING_TRACE.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def validate_production_plan_wiring(
    plan: dict[str, Any],
    *,
    job_id: str,
    work_dir: Optional[Path] = None,
    research_notes: str = "",
    persist: bool = True,
) -> PipelineTrace:
    """Wire director plan through canonical contracts; detect orphans; persist trace."""
    trace = wire_pipeline_from_plan(plan, job_id=job_id, research_notes=research_notes)
    orphan_report = detect_orphans(trace)
    if not orphan_report.clean:
        trace.stopped_at = trace.stopped_at or "orphan"
        trace.errors.extend(orphan_report.orphans)
    if trace.passed and not stage_order_valid(trace.executed_stages):
        trace.stopped_at = "stage_order"
        trace.errors.append(f"invalid stage order: {trace.executed_stages}")
    if persist and work_dir is not None:
        persist_work_trace(Path(work_dir), trace)
        try:
            from pipeline.contract_wiring.orchestrator_bridge import persist_trace

            persist_trace(trace)
        except Exception as exc:
            logger.debug("global trace persist skipped: %s", exc)
    return trace


def assert_production_plan_wiring(
    plan: dict[str, Any],
    *,
    job_id: str,
    work_dir: Optional[Path] = None,
    research_notes: str = "",
) -> PipelineTrace:
    """Fail-closed production gate — raises ProductionWiringError on failure."""
    trace = validate_production_plan_wiring(
        plan,
        job_id=job_id,
        work_dir=work_dir,
        research_notes=research_notes,
        persist=work_dir is not None,
    )
    if not trace.passed or trace.stopped_at:
        raise ProductionWiringError(trace)
    return trace
