"""C01-B — Shared generation execution guard (idle pregen ↔ customer Generate).

NOT a second scheduler, queue, or job engine.
Protects only the shared generate_video execution resource so idle pregen
and customer Generate cannot overlap in-process.

Authority: used by SchedulerService and POST /api/generate (via live worker).
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

_lock = threading.RLock()
_busy: bool = False
_owner: Optional[str] = None
_metrics: Dict[str, int] = {
    "enters": 0,
    "rejects": 0,
    "releases": 0,
    "max_observed_concurrent": 0,
    "_inflight": 0,
}


def try_acquire(owner: str) -> bool:
    """Acquire exclusive generation slot. Returns False if busy or live worker active (for non-customer)."""
    global _busy, _owner
    owner = str(owner or "unknown")
    with _lock:
        if _busy:
            _metrics["rejects"] += 1
            return False
        # Idle/scheduler must not overlap an active customer live worker
        if owner != "customer":
            try:
                from pipeline.live_activity import snapshot

                if snapshot().get("active"):
                    _metrics["rejects"] += 1
                    return False
            except Exception:
                pass
        _busy = True
        _owner = owner
        _metrics["enters"] += 1
        _metrics["_inflight"] += 1
        if _metrics["_inflight"] > _metrics["max_observed_concurrent"]:
            _metrics["max_observed_concurrent"] = _metrics["_inflight"]
        return True


def release(owner: str) -> None:
    """Release generation slot. Only the owning owner may release (fail-closed)."""
    global _busy, _owner
    owner = str(owner or "unknown")
    with _lock:
        if not _busy:
            return
        if _owner is not None and _owner != owner:
            return
        _busy = False
        _owner = None
        _metrics["releases"] += 1
        if _metrics["_inflight"] > 0:
            _metrics["_inflight"] -= 1


def force_release() -> None:
    """Test/emergency only — clear slot."""
    global _busy, _owner
    with _lock:
        _busy = False
        _owner = None
        _metrics["_inflight"] = 0


def is_busy() -> bool:
    """True if guard held OR live customer generation is active."""
    with _lock:
        if _busy:
            return True
    try:
        from pipeline.live_activity import snapshot

        return bool(snapshot().get("active"))
    except Exception:
        return False


def owner() -> Optional[str]:
    with _lock:
        return _owner


def metrics_snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "busy": _busy,
            "owner": _owner,
            "enters": int(_metrics["enters"]),
            "rejects": int(_metrics["rejects"]),
            "releases": int(_metrics["releases"]),
            "max_observed_concurrent": int(_metrics["max_observed_concurrent"]),
            "inflight": int(_metrics["_inflight"]),
        }


def reset_for_tests() -> None:
    """Reset guard + metrics (unit tests only)."""
    global _busy, _owner, _metrics
    with _lock:
        _busy = False
        _owner = None
        _metrics = {
            "enters": 0,
            "rejects": 0,
            "releases": 0,
            "max_observed_concurrent": 0,
            "_inflight": 0,
        }
