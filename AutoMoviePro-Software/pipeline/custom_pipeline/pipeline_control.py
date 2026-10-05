"""Cancel tokens + progress callbacks for custom pipeline.

Industrial rules:
  - cancel is durable (RAM flag + job_state.json)
  - progress updates mutate in-memory state when provided (never clobber stages)
  - long sleeps are interruptible and must re-raise PipelineCancelled
  - disk cancel is re-read so cross-process CLI cancel works
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]
CancelCheck = Callable[[], bool]

_lock = threading.RLock()
_cancel_flags: Dict[str, bool] = {}
_progress_cbs: Dict[str, ProgressCb] = {}


class PipelineCancelled(Exception):
    """Raised when cancel is requested mid-run."""


def _key(package_root: Path | str) -> str:
    try:
        return str(Path(package_root).resolve())
    except Exception:
        return str(package_root)


def register_progress(package_root: Path | str, cb: Optional[ProgressCb]) -> None:
    with _lock:
        k = _key(package_root)
        if cb:
            _progress_cbs[k] = cb
        else:
            _progress_cbs.pop(k, None)


def request_cancel(package_root: Path | str) -> None:
    with _lock:
        _cancel_flags[_key(package_root)] = True
    try:
        from pipeline.custom_pipeline.job_state import request_cancel as js_cancel

        js_cancel(Path(package_root))
    except Exception as exc:
        logger.debug("job_state cancel soft-fail: %s", exc)


def clear_cancel(package_root: Path | str) -> None:
    """Clear RAM cancel + durable cancel_requested (for intentional resume)."""
    with _lock:
        _cancel_flags.pop(_key(package_root), None)
    try:
        from pipeline.custom_pipeline.job_state import load_job_state, mutate_job_state

        pkg = Path(package_root)
        if load_job_state(pkg) is None:
            return

        def _clear(st: Dict[str, Any]) -> None:
            st["cancel_requested"] = False
            # Do not force status — caller (prepare_resume) owns that

        mutate_job_state(pkg, _clear, create=False)
    except Exception as exc:
        logger.debug("clear_cancel disk soft-fail: %s", exc)


def _disk_cancel_requested(package_root: Path | str) -> bool:
    try:
        from pipeline.custom_pipeline.job_state import load_job_state

        st = load_job_state(Path(package_root))
        return bool(st and st.get("cancel_requested"))
    except Exception:
        return False


def is_cancelled(package_root: Path | str = "", state: Optional[Dict[str, Any]] = None) -> bool:
    if state and state.get("cancel_requested"):
        return True
    if not package_root:
        return False
    with _lock:
        if bool(_cancel_flags.get(_key(package_root))):
            return True
    # Cross-process: CLI `cancel` writes job_state while runner holds old state dict
    if _disk_cancel_requested(package_root):
        if state is not None:
            state["cancel_requested"] = True
        with _lock:
            _cancel_flags[_key(package_root)] = True
        return True
    return False


def emit_progress(
    package_root: Path | str,
    pct: float,
    message: str = "",
    *,
    state: Optional[Dict[str, Any]] = None,
) -> None:
    """Update progress. Prefer in-memory `state` to avoid clobbering unsaved stages."""
    with _lock:
        cb = _progress_cbs.get(_key(package_root))
    if cb:
        try:
            cb(float(pct), message)
        except Exception as exc:
            logger.debug("progress cb failed: %s", exc)
    try:
        from pipeline.custom_pipeline.job_state import (
            heartbeat,
            mutate_job_state,
            set_progress,
        )

        pkg = Path(package_root)
        if state is not None:
            set_progress(state, pct, message)
            heartbeat(pkg, state, message)
            return

        def _upd(st: Dict[str, Any]) -> None:
            set_progress(st, pct, message)
            st["heartbeat_at"] = time.time()
            if message:
                st["progress_message"] = message

        mutate_job_state(pkg, _upd, create=False)
    except Exception:
        pass


def check_cancelled(package_root: Path | str = "", state: Optional[Dict[str, Any]] = None) -> None:
    if is_cancelled(package_root, state):
        raise PipelineCancelled("Pipeline cancelled by user")


def interruptible_sleep(
    seconds: float,
    *,
    package_root: Path | str = "",
    state: Optional[Dict[str, Any]] = None,
    slice_sec: float = 1.0,
) -> None:
    """Sleep in slices so cancel can interrupt long API gaps."""
    end = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < end:
        check_cancelled(package_root, state)
        remaining = end - time.monotonic()
        time.sleep(min(slice_sec, max(0.05, remaining)))


def wall_clock_exceeded(started_at: float, max_sec: float) -> bool:
    if max_sec <= 0:
        return False
    return (time.time() - started_at) >= max_sec
