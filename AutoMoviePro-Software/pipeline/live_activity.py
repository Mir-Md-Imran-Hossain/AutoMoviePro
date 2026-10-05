"""
Live activity bus for AutoMovie Pro desktop UI.

Tracks the currently running pipeline (generate / upload / API calls)
so the dashboard can show a terminal-style second-by-second stream.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.RLock()
_EVENT_CAP = 600
_API_CAP = 120
_STREAM_CAP = 800
_COALESCE_SEC = 2.5

_state: Dict[str, Any] = {
    "active": False,
    "job_id": "",
    "db_job_id": None,  # C01-A: persisted jobs.id when Generate created one
    "kind": "",  # short | long | upload | hidden | idle
    "channel_id": None,
    "channel_name": "",
    "phase": "idle",
    "detail": "",
    "scene": None,
    "scene_total": None,
    "apis": [],
    "events": [],
    "stream": [],
    "current": None,
    "started_at": 0.0,
    "updated_at": 0.0,
    "cancel_requested": False,
    "error": "",
    "result": None,
}
_cancel = threading.Event()
_thread: Optional[threading.Thread] = None

try:
    from app.config import DATA_DIR

    _STREAM_DIR = Path(DATA_DIR) / "live_activity"
except Exception:
    _STREAM_DIR = Path(__file__).resolve().parents[1] / "data" / "live_activity"


def _preview(text: Any, limit: int = 160) -> str:
    s = " ".join(str(text or "").replace("\r", " ").split())
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


def _stream_path() -> Path:
    _STREAM_DIR.mkdir(parents=True, exist_ok=True)
    return _STREAM_DIR / "stream.jsonl"


def _persist_line(ev: Dict[str, Any]) -> None:
    try:
        path = _stream_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        # Soft trim file if huge
        if path.stat().st_size > 2_500_000:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-_STREAM_CAP:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def snapshot(*, since_seq: int = 0) -> Dict[str, Any]:
    with _lock:
        s = dict(_state)
        stream = list(_state.get("stream") or [])
        if since_seq > 0:
            stream = [e for e in stream if int(e.get("seq") or 0) > since_seq]
        else:
            stream = stream[-250:]
        s["stream"] = stream
        s["events"] = list(_state.get("events") or [])[-80:]
        s["apis"] = list(_state.get("apis") or [])[-40:]
        s["current"] = dict(_state["current"]) if _state.get("current") else None
        s["stream_seq"] = int((_state.get("stream") or [{}])[-1].get("seq") or 0) if _state.get("stream") else 0
        s["elapsed_sec"] = (
            round(time.time() - float(s["started_at"]), 1) if s.get("started_at") else 0
        )
        return s


def is_cancel_requested() -> bool:
    return _cancel.is_set()


def clear_cancel() -> None:
    _cancel.clear()
    with _lock:
        _state["cancel_requested"] = False


def request_stop() -> Dict[str, Any]:
    _cancel.set()
    with _lock:
        _state["cancel_requested"] = True
        _push_event("stop_requested", "User requested process stop")
    return snapshot()


def _next_seq() -> int:
    stream = _state.get("stream") or []
    if not stream:
        return 1
    return int(stream[-1].get("seq") or 0) + 1


def _push_event(kind: str, message: str, **extra: Any) -> None:
    now = time.time()
    msg = str(message or "").strip() or kind
    events = list(_state.get("events") or [])
    stream = list(_state.get("stream") or [])
    last = stream[-1] if stream else None

    # Sticky / coalesce: same ongoing activity keeps one terminal line until next step
    coalesce_key = str(extra.get("coalesce") or f"{kind}|{msg}")
    if (
        last
        and last.get("coalesce") == coalesce_key
        and (now - float(last.get("updated_at") or last.get("ts") or 0)) < _COALESCE_SEC
        and not extra.get("force_new")
    ):
        last["updated_at"] = now
        last["ticks"] = int(last.get("ticks") or 1) + 1
        last["duration_sec"] = round(now - float(last.get("ts") or now), 1)
        if extra.get("response"):
            last["response"] = _preview(extra.get("response"), 220)
        if extra.get("dest"):
            last["dest"] = str(extra.get("dest"))
        _state["stream"] = stream
        _state["current"] = last
        _state["updated_at"] = now
        _state["detail"] = msg
        events.append(
            {
                "ts": now,
                "kind": kind,
                "message": msg,
                "tick": True,
            }
        )
        _state["events"] = events[-_EVENT_CAP:]
        return

    ev = {
        "seq": _next_seq(),
        "ts": now,
        "updated_at": now,
        "ticks": 1,
        "duration_sec": 0.0,
        "kind": kind,
        "message": msg,
        "coalesce": coalesce_key,
        "phase": _state.get("phase") or "",
        "scene": _state.get("scene"),
        "job_id": _state.get("job_id") or "",
    }
    for key in (
        "provider",
        "action",
        "status",
        "request",
        "response",
        "dest",
        "scene",
        "total",
        "phase",
        "level",
    ):
        if key in extra and extra[key] is not None:
            val = extra[key]
            if key in ("request", "response"):
                val = _preview(val, 220)
            ev[key] = val

    stream.append(ev)
    _state["stream"] = stream[-_STREAM_CAP:]
    _state["current"] = ev
    _state["updated_at"] = now
    _state["detail"] = msg
    events.append({"ts": now, "kind": kind, "message": msg, **{k: ev[k] for k in ("provider", "action", "status") if k in ev}})
    _state["events"] = events[-_EVENT_CAP:]
    _persist_line(ev)


def log(kind: str, message: str, **extra: Any) -> None:
    """Public detailed terminal line (works even mid-step)."""
    with _lock:
        if not _state.get("active") and kind not in ("system", "idle"):
            # Still record if a job recently finished — keep last 2 min window
            if (time.time() - float(_state.get("updated_at") or 0)) > 120:
                return
        _push_event(kind, message, **extra)


def start_job(
    *,
    kind: str,
    channel_id: Optional[int] = None,
    channel_name: str = "",
    phase: str = "starting",
    detail: str = "",
    db_job_id: Optional[int] = None,
) -> str:
    global _thread
    job_id = uuid.uuid4().hex[:12]
    clear_cancel()
    with _lock:
        _state.update(
            {
                "active": True,
                "job_id": job_id,
                "db_job_id": int(db_job_id) if db_job_id is not None else None,
                "kind": kind,
                "channel_id": channel_id,
                "channel_name": channel_name or "",
                "phase": phase,
                "detail": detail or f"{kind} started",
                "scene": None,
                "scene_total": None,
                "apis": [],
                "events": [],
                "stream": [],
                "current": None,
                "started_at": time.time(),
                "updated_at": time.time(),
                "cancel_requested": False,
                "error": "",
                "result": None,
            }
        )
        _push_event("start", detail or f"{kind} job started", job_id=job_id, force_new=True)
    return job_id


def set_phase(phase: str, detail: str = "") -> None:
    db_job_id = None
    with _lock:
        if not _state.get("active"):
            return
        _state["phase"] = phase
        db_job_id = _state.get("db_job_id")
        if detail:
            _push_event("phase", detail, phase=phase, force_new=True)
        else:
            _state["updated_at"] = time.time()
    if db_job_id is not None:
        try:
            from app.customer_job import sync_from_live_phase

            sync_from_live_phase(int(db_job_id), phase, detail)
        except Exception:
            pass
    try:
        from pipeline.live_lab import mirror_activity

        mirror_activity(phase, detail)
    except Exception:
        pass


def set_scene(scene: Optional[int], total: Optional[int] = None, detail: str = "") -> None:
    with _lock:
        if not _state.get("active"):
            return
        _state["scene"] = scene
        if total is not None:
            _state["scene_total"] = total
        msg = detail or (f"Scene {scene}" + (f"/{total}" if total else ""))
        _push_event("scene", msg, scene=scene, total=total, force_new=True)


def note_api(
    provider: str,
    action: str = "",
    status: str = "call",
    *,
    request: str = "",
    response: str = "",
    dest: str = "",
) -> None:
    with _lock:
        if not _state.get("active"):
            return
        row = {
            "ts": time.time(),
            "provider": provider,
            "action": action,
            "status": status,
        }
        apis = list(_state.get("apis") or [])
        apis.append(row)
        _state["apis"] = apis[-_API_CAP:]
        parts = [f"API {provider}", action or "", f"[{status}]"]
        if request:
            parts.append(f"req={_preview(request, 100)}")
        if response:
            parts.append(f"→ {_preview(response, 120)}")
        if dest:
            parts.append(f"→ {dest}")
        _push_event(
            "api",
            " ".join(p for p in parts if p).strip(),
            provider=provider,
            action=action,
            status=status,
            request=request,
            response=response,
            dest=dest,
            force_new=status in ("ok", "fail", "error", "start"),
            coalesce=f"api|{provider}|{action}|{status}|{_preview(request, 40)}",
        )


def finish(ok: bool = True, result: Any = None, error: str = "") -> None:
    with _lock:
        _state["active"] = False
        _state["phase"] = "done" if ok else "failed"
        _state["result"] = result
        _state["error"] = error or ""
        _state["updated_at"] = time.time()
        _push_event(
            "done" if ok else "error",
            "Completed" if ok else (error or "Failed"),
            force_new=True,
            level="ok" if ok else "error",
        )
    clear_cancel()


def run_in_background(
    target,
    *,
    kind: str,
    channel_id=None,
    channel_name: str = "",
    db_job_id: Optional[int] = None,
    generation_owner: Optional[str] = None,
) -> str:
    """Start target() in a daemon thread; returns live correlation job_id (not DB id).

    generation_owner: when set, releases app.generation_guard on completion (C01-B).
    """
    global _thread
    if _state.get("active") and _thread and _thread.is_alive():
        raise RuntimeError("already_running")

    job_id = start_job(
        kind=kind,
        channel_id=channel_id,
        channel_name=channel_name,
        db_job_id=db_job_id,
    )

    def _wrap() -> None:
        try:
            result = target()
            if is_cancel_requested():
                finish(False, error="cancelled_by_user")
                if db_job_id is not None:
                    try:
                        from app.customer_job import mark_failed

                        mark_failed(int(db_job_id), "cancelled_by_user", recoverable=False)
                    except Exception:
                        pass
            else:
                finish(True, result=result)
                if db_job_id is not None:
                    try:
                        from app.customer_job import mark_from_pipeline_result

                        mark_from_pipeline_result(
                            int(db_job_id),
                            result if isinstance(result, dict) else {},
                        )
                    except Exception:
                        pass
        except Exception as exc:
            finish(False, error=str(exc)[:300])
            if db_job_id is not None:
                try:
                    from app.customer_job import mark_failed

                    mark_failed(int(db_job_id), exc, recoverable=True)
                except Exception:
                    pass
        finally:
            if generation_owner:
                try:
                    from app.generation_guard import release as generation_release

                    generation_release(str(generation_owner))
                except Exception:
                    pass

    _thread = threading.Thread(target=_wrap, name=f"amp-{kind}-{job_id}", daemon=True)
    _thread.start()
    return job_id
