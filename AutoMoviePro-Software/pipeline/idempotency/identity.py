"""Execution identity hierarchy (BUILD-03)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class JobIdentity:
    job_id: str
    job_type: str = "video_generation"


@dataclass(frozen=True)
class StageIdentity:
    job_id: str
    stage: str
    entity_id: str


@dataclass(frozen=True)
class AttemptIdentity:
    job_id: str
    stage: str
    fingerprint: str
    attempt_number: int


@dataclass(frozen=True)
class ExecutionIdentity:
    """Deterministic stage execution identity (not random UUID for idempotency)."""

    job_id: str
    stage: str
    entity_id: str
    fingerprint: str

    @classmethod
    def from_parts(cls, job_id: str, stage: str, entity_id: str, fingerprint: str) -> "ExecutionIdentity":
        return cls(
            job_id=job_id,
            stage=stage.strip().lower(),
            entity_id=entity_id.strip(),
            fingerprint=fingerprint.strip(),
        )

    @property
    def execution_key(self) -> str:
        return f"{self.job_id}|{self.stage}|{self.entity_id}|{self.fingerprint}"
