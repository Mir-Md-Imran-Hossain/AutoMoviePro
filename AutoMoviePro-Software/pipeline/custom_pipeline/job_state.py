"""Durable job + stage state for custom pipeline packages.

Persists to File/job_state.json so crashes can resume and UIs can poll progress.

Industrial guarantees:
  - atomic write (tmp + replace) + optional .bak
  - schema normalize / migrate on load
  - stage name validation
  - process-local lock around read-modify-write
  - stale heartbeat reaper
  - honest terminal status via compute_shippable
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STAGES = (
    "topic",
    "visual",
    "localize",
    "tts",
    "media",
    "thumbnail",
    "quality",
    "archive",
)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_SKIPPED = "skipped"
STATUS_PARTIAL = "partial"

TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED, STATUS_PARTIAL}
)
SCHEMA_VERSION = 2

_io_lock = threading.RLock()


def job_state_path(package_root: Path) -> Path:
    from pipeline.custom_pipeline.package_layout import open_package

    return open_package(package_root).file_dir / "job_state.json"


def _empty_stage() -> Dict[str, Any]:
    return {
        "status": STATUS_PENDING,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "detail": {},
    }


def _empty_stages() -> Dict[str, Any]:
    return {name: _empty_stage() for name in STAGES}


def new_job_state(
    *,
    package_root: Path,
    video_type: str,
    session_id: str = "",
    expected_languages: Optional[List[str]] = None,
    expected_shots: Optional[int] = None,
) -> Dict[str, Any]:
    now = time.time()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": str(uuid.uuid4()),
        "package_root": str(package_root),
        "video_type": video_type,
        "session_id": session_id or "",
        "status": STATUS_RUNNING,
        "shippable": False,
        "partial": False,
        "created_at": now,
        "updated_at": now,
        "heartbeat_at": now,
        "cancel_requested": False,
        "progress_pct": 0,
        "progress_message": "starting",
        "active_stage": None,
        "expected_languages": list(expected_languages or []),
        "expected_shots": expected_shots,
        "stages": _empty_stages(),
        "events": [],
        "budget": {"spent_units": 0.0, "cap_units": None, "entries": []},
        "degraded": [],
        "resume_count": 0,
    }


def normalize_job_state(state: Dict[str, Any], *, package_root: Optional[Path] = None) -> Dict[str, Any]:
    """Fill missing fields / migrate older job_state.json shapes."""
    if not isinstance(state, dict):
        raise TypeError("job_state must be a dict")
    base = new_job_state(
        package_root=package_root or Path(str(state.get("package_root") or ".")),
        video_type=str(state.get("video_type") or "short"),
        session_id=str(state.get("session_id") or ""),
        expected_languages=list(state.get("expected_languages") or []),
        expected_shots=state.get("expected_shots"),
    )
    # Preserve identity / ledger fields from disk
    for key in (
        "job_id",
        "package_root",
        "video_type",
        "session_id",
        "status",
        "shippable",
        "partial",
        "created_at",
        "updated_at",
        "heartbeat_at",
        "cancel_requested",
        "progress_pct",
        "progress_message",
        "active_stage",
        "expected_languages",
        "expected_shots",
        "events",
        "budget",
        "degraded",
        "resume_count",
        "character_reference",
    ):
        if key in state and state[key] is not None:
            base[key] = state[key]

    stages_in = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    stages = _empty_stages()
    for name in STAGES:
        raw = stages_in.get(name) if isinstance(stages_in.get(name), dict) else {}
        item = _empty_stage()
        item.update({k: raw[k] for k in item.keys() if k in raw})
        # coerce status
        st = str(item.get("status") or STATUS_PENDING).lower()
        if st not in {
            STATUS_PENDING,
            STATUS_RUNNING,
            STATUS_SUCCEEDED,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_SKIPPED,
            STATUS_PARTIAL,
        }:
            st = STATUS_PENDING
        item["status"] = st
        stages[name] = item
    base["stages"] = stages

    # budget shape
    budget = base.get("budget") if isinstance(base.get("budget"), dict) else {}
    base["budget"] = {
        "spent_units": float(budget.get("spent_units") or 0.0),
        "cap_units": budget.get("cap_units"),
        "entries": list(budget.get("entries") or [])[-300:],
    }
    base["events"] = list(base.get("events") or [])[-200:]
    base["degraded"] = list(base.get("degraded") or [])[-200:]
    base["schema_version"] = SCHEMA_VERSION
    if base.get("status") not in {
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_CANCELLED,
        STATUS_PARTIAL,
    }:
        base["status"] = STATUS_RUNNING
    return base


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    bak = path.with_suffix(path.suffix + ".bak")
    try:
        tmp.write_text(text, encoding="utf-8")
        # Keep previous good copy
        if path.is_file():
            try:
                if bak.exists():
                    bak.unlink()
                path.replace(bak)
            except Exception:
                pass
        # Atomic replace on same volume
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def load_job_state(package_root: Path) -> Optional[Dict[str, Any]]:
    path = job_state_path(package_root)
    with _io_lock:
        for candidate in (path, path.with_suffix(path.suffix + ".bak")):
            if not candidate.is_file():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
                return normalize_job_state(raw, package_root=Path(package_root))
            except Exception as exc:
                logger.warning("job_state load failed from %s: %s", candidate.name, exc)
        return None


def save_job_state(package_root: Path, state: Dict[str, Any]) -> Path:
    with _io_lock:
        normalized = normalize_job_state(state, package_root=Path(package_root))
        normalized["updated_at"] = time.time()
        # write back into caller dict so in-memory stays in sync
        state.clear()
        state.update(normalized)
        path = job_state_path(package_root)
        _atomic_write_json(path, normalized)
        return path


def heartbeat(package_root: Path, state: Dict[str, Any], message: str = "") -> None:
    state["heartbeat_at"] = time.time()
    if message:
        state["progress_message"] = message
    save_job_state(package_root, state)


def append_event(state: Dict[str, Any], kind: str, message: str = "", **extra: Any) -> None:
    ev = {"ts": time.time(), "kind": kind, "message": message, **extra}
    events = list(state.get("events") or [])
    events.append(ev)
    state["events"] = events[-200:]


def set_progress(state: Dict[str, Any], pct: float, message: str = "") -> None:
    state["progress_pct"] = max(0, min(100, float(pct)))
    if message:
        state["progress_message"] = message


def _require_stage(stage: str) -> str:
    name = str(stage or "").strip().lower()
    if name not in STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Valid: {STAGES}")
    return name


def start_stage(state: Dict[str, Any], stage: str) -> None:
    name = _require_stage(stage)
    stages = state.setdefault("stages", _empty_stages())
    item = stages.setdefault(name, _empty_stage())
    item["status"] = STATUS_RUNNING
    item["started_at"] = time.time()
    item["finished_at"] = None
    item["error"] = None
    state["active_stage"] = name
    state["status"] = STATUS_RUNNING
    append_event(state, "stage.started", stage=name)


def finish_stage(
    state: Dict[str, Any],
    stage: str,
    *,
    status: str,
    detail: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> None:
    name = _require_stage(stage)
    st = str(status or STATUS_SUCCEEDED).lower()
    if st not in {
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_CANCELLED,
        STATUS_SKIPPED,
        STATUS_PARTIAL,
        STATUS_PENDING,
    }:
        st = STATUS_FAILED
    stages = state.setdefault("stages", _empty_stages())
    item = stages.setdefault(name, _empty_stage())
    item["status"] = st
    item["finished_at"] = time.time()
    if detail is not None:
        item["detail"] = detail
    if error:
        item["error"] = error[:800]
    if state.get("active_stage") == name:
        state["active_stage"] = None
    append_event(state, "stage.finished", stage=name, status=st, error=error or None)


def finish_active_stage(
    state: Dict[str, Any],
    *,
    status: str,
    error: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Finish whichever stage is active (safe for exception handlers)."""
    name = state.get("active_stage")
    if not name:
        # Fall back to first running stage
        for s, item in (state.get("stages") or {}).items():
            if isinstance(item, dict) and item.get("status") == STATUS_RUNNING:
                name = s
                break
    if not name or name not in STAGES:
        return None
    finish_stage(state, name, status=status, error=error, detail=detail)
    return name


