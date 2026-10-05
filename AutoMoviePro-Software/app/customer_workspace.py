"""C06-A — Customer Production Workspace projection (derive-only).

Does NOT own job lifecycle, quality, publishability, auth, or generation.
Derives UI workflow stages from existing C01/C02/C04 + live_activity authorities.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.customer_job import (
    sanitize_customer_error,
    is_terminal_state,
)

WORKFLOW_STAGES = (
    "TOPIC",
    "RESEARCH",
    "SCRIPT",
    "PLAN",
    "GENERATE",
    "QUALITY",
    "PREVIEW",
    "APPROVAL",
)

STAGE_STATUSES = (
    "NOT_STARTED",
    "READY",
    "RUNNING",
    "BLOCKED",
    "FAILED",
    "COMPLETED",
)

APPROVAL_STATES = (
    "NOT_READY",
    "PENDING",  # C06-F canonical — replaces READY_FOR_REVIEW for approval decision plane
    "READY_FOR_REVIEW",  # legacy alias accepted in projections
    "APPROVED",
    "REJECTED",
)

ACTION_KINDS = (
    "CUSTOMER_ACTION_REQUIRED",
    "SYSTEM_RUNNING",
    "SYSTEM_BLOCKED",
    "SYSTEM_FAILED",
    "COMPLETED",
)

# Live phase → which workflow stage is RUNNING (honest coarse map; no fake %)
PHASE_TO_WORKFLOW: Dict[str, str] = {
    "starting": "GENERATE",
    "generate": "TOPIC",
    "generate_short": "TOPIC",
    "generate_long": "TOPIC",
    "director": "RESEARCH",
    "humanize": "SCRIPT",
    "scenes": "PLAN",
    "scene": "PLAN",
    "tts": "GENERATE",
    "visual": "GENERATE",
    "localize": "QUALITY",
    "compose": "GENERATE",
    "package": "QUALITY",
    "upload_check": "QUALITY",
}

QUALITY_DIMENSIONS = (
    "Technical",
    "Creative",
    "Continuity",
    "Audio",
    "Localization",
    "Multimodal",
    "Artifact",
    "Rendering",
    "Publishability",
)


def _empty_stage(name: str, status: str = "NOT_STARTED", **extra: Any) -> Dict[str, Any]:
    return {
        "stage": name,
        "status": status,
        "started_at": extra.get("started_at"),
        "completed_at": extra.get("completed_at"),
        "blocked_reason": extra.get("blocked_reason"),
        "error_code": extra.get("error_code"),
        "action_required": extra.get("action_required"),
        "progress": extra.get("progress"),  # only when truthful (e.g. scene n/m)
    }


def _normalize_verdict(raw: Any) -> str:
    """Map existing truth → PASS|FAIL|BLOCKED|UNKNOWN|NOT_RUN. Never promote UNKNOWN→PASS."""
    if raw is None or raw == "":
        return "NOT_RUN"
    s = str(raw).strip().upper()
    if s in ("PASS", "PASSED", "OK", "PUBLISHABLE", "TRUE", "1"):
        return "PASS"
    if s in ("FAIL", "FAILED", "FALSE", "0", "REJECTED"):
        return "FAIL"
    if s in ("BLOCKED", "BLOCK"):
        return "BLOCKED"
    if s in ("UNKNOWN", "UNAVAILABLE", "OBSERVED_UNKNOWN"):
        return "UNKNOWN"
    if s in ("NOT_RUN", "NOTRUN", "PENDING", "N/A", "NA"):
        return "NOT_RUN"
    # Unrecognized ≠ PASS
    if "UNKNOWN" in s:
        return "UNKNOWN"
    if "BLOCK" in s:
        return "BLOCKED"
    if "FAIL" in s or "ERROR" in s:
        return "FAIL"
    if "PASS" in s or "PUBLISH" in s:
        return "PASS"
    return "UNKNOWN"


def build_project_header(
    *,
    channel: Optional[Dict[str, Any]],
    job: Optional[Dict[str, Any]],
    login_id: str,
) -> Dict[str, Any]:
    ch = channel or {}
    j = job or {}
    project_id = f"ch{ch.get('id') or 0}-job{j.get('job_id') or 0}"
    return {
        "project_id": project_id,
        "owner_login_id": login_id,
        "channel_id": ch.get("id") or j.get("channel_id"),
        "title": j.get("title") or ch.get("youtube_name") or ch.get("niche") or "Untitled production",
        "language": j.get("lang_code") or _channel_language(ch),
        "format": j.get("request_type") or "short",
        "duration": j.get("duration_sec"),
        "created_at": j.get("created_at"),
        "updated_at": j.get("updated_at"),
        "current_status": j.get("state") if j else "NO_JOB",
    }


def _channel_language(ch: Dict[str, Any]) -> str:
    raw = ch.get("languages_json") or ch.get("languages") or ""
    if isinstance(raw, list) and raw:
        return str(raw[0])
    if isinstance(raw, str) and raw.strip().startswith("["):
        try:
            arr = json.loads(raw)
            if arr:
                return str(arr[0])
        except Exception:
            pass
    return str(ch.get("lang_code") or "en")


def derive_workflow_stages(
    *,
    job: Optional[Dict[str, Any]],
    live: Optional[Dict[str, Any]] = None,
    foundation: Optional[Dict[str, Any]] = None,
    access: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Derive TOPIC→APPROVAL stages from existing authorities. No fabricated %.

    Granular progress only when live exposes scene/scene_total.
    """
    foundation = foundation or {}
    access = access or {}
    live = live or {}
    stages = {name: _empty_stage(name) for name in WORKFLOW_STAGES}

    generate_allowed = bool(foundation.get("generate_allowed"))
    access_allowed = access.get("production_allowed")
    if access_allowed is None:
        access_allowed = access.get("allowed", generate_allowed)

    block_reason = (
        access.get("block_reason")
        or (foundation.get("generate_block_reasons") or [None])[0]
        or None
    )

    if not access_allowed or not generate_allowed:
        for name in WORKFLOW_STAGES:
            stages[name] = _empty_stage(
                name,
                "BLOCKED" if name == "TOPIC" else "NOT_STARTED",
                blocked_reason=str(block_reason or "production_not_ready"),
                error_code="configuration_blocked" if name == "TOPIC" else None,
                action_required="Fix configuration / readiness, then Generate",
            )
        if job and str(job.get("state") or "") in ("FAILED", "INTERRUPTED", "CANCELLED"):
            # still show failure on GENERATE if a job exists
            stages["GENERATE"] = _empty_stage(
                "GENERATE",
                "FAILED",
                error_code=job.get("error_class"),
                blocked_reason=job.get("error_summary"),
                action_required=job.get("next_action"),
                completed_at=job.get("failed_at"),
            )
        return [stages[n] for n in WORKFLOW_STAGES]

    # Ready to produce but no job yet
    if not job:
        stages["TOPIC"] = _empty_stage(
            "TOPIC",
            "READY",
            action_required="Start Generate when ready",
        )
        return [stages[n] for n in WORKFLOW_STAGES]

    state = str(job.get("state") or "").upper()
    started = job.get("started_at") or job.get("created_at")
    updated = job.get("updated_at")
    failed_at = job.get("failed_at")
    completed_at = job.get("completed_at")

    progress = None
    if live.get("active") and str(live.get("db_job_id") or "") == str(job.get("job_id")):
        if live.get("scene") is not None:
            total = live.get("scene_total")
            progress = {
                "scene": live.get("scene"),
                "scene_total": total,
                "label": f"Scene {live.get('scene')}"
                + (f" / {total}" if total is not None else ""),
            }

    def mark_completed_through(last: str) -> None:
        hit = False
        for name in WORKFLOW_STAGES:
            if not hit:
                stages[name] = _empty_stage(
                    name, "COMPLETED", started_at=started, completed_at=updated
                )
            if name == last:
                hit = True

    def mark_running(name: str) -> None:
        # prior stages completed
        for n in WORKFLOW_STAGES:
            if n == name:
                break
            stages[n] = _empty_stage(n, "COMPLETED", started_at=started, completed_at=updated)
        stages[name] = _empty_stage(
            name,
            "RUNNING",
            started_at=started,
            progress=progress if name == "GENERATE" else None,
        )
        # later remain NOT_STARTED

    if state in ("QUEUED", "STARTING", "PREPARING", "RECOVERING"):
        stages["TOPIC"] = _empty_stage("TOPIC", "COMPLETED", started_at=started, completed_at=updated)
        stages["GENERATE"] = _empty_stage("GENERATE", "RUNNING", started_at=started)
    elif state in ("GENERATING", "VALIDATING", "REPAIRING", "RENDERING", "PREPARING_REVIEW"):
        phase = ""
        if live.get("active") and str(live.get("db_job_id") or "") == str(job.get("job_id")):
            phase = str(live.get("phase") or "").lower()
        running = PHASE_TO_WORKFLOW.get(phase, "GENERATE")
        if state in ("VALIDATING",) and not phase:
            running = "QUALITY"
        if state in ("RENDERING", "PREPARING_REVIEW") and not phase:
            running = "GENERATE"
        mark_running(running)
    elif state == "READY_FOR_REVIEW":
        mark_completed_through("QUALITY")
        stages["PREVIEW"] = _empty_stage(
            "PREVIEW",
            "COMPLETED" if job.get("artifact_available") else "READY",
            started_at=started,
            completed_at=completed_at,
            action_required=None if job.get("artifact_available") else "Preview not available yet",
        )
        approval = str((job.get("approval") or {}).get("state") or job.get("approval_state") or "READY_FOR_REVIEW")
        if approval == "APPROVED":
            stages["APPROVAL"] = _empty_stage(
                "APPROVAL", "COMPLETED", started_at=started, completed_at=updated
            )
        elif approval == "REJECTED":
            stages["APPROVAL"] = _empty_stage(
                "APPROVAL",
                "FAILED",
                started_at=started,
                completed_at=updated,
                action_required="Customer rejected — revise via new Generate",
                error_code="customer_rejected",
            )
        else:
            stages["APPROVAL"] = _empty_stage(
                "APPROVAL",
                "READY",
                started_at=started,
                action_required="Review and approve or reject (does not publish)",
            )
    elif state in ("FAILED", "INTERRUPTED", "CANCELLED"):
        # Fail at GENERATE/QUALITY honestly
        mark_running("GENERATE")
        stages["GENERATE"] = _empty_stage(
            "GENERATE",
            "FAILED",
            started_at=started,
            completed_at=failed_at,
            blocked_reason=job.get("error_summary"),
            error_code=job.get("error_class"),
            action_required=job.get("next_action"),
        )
        for n in ("QUALITY", "PREVIEW", "APPROVAL"):
            stages[n] = _empty_stage(n, "NOT_STARTED")
    elif state == "COMPLETED":
        mark_completed_through("APPROVAL")
    else:
        stages["TOPIC"] = _empty_stage("TOPIC", "READY")

    return [stages[n] for n in WORKFLOW_STAGES]


