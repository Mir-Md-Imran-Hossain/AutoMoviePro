"""Observability metrics for BUILD-03 idempotency layer (+ H3 usage accounting).

Not a second cost engine — extends store metrics with safe usage/latency fields.
Monetary cost: COST_NOT_DETERMINABLE (no pricing tables in repository).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.store import IdempotencyStore

USAGE_LEDGER_FILE = "H3_USAGE_LEDGER.json"
COST_NOT_DETERMINABLE = "COST_NOT_DETERMINABLE"


@dataclass
class IdempotencyMetrics:
    generation_started: int = 0
    generation_completed: int = 0
    result_reused: int = 0
    duplicate_prevented: int = 0
    retry_count: int = 0
    unknown_count: int = 0
    recovery_count: int = 0
    checkpoint_count: int = 0
    resume_count: int = 0
    tts_legacy_fallback: int = 0
    translate_cache_hit: int = 0
    translate_cache_miss: int = 0
    ffprobe_cache_hit: int = 0
    ffprobe_cache_miss: int = 0

    @classmethod
    def from_store(cls, store: IdempotencyStore) -> "IdempotencyMetrics":
        m = store.metrics()
        return cls(
            generation_started=int(m.get("generation_started") or 0),
            generation_completed=int(m.get("generation_completed") or 0),
            result_reused=int(m.get("result_reused") or 0),
            duplicate_prevented=int(m.get("duplicate_prevented") or 0),
            retry_count=int(m.get("retry_count") or 0),
            unknown_count=int(m.get("unknown_count") or 0),
            recovery_count=int(m.get("recovery_count") or 0),
            checkpoint_count=int(m.get("checkpoint_count") or 0),
            resume_count=int(m.get("resume_count") or 0),
            tts_legacy_fallback=int(m.get("tts_legacy_fallback") or 0),
            translate_cache_hit=int(m.get("translate_cache_hit") or 0),
            translate_cache_miss=int(m.get("translate_cache_miss") or 0),
            ffprobe_cache_hit=int(m.get("ffprobe_cache_hit") or 0),
            ffprobe_cache_miss=int(m.get("ffprobe_cache_miss") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "generation_started": self.generation_started,
            "generation_completed": self.generation_completed,
            "result_reused": self.result_reused,
            "duplicate_prevented": self.duplicate_prevented,
            "retry_count": self.retry_count,
            "unknown_count": self.unknown_count,
            "recovery_count": self.recovery_count,
            "checkpoint_count": self.checkpoint_count,
            "resume_count": self.resume_count,
            "tts_legacy_fallback": self.tts_legacy_fallback,
            "translate_cache_hit": self.translate_cache_hit,
            "translate_cache_miss": self.translate_cache_miss,
            "ffprobe_cache_hit": self.ffprobe_cache_hit,
            "ffprobe_cache_miss": self.ffprobe_cache_miss,
            "monetary_cost": COST_NOT_DETERMINABLE,
        }
        return d

    @property
    def api_calls_avoided(self) -> int:
        return (
            self.result_reused
            + self.duplicate_prevented
            + self.translate_cache_hit
            + self.ffprobe_cache_hit
        )


@dataclass
class UsageEvent:
    operation: str
    provider: str = ""
    model: str = ""
    call_count: int = 1
    retry_count: int = 0
    cache_hit: bool = False
    latency_sec: float = 0.0
    detail: str = ""
    status_code_class: str = ""  # e.g. CLASS_429 / CLASS_403 / TIMEOUT / OK
    outcome: str = ""  # success | failure | retry | circuit_open


def record_usage_event(work_dir: Optional[Path], event: UsageEvent) -> None:
    """Append-only usage/latency event under work_dir. Never logs secrets. Never calls providers."""
    if work_dir is None:
        return
    try:
        path = Path(work_dir) / USAGE_LEDGER_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {"monetary_cost": COST_NOT_DETERMINABLE, "events": []}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {"monetary_cost": COST_NOT_DETERMINABLE, "events": []}
        data.setdefault("events", [])
        data["monetary_cost"] = COST_NOT_DETERMINABLE
        model = str(event.model or "").strip() or "UNSPECIFIED"
        provider = str(event.provider or "").strip() or "UNSPECIFIED"
        data["events"].append(
            {
                "ts": time.time(),
                "operation": str(event.operation)[:80],
                "provider": provider[:40],
                "model": model[:40],
                "call_count": int(event.call_count),
                "retry_count": int(event.retry_count),
                "cache_hit": bool(event.cache_hit),
                "latency_sec": round(float(event.latency_sec), 4),
                "detail": str(event.detail)[:120],
                "status_code_class": str(event.status_code_class or "")[:40],
                "outcome": str(event.outcome or "")[:40],
            }
        )
        # Bound ledger growth
        if len(data["events"]) > 500:
            data["events"] = data["events"][-500:]
        tmp = path.with_suffix(f".{time.time_ns()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        import os

        os.replace(tmp, path)
        try:
            from app.customer_marathon_observability import on_usage_event

            on_usage_event(Path(work_dir), event)
        except Exception:
            pass
    except Exception:
        # Accounting must never break the pipeline or induce retries
        pass


def load_usage_ledger(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / USAGE_LEDGER_FILE
    if not path.exists():
        return {"monetary_cost": COST_NOT_DETERMINABLE, "events": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["monetary_cost"] = COST_NOT_DETERMINABLE
        return data
    except Exception:
        return {"monetary_cost": COST_NOT_DETERMINABLE, "events": []}
