"""Per-job context (work_dir) for budget/watchdog without threading every kwarg."""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

_work: ContextVar[Optional[Path]] = ContextVar("amp_job_work", default=None)


def set_job_work(path: Any) -> None:
    try:
        _work.set(Path(str(path)) if path else None)
    except Exception:
        _work.set(None)


def get_job_work() -> Optional[Path]:
    try:
        return _work.get()
    except Exception:
        return None


def budget_consume(kind: str, n: int = 1) -> dict:
    """Best-effort; if no work dir, allow (do not break legacy callers)."""
    work = get_job_work()
    if work is None:
        return {"ok": True, "skipped": True}
    try:
        from pipeline.api_budget import ApiBudget

        return ApiBudget(work).consume(kind, n)
    except Exception as exc:
        return {"ok": True, "skipped": True, "error": str(exc)[:120]}
