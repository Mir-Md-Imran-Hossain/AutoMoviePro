"""C10 — Marathon Observability & Forensic Test Harness (observation only).

Evidence / watchdog / report infrastructure for a FUTURE Marathon Test.
Does NOT own production state. Does NOT run the real Marathon.
Does NOT call paid providers. Does NOT auto-modify production code.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import DATA_DIR

CONTRACT_VERSION = "C10.1"
SCHEMA_VERSION = "c10.evidence.v1"

WATCHDOG_DEFAULT_INTERVAL_SEC = 600  # 10 minutes

WATCHDOG_STATES = (
    "HEALTHY",
    "PROGRESSING",
    "WAITING",
    "SLOW",
    "STUCK",
    "FAILED",
    "UNKNOWN",
    "COMPLETED",
)

KNOWN_WAIT_STATES = frozenset(
    {
        "REMOTE_PROCESSING",
        "UPLOAD_ACCEPTED",
        "SCHEDULED",
        "DUE",
        "WAITING_PROVIDER",
        "APPROVAL_PENDING",
        "PREVIEW_READY",
        "QUEUED",
    }
)

TERMINAL_SUCCESS = frozenset({"PUBLISHED", "COMPLETED", "DONE", "SUCCESS"})
TERMINAL_FAILURE = frozenset({"FAILED", "CANCELLED", "MISSED", "ABORTED"})

LEDGER_DIRS = (
    "timeline",
    "api",
    "prompts",
    "scripts",
    "scenes",
    "beats",
    "visual",
    "audio",
    "subtitles",
    "quality",
    "repair",
    "render",
    "publish",
    "schedule",
    "failures",
    "watchdog",
    "interventions",
)

SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "cookie",
    "oauth",
    "refresh_token",
    "access_token",
    "private_key",
)

_LOCK = threading.RLock()
# Active bindings: job_id -> session_id ; work_dir_str -> session_id
_JOB_BINDINGS: Dict[int, str] = {}
_WORKDIR_BINDINGS: Dict[str, str] = {}
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mono() -> float:
    return time.monotonic()


def redact(obj: Any) -> Any:
    """Fail-closed secret redaction for evidence persistence."""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(x in lk for x in SECRET_KEY_FRAGMENTS):
                out[k] = "[redacted]"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        s = obj
        if re.search(r"(?i)(api[_-]?key|sk-[A-Za-z0-9]{8,}|bearer\s+[A-Za-z0-9._\-]+)", s):
            return "[redacted]"
        return s
    return obj


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def marathon_root(data_dir: Optional[Path] = None) -> Path:
    root = Path(data_dir or DATA_DIR) / "marathon_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_dir(session_id: str, *, data_dir: Optional[Path] = None) -> Path:
    d = marathon_root(data_dir) / str(session_id)
    d.mkdir(parents=True, exist_ok=True)
    for name in LEDGER_DIRS:
        (d / name).mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(session_id: str, *, data_dir: Optional[Path] = None) -> Path:
    return session_dir(session_id, data_dir=data_dir) / "manifest.json"


def _run_path(session_id: str, *, data_dir: Optional[Path] = None) -> Path:
    return session_dir(session_id, data_dir=data_dir) / "run.json"


def load_manifest(session_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _manifest_path(session_id, data_dir=data_dir)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(session_id: str, data: Dict[str, Any], *, data_dir: Optional[Path] = None) -> None:
    p = _manifest_path(session_id, data_dir=data_dir)
    p.write_text(json.dumps(redact(data), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_run(session_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _run_path(session_id, data_dir=data_dir)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_run(session_id: str, data: Dict[str, Any], *, data_dir: Optional[Path] = None) -> None:
    p = _run_path(session_id, data_dir=data_dir)
    p.write_text(json.dumps(redact(data), indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _last_chain_hash(session_id: str, ledger: str, *, data_dir: Optional[Path] = None) -> str:
    path = session_dir(session_id, data_dir=data_dir) / ledger / "events.jsonl"
    if not path.is_file():
        return "GENESIS"
    last = ""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line.strip()
        if not last:
            return "GENESIS"
        prev = json.loads(last)
        return str(prev.get("record_hash") or prev.get("event_id") or "GENESIS")
    except Exception:
        return "GENESIS"


def _append_jsonl(session_id: str, ledger: str, record: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    with _LOCK:
        prev = _last_chain_hash(session_id, ledger, data_dir=data_dir)
        body = redact(dict(record))
        body.setdefault("schema_version", SCHEMA_VERSION)
        body.setdefault("contract", CONTRACT_VERSION)
        body.setdefault("timestamp", _now_iso())
        body.setdefault("monotonic_timestamp", round(_mono(), 6))
        body.setdefault("source", "customer_marathon_observability")
        body.setdefault("marathon_session_id", session_id)
        body["prev_hash"] = prev
        if "event_id" not in body:
            # provisional id before hash; final id derived from record_hash below if still provisional
            body["event_id"] = f"tmp_{uuid.uuid4().hex[:12]}"
        material = {k: v for k, v in body.items() if k != "record_hash"}
        body["record_hash"] = _hash_text(_canonical(material))[:40]
        if str(body.get("event_id", "")).startswith("tmp_"):
            # Re-hash once with stable event_id derived from content hash
            body["event_id"] = body["record_hash"][:24]
            material = {k: v for k, v in body.items() if k != "record_hash"}
            body["record_hash"] = _hash_text(_canonical(material))[:40]
        path = session_dir(session_id, data_dir=data_dir) / ledger / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, default=str) + "\n")
        return body


def read_ledger(session_id: str, ledger: str, *, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = session_dir(session_id, data_dir=data_dir) / ledger / "events.jsonl"
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def verify_ledger_integrity(session_id: str, ledger: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    rows = read_ledger(session_id, ledger, data_dir=data_dir)
    prev = "GENESIS"
    for i, row in enumerate(rows):
        if str(row.get("prev_hash")) != prev:
            return {"ok": False, "index": i, "error": "chain_break", "expected_prev": prev}
        material = {k: v for k, v in row.items() if k != "record_hash"}
        expected = _hash_text(_canonical(material))[:40]
        if str(row.get("record_hash")) != expected:
            return {"ok": False, "index": i, "error": "hash_mismatch"}
        prev = str(row.get("record_hash"))
    return {"ok": True, "count": len(rows)}


# ---------------------------------------------------------------------------
# Test case contracts (definitions only — do not execute Marathon)
# ---------------------------------------------------------------------------

MARATHON_TEST_CASES: Dict[str, Dict[str, Any]] = {
    "MARATHON_LONG": {
        "test_case_id": "MARATHON_LONG",
        "video_type": "LONG",
        "target_duration_sec": 480,
        "locale": "en",
        "production_mode": "customer_canonical_queue",
        "provider_mode": "offline_mock",
        "maximum_runtime_sec": 6 * 3600,
        "watchdog_interval_sec": WATCHDOG_DEFAULT_INTERVAL_SEC,
        "niche": None,  # selected by future Marathon — not in C10
        "channel": None,
        "output_path": None,
        "mutates_production": False,
        "note": "Definition only — C10 does not execute",
    },
    "MARATHON_SHORT": {
        "test_case_id": "MARATHON_SHORT",
        "video_type": "SHORT",
        "target_duration_sec": 45,
        "locale": "en",
        "production_mode": "customer_canonical_queue",
        "provider_mode": "offline_mock",
        "maximum_runtime_sec": 3 * 3600,
        "watchdog_interval_sec": WATCHDOG_DEFAULT_INTERVAL_SEC,
        "niche": None,
        "channel": None,
        "output_path": None,
        "mutates_production": False,
        "note": "Definition only — C10 does not execute",
    },
}


def get_test_case(test_case_id: str) -> Dict[str, Any]:
    key = str(test_case_id or "").upper()
    if key not in MARATHON_TEST_CASES:
        return {"ok": False, "error": "unknown_test_case", "error_code": "NOT_AVAILABLE"}
    return {"ok": True, "test_case": dict(MARATHON_TEST_CASES[key])}


# ---------------------------------------------------------------------------
# Run identity
# ---------------------------------------------------------------------------

def create_marathon_session(
    *,
    login_id: str,
    test_case_id: str,
    video_type: str,
    niche: str = "synthetic_offline",
    locale: str = "en",
    timezone_name: str = "UTC",
    environment: str = "offline_smoke",
    channel_id: Optional[int] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create run identity + empty evidence tree. Never stores secrets."""
    tc = get_test_case(test_case_id)
    if not tc.get("ok"):
        return tc
    case = tc["test_case"]
    vt = str(video_type or case["video_type"]).upper()
    if vt not in ("LONG", "SHORT"):
        return {"ok": False, "error": "invalid_video_type", "error_code": "CONTRACT"}

    session_id = f"ms_{uuid.uuid4().hex[:16]}"
    run_id = f"mr_{uuid.uuid4().hex[:16]}"
    release: Dict[str, Any] = {}
    try:
        from app.release_identity import RELEASE_VERSION, get_release_identity

        release = get_release_identity(include_media=False)
        app_version = RELEASE_VERSION
    except Exception:
        app_version = "UNKNOWN"
        release = {"release_version": "UNKNOWN"}

    identity = redact(
        {
            "ok": True,
            "contract": CONTRACT_VERSION,
            "marathon_session_id": session_id,
            "run_id": run_id,
            "test_case_id": case["test_case_id"],
            "video_type": vt,
            "login_id": str(login_id),
            "channel_id": channel_id,
            "niche": str(niche),
            "locale": str(locale or case.get("locale") or "en"),
            "timezone": str(timezone_name),
            "application_version": app_version,
            "source_release_revision": release.get("build_id"),
            "environment": environment,
            "start_time": _now_iso(),
            "end_time": None,
            "status": "CREATED",
            "watchdog_interval_sec": int(case.get("watchdog_interval_sec") or WATCHDOG_DEFAULT_INTERVAL_SEC),
            "maximum_runtime_sec": int(case.get("maximum_runtime_sec") or 0),
            "target_duration_sec": int(case.get("target_duration_sec") or 0),
            "provider_mode": case.get("provider_mode"),
            "production_mode": case.get("production_mode"),
            "owns_production": False,
            "paid_api_calls": 0,
            "external_provider_calls": 0,
        }
    )
    session_dir(session_id, data_dir=data_dir)
    save_manifest(session_id, {"schema_version": SCHEMA_VERSION, "identity": identity}, data_dir=data_dir)
    save_run(session_id, identity, data_dir=data_dir)
    with _LOCK:
        _ACTIVE_SESSIONS[session_id] = {"login_id": str(login_id), "run_id": run_id, "data_dir": str(data_dir) if data_dir else None}
    record_evidence(
        session_id,
        ledger="timeline",
        stage="SESSION",
        component="harness",
        operation="create_session",
        event_type="SESSION_CREATED",
        status="OK",
        metadata={"video_type": vt, "test_case_id": case["test_case_id"]},
        data_dir=data_dir,
    )
    return identity


