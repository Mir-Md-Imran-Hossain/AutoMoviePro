"""
PC load / idle detector — pause heavy video generation when the machine is busy.
Uses psutil when available; Windows GetSystemTimes fallback otherwise.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_LAST_IDLE: Optional[Tuple[float, float]] = None  # (wall, idle_ratio)


def _cpu_percent_psutil(sample_sec: float = 0.4) -> Optional[float]:
    try:
        import psutil

        return float(psutil.cpu_percent(interval=max(0.05, sample_sec)))
    except Exception:
        return None


def _cpu_percent_windows(sample_sec: float = 0.4) -> Optional[float]:
    """Estimate CPU busy % via GetSystemTimes (Windows)."""
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        GetSystemTimes = ctypes.windll.kernel32.GetSystemTimes
        GetSystemTimes.argtypes = [
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        ]

        def _read() -> Tuple[int, int]:
            GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))

            def _u64(ft: FILETIME) -> int:
                return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

            i = _u64(idle)
            total = _u64(kernel) + _u64(user)
            return i, total

        i1, t1 = _read()
        time.sleep(max(0.05, sample_sec))
        i2, t2 = _read()
        di = max(0, i2 - i1)
        dt = max(1, t2 - t1)
        idle_ratio = di / dt
        busy = max(0.0, min(100.0, (1.0 - idle_ratio) * 100.0))
        return busy
    except Exception as exc:
        logger.debug("windows cpu sample failed: %s", exc)
        return None


def sample_cpu_percent(sample_sec: float = 0.4) -> float:
    env = os.environ.get("AMP_FORCE_CPU_PERCENT", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    pct = _cpu_percent_psutil(sample_sec)
    if pct is None:
        pct = _cpu_percent_windows(sample_sec)
    if pct is None:
        # Conservative: treat unknown as moderately busy so we still try sometimes
        return 55.0
    return float(pct)


def idle_threshold() -> float:
    try:
        return float(os.environ.get("AMP_IDLE_CPU_MAX", "45").strip() or "45")
    except ValueError:
        return 45.0


def is_pc_idle(*, sample_sec: float = 0.35, threshold: Optional[float] = None) -> bool:
    """
    True when CPU busy% is at/under threshold (default 45%).
    AMP_IDLE_CPU_MAX overrides threshold. AMP_FORCE_CPU_PERCENT forces a sample.
    """
    busy = sample_cpu_percent(sample_sec)
    limit = idle_threshold() if threshold is None else float(threshold)
    idle = busy <= limit
    global _LAST_IDLE
    _LAST_IDLE = (time.time(), busy)
    return idle


def load_snapshot() -> Dict[str, Any]:
    busy = sample_cpu_percent(0.2)
    return {
        "cpu_busy_percent": round(busy, 1),
        "idle_threshold": idle_threshold(),
        "is_idle": busy <= idle_threshold(),
    }


def should_run_background_generate(
    *,
    has_pending_job: bool,
    cancel_requested: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Decide whether idle pre-generation should run now.
    If PC is busy → pause. If pending job already queued → skip.
    """
    if cancel_requested:
        return {"ok": False, "reason": "cancel_requested"}
    if has_pending_job:
        return {"ok": False, "reason": "pending_job_exists"}
    if force:
        return {"ok": True, "reason": "forced", "load": load_snapshot()}
    snap = load_snapshot()
    if not snap["is_idle"]:
        return {"ok": False, "reason": "pc_busy", "load": snap}
    return {"ok": True, "reason": "pc_idle", "load": snap}
