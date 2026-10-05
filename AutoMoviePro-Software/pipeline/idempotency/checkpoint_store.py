"""Checkpoint persistence (BUILD-03) — after validated output only."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from domain.enums import JobState
from domain.execution import Checkpoint
from pipeline.idempotency.fs_lock import exclusive_path_lock


class CheckpointStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "CHECKPOINTS.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"checkpoints": [], "by_stage": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"checkpoints": [], "by_stage": {}}
            data.setdefault("checkpoints", [])
            data.setdefault("by_stage", {})
            return data
        except Exception:
            bak = self.path.with_suffix(".corrupt")
            try:
                if self.path.is_file():
                    os.replace(self.path, bak)
            except OSError:
                pass
            return {"checkpoints": [], "by_stage": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def save_checkpoint(self, cp: Checkpoint) -> None:
        with exclusive_path_lock(self.path):
            data = self._load()
            row = cp.model_dump(mode="json")
            data.setdefault("checkpoints", []).append(row)
            data.setdefault("by_stage", {})[cp.stage] = row
            self._save(data)

    def latest_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with exclusive_path_lock(self.path):
            data = self._load()
            return [c for c in data.get("checkpoints") or [] if c.get("job_id") == job_id]

    def highest_completed_stage(self, job_id: str, stage_order: list[str]) -> Optional[str]:
        with exclusive_path_lock(self.path):
            data = self._load()
            by_stage = data.get("by_stage") or {}
            completed = []
            for stage in stage_order:
                row = by_stage.get(stage)
                if row and row.get("job_id") == job_id:
                    completed.append(stage)
            return completed[-1] if completed else None

    def create_checkpoint(
        self,
        *,
        job_id: str,
        stage: str,
        input_hash: str,
        output_hash: str,
        result_reference: str,
        state: JobState = JobState.VERIFYING,
    ) -> Checkpoint:
        return Checkpoint(
            job_id=job_id,
            stage=stage,
            state=state,
            input_hash=input_hash,
            output_hash=output_hash,
            metadata={"result_reference": result_reference},
        )