def bind_job(session_id: str, job_id: int, *, login_id: Optional[str] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found", "error_code": "NOT_AVAILABLE"}
    if login_id is not None and str(run.get("login_id")) != str(login_id):
        return {"ok": False, "error": "access_denied", "error_code": "OWNERSHIP_FAILURE"}
    with _LOCK:
        _JOB_BINDINGS[int(job_id)] = session_id
    run["job_id"] = int(job_id)
    run["status"] = "BOUND"
    save_run(session_id, run, data_dir=data_dir)
    return {"ok": True, "marathon_session_id": session_id, "job_id": int(job_id)}


def bind_work_dir(session_id: str, work_dir: Path | str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found"}
    key = str(Path(work_dir).resolve())
    with _LOCK:
        _WORKDIR_BINDINGS[key] = session_id
    run["work_dir"] = key
    save_run(session_id, run, data_dir=data_dir)
    return {"ok": True, "work_dir": key}


def unbind_job(job_id: int) -> None:
    with _LOCK:
        _JOB_BINDINGS.pop(int(job_id), None)


def finish_session(session_id: str, *, status: str = "COMPLETED", data_dir: Optional[Path] = None) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found"}
    run["end_time"] = _now_iso()
    run["status"] = status
    save_run(session_id, run, data_dir=data_dir)
    record_evidence(
        session_id,
        ledger="timeline",
        stage="SESSION",
        component="harness",
        operation="finish_session",
        event_type="SESSION_FINISHED",
        status=status,
        data_dir=data_dir,
    )
    return {"ok": True, "run": run}


# ---------------------------------------------------------------------------
# Generic evidence recording
# ---------------------------------------------------------------------------

def record_evidence(
    session_id: str,
    *,
    ledger: str,
    stage: str,
    component: str,
    operation: str,
    event_type: str,
    status: str = "OK",
    job_id: Optional[int] = None,
    scene_id: Optional[str] = None,
    beat_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    provider: Optional[str] = None,
    request_id: Optional[str] = None,
    source_ref: Optional[str] = None,
    duration_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if ledger not in LEDGER_DIRS:
        return {"ok": False, "error": "unknown_ledger", "error_code": "CONTRACT"}
    run = load_run(session_id, data_dir=data_dir)
    rid = run_id or (run.get("run_id") if run else None)
    rec = {
        "run_id": rid,
        "stage": stage,
        "component": component,
        "operation": operation,
        "event_type": event_type,
        "job_id": job_id,
        "scene_id": scene_id,
        "beat_id": beat_id,
        "asset_id": asset_id,
        "provider": provider,
        "request_id": request_id,
        "source_ref": source_ref,
        "status": status,
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }
    stored = _append_jsonl(session_id, ledger, rec, data_dir=data_dir)
    return {"ok": True, "record": stored}


def record_api_call(
    session_id: str,
    *,
    provider: str,
    operation: str,
    status: str,
    latency_ms: float,
    stage: str = "PROVIDER",
    request_id: Optional[str] = None,
    job_id: Optional[int] = None,
    scene_id: Optional[str] = None,
    beat_id: Optional[str] = None,
    http_status: Optional[int] = None,
    retry_count: int = 0,
    timeout: bool = False,
    error_classification: Optional[str] = None,
    response_classification: Optional[str] = None,
    paid: bool = False,
    cache_reuse: bool = False,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    meta = {
        "http_status": http_status,
        "retry_count": int(retry_count),
        "timeout": bool(timeout),
        "error_classification": error_classification,
        "response_classification": response_classification,
        "paid": bool(paid),
        "cache_reuse": bool(cache_reuse),
        "start_time": start_time,
        "end_time": end_time,
    }
    return record_evidence(
        session_id,
        ledger="api",
        stage=stage,
        component="provider",
        operation=operation,
        event_type="API_CALL",
        status=status,
        job_id=job_id,
        scene_id=scene_id,
        beat_id=beat_id,
        provider=provider,
        request_id=request_id or f"req_{uuid.uuid4().hex[:12]}",
        duration_ms=float(latency_ms),
        metadata=meta,
        data_dir=data_dir,
    )


def record_prompt(
    session_id: str,
    *,
    provider: str,
    operation: str,
    prompt_text: str,
    scene_id: Optional[str] = None,
    beat_id: Optional[str] = None,
    dialogue_id: Optional[str] = None,
    compilation_source: str = "compile_provider_prompt",
    visual_mode: Optional[str] = None,
    character_identity: Optional[str] = None,
    location: Optional[str] = None,
    objects_entities: Optional[Any] = None,
    relationships: Optional[Any] = None,
    camera: Optional[str] = None,
    lighting: Optional[str] = None,
    emotion: Optional[str] = None,
    continuity_context: Optional[Any] = None,
    pre_transform_prompt: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    safe_text = str(prompt_text or "")
    prompt_hash = _hash_text(safe_text)[:32]
    prompt_id = f"pr_{prompt_hash[:16]}"
    return record_evidence(
        session_id,
        ledger="prompts",
        stage="PROMPT",
        component="prompt_compiler",
        operation=operation,
        event_type="PROMPT_CAPTURE",
        status="OK",
        scene_id=scene_id,
        beat_id=beat_id,
        provider=provider,
        source_ref=prompt_id,
        metadata={
            "prompt_id": prompt_id,
            "prompt_hash": prompt_hash,
            "dialogue_id": dialogue_id,
            "prompt_text": safe_text[:8000],
            "prompt_compilation_source": compilation_source,
            "visual_mode": visual_mode,
            "character_identity": character_identity,
            "location": location,
            "objects_entities": objects_entities,
            "relationships": relationships,
            "camera": camera,
            "lighting": lighting,
            "emotion": emotion,
            "continuity_context": continuity_context,
            "pre_transform_prompt": (pre_transform_prompt or "")[:8000] or None,
        },
        data_dir=data_dir,
    )


def record_script_beats(
    session_id: str,
    *,
    topic: Optional[str] = None,
    research_id: Optional[str] = None,
    script_id: Optional[str] = None,
    dialogues: Optional[Sequence[Dict[str, Any]]] = None,
    narrative_beats: Optional[Sequence[Dict[str, Any]]] = None,
    visual_beats: Optional[Sequence[Dict[str, Any]]] = None,
    scenes: Optional[Sequence[Dict[str, Any]]] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    out = record_evidence(
        session_id,
        ledger="scripts",
        stage="SCRIPT",
        component="trs_plan",
        operation="capture_script",
        event_type="SCRIPT_SNAPSHOT",
        status="OK",
        metadata={
            "topic": topic,
            "research_identity": research_id,
            "script_identity": script_id,
            "dialogue_segments": list(dialogues or []),
            "narrative_beats": list(narrative_beats or []),
        },
        data_dir=data_dir,
    )
    for vb in visual_beats or []:
        record_evidence(
            session_id,
            ledger="beats",
            stage="BEAT",
            component="story_visual_direction",
            operation="capture_visual_beat",
            event_type="VISUAL_BEAT",
            status="OK",
            scene_id=str(vb.get("scene_id") or "") or None,
            beat_id=str(vb.get("beat_id") or vb.get("id") or "") or None,
            metadata=dict(vb),
            data_dir=data_dir,
        )
    for sc in scenes or []:
        record_evidence(
            session_id,
            ledger="scenes",
            stage="SCENE",
            component="scene_runtime",
            operation="capture_scene",
            event_type="SCENE_SNAPSHOT",
            status="OK",
            scene_id=str(sc.get("scene_id") or sc.get("id") or "") or None,
            metadata=dict(sc),
            data_dir=data_dir,
        )
    return out


def record_visual_artifact(session_id: str, artifact: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="visual",
        stage="VISUAL",
        component="visual_runtime",
        operation="artifact",
        event_type="VISUAL_ARTIFACT",
        status=str(artifact.get("verification_status") or artifact.get("status") or "UNKNOWN"),
        scene_id=artifact.get("scene_id"),
        beat_id=artifact.get("beat_id"),
        asset_id=artifact.get("asset_id"),
        provider=artifact.get("provider"),
        duration_ms=artifact.get("latency_ms"),
        metadata=artifact,
        data_dir=data_dir,
    )


def record_audio_artifact(session_id: str, artifact: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="audio",
        stage="AUDIO",
        component="audio_runtime",
        operation="artifact",
        event_type="AUDIO_ARTIFACT",
        status=str(artifact.get("verification_state") or artifact.get("status") or "UNKNOWN"),
        scene_id=artifact.get("scene_id"),
        asset_id=artifact.get("audio_id"),
        provider=artifact.get("provider"),
        duration_ms=artifact.get("generation_latency_ms"),
        metadata=artifact,
        data_dir=data_dir,
    )


def record_subtitle(session_id: str, row: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="subtitles",
        stage="SUBTITLE",
        component="localization",
        operation="subtitle_segment",
        event_type="SUBTITLE_SEGMENT",
        status=str(row.get("validation_status") or row.get("status") or "UNKNOWN"),
        metadata=row,
        data_dir=data_dir,
    )


def record_state_transition(
    session_id: str,
    *,
    from_state: Optional[str],
    to_state: str,
    job_id: Optional[int] = None,
    source_ref: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="timeline",
        stage="STATE",
        component="lifecycle",
        operation="transition",
        event_type="STATE_TRANSITION",
        status=to_state,
        job_id=job_id,
        source_ref=source_ref,
        metadata={"from_state": from_state, "to_state": to_state},
        data_dir=data_dir,
    )


def record_failure(
    session_id: str,
    *,
    failure_code: str,
    stage: str,
    component: str,
    attempt: int = 1,
    retry_count: int = 0,
    retry_owner: str = "customer_job_automation",
    recovery_action: Optional[str] = None,
    final_state: Optional[str] = None,
    recovery_latency_ms: Optional[float] = None,
    evidence_ref: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="failures",
        stage=stage,
        component=component,
        operation="failure",
        event_type="FAILURE",
        status=failure_code,
        duration_ms=recovery_latency_ms,
        source_ref=evidence_ref,
        metadata={
            "failure_code": failure_code,
            "attempt": attempt,
            "retry_count": retry_count,
            "retry_owner": retry_owner,
            "recovery_action": recovery_action,
            "final_state": final_state,
        },
        data_dir=data_dir,
    )


def record_repair(session_id: str, repair: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="repair",
        stage="REPAIR",
        component="build04f_repair",
        operation="repair",
        event_type="REPAIR",
        status=str(repair.get("post_repair_status") or repair.get("status") or "UNKNOWN"),
        job_id=repair.get("job_id"),
        scene_id=repair.get("scene_id"),
        beat_id=repair.get("beat_id"),
        duration_ms=repair.get("repair_latency_ms"),
        metadata=repair,
        data_dir=data_dir,
    )


def record_render(session_id: str, render: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    # Never store raw credentials in ffmpeg command lines
    safe = dict(render)
    if "command" in safe:
        safe["command_hash"] = _hash_text(str(safe.pop("command")))[:32]
    if "ffmpeg_command" in safe:
        safe["command_hash"] = _hash_text(str(safe.pop("ffmpeg_command")))[:32]
    return record_evidence(
        session_id,
        ledger="render",
        stage="RENDER",
        component="ffmpeg_render",
        operation="render",
        event_type="RENDER",
        status=str(safe.get("status") or "UNKNOWN"),
        duration_ms=safe.get("duration_ms"),
        metadata=safe,
        data_dir=data_dir,
    )


def record_publish(session_id: str, row: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="publish",
        stage="PUBLISH",
        component="customer_publish",
        operation=str(row.get("operation") or "publish"),
        event_type="PUBLISH",
        status=str(row.get("status") or "UNKNOWN"),
        job_id=row.get("job_id"),
        duration_ms=row.get("upload_latency_ms"),
        metadata=row,
        data_dir=data_dir,
    )


def record_schedule(session_id: str, row: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="schedule",
        stage="SCHEDULE",
        component="customer_publish_schedule",
        operation=str(row.get("operation") or "schedule"),
        event_type="SCHEDULE",
        status=str(row.get("status") or "UNKNOWN"),
        job_id=row.get("job_id"),
        metadata=row,
        data_dir=data_dir,
    )


def record_quality(session_id: str, row: Dict[str, Any], *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    return record_evidence(
        session_id,
        ledger="quality",
        stage="QUALITY",
        component="quality_gate",
        operation=str(row.get("operation") or "evaluate"),
        event_type="QUALITY",
        status=str(row.get("status") or "UNKNOWN"),
        metadata=row,
        data_dir=data_dir,
    )


# ---------------------------------------------------------------------------
# Intervention contract (record-only — no autonomous code modification)
# ---------------------------------------------------------------------------

INTERVENTION_STEPS = ("DETECT", "COLLECT_EVIDENCE", "CLASSIFY", "PROPOSE_MINIMAL_FIX", "RUN_TARGETED_TEST", "VALIDATE", "RESUME")


def record_intervention(
    session_id: str,
    *,
    step: str,
    classification: str,
    proposal: Optional[str] = None,
    applied: bool = False,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if step not in INTERVENTION_STEPS:
        return {"ok": False, "error": "invalid_intervention_step"}
    if applied:
        # C10 forbids unbounded autonomous code modification
        return {
            "ok": False,
            "error": "auto_apply_forbidden",
            "error_code": "SAFE_AUTO_REPAIR_BOUNDARY",
            "note": "C10 records proposals only; does not modify production code",
        }
    return record_evidence(
        session_id,
        ledger="interventions",
        stage="INTERVENTION",
        component="harness",
        operation=step,
        event_type="INTERVENTION",
        status=classification,
        metadata={"step": step, "proposal": proposal, "applied": False, "mutates_code": False},
        data_dir=data_dir,
    )


# ---------------------------------------------------------------------------
# Fail-closed production fan-out observers
# ---------------------------------------------------------------------------

def on_lifecycle_event(job_id: int, event: Dict[str, Any]) -> None:
    """Called from append_lifecycle_event — never raises into production."""
    try:
        with _LOCK:
            session_id = _JOB_BINDINGS.get(int(job_id))
        if not session_id:
            return
        data_dir = None
        with _LOCK:
            meta = _ACTIVE_SESSIONS.get(session_id) or {}
            if meta.get("data_dir"):
                data_dir = Path(meta["data_dir"])
        et = str(event.get("type") or event.get("event") or "LIFECYCLE").upper()
        record_evidence(
            session_id,
            ledger="timeline",
            stage="LIFECYCLE",
            component="customer_job_automation",
            operation="lifecycle_event",
            event_type=et,
            status=str(event.get("status") or "OK"),
            job_id=int(job_id),
            source_ref=str(event.get("at") or ""),
            metadata={"raw_type": et, "detail": event.get("detail")},
            data_dir=data_dir,
        )
        to_state = event.get("state") or event.get("to_state") or event.get("monitor_state")
        if to_state:
            record_state_transition(
                session_id,
                from_state=event.get("from_state"),
                to_state=str(to_state),
                job_id=int(job_id),
                data_dir=data_dir,
            )
    except Exception:
        return


def on_usage_event(work_dir: Optional[Path], event: Any) -> None:
    """Optional fan-out from record_usage_event when work_dir is marathon-bound."""
    try:
        if work_dir is None:
            return
        key = str(Path(work_dir).resolve())
        with _LOCK:
            session_id = _WORKDIR_BINDINGS.get(key)
        if not session_id:
            return
        data_dir = None
        with _LOCK:
            meta = _ACTIVE_SESSIONS.get(session_id) or {}
            if meta.get("data_dir"):
                data_dir = Path(meta["data_dir"])
        op = getattr(event, "operation", None) or (event.get("operation") if isinstance(event, dict) else "usage")
        provider = getattr(event, "provider", None) or (event.get("provider") if isinstance(event, dict) else "unknown")
        latency = getattr(event, "latency_sec", None)
        if latency is None and isinstance(event, dict):
            latency = event.get("latency_sec")
        retry = getattr(event, "retry_count", 0)
        if isinstance(event, dict):
            retry = event.get("retry_count", 0)
        cache = getattr(event, "cache_hit", False)
        if isinstance(event, dict):
            cache = event.get("cache_hit", False)
        record_api_call(
            session_id,
            provider=str(provider),
            operation=str(op),
            status="OK",
            latency_ms=float(latency or 0) * 1000.0,
            retry_count=int(retry or 0),
            cache_reuse=bool(cache),
            paid=False,
            data_dir=data_dir,
        )
    except Exception:
        return


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

def classify_watchdog(
    *,
    current_state: Optional[str],
    last_event_age_sec: Optional[float],
    interval_sec: int = WATCHDOG_DEFAULT_INTERVAL_SEC,
    progress_seen: bool = False,
    failed: bool = False,
    completed: bool = False,
    provider_pending: bool = False,
    scheduler_waiting: bool = False,
) -> Dict[str, Any]:
    """Deterministic watchdog classification — never assumes silence == stuck."""
    state = str(current_state or "UNKNOWN").upper()
    if completed or state in TERMINAL_SUCCESS:
        return {"classification": "COMPLETED", "confidence": "HIGH", "reason": "terminal_success"}
    if failed or state in TERMINAL_FAILURE:
        return {"classification": "FAILED", "confidence": "HIGH", "reason": "terminal_failure"}
    if state == "UNKNOWN" and last_event_age_sec is None:
        return {"classification": "UNKNOWN", "confidence": "LOW", "reason": "no_evidence"}
    if provider_pending or scheduler_waiting or state in KNOWN_WAIT_STATES:
        return {"classification": "WAITING", "confidence": "MEDIUM", "reason": f"expected_wait:{state}"}
    age = float(last_event_age_sec if last_event_age_sec is not None else 0)
    if progress_seen and age < interval_sec:
        return {"classification": "PROGRESSING", "confidence": "HIGH", "reason": "recent_progress"}
    if age < interval_sec * 0.5:
        return {"classification": "HEALTHY", "confidence": "MEDIUM", "reason": "fresh_events"}
    if age < interval_sec * 2:
        return {"classification": "SLOW", "confidence": "MEDIUM", "reason": "elevated_silence"}
    if age >= interval_sec * 2 and state not in KNOWN_WAIT_STATES:
        return {
            "classification": "STUCK",
            "confidence": "MEDIUM",
            "reason": "zero_progress_beyond_threshold",
            "suspected_component": state or "UNKNOWN",
        }
    return {"classification": "UNKNOWN", "confidence": "LOW", "reason": "insufficient_signal"}


def run_watchdog_check(
    session_id: str,
    *,
    now_monotonic: Optional[float] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found"}
    timeline = read_ledger(session_id, "timeline", data_dir=data_dir)
    failures = read_ledger(session_id, "failures", data_dir=data_dir)
    publish = read_ledger(session_id, "publish", data_dir=data_dir)
    schedule = read_ledger(session_id, "schedule", data_dir=data_dir)

    last = timeline[-1] if timeline else None
    mono_now = float(now_monotonic if now_monotonic is not None else _mono())
    last_age = None
    if last and last.get("monotonic_timestamp") is not None:
        last_age = max(0.0, mono_now - float(last["monotonic_timestamp"]))

    current_state = None
    if last:
        current_state = (last.get("metadata") or {}).get("to_state") or last.get("status")
    if run.get("status") in ("COMPLETED", "FAILED"):
        current_state = run.get("status")

    provider_pending = any(
        str((p.get("metadata") or {}).get("status") or p.get("status") or "").upper() in ("REMOTE_PROCESSING", "UPLOAD_ACCEPTED")
        for p in publish[-5:]
    )
    scheduler_waiting = any(
        str((s.get("metadata") or {}).get("status") or s.get("status") or "").upper() in ("SCHEDULED", "DUE")
        for s in schedule[-5:]
    )
    failed = bool(failures) and str((failures[-1].get("metadata") or {}).get("final_state") or "").upper() in TERMINAL_FAILURE
    completed = str(run.get("status") or "").upper() == "COMPLETED"
    progress_seen = bool(timeline) and last_age is not None and last_age < float(run.get("watchdog_interval_sec") or WATCHDOG_DEFAULT_INTERVAL_SEC)

    clf = classify_watchdog(
        current_state=current_state,
        last_event_age_sec=last_age,
        interval_sec=int(run.get("watchdog_interval_sec") or WATCHDOG_DEFAULT_INTERVAL_SEC),
        progress_seen=progress_seen,
        failed=failed,
        completed=completed,
        provider_pending=provider_pending,
        scheduler_waiting=scheduler_waiting,
    )
    alert = {
        "run_id": run.get("run_id"),
        "current_state": current_state,
        "last_event": last.get("event_type") if last else None,
        "last_progress_evidence": last.get("event_id") if last else None,
        "elapsed_time_sec": last_age,
        "suspected_component": clf.get("suspected_component") or current_state,
        "evidence_references": [last.get("event_id")] if last else [],
        "classification": clf["classification"],
        "confidence": clf["confidence"],
        "recommended_diagnostic_action": _diagnostic_action(clf["classification"]),
        "reason": clf.get("reason"),
        "modifies_production": False,
    }
    stored = record_evidence(
        session_id,
        ledger="watchdog",
        stage="WATCHDOG",
        component="watchdog",
        operation="check",
        event_type="WATCHDOG_CHECK",
        status=clf["classification"],
        metadata=alert,
        data_dir=data_dir,
    )
    return {"ok": True, "alert": alert, "record": stored.get("record")}


def _diagnostic_action(classification: str) -> str:
    return {
        "HEALTHY": "Continue observation",
        "PROGRESSING": "Continue observation",
        "WAITING": "Confirm expected wait (provider/scheduler/approval); do not force retry",
        "SLOW": "Inspect last stage latency and provider ledger",
        "STUCK": "Collect evidence; classify; propose minimal fix — do not auto-modify code",
        "FAILED": "Inspect failure ledger and recovery owner",
        "UNKNOWN": "Gather more authoritative state before acting",
        "COMPLETED": "Generate forensic report",
    }.get(classification, "Collect evidence")


# ---------------------------------------------------------------------------
# Anomaly detection (test findings — not a quality authority)
# ---------------------------------------------------------------------------

def detect_anomalies(session_id: str, *, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    api = read_ledger(session_id, "api", data_dir=data_dir)
    timeline = read_ledger(session_id, "timeline", data_dir=data_dir)
    publish = read_ledger(session_id, "publish", data_dir=data_dir)
    schedule = read_ledger(session_id, "schedule", data_dir=data_dir)
    visual = read_ledger(session_id, "visual", data_dir=data_dir)
    failures = read_ledger(session_id, "failures", data_dir=data_dir)
    run = load_run(session_id, data_dir=data_dir)

    # duplicate provider calls (same provider+operation+scene+beat within 1s mono)
    seen: Dict[Tuple[Any, ...], int] = {}
    for row in api:
        key = (
            row.get("provider"),
            row.get("operation"),
            row.get("scene_id"),
            row.get("beat_id"),
            round(float(row.get("monotonic_timestamp") or 0), 0),
        )
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            findings.append(
                {
                    "rule": "unexpected_duplicate_provider_calls",
                    "severity": "MEDIUM",
                    "detail": {"key": list(key), "count": count},
                }
            )

    # long latency
    for row in api:
        lat = float(row.get("duration_ms") or 0)
        if lat >= 120_000:
            findings.append(
                {
                    "rule": "unusually_long_provider_latency",
                    "severity": "MEDIUM",
                    "detail": {"operation": row.get("operation"), "latency_ms": lat},
                }
            )

    # repeated retries
    for row in api:
        rc = int((row.get("metadata") or {}).get("retry_count") or 0)
        if rc >= 3:
            findings.append(
                {
                    "rule": "repeated_retries",
                    "severity": "HIGH",
                    "detail": {"operation": row.get("operation"), "retry_count": rc},
                }
            )

    # state regression / terminal then execution
    states: List[str] = []
    for row in timeline:
        if row.get("event_type") == "STATE_TRANSITION":
            states.append(str((row.get("metadata") or {}).get("to_state") or row.get("status") or "").upper())
    for i in range(1, len(states)):
        if states[i - 1] in TERMINAL_SUCCESS and states[i] not in TERMINAL_SUCCESS | {"SCHEDULED"}:
            findings.append(
                {
                    "rule": "terminal_state_followed_by_execution",
                    "severity": "HIGH",
                    "detail": {"from": states[i - 1], "to": states[i]},
                }
            )
        if states[i - 1] == "PUBLISHED" and states[i] in ("GENERATING", "RUNNING", "CLAIMED"):
            findings.append(
                {
                    "rule": "state_regression",
                    "severity": "HIGH",
                    "detail": {"from": states[i - 1], "to": states[i]},
                }
            )

    # publish before approval
    pub_statuses = [str((p.get("metadata") or {}).get("status") or p.get("status") or "").upper() for p in publish]
    if "PUBLISHED" in pub_statuses and "APPROVED" not in states and not any("APPROVED" in s for s in states):
        # only flag if timeline never saw APPROVED and publish claims PUBLISHED
        if any(s == "PUBLISHED" for s in pub_statuses):
            findings.append(
                {
                    "rule": "publish_before_approval",
                    "severity": "HIGH",
                    "detail": {"publish_statuses": pub_statuses[-5:], "states": states[-10:]},
                }
            )

    # schedule before publishability (if schedule exists but no publishability/approved)
    if schedule and not any(s in ("APPROVED", "PUBLISHABLE", "READY_TO_UPLOAD") for s in states):
        findings.append(
            {
                "rule": "schedule_before_publishability",
                "severity": "MEDIUM",
                "detail": {"schedule_count": len(schedule)},
            }
        )

    # PUBLISHED without confirmation
    for p in publish:
        st = str((p.get("metadata") or {}).get("status") or p.get("status") or "").upper()
        confirmed = bool((p.get("metadata") or {}).get("authoritative_confirmation"))
        if st == "PUBLISHED" and (p.get("metadata") or {}).get("authoritative_confirmation") is False:
            findings.append(
                {
                    "rule": "published_without_authoritative_confirmation",
                    "severity": "HIGH",
                    "detail": {"event_id": p.get("event_id")},
                }
            )

    # UNKNOWN promoted to success
    for row in timeline + publish:
        meta = row.get("metadata") or {}
        if str(meta.get("from_state") or "").upper() == "UNKNOWN" and str(meta.get("to_state") or "").upper() in TERMINAL_SUCCESS:
            findings.append(
                {
                    "rule": "unknown_promoted_to_success",
                    "severity": "CRITICAL",
                    "detail": meta,
                }
            )

    # cross-customer reference
    owner = str(run.get("login_id") or "")
    for row in timeline + api + publish:
        other = (row.get("metadata") or {}).get("login_id")
        if other and owner and str(other) != owner:
            findings.append(
                {
                    "rule": "cross_customer_reference",
                    "severity": "CRITICAL",
                    "detail": {"owner": owner, "foreign": other},
                }
            )

    # visual duration / resolution / fps mismatches when both sides present
    for v in visual:
        meta = v.get("metadata") or {}
        exp = meta.get("expected_duration")
        act = meta.get("actual_duration")
        if exp is not None and act is not None:
            try:
                if abs(float(exp) - float(act)) > max(1.0, float(exp) * 0.25):
                    findings.append(
                        {
                            "rule": "artifact_duration_mismatch",
                            "severity": "MEDIUM",
                            "detail": {"expected": exp, "actual": act, "asset_id": meta.get("asset_id")},
                        }
                    )
            except Exception:
                pass
        if meta.get("unexpected_resolution"):
            findings.append({"rule": "unexpected_resolution", "severity": "LOW", "detail": meta})
        if meta.get("unexpected_fps"):
            findings.append({"rule": "unexpected_fps", "severity": "LOW", "detail": meta})
        if meta.get("missing_expected_artifact"):
            findings.append({"rule": "missing_expected_artifact", "severity": "HIGH", "detail": meta})

    # prompt/entity mismatch flag when provided
    for p in read_ledger(session_id, "prompts", data_dir=data_dir):
        meta = p.get("metadata") or {}
        if meta.get("entity_mismatch") is True:
            findings.append({"rule": "prompt_entity_mismatch", "severity": "MEDIUM", "detail": {"prompt_id": meta.get("prompt_id")}})

    # zero-progress from failures with no recovery
    if failures and not any((f.get("metadata") or {}).get("recovery_action") for f in failures):
        if len(failures) >= 2:
            findings.append(
                {
                    "rule": "zero_progress_interval",
                    "severity": "MEDIUM",
                    "detail": {"failure_count": len(failures)},
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Metrics (evidence-backed only)
# ---------------------------------------------------------------------------

def compute_metrics(session_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    api = read_ledger(session_id, "api", data_dir=data_dir)
    timeline = read_ledger(session_id, "timeline", data_dir=data_dir)
    visual = read_ledger(session_id, "visual", data_dir=data_dir)
    audio = read_ledger(session_id, "audio", data_dir=data_dir)
    subs = read_ledger(session_id, "subtitles", data_dir=data_dir)
    repair = read_ledger(session_id, "repair", data_dir=data_dir)
    failures = read_ledger(session_id, "failures", data_dir=data_dir)
    watchdog = read_ledger(session_id, "watchdog", data_dir=data_dir)
    prompts = read_ledger(session_id, "prompts", data_dir=data_dir)

    latencies = [float(r.get("duration_ms") or 0) for r in api if r.get("duration_ms") is not None]
    p50 = p95 = None
    if len(latencies) >= 2:
        try:
            p50 = statistics.median(latencies)
            p95 = sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)]
        except Exception:
            p50 = p95 = None
    elif len(latencies) == 1:
        p50 = latencies[0]

    retries = sum(int((r.get("metadata") or {}).get("retry_count") or 0) for r in api)
    cache_hits = sum(1 for r in api if (r.get("metadata") or {}).get("cache_reuse"))
    paid = sum(1 for r in api if (r.get("metadata") or {}).get("paid"))
    stuck = sum(1 for w in watchdog if str(w.get("status") or "").upper() == "STUCK")
    unknown = sum(1 for r in timeline + visual + audio if str(r.get("status") or "").upper() == "UNKNOWN")

    stage_runtime: Dict[str, float] = {}
    for r in timeline:
        st = str(r.get("stage") or "UNKNOWN")
        stage_runtime[st] = stage_runtime.get(st, 0.0) + float(r.get("duration_ms") or 0)

    total_runtime = None
    if run.get("start_time") and run.get("end_time"):
        try:
            # approximate from ISO Z
            total_runtime = "computed_from_identity"
        except Exception:
            total_runtime = None

    image_count = sum(1 for v in visual if str((v.get("metadata") or {}).get("actual_artifact_type") or "").lower() in ("image", "img"))
    video_count = sum(1 for v in visual if str((v.get("metadata") or {}).get("actual_artifact_type") or "").lower() in ("video", "clip"))

    return {
        "total_runtime_note": total_runtime,
        "start_time": run.get("start_time"),
        "end_time": run.get("end_time"),
        "per_stage_runtime_ms": stage_runtime,
        "provider_latency_ms_samples": len(latencies),
        "provider_latency_p50_ms": p50,
        "provider_latency_p95_ms": p95,
        "api_call_count": len(api),
        "retry_count": retries,
        "repair_count": len(repair),
        "cache_reuse_count": cache_hits,
        "new_artifact_count": len(visual) + len(audio),
        "image_count": image_count,
        "video_clip_count": video_count,
        "audio_count": len(audio),
        "subtitle_count": len(subs),
        "prompt_count": len(prompts),
        "failure_count": len(failures),
        "recovery_count": sum(1 for f in failures if (f.get("metadata") or {}).get("recovery_action")),
        "watchdog_count": len(watchdog),
        "stuck_count": stuck,
        "unknown_count": unknown,
        "paid_call_count": paid,
        "fabricated": False,
    }


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_marathon_report(
    session_id: str,
    *,
    data_dir: Optional[Path] = None,
    docs_root: Optional[Path] = None,
) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found"}
    metrics = compute_metrics(session_id, data_dir=data_dir)
    anomalies = detect_anomalies(session_id, data_dir=data_dir)
    timeline = read_ledger(session_id, "timeline", data_dir=data_dir)
    api = read_ledger(session_id, "api", data_dir=data_dir)
    prompts = read_ledger(session_id, "prompts", data_dir=data_dir)
    scripts = read_ledger(session_id, "scripts", data_dir=data_dir)
    beats = read_ledger(session_id, "beats", data_dir=data_dir)
    visual = read_ledger(session_id, "visual", data_dir=data_dir)
    audio = read_ledger(session_id, "audio", data_dir=data_dir)
    subs = read_ledger(session_id, "subtitles", data_dir=data_dir)
    quality = read_ledger(session_id, "quality", data_dir=data_dir)
    repair = read_ledger(session_id, "repair", data_dir=data_dir)
    render = read_ledger(session_id, "render", data_dir=data_dir)
    publish = read_ledger(session_id, "publish", data_dir=data_dir)
    schedule = read_ledger(session_id, "schedule", data_dir=data_dir)
    watchdog = read_ledger(session_id, "watchdog", data_dir=data_dir)
    failures = read_ledger(session_id, "failures", data_dir=data_dir)

    slowest = sorted(api, key=lambda r: float(r.get("duration_ms") or 0), reverse=True)[:10]
    severity_rank = sorted(anomalies, key=lambda a: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(a.get("severity"), 9))

    verdict = "PASS"
    if any(a.get("severity") == "CRITICAL" for a in anomalies):
        verdict = "FAIL"
    elif any(a.get("severity") == "HIGH" for a in anomalies):
        verdict = "PASS_WITH_LIMITATION"
    elif str(run.get("status") or "").upper() not in ("COMPLETED", "CREATED", "BOUND"):
        verdict = "PASS_WITH_LIMITATION"

    lines = [
        f"# Marathon Forensic Report — `{run.get('run_id')}`",
        "",
        f"**Schema:** {SCHEMA_VERSION}",
        f"**Generated:** {_now_iso()}",
        f"**Paid API calls (recorded):** {metrics.get('paid_call_count', 0)}",
        "",
        "## 1. Executive Summary",
        f"- Session: `{session_id}`",
        f"- Video type: **{run.get('video_type')}**",
        f"- Final status: **{run.get('status')}**",
        f"- Anomaly count: {len(anomalies)}",
        f"- Verdict: **{verdict}**",
        "",
        "## 2. Run Identity",
        "```json",
        json.dumps(redact(run), indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "## 3. Environment",
        f"- environment: `{run.get('environment')}`",
        f"- application_version: `{run.get('application_version')}`",
        f"- source_release_revision: `{run.get('source_release_revision')}`",
        "",
        "## 4. Niche",
        f"- `{run.get('niche')}`",
        "",
        "## 5. Long/Short Type",
        f"- `{run.get('video_type')}` / test_case `{run.get('test_case_id')}`",
        "",
        "## 6. Start/End",
        f"- start: `{run.get('start_time')}`",
        f"- end: `{run.get('end_time')}`",
        "",
        "## 7. Total Runtime",
        f"- note: `{metrics.get('total_runtime_note')}`",
        f"- per-stage ms: `{metrics.get('per_stage_runtime_ms')}`",
        "",
        "## 8. Final State",
        f"- `{run.get('status')}`",
        "",
        "## 9. Full Timeline",
        f"- events: {len(timeline)}",
        _md_table(
            ["timestamp", "event_type", "status", "stage"],
            [[r.get("timestamp"), r.get("event_type"), r.get("status"), r.get("stage")] for r in timeline[-50:]],
        ),
        "",
        "## 10. API Call Ledger",
        f"- count: {len(api)}",
        _md_table(
            ["timestamp", "provider", "operation", "latency_ms", "status", "retry"],
            [
                [
                    r.get("timestamp"),
                    r.get("provider"),
                    r.get("operation"),
                    r.get("duration_ms"),
                    r.get("status"),
                    (r.get("metadata") or {}).get("retry_count"),
                ]
                for r in api
            ],
        ),
        "",
        "## 11. Prompt Ledger",
        f"- count: {len(prompts)}",
        "",
        "## 12. Script/Beat Analysis",
        f"- scripts: {len(scripts)}; beats: {len(beats)}",
        "",
        "## 13. Visual Asset Ledger",
        f"- count: {len(visual)}",
        "",
        "## 14. Audio Ledger",
        f"- count: {len(audio)}",
        "",
        "## 15. Subtitle/Localization Ledger",
        f"- count: {len(subs)}",
        "",
        "## 16. Quality/Verification",
        f"- count: {len(quality)}",
        "",
        "## 17. Repair Ledger",
        f"- count: {len(repair)}",
        "",
        "## 18. Render/FFmpeg",
        f"- count: {len(render)}",
        "",
        "## 19. Publishing",
        f"- count: {len(publish)}",
        "",
        "## 20. Scheduling",
        f"- count: {len(schedule)}",
        "",
        "## 21. Watchdog Checks",
        f"- count: {len(watchdog)}",
        "",
        "## 22. Failures",
        f"- count: {len(failures)}",
        "",
        "## 23. Retries",
        f"- retry_count: {metrics.get('retry_count')}",
        "",
        "## 24. Recovery",
        f"- recovery_count: {metrics.get('recovery_count')}",
        "",
        "## 25. Bottlenecks",
        f"- slowest operations sampled: {len(slowest)}",
        "",
        "## 26. Slowest Operations",
        _md_table(
            ["provider", "operation", "latency_ms"],
            [[s.get("provider"), s.get("operation"), s.get("duration_ms")] for s in slowest],
        ),
        "",
        "## 27. Duplicate/Unexpected Calls",
        f"- duplicate findings: {sum(1 for a in anomalies if a.get('rule') == 'unexpected_duplicate_provider_calls')}",
        "",
        "## 28. UNKNOWN States",
        f"- unknown_count: {metrics.get('unknown_count')}",
        "",
        "## 29. Provider Usage",
        f"- api_call_count: {metrics.get('api_call_count')}",
        "",
        "## 30. Cost Evidence",
        "- monetary cost: NOT_DETERMINABLE (harness does not invent cost)",
        f"- paid_call_count: {metrics.get('paid_call_count')}",
        "",
        "## 31. Artifact Statistics",
        f"- images: {metrics.get('image_count')}; video clips: {metrics.get('video_clip_count')}; audio: {metrics.get('audio_count')}; subtitles: {metrics.get('subtitle_count')}",
        "",
        "## 32. Duration Statistics",
        f"- p50_ms: {metrics.get('provider_latency_p50_ms')}; p95_ms: {metrics.get('provider_latency_p95_ms')}",
        "",
        "## 33. Recommendations",
        "- Use WAITING classification for legitimate provider/scheduler pending states.",
        "- Do not promote UNKNOWN to success.",
        "- Apply only minimal safe fixes via intervention contract (record-only in C10).",
        "",
        "## 34. Severity-ranked Findings",
    ]
    if severity_rank:
        lines.extend([f"- **{a.get('severity')}** `{a.get('rule')}` — {a.get('detail')}" for a in severity_rank])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## 35. Final Verdict",
            f"**{verdict}**",
            "",
            "---",
            "C10 observation harness — not a production authority.",
        ]
    )
    body = "\n".join(lines)
    root = Path(docs_root) if docs_root else Path(__file__).resolve().parents[1] / "docs" / "marathon" / "runs"
    out_dir = root / str(run.get("run_id"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "MARATHON_REPORT.md"
    out_path.write_text(body, encoding="utf-8")
    # also copy summary into session
    (session_dir(session_id, data_dir=data_dir) / "MARATHON_REPORT.md").write_text(body, encoding="utf-8")
    return {"ok": True, "path": str(out_path), "verdict": verdict, "anomaly_count": len(anomalies), "metrics": metrics}


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_(empty)_"
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join("" if c is None else str(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


# ---------------------------------------------------------------------------
# Isolation helpers
# ---------------------------------------------------------------------------

def assert_session_owner(session_id: str, login_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    run = load_run(session_id, data_dir=data_dir)
    if not run:
        return {"ok": False, "error": "session_not_found", "error_code": "NOT_AVAILABLE"}
    if str(run.get("login_id")) != str(login_id):
        return {"ok": False, "error": "access_denied", "error_code": "OWNERSHIP_FAILURE"}
    return {"ok": True}


def project_session_for_customer(session_id: str, login_id: str, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    gate = assert_session_owner(session_id, login_id, data_dir=data_dir)
    if not gate.get("ok"):
        return gate
    run = load_run(session_id, data_dir=data_dir)
    return {"ok": True, "run": redact(run), "owns_production": False}


# ---------------------------------------------------------------------------
# Offline smoke (synthetic LONG + SHORT — no providers)
# ---------------------------------------------------------------------------

def run_offline_smoke(*, data_dir: Optional[Path] = None, docs_root: Optional[Path] = None) -> Dict[str, Any]:
    """Synthetic evidence capture only. No niche Marathon. No paid APIs."""
    results = []
    for case_id, vtype in (("MARATHON_LONG", "LONG"), ("MARATHON_SHORT", "SHORT")):
        sess = create_marathon_session(
            login_id="smoke_customer",
            test_case_id=case_id,
            video_type=vtype,
            niche="synthetic_offline",
            environment="c10_offline_smoke",
            data_dir=data_dir,
        )
        sid = sess["marathon_session_id"]
        record_state_transition(sid, from_state="QUEUED", to_state="CLAIMED", job_id=1, data_dir=data_dir)
        record_state_transition(sid, from_state="CLAIMED", to_state="RUNNING", job_id=1, data_dir=data_dir)
        record_api_call(sid, provider="mock", operation="visual.generate", status="OK", latency_ms=120.0, scene_id="s1", beat_id="b1", data_dir=data_dir)
        record_prompt(sid, provider="mock", operation="visual", prompt_text="A calm desk scene", scene_id="s1", beat_id="b1", data_dir=data_dir)
        record_script_beats(
            sid,
            topic="synthetic",
            research_id="r1",
            script_id="sc1",
            dialogues=[{"dialogue_id": "d1", "text": "Hello"}],
            visual_beats=[{"beat_id": "b1", "scene_id": "s1", "camera": "wide"}],
            scenes=[{"scene_id": "s1", "location": "studio"}],
            data_dir=data_dir,
        )
        record_visual_artifact(
            sid,
            {
                "asset_id": "va1",
                "scene_id": "s1",
                "beat_id": "b1",
                "provider": "mock",
                "requested_mode": "image",
                "actual_artifact_type": "image",
                "verification_status": "UNKNOWN",
                "quality_status": "UNKNOWN",
                "reuse": False,
            },
            data_dir=data_dir,
        )
        record_audio_artifact(
            sid,
            {
                "audio_id": "a1",
                "dialogue_id": "d1",
                "scene_id": "s1",
                "provider": "mock_tts",
                "verification_state": "UNKNOWN",
                "sample_rate": 24000,
            },
            data_dir=data_dir,
        )
        record_subtitle(
            sid,
            {"dialogue_id": "d1", "locale": "en", "text_hash": _hash_text("Hello")[:16], "validation_status": "OK"},
            data_dir=data_dir,
        )
        record_quality(sid, {"operation": "publishability", "status": "UNKNOWN"}, data_dir=data_dir)
        record_repair(
            sid,
            {"repair_id": "rp1", "scene_id": "s1", "failure_reason": "synthetic", "post_repair_status": "OK", "repair_latency_ms": 10},
            data_dir=data_dir,
        )
        record_render(
            sid,
            {"render_request_id": "rr1", "status": "OK", "return_code": 0, "ffmpeg_version": "bundled", "duration_ms": 50},
            data_dir=data_dir,
        )
        record_publish(
            sid,
            {"operation": "upload", "status": "UPLOAD_ACCEPTED", "job_id": 1, "authoritative_confirmation": False},
            data_dir=data_dir,
        )
        record_schedule(
            sid,
            {"operation": "create", "status": "SCHEDULED", "timezone": "UTC", "job_id": 1},
            data_dir=data_dir,
        )
        wd = run_watchdog_check(sid, data_dir=data_dir)
        record_intervention(sid, step="DETECT", classification="WAITING", proposal="none", applied=False, data_dir=data_dir)
        finish_session(sid, status="COMPLETED", data_dir=data_dir)
        report = generate_marathon_report(sid, data_dir=data_dir, docs_root=docs_root)
        results.append(
            {
                "session_id": sid,
                "run_id": sess["run_id"],
                "video_type": vtype,
                "watchdog": wd.get("alert", {}).get("classification"),
                "report_ok": report.get("ok"),
                "report_path": report.get("path"),
                "paid_api_calls": 0,
            }
        )
    return {"ok": True, "cases": results, "paid_api_calls": 0, "external_provider_calls": 0, "executed_real_marathon": False}


def detect_duplicate_engines(source: str) -> List[str]:
    """Static guard used by tests — flags accidental second engines in new code text."""
    hits = []
    patterns = {
        "second_idempotency_store": r"class\s+IdempotencyStore\b",
        "second_scheduler": r"class\s+SchedulerService\b",
        "second_job_queue": r"def\s+claim_next_job\b",
        "second_publish_provider": r"class\s+YouTubeDataApiProvider\b",
    }
    for name, pat in patterns.items():
        if re.search(pat, source or ""):
            hits.append(name)
    return hits