def derive_action_model(
    *,
    stages: List[Dict[str, Any]],
    job: Optional[Dict[str, Any]],
    access: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    access = access or {}
    if access.get("production_allowed") is False or access.get("allowed") is False:
        return {
            "kind": "CUSTOMER_ACTION_REQUIRED",
            "stage": "TOPIC",
            "reason": access.get("message") or access.get("block_reason") or "Configuration required",
            "error_code": access.get("block_reason") or "configuration_blocked",
            "recommended_action": "Complete channel configuration and readiness",
        }
    if job and str(job.get("state") or "") in ("FAILED", "INTERRUPTED"):
        return {
            "kind": "SYSTEM_FAILED",
            "stage": "GENERATE",
            "reason": job.get("error_summary") or "Generation failed",
            "error_code": job.get("error_class"),
            "recommended_action": job.get("next_action") or "Start a new Generate after fixing the cause",
        }
    for st in stages:
        if st.get("status") == "BLOCKED":
            return {
                "kind": "SYSTEM_BLOCKED",
                "stage": st.get("stage"),
                "reason": st.get("blocked_reason") or "Blocked",
                "error_code": st.get("error_code"),
                "recommended_action": st.get("action_required"),
            }
        if st.get("status") == "RUNNING":
            return {
                "kind": "SYSTEM_RUNNING",
                "stage": st.get("stage"),
                "reason": "Production in progress",
                "error_code": None,
                "recommended_action": "Wait — do not double-start Generate",
                "progress": st.get("progress"),
            }
        if st.get("stage") == "APPROVAL" and st.get("status") == "READY":
            return {
                "kind": "CUSTOMER_ACTION_REQUIRED",
                "stage": "APPROVAL",
                "reason": "Ready for customer review",
                "error_code": None,
                "recommended_action": "Approve or reject (does not publish)",
            }
        if st.get("stage") == "TOPIC" and st.get("status") == "READY" and not job:
            return {
                "kind": "CUSTOMER_ACTION_REQUIRED",
                "stage": "TOPIC",
                "reason": "Ready to generate",
                "error_code": None,
                "recommended_action": "Click Generate Short or Generate Long",
            }
    if job and str(job.get("state") or "") == "READY_FOR_REVIEW":
        approval = str((job.get("approval") or {}).get("state") or job.get("approval_state") or "")
        if approval == "APPROVED":
            return {
                "kind": "COMPLETED",
                "stage": "APPROVAL",
                "reason": "Customer approved for review — not published",
                "error_code": None,
                "recommended_action": "Publishing is a later phase",
            }
    return {
        "kind": "COMPLETED" if (job and is_terminal_state(str(job.get("state") or ""))) else "CUSTOMER_ACTION_REQUIRED",
        "stage": None,
        "reason": "Idle",
        "error_code": None,
        "recommended_action": "Select a job or Generate",
    }


def project_quality_panel(
    job: Optional[Dict[str, Any]],
    *,
    sidecar: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Read-only quality projection. UNKNOWN never displayed as PASS."""
    dims: Dict[str, str] = {d: "NOT_RUN" for d in QUALITY_DIMENSIONS}
    notes: List[str] = []
    if not job:
        return {
            "dimensions": [{"name": k, "status": v} for k, v in dims.items()],
            "publishability": "NOT_RUN",
            "note": "No job selected",
            "unknown_is_not_pass": True,
        }

    quality = job.get("quality") if isinstance(job.get("quality"), dict) else {}
    sidecar = sidecar or {}

    # Publishability from authoritative customer projection
    if job.get("publishable") is True:
        dims["Publishability"] = "PASS"
    elif job.get("state") in ("FAILED", "INTERRUPTED", "CANCELLED"):
        dims["Publishability"] = "FAIL" if "publishability" in str(job.get("error_summary") or "").lower() or "quality" in str(job.get("error_class") or "") else "BLOCKED"
    elif job.get("state") == "READY_FOR_REVIEW":
        dims["Publishability"] = "PASS" if job.get("publishable") else "UNKNOWN"
    elif not is_terminal_state(str(job.get("state") or "")):
        dims["Publishability"] = "NOT_RUN"
    else:
        dims["Publishability"] = "UNKNOWN"

    planes = job.get("result_planes") or {}
    verification = job.get("verification") or {}

    # Technical / Artifact / Rendering — file existence alone is never PASS
    if planes.get("technically_verified") is True and job.get("publishable"):
        dims["Technical"] = "PASS"
        dims["Artifact"] = "PASS"
        dims["Rendering"] = "PASS"
    elif planes.get("file_exists") and not job.get("publishable"):
        dims["Technical"] = "UNKNOWN"
        dims["Artifact"] = "UNKNOWN"
        dims["Rendering"] = "UNKNOWN"
        notes.append("file_exists_without_publishability_is_UNKNOWN")
    elif job.get("state") in ("FAILED",) and job.get("error_class") == "rendering_failure":
        dims["Rendering"] = "FAIL"
        dims["Technical"] = "FAIL"

    # Creative from quality_summary if present
    if isinstance(quality, dict):
        if "creative_verdict" in quality:
            dims["Creative"] = _normalize_verdict(quality.get("creative_verdict"))
        if "continuity_verdict" in quality:
            dims["Continuity"] = _normalize_verdict(quality.get("continuity_verdict"))
        if "audio_verdict" in quality:
            dims["Audio"] = _normalize_verdict(quality.get("audio_verdict"))
        if "localization_verdict" in quality:
            dims["Localization"] = _normalize_verdict(quality.get("localization_verdict"))
        if "multimodal_verdict" in quality:
            dims["Multimodal"] = _normalize_verdict(quality.get("multimodal_verdict"))
        if quality.get("note"):
            notes.append(sanitize_customer_error(str(quality.get("note")), 160))

    # Sidecar gates (optional, already owned path)
    for key, dim in (
        ("creative", "Creative"),
        ("continuity", "Continuity"),
        ("audio", "Audio"),
        ("localization", "Localization"),
        ("multimodal", "Multimodal"),
        ("artifact", "Artifact"),
        ("rendering", "Rendering"),
        ("publishability", "Publishability"),
        ("technical", "Technical"),
    ):
        if key in sidecar:
            dims[dim] = _normalize_verdict(sidecar.get(key))

    # P04 honesty: multimodal stays UNKNOWN unless explicit observed pass
    if dims["Multimodal"] == "PASS" and str(sidecar.get("multimodal_source") or "").upper() in (
        "",
        "INFERRED",
        "METADATA",
    ):
        # Do not invent multimodal PASS from metadata alone
        if not sidecar.get("vlm_observed") and not sidecar.get("asr_observed"):
            dims["Multimodal"] = "UNKNOWN"
            notes.append("multimodal_UNKNOWN_without_VLM_ASR")

    # Final safety: never leave a string that looks like pass for unknown
    for k, v in list(dims.items()):
        if v not in ("PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_RUN"):
            dims[k] = "UNKNOWN"

    return {
        "dimensions": [{"name": k, "status": dims[k]} for k in QUALITY_DIMENSIONS],
        "publishability": dims["Publishability"],
        "note": "; ".join(notes) if notes else verification.get("note"),
        "unknown_is_not_pass": True,
    }


def project_preview(job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not job:
        return {
            "available": False,
            "status": "PREVIEW_NOT_AVAILABLE_YET",
            "message": "PREVIEW NOT AVAILABLE YET",
            "path": None,
            "verification_status": "UNKNOWN",
            "quality_status": "UNKNOWN",
            "publishability_status": "NOT_PUBLISHABLE",
            "ready_to_upload": False,
            "note": "Preview available != VERIFIED != PUBLISHABLE != APPROVED != PUBLISHED",
        }
    path = job.get("artifact_path") or None
    exists = bool(path) and os.path.isfile(str(path))
    planes = job.get("result_planes") or {}
    qs = job.get("quality_summary") if isinstance(job.get("quality_summary"), dict) else {}
    verification = "UNKNOWN"
    if qs.get("artifact_verification"):
        verification = str(qs.get("artifact_verification")).upper()
    elif qs.get("verified") is True or planes.get("technically_verified"):
        verification = "VERIFIED"
    publishable = bool(job.get("publishable") or qs.get("publishable"))
    ready = bool(planes.get("ready_to_upload")) or str(job.get("state") or "") == "READY_FOR_REVIEW"
    base = {
        "job_id": job.get("job_id"),
        "plan_id": job.get("production_plan_id") or job.get("plan_id"),
        "plan_revision": job.get("production_plan_revision") or job.get("plan_revision"),
        "revision_id": job.get("revision_id"),
        "verification_status": verification,
        "quality_status": (
            "PASS"
            if qs.get("verified") and publishable
            else ("FAIL" if qs.get("verified") is False else "UNKNOWN")
        ),
        "publishability_status": "PUBLISHABLE" if publishable else "NOT_PUBLISHABLE",
        "ready_to_upload": bool(ready and publishable),
        "language": job.get("language") or job.get("lang_code"),
        "generation_mode": job.get("video_type") or job.get("generation_mode"),
        "note": "File existence is never semantic PASS. UNKNOWN remains UNKNOWN.",
    }
    if exists and job.get("artifact_available"):
        return {
            **base,
            "available": True,
            "status": "AVAILABLE",
            "message": "Local artifact path available (no fake player)",
            "path": path,
            "artifact_available": True,
        }
    return {
        **base,
        "available": False,
        "status": "PREVIEW_NOT_AVAILABLE_YET",
        "message": "PREVIEW NOT AVAILABLE YET",
        "path": path if path else None,
        "artifact_available": False,
    }


def project_approval(job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not job:
        return {
            "state": "NOT_READY",
            "approval_status": "NOT_READY",
            "note": "No job selected",
            "publishes": False,
        }
    stored = None
    if isinstance(job.get("approval"), dict):
        stored = job["approval"].get("state")
    stored = stored or job.get("approval_state")
    state = str(job.get("state") or "").upper()
    if stored in ("APPROVED", "REJECTED"):
        return {
            "state": stored,
            "approval_status": stored,
            "note": "Customer workflow only — does not mean published/uploaded/scheduled",
            "publishes": False,
            "updated_at": (job.get("approval") or {}).get("updated_at"),
        }
    if state == "READY_FOR_REVIEW" and job.get("publishable"):
        # C06-F: PENDING is the approval decision plane (job may still be READY_FOR_REVIEW)
        return {
            "state": "PENDING",
            "approval_status": "PENDING",
            "job_state": "READY_FOR_REVIEW",
            "note": "Pending customer decision — Approve does not publish",
            "publishes": False,
        }
    return {
        "state": "NOT_READY",
        "approval_status": "NOT_READY",
        "note": "Not ready for approval",
        "publishes": False,
    }


def load_c05_summary_from_artifact(job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Best-effort read of existing C05 sidecars beside artifact. Never regenerates plans."""
    empty = {
        "scenes": None,
        "dialogue_beats": None,
        "visual_beats": None,
        "audio_state": "UNKNOWN",
        "subtitle_localization_state": "UNKNOWN",
        "verification_state": "UNKNOWN",
        "publishability_state": "UNKNOWN",
        "source": "unavailable",
        "c05_visible": False,
    }
    if not job or not job.get("artifact_path"):
        return empty
    path = Path(str(job["artifact_path"]))
    work = path.parent if path.suffix else path
    if not work.is_dir():
        return empty

    scenes = 0
    dialogue_beats = 0
    visual_beats = 0
    found = False
    for p in work.glob("scene_*_beat_materialization.json"):
        found = True
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            units = data.get("units") or []
            visual_beats += len(units)
            dialogue_beats += len({u.get("dialogue_id") for u in units if u.get("dialogue_id")})
            scenes += 1
        except Exception:
            continue
    # Count scene folders / clips
    if not scenes:
        scenes = len(list(work.glob("scene_*.mp4"))) or len(list(work.glob("scene_*")))

    pub = "UNKNOWN"
    if job.get("publishable") is True:
        pub = "PASS"
    elif job.get("state") == "FAILED":
        pub = "FAIL"

    return {
        "scenes": scenes or None,
        "dialogue_beats": dialogue_beats or None,
        "visual_beats": visual_beats or None,
        "audio_state": "UNKNOWN",
        "subtitle_localization_state": "UNKNOWN",
        "verification_state": "PASS" if job.get("publishable") else ("UNKNOWN" if job.get("artifact_available") else "NOT_RUN"),
        "publishability_state": pub,
        "source": "c05_sidecars" if found else "artifact_dir_scan",
        "c05_visible": found,
    }


def load_quality_sidecar(job: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not job or not job.get("artifact_path"):
        return out
    work = Path(str(job["artifact_path"])).parent
    if not work.is_dir():
        return out
    mapping = {
        "CREATIVE_QUALITY_GATE.json": "creative",
        "PUBLISHABILITY_GATE.json": "publishability",
        "ARTIFACT_GATE.json": "artifact",
        "RENDERING_INTEGRITY_GATE.json": "rendering",
        "quality_report.json": "technical",
    }
    for fname, key in mapping.items():
        fp = work / fname
        if not fp.is_file():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            verdict = (
                data.get("overall_verdict")
                or data.get("verdict")
                or data.get("status")
                or data.get("publishable")
            )
            if key == "publishability" and "publishable" in data:
                verdict = "PASS" if data.get("publishable") else data.get("reason") or "FAIL"
            out[key] = verdict
            if key == "artifact" and str(data.get("observation_status") or "").upper() == "UNKNOWN":
                out[key] = "UNKNOWN"
                out["multimodal"] = "UNKNOWN"
                out["multimodal_source"] = "P04"
        except Exception:
            continue
    return out


def build_workspace_projection(
    *,
    login_id: str,
    channel: Optional[Dict[str, Any]],
    job: Optional[Dict[str, Any]],
    live: Optional[Dict[str, Any]],
    foundation: Optional[Dict[str, Any]],
    access: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Full C06-A workspace projection attached to /api/workspace."""
    # Enrich job with approval nested view if flat field present
    job_view = dict(job) if job else None
    if job_view and job_view.get("approval_state") and "approval" not in job_view:
        job_view["approval"] = {"state": job_view.get("approval_state")}

    sidecar = load_quality_sidecar(job_view)
    stages = derive_workflow_stages(
        job=job_view,
        live=live,
        foundation=foundation,
        access=access,
    )
    preview = project_preview(job_view)
    approval = project_approval(job_view)
    revision_history: Dict[str, Any] = {"ok": True, "entries": [], "current_revision": None}
    automation: Dict[str, Any] = {"available": False}
    production_monitor: Dict[str, Any] = {"available": False}
    publishing: Dict[str, Any] = {"available": False}
    publishing_schedule: Dict[str, Any] = {"available": False}
    # Enrich from C06-F compose authority when job + login present (no second engine)
    if job_view and job_view.get("job_id") is not None and login_id:
        try:
            from app.customer_preview_approval import (
                list_revision_history,
                project_customer_preview,
            )

            ch_id = int((channel or {}).get("id") or job_view.get("channel_id") or 0)
            channel_ids = [ch_id] if ch_id else []
            rich = project_customer_preview(
                login_id, int(job_view["job_id"]), channel_ids=channel_ids
            )
            if rich.get("ok"):
                preview = {**preview, **{k: rich[k] for k in rich if k not in ("ok",)}}
                preview["available"] = bool(rich.get("artifact_available"))
                preview["status"] = "AVAILABLE" if rich.get("artifact_available") else preview.get("status")
                if rich.get("approval_status") in ("PENDING", "APPROVED", "REJECTED", "NOT_READY"):
                    approval = {
                        **approval,
                        "state": rich["approval_status"]
                        if rich["approval_status"] != "NOT_READY"
                        else approval.get("state"),
                        "approval_status": rich["approval_status"],
                        "revision_id": rich.get("revision_id"),
                        "publishes": False,
                    }
            hist = list_revision_history(
                login_id, int(job_view["job_id"]), channel_ids=channel_ids
            )
            if hist.get("ok"):
                revision_history = hist
        except Exception:
            pass
        try:
            from app.customer_job import get_job
            from app.customer_job_automation import project_job_automation
            from app.customer_production_monitor import project_production_monitor

            raw = get_job(int(job_view["job_id"]))
            automation = project_job_automation(raw)
            automation["available"] = True
            automation["job_state"] = job_view.get("state")
            automation["updated_at"] = job_view.get("updated_at") or (raw or {}).get("updated_at")
            automation["created_at"] = job_view.get("created_at") or (raw or {}).get("created_at")
            ch_id = int((channel or {}).get("id") or job_view.get("channel_id") or 0)
            mon = project_production_monitor(
                login_id, int(job_view["job_id"]), channel_ids=[ch_id] if ch_id else []
            )
            if mon.get("ok"):
                automation["progress"] = mon.get("progress") or "UNKNOWN"
                automation["monitor_state"] = mon.get("monitor_state")
                automation["execution_path"] = mon.get("execution_path")
                automation["lifecycle_events"] = mon.get("lifecycle_events")
                automation["attention"] = mon.get("attention")
                automation["cancellation_status"] = mon.get("cancellation_status")
                automation["recovery_status"] = mon.get("recovery_status")
                automation["verification_status"] = mon.get("verification_status")
                automation["planes"] = mon.get("planes") or automation.get("planes")
                production_monitor = mon
            else:
                automation["progress"] = "UNKNOWN"
            try:
                from app.customer_publish import project_publishing

                pub = project_publishing(
                    login_id, int(job_view["job_id"]), channel_ids=[ch_id] if ch_id else []
                )
                if pub.get("ok"):
                    publishing = pub
            except Exception:
                publishing = {"available": False, "error": "publish_projection_unavailable"}
            try:
                from app.customer_publish_schedule import project_schedule_panel

                publishing_schedule = project_schedule_panel(
                    login_id,
                    channel_ids=[ch_id] if ch_id else [],
                    job_id=int(job_view["job_id"]),
                )
            except Exception:
                publishing_schedule = {"available": False}
        except Exception:
            automation["progress"] = "UNKNOWN"

    return {
        "contract": "C06-A+C06-F+C06-G+C06-H+C07-PUB+C07-SCHED",
        "project": build_project_header(channel=channel, job=job_view, login_id=login_id),
        "workflow": {"stages": stages},
        "production_summary": load_c05_summary_from_artifact(job_view),
        "quality_panel": project_quality_panel(job_view, sidecar=sidecar),
        "preview": preview,
        "approval": approval,
        "revision_history": revision_history,
        "automation": automation,
        "production_monitor": production_monitor,
        "publishing": publishing,
        "publishing_schedule": publishing_schedule,
        "action": derive_action_model(stages=stages, job=job_view, access=access),
        "note": (
            "Projection only — does not own job/quality/publishability/auth. "
            "Approval ≠ published. Schedule ≠ published. Upload accepted ≠ published."
        ),
    }


def detect_duplicate_engines_in_source(source: str) -> List[str]:
    """Static guard used by tests — flags second-engine *definitions* only."""
    import re

    bad = []
    patterns = (
        r"(?m)^\s*class\s+JobEngine\b",
        r"(?m)^\s*class\s+QualityEngine\b",
        r"(?m)^\s*class\s+IdempotencyEngine\b",
        r"(?m)^\s*class\s+PublishabilityEngine\b",
        r"(?m)^\s*def\s+evaluate_publishability\s*\(",
        r"(?m)^\s*def\s+generate_video\s*\(",
    )
    for pat in patterns:
        if re.search(pat, source):
            bad.append(pat)
    return bad
