"""Resume resolver — skip completed stages (BUILD-03)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline.idempotency.checkpoint_store import CheckpointStore

DEFAULT_STAGE_ORDER = [
    "topic",
    "research",
    "factpack",
    "script",
    "scene",
    "visual",
    "audio",
    "localization",
    "subtitle",
    "render",
    "metadata",
    "thumbnail",
    "upload",
    "publication",
    "engagement",
]


@dataclass
class ResumePlan:
    job_id: str
    resume_from: str
    completed_stages: list[str] = field(default_factory=list)
    skip_stages: list[str] = field(default_factory=list)


class ResumeResolver:
    def __init__(self, work_dir: Path, *, stage_order: list[str] | None = None):
        self.checkpoint_store = CheckpointStore(Path(work_dir) / "checkpoints")
        self.stage_order = stage_order or DEFAULT_STAGE_ORDER

    def resolve(self, job_id: str) -> ResumePlan:
        completed: list[str] = []
        for stage in self.stage_order:
            rows = [
                r
                for r in self.checkpoint_store.latest_for_job(job_id)
                if r.get("stage") == stage and r.get("output_hash")
            ]
            if rows:
                completed.append(stage)
        if not completed:
            return ResumePlan(job_id=job_id, resume_from=self.stage_order[0], completed_stages=[])
        last = completed[-1]
        try:
            idx = self.stage_order.index(last)
            next_stage = self.stage_order[idx + 1] if idx + 1 < len(self.stage_order) else last
        except ValueError:
            next_stage = self.stage_order[0]
        return ResumePlan(
            job_id=job_id,
            resume_from=next_stage,
            completed_stages=completed,
            skip_stages=list(completed),
        )

    def should_skip_stage(self, job_id: str, stage: str) -> bool:
        plan = self.resolve(job_id)
        return stage in plan.skip_stages and stage != plan.resume_from
