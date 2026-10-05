"""Filesystem idempotency record store (BUILD-03)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.fs_lock import exclusive_path_lock, normalize_lock_key, thread_lock_for
from pipeline.idempotency.states import IdempotencyState

DEFAULT_STALE_SEC = 3600  # 1 hour in-progress considered stale


def _store_lock(path: Path):
    """Backward-compatible name — normalized thread lock (H1)."""
    return thread_lock_for(path)


@dataclass
class IdempotencyRecord:
    fingerprint: str
    job_id: str
    stage: str
    entity_id: str
    provider: str = ""
    request_state: IdempotencyState = IdempotencyState.NOT_STARTED
    result_reference: str = ""
    result_hash: str = ""
    attempt: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "job_id": self.job_id,
            "stage": self.stage,
            "entity_id": self.entity_id,
            "provider": self.provider,
            "request_state": self.request_state.value,
            "result_reference": self.result_reference,
            "result_hash": self.result_hash,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdempotencyRecord":
        state_raw = str(data.get("request_state") or "NOT_STARTED")
        try:
            state = IdempotencyState(state_raw)
        except ValueError:
            state = IdempotencyState.UNKNOWN
        return cls(
            fingerprint=str(data.get("fingerprint") or ""),
            job_id=str(data.get("job_id") or ""),
            stage=str(data.get("stage") or ""),
            entity_id=str(data.get("entity_id") or ""),
            provider=str(data.get("provider") or ""),
            request_state=state,
            result_reference=str(data.get("result_reference") or ""),
            result_hash=str(data.get("result_hash") or ""),
            attempt=int(data.get("attempt") or 0),
            max_attempts=int(data.get("max_attempts") or 3),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            completed_at=float(data["completed_at"]) if data.get("completed_at") else None,
            metadata=dict(data.get("metadata") or {}),
        )


class IdempotencyStore:
    """JSON-backed idempotency store with atomic write."""

    def __init__(self, base_dir: Path, *, stale_sec: float = DEFAULT_STALE_SEC):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "IDEMPOTENCY.json"
        self.stale_sec = stale_sec
        self._data: dict[str, Any] = {"records": {}, "metrics": {}}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._data.setdefault("records", {})
        self._data.setdefault("metrics", {})

    def _save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with exclusive_path_lock(self.path):
            self._write_unlocked()

    def _reload(self) -> None:
        with exclusive_path_lock(self.path):
            self._load()

    def get(self, fingerprint: str) -> Optional[IdempotencyRecord]:
        with exclusive_path_lock(self.path):
            self._load()
            row = (self._data.get("records") or {}).get(fingerprint)
            if not isinstance(row, dict):
                return None
            return IdempotencyRecord.from_dict(row)

    def put(self, record: IdempotencyRecord) -> None:
        with exclusive_path_lock(self.path):
            self._load()
            record.updated_at = time.time()
            self._data.setdefault("records", {})[record.fingerprint] = record.to_dict()
            self._write_unlocked()

    def increment_metric(self, key: str, amount: int = 1) -> None:
        with exclusive_path_lock(self.path):
            self._load()
            metrics = self._data.setdefault("metrics", {})
            metrics[key] = int(metrics.get(key) or 0) + amount
            self._write_unlocked()

    def metrics(self) -> dict[str, int]:
        return {k: int(v) for k, v in (self._data.get("metrics") or {}).items()}

    def is_stale_in_progress(self, record: IdempotencyRecord) -> bool:
        if record.request_state != IdempotencyState.IN_PROGRESS:
            return False
        return (time.time() - record.updated_at) > self.stale_sec

    def atomic_claim(
        self,
        record: IdempotencyRecord,
        *,
        worker_id: str = "",
    ) -> tuple[bool, Optional[IdempotencyRecord]]:
        """
        Attempt atomic claim. Returns (claimed, existing_record).
        claimed=True means this worker owns execution.
        """
        with exclusive_path_lock(self.path):
            self._load()
            existing_row = (self._data.get("records") or {}).get(record.fingerprint)
            existing = IdempotencyRecord.from_dict(existing_row) if isinstance(existing_row, dict) else None
            if existing is None:
                record.request_state = IdempotencyState.IN_PROGRESS
                record.attempt = max(1, record.attempt)
                record.metadata["worker_id"] = worker_id
                record.metadata["lock_key"] = normalize_lock_key(self.path)
                record.updated_at = time.time()
                self._data.setdefault("records", {})[record.fingerprint] = record.to_dict()
                metrics = self._data.setdefault("metrics", {})
                metrics["generation_started"] = int(metrics.get("generation_started") or 0) + 1
                self._write_unlocked()
                return True, None

            if existing.request_state == IdempotencyState.SUCCEEDED:
                return False, existing

            if existing.request_state == IdempotencyState.IN_PROGRESS:
                if not self.is_stale_in_progress(existing):
                    return False, existing
                if existing.attempt >= existing.max_attempts:
                    existing.request_state = IdempotencyState.FAILED_FINAL
                    existing.metadata["stale_exceeded"] = True
                    existing.updated_at = time.time()
                    self._data["records"][record.fingerprint] = existing.to_dict()
                    self._write_unlocked()
                    return False, existing
                existing.attempt = max(1, existing.attempt + 1)
                existing.request_state = IdempotencyState.IN_PROGRESS
                existing.metadata["stale_reclaimed"] = True
                existing.metadata["worker_id"] = worker_id
                existing.updated_at = time.time()
                self._data["records"][record.fingerprint] = existing.to_dict()
                metrics = self._data.setdefault("metrics", {})
                metrics["stale_reclaim_count"] = int(metrics.get("stale_reclaim_count") or 0) + 1
                self._write_unlocked()
                return True, existing

            if existing.request_state == IdempotencyState.FAILED_FINAL:
                return False, existing

            if existing.request_state == IdempotencyState.FAILED_RETRYABLE:
                if existing.attempt >= existing.max_attempts:
                    existing.request_state = IdempotencyState.FAILED_FINAL
                    existing.updated_at = time.time()
                    self._data["records"][record.fingerprint] = existing.to_dict()
                    self._write_unlocked()
                    return False, existing
                existing.request_state = IdempotencyState.IN_PROGRESS
                existing.attempt += 1
                existing.metadata["worker_id"] = worker_id
                existing.updated_at = time.time()
                self._data["records"][record.fingerprint] = existing.to_dict()
                metrics = self._data.setdefault("metrics", {})
                metrics["retry_count"] = int(metrics.get("retry_count") or 0) + 1
                self._write_unlocked()
                return True, existing

            if existing.request_state == IdempotencyState.UNKNOWN:
                return False, existing

            existing.request_state = IdempotencyState.IN_PROGRESS
            existing.metadata["worker_id"] = worker_id
            existing.updated_at = time.time()
            self._data["records"][record.fingerprint] = existing.to_dict()
            self._write_unlocked()
            return True, existing

    def _write_unlocked(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{time.time_ns()}.tmp")
        for attempt in range(5):
            try:
                tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
                return
            except OSError:
                time.sleep(0.02 * (attempt + 1))
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
