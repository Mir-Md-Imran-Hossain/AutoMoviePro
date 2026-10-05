"""E2E execution evidence — no secrets."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

EVIDENCE_FILE = "E2E_EXECUTION_EVIDENCE.json"


@dataclass
class StageEvidence:
    stage: str
    status: str
    started_at: float
    completed_at: float = 0.0
    error_classification: str = ""
    retry_count: int = 0
    artifact_ids: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["elapsed_sec"] = round(max(0.0, (self.completed_at or time.time()) - self.started_at), 4)
        return d


@dataclass
class ExecutionEvidence:
    job_id: str
    phase: str = "PHASE-09"
    stages: list[StageEvidence] = field(default_factory=list)
    render_id: str = ""
    publishability: dict[str, Any] = field(default_factory=dict)
    provider_call_count: int = 0
    unnecessary_regeneration_count: int = 0
    environment: dict[str, Any] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    final_status: str = "UNKNOWN"
    soft_handoff: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def begin(self, stage: str) -> StageEvidence:
        ev = StageEvidence(stage=stage, status="RUNNING", started_at=time.time())
        self.stages.append(ev)
        return ev

    def end(self, ev: StageEvidence, status: str, *, detail: Optional[dict] = None, classification: str = "") -> None:
        ev.status = status
        ev.completed_at = time.time()
        ev.error_classification = classification
        if detail:
            from pipeline.api_keys import redact_mapping

            ev.detail = redact_mapping(detail)

    def to_dict(self) -> dict[str, Any]:
        self.completed_at = self.completed_at or time.time()
        return {
            "job_id": self.job_id,
            "phase": self.phase,
            "render_id": self.render_id,
            "stages": [s.to_dict() for s in self.stages],
            "publishability": dict(self.publishability),
            "provider_call_count": self.provider_call_count,
            "unnecessary_regeneration_count": self.unnecessary_regeneration_count,
            "environment": dict(self.environment),
            "identity": dict(self.identity),
            "final_status": self.final_status,
            "soft_handoff": bool(self.soft_handoff),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_elapsed_sec": round(self.completed_at - self.started_at, 4),
        }


def persist_evidence(work_dir: Path, evidence: ExecutionEvidence) -> Path:
    path = Path(work_dir) / EVIDENCE_FILE
    path.write_text(json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