def prepare_resume(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mark a crash/zombie job as runnable again while preserving history."""
    prev = str(state.get("status") or "")
    state["resume_count"] = int(state.get("resume_count") or 0) + 1
    state["cancel_requested"] = False
    state["status"] = STATUS_RUNNING
    state["heartbeat_at"] = time.time()
    # Any RUNNING stage left from crash → failed (will be re-entered)
    for name, item in (state.get("stages") or {}).items():
        if isinstance(item, dict) and item.get("status") == STATUS_RUNNING:
            item["status"] = STATUS_FAILED
            item["error"] = item.get("error") or "interrupted_resume"
            item["finished_at"] = time.time()
    state["active_stage"] = None
    append_event(state, "job.resume", message=f"from_{prev}", resume_count=state["resume_count"])
    return state


def request_cancel(package_root: Path) -> Dict[str, Any]:
    with _io_lock:
        state = load_job_state(package_root) or new_job_state(
            package_root=package_root, video_type="short"
        )
        state["cancel_requested"] = True
        state["status"] = STATUS_CANCELLED
        append_event(state, "cancel.requested")
        save_job_state(package_root, state)
        return state


def is_cancel_requested(state: Optional[Dict[str, Any]]) -> bool:
    return bool(state and state.get("cancel_requested"))


def mark_degraded(state: Dict[str, Any], shot: str, provider: str, reason: str = "") -> None:
    degraded = list(state.get("degraded") or [])
    degraded.append(
        {"shot": shot, "provider": provider, "reason": reason, "ts": time.time()}
    )
    state["degraded"] = degraded[-200:]
    append_event(state, "shot.degraded", shot=shot, provider=provider, reason=reason)


def compute_shippable(
    state: Dict[str, Any],
    *,
    shared_success: int,
    shared_expected: int,
    finals_ok: List[str],
    expected_languages: List[str],
) -> Dict[str, Any]:
    """Honest ship gate: BN/primary ready to ship; all-langs tracked separately."""
    from pipeline.custom_pipeline.honest_status import honest_shippable

    planned = list(state.get("planned_languages") or expected_languages)
    result = honest_shippable(
        shared_success=shared_success,
        shared_expected=shared_expected,
        finals_ok=finals_ok,
        expected_languages=planned,
        cancel_requested=bool(state.get("cancel_requested")),
    )
    state["shippable"] = result["shippable"]
    state["shippable_bn_only"] = result.get("shippable_bn_only")
    state["shippable_all_languages"] = result.get("shippable_all_languages")
    state["partial"] = bool(result["partial"])
    state["missing_languages"] = list(result.get("missing_languages") or [])
    if state.get("cancel_requested"):
        state["status"] = STATUS_CANCELLED
    elif result.get("shippable_all_languages"):
        state["status"] = STATUS_SUCCEEDED
    elif result["shippable"]:
        # Primary/BN ready but optional langs missing
        state["status"] = STATUS_PARTIAL if result["partial"] else STATUS_SUCCEEDED
    elif result["partial"]:
        state["status"] = STATUS_PARTIAL
    else:
        state["status"] = STATUS_FAILED
    return result


def is_stale(state: Dict[str, Any], *, max_silent_sec: float = 1800.0) -> bool:
    if state.get("status") not in (STATUS_RUNNING, STATUS_PENDING):
        return False
    hb = float(state.get("heartbeat_at") or state.get("updated_at") or 0)
    return hb > 0 and (time.time() - hb) > max_silent_sec


def reaper_mark_stale(
    package_root: Path, *, max_silent_sec: float = 1800.0
) -> Optional[Dict[str, Any]]:
    with _io_lock:
        state = load_job_state(package_root)
        if not state or not is_stale(state, max_silent_sec=max_silent_sec):
            return state
        state["status"] = STATUS_FAILED
        append_event(state, "reaper.stale", message=f"no heartbeat >{max_silent_sec}s")
        for _name, item in (state.get("stages") or {}).items():
            if item.get("status") == STATUS_RUNNING:
                item["status"] = STATUS_FAILED
                item["error"] = "stale_heartbeat"
                item["finished_at"] = time.time()
        state["active_stage"] = None
        save_job_state(package_root, state)
        return state


def mutate_job_state(
    package_root: Path,
    mutator,
    *,
    create: bool = True,
    video_type: str = "short",
) -> Optional[Dict[str, Any]]:
    """Atomic read-modify-write under process lock (safe for heartbeat/cancel races)."""
    with _io_lock:
        state = load_job_state(package_root)
        if state is None:
            if not create:
                return None
            state = new_job_state(package_root=package_root, video_type=video_type)
        mutator(state)
        save_job_state(package_root, state)
        return state


def summarize_stages(state: Dict[str, Any]) -> Dict[str, str]:
    return {
        name: str((state.get("stages") or {}).get(name, {}).get("status") or STATUS_PENDING)
        for name in STAGES
    }
