"""C08 — Customer Production Certification (inspect/compose only).

Thin journey contract over existing C01→C07-SCHED authorities.
Does NOT create a second workflow/job/queue/scheduler/publish engine.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

CONTRACT_VERSION = "C08.1"

# Distinct planes — never collapse
PLANE_ORDER = (
    "GENERATED",
    "VERIFIED",
    "PUBLISHABLE",
    "APPROVED",
    "READY_TO_UPLOAD",
    "UPLOAD_ACCEPTED",
    "REMOTE_PROCESSING",
    "PUBLISHED",
    "SCHEDULED",
)

JOURNEY_STAGES = (
    "AUTH",
    "ENTITLEMENT",
    "ONBOARDING",
    "CHANNEL",
    "API_CONFIGURATION",
    "TOPIC",
    "RESEARCH",
    "SCRIPT",
    "TRS",
    "PRODUCTION_PLAN",
    "GENERATION",
    "OBSERVATION",
    "QUALITY_VERIFICATION",
    "REPAIR",
    "RENDER",
    "PREVIEW",
    "APPROVAL",
    "PUBLISHABILITY",
    "PUBLISH",
    "REMOTE_PROCESSING",
    "PUBLISHED",
    "SCHEDULE",
    "MONITOR_RECOVERY",
)

LEGACY_PATH_CLASSIFICATION = {
    "workspace_generate_queue": {
        "class": "CANONICAL_CUSTOMER_PRODUCTION",
        "path": "POST /api/workspace/generate queue=true",
    },
    "workspace_generate_sync": {
        "class": "LEGACY_COMPAT",
        "path": "POST /api/workspace/generate default → start_customer_generation",
    },
    "api_generate": {
        "class": "LEGACY_COMPAT",
        "path": "POST /api/generate",
    },
    "idle_pregen": {
        "class": "LEGACY_COMPAT",
        "path": "SchedulerService.idle_pregenerate_job",
    },
    "timed_fallback": {
        "class": "LEGACY_COMPAT",
        "path": "SchedulerService timed_fallback generate",
    },
    "timed_upload": {
        "class": "INTERNAL_ONLY",
        "path": "SchedulerService.timed_upload_job",
        "note": "Not approval-first customer path",
    },
    "browser_studio": {
        "class": "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        "path": "publishers youtube Studio / playwright",
    },
    "live_lab": {
        "class": "FORBIDDEN_FOR_CUSTOMER_PRODUCTION",
        "path": "pipeline.live_lab",
    },
    "legacy_no_plan_generation": {
        "class": "LEGACY_COMPAT",
        "path": "generate without production plan",
    },
}

FAILURE_MATRIX: Dict[str, Dict[str, Any]] = {
    "AUTH_FAILURE": {
        "state": "AUTH_REQUIRED",
        "label": "Sign in required",
        "false_success": False,
        "retry_owner": "customer_auth",
        "manual_action": True,
    },
    "ENTITLEMENT_FAILURE": {
        "state": "ENTITLEMENT_REQUIRED",
        "label": "Active entitlement required",
        "false_success": False,
        "retry_owner": "customer_auth",
        "manual_action": True,
    },
    "CHANNEL_OWNERSHIP_FAILURE": {
        "state": "OWNERSHIP_DENIED",
        "label": "Channel not owned",
        "false_success": False,
        "retry_owner": "customer_config",
        "manual_action": True,
    },
    "API_NOT_READY": {
        "state": "API_NOT_READY",
        "label": "API configuration incomplete",
        "false_success": False,
        "retry_owner": "channel_api_slots",
        "manual_action": True,
    },
    "TOPIC_FAILURE": {
        "state": "TOPIC_BLOCKED",
        "label": "Topic blocked",
        "false_success": False,
        "retry_owner": "customer_trs_workflow",
        "manual_action": True,
    },
    "RESEARCH_FAILURE": {
        "state": "RESEARCH_FAILED",
        "label": "Research failed",
        "false_success": False,
        "retry_owner": "customer_trs_workflow",
        "manual_action": True,
    },
    "SCRIPT_FAILURE": {
        "state": "SCRIPT_FAILED",
        "label": "Script failed",
        "false_success": False,
        "retry_owner": "customer_trs_workflow",
        "manual_action": True,
    },
    "PLAN_FAILURE": {
        "state": "PLAN_BLOCKED",
        "label": "Production plan not ready",
        "false_success": False,
        "retry_owner": "customer_production_plan",
        "manual_action": True,
    },
    "GENERATION_FAILURE": {
        "state": "FAILED",
        "label": "Generation failed",
        "false_success": False,
        "retry_owner": "customer_job_automation",
        "manual_action": False,
    },
    "OBSERVATION_UNKNOWN": {
        "state": "UNKNOWN",
        "label": "Observation UNKNOWN (not PASS)",
        "false_success": False,
        "retry_owner": "quality/observation",
        "manual_action": True,
    },
    "QUALITY_FAILURE": {
        "state": "QUALITY_BLOCKED",
        "label": "Quality blocked",
        "false_success": False,
        "retry_owner": "BUILD-04F",
        "manual_action": False,
    },
    "REPAIR_FAILURE": {
        "state": "REPAIR_FAILED",
        "label": "Repair failed",
        "false_success": False,
        "retry_owner": "BUILD-04F / av_self_repair",
        "manual_action": True,
    },
    "RENDER_FAILURE": {
        "state": "RENDER_FAILED",
        "label": "Render failed",
        "false_success": False,
        "retry_owner": "render_bridge",
        "manual_action": False,
    },
    "PREVIEW_UNAVAILABLE": {
        "state": "PREVIEW_NOT_AVAILABLE",
        "label": "Preview not available yet",
        "false_success": False,
        "retry_owner": "customer_preview_approval",
        "manual_action": False,
    },
    "APPROVAL_REJECTED": {
        "state": "REJECTED",
        "label": "Rejected (does not regenerate)",
        "false_success": False,
        "retry_owner": "customer (manual)",
        "manual_action": True,
    },
    "PUBLISHABILITY_FAILURE": {
        "state": "NOT_PUBLISHABLE",
        "label": "Not publishable",
        "false_success": False,
        "retry_owner": "publishability",
        "manual_action": True,
    },
    "UPLOAD_FAILURE": {
        "state": "PUBLISH_FAILED",
        "label": "Upload/publish failed",
        "false_success": False,
        "retry_owner": "customer_publish + BUILD-03",
        "manual_action": False,
    },
    "REMOTE_PROCESSING": {
        "state": "REMOTE_PROCESSING",
        "label": "Remote processing (not published)",
        "false_success": False,
        "retry_owner": "observe/refresh",
        "manual_action": False,
    },
    "REMOTE_FAILURE": {
        "state": "FAILED",
        "label": "Remote processing failed",
        "false_success": False,
        "retry_owner": "customer_publish",
        "manual_action": True,
    },
    "RECONCILIATION_REQUIRED": {
        "state": "RECONCILIATION_REQUIRED",
        "label": "Reconciliation required",
        "false_success": False,
        "retry_owner": "reconcile_ambiguous_publish",
        "manual_action": True,
    },
    "SCHEDULE_CANCELLED": {
        "state": "CANCELLED",
        "label": "Schedule cancelled",
        "false_success": False,
        "retry_owner": "customer_publish_schedule",
        "manual_action": False,
    },
    "SCHEDULE_MISSED": {
        "state": "MISSED",
        "label": "Schedule missed — action required",
        "false_success": False,
        "retry_owner": "customer_publish_schedule",
        "manual_action": True,
    },
    "RESTART_DURING_GENERATION": {
        "state": "INTERRUPTED",
        "label": "Interrupted — recovery",
        "false_success": False,
        "retry_owner": "recover_after_restart",
        "manual_action": False,
    },
    "RESTART_DURING_PUBLISH": {
        "state": "RECONCILIATION_OR_IN_PROGRESS",
        "label": "Publish interrupted — reconcile",
        "false_success": False,
        "retry_owner": "BUILD-03 + customer_publish",
        "manual_action": True,
    },
    "RESTART_DURING_SCHEDULE": {
        "state": "SCHEDULED_OR_MISSED",
        "label": "Schedule recovered",
        "false_success": False,
        "retry_owner": "recover_schedules_after_restart",
        "manual_action": False,
    },
    "DUPLICATE_GENERATE": {
        "state": "REUSE",
        "label": "Duplicate generate blocked/reused",
        "false_success": False,
        "retry_owner": "BUILD-03 / queue_fingerprint",
        "manual_action": False,
    },
    "DUPLICATE_PUBLISH": {
        "state": "IDEMPOTENT_REUSE",
        "label": "Duplicate publish blocked",
        "false_success": False,
        "retry_owner": "BUILD-03 publish stage",
        "manual_action": False,
    },
    "DUPLICATE_SCHEDULE": {
        "state": "IDEMPOTENT_REUSE",
        "label": "Duplicate schedule blocked",
        "false_success": False,
        "retry_owner": "BUILD-03 schedule stage",
        "manual_action": False,
    },
    "FORGED_CUSTOMER_ACCESS": {
        "state": "OWNERSHIP_DENIED",
        "label": "Access denied",
        "false_success": False,
        "retry_owner": "C02/C04 ownership",
        "manual_action": False,
    },
}


def stage_record(
    *,
    stage: str,
    state: str,
    authoritative_source: str,
    blocking_reason: Optional[str] = None,
    customer_visible_label: str = "",
    recovery_action: str = "None",
    terminal: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "stage": stage,
        "state": state,
        "authoritative_source": authoritative_source,
        "blocking_reason": blocking_reason,
        "customer_visible_label": customer_visible_label or state,
        "recovery_action": recovery_action,
        "terminal": bool(terminal),
        "non_terminal": not bool(terminal),
        **(extra or {}),
    }


def assert_planes_distinct() -> Dict[str, bool]:
    """Prove plane labels are pairwise unequal as strings."""
    names = list(PLANE_ORDER)
    return {f"{a}_neq_{b}": a != b for i, a in enumerate(names) for b in names[i + 1 :]}


def project_result_planes(job_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map job + publish fields → distinct planes without promotion."""
    if not job_row:
        return {p: False for p in PLANE_ORDER} | {"note": "no_job"}
    upload = str(job_row.get("upload_status") or "")
    approval = str(job_row.get("customer_approval") or "").upper()
    pstat = str(job_row.get("publish_status") or "").upper()
    qs = job_row.get("quality_summary")
    if isinstance(qs, str):
        try:
            qs = json.loads(qs)
        except Exception:
            qs = {}
    qs = qs if isinstance(qs, dict) else {}
    publishable = bool(qs.get("publishable")) or upload == "ready_to_upload"
    verified = bool(qs.get("verified")) or str(qs.get("artifact_verification") or "").upper() == "VERIFIED"
    generated = bool(job_row.get("local_path")) or upload in (
        "ready_to_upload",
        "generated",
        "uploaded",
        "dry_run_uploaded",
    )
    return {
        "GENERATED": generated,
        "VERIFIED": verified,
        "PUBLISHABLE": publishable and upload == "ready_to_upload",
        "APPROVED": approval == "APPROVED",
        "READY_TO_UPLOAD": upload == "ready_to_upload",
        "UPLOAD_ACCEPTED": pstat in ("UPLOAD_ACCEPTED", "REMOTE_PROCESSING", "PUBLISHED"),
        "REMOTE_PROCESSING": pstat == "REMOTE_PROCESSING",
        "PUBLISHED": pstat == "PUBLISHED",
        "SCHEDULED": False,  # filled by schedule projection
        "note": "Planes are independent — upload accepted does not set PUBLISHED",
    }


def project_journey(
    login_id: str,
    *,
    channel_ids: Sequence[int],
    job_id: Optional[int] = None,
    channel: Optional[Dict[str, Any]] = None,
    identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Inspect existing authorities into one journey projection (not a second engine)."""
    from app.customer_auth import evaluate_session
    from app.customer_job import get_job, job_owned_by_channels

    ident = identity if identity is not None else evaluate_session()
    stages: List[Dict[str, Any]] = []

    # AUTH
    auth_ok = bool(ident.get("authenticated") or ident.get("auth_state") in ("AUTHENTICATED", "OK"))
    if ident.get("authenticated") is False:
        auth_ok = False
    stages.append(
        stage_record(
            stage="AUTH",
            state="AUTHENTICATED" if auth_ok else "AUTH_REQUIRED",
            authoritative_source="customer_auth.evaluate_session",
            blocking_reason=None if auth_ok else "authentication_required",
            customer_visible_label="Signed in" if auth_ok else "Sign in required",
            recovery_action="Login" if not auth_ok else "None",
            terminal=False,
        )
    )

    # ENTITLEMENT
    ent = str(ident.get("entitlement_state") or "")
    ent_ok = bool(ident.get("production_access")) and ent in ("ACTIVE", "")
    if ent in ("NONE", "EXPIRED", "SUSPENDED", "UNKNOWN", "INACTIVE"):
        ent_ok = False
    if ident.get("production_access") is False:
        ent_ok = False
    stages.append(
        stage_record(
            stage="ENTITLEMENT",
            state="ACTIVE" if ent_ok else "ENTITLEMENT_REQUIRED",
            authoritative_source="customer_auth.can_customer_produce / production_access",
            blocking_reason=None if ent_ok else (ident.get("block_reason") or "entitlement"),
            customer_visible_label="Entitled" if ent_ok else "Entitlement required",
            recovery_action="Activate entitlement" if not ent_ok else "None",
        )
    )

    # CHANNEL / ownership
    ch = channel or {}
    ch_id = int(ch.get("id") or 0)
    owned = ch_id in {int(x) for x in channel_ids} if ch_id else bool(channel_ids)
    stages.append(
        stage_record(
            stage="CHANNEL",
            state="OWNED" if owned else "OWNERSHIP_DENIED",
            authoritative_source="customer_config.require_owned_channel / list_owned_channels",
            blocking_reason=None if owned else "unowned_channel",
            customer_visible_label="Channel ready" if owned else "Claim/own channel",
            recovery_action="Configure channel" if not owned else "None",
        )
    )

    # API readiness (best-effort)
    api_state = "UNKNOWN"
    try:
        from pipeline.channel_api_slots import evaluate_readiness

        ready = evaluate_readiness(channel=ch)
        api_ok = bool(ready.get("ready") or ready.get("ok"))
        api_state = "READY" if api_ok else "API_NOT_READY"
    except Exception:
        api_ok = True  # offline cert may not have slots module shape
        api_state = "UNKNOWN"
    stages.append(
        stage_record(
            stage="API_CONFIGURATION",
            state=api_state,
            authoritative_source="pipeline.channel_api_slots.evaluate_readiness",
            blocking_reason=None if api_state != "API_NOT_READY" else "api_not_ready",
            customer_visible_label=api_state,
            recovery_action="Configure API slots" if api_state == "API_NOT_READY" else "None",
        )
    )

    job = get_job(int(job_id)) if job_id else None
    if job and not job_owned_by_channels(job, list(channel_ids)):
        job = None
        stages.append(
            stage_record(
                stage="GENERATION",
                state="OWNERSHIP_DENIED",
                authoritative_source="customer_job.job_owned_by_channels",
                blocking_reason="foreign_job",
                customer_visible_label="Access denied",
                recovery_action="None",
                terminal=True,
            )
        )

    planes = project_result_planes(job)

    # TRS / plan — inspect if modules available
    for stage, src, key in (
        ("TOPIC", "customer_trs_workflow", "topic"),
        ("RESEARCH", "customer_trs_workflow", "research"),
        ("SCRIPT", "customer_trs_workflow", "script"),
        ("PRODUCTION_PLAN", "customer_production_plan", "plan"),
    ):
        stages.append(
            stage_record(
                stage=stage,
                state="INSPECT_VIA_EXISTING_AUTHORITY",
                authoritative_source=src,
                customer_visible_label=stage.replace("_", " ").title(),
                recovery_action="Use existing TRS/plan APIs",
                extra={"inspect_key": key},
            )
        )

    if job:
        upload = str(job.get("upload_status") or "")
        cust = str(job.get("customer_state") or "")
        stages.append(
            stage_record(
                stage="GENERATION",
                state=cust or upload or "UNKNOWN",
                authoritative_source="customer_job / customer_job_automation.execute_claimed_job",
                customer_visible_label=cust or upload or "Unknown",
                recovery_action="Retry via C06-G" if upload in ("failed", "interrupted") else "None",
                terminal=upload in ("failed", "cancelled"),
            )
        )
        qs = job.get("quality_summary")
        if isinstance(qs, str):
            try:
                qs = json.loads(qs)
            except Exception:
                qs = {}
        qs = qs if isinstance(qs, dict) else {}
        obs = str(qs.get("multimodal_status") or qs.get("observation") or "UNKNOWN").upper()
        if obs in ("", "ABSENT"):
            obs = "UNKNOWN"
        stages.append(
            stage_record(
                stage="OBSERVATION",
                state=obs,
                authoritative_source="quality_summary / multimodal gates",
                blocking_reason="UNKNOWN remains UNKNOWN" if obs == "UNKNOWN" else None,
                customer_visible_label=obs,
                recovery_action="Provide verified observation" if obs == "UNKNOWN" else "None",
            )
        )
        stages.append(
            stage_record(
                stage="QUALITY_VERIFICATION",
                state="VERIFIED" if planes["VERIFIED"] else ("PUBLISHABLE" if planes["PUBLISHABLE"] else "NOT_VERIFIED"),
                authoritative_source="pipeline.quality + video_pipeline gates",
                customer_visible_label="Verified" if planes["VERIFIED"] else "Not verified",
            )
        )
        stages.append(
            stage_record(
                stage="APPROVAL",
                state=str(job.get("customer_approval") or "NOT_READY").upper(),
                authoritative_source="customer_preview_approval.record_customer_approval",
                customer_visible_label=str(job.get("customer_approval") or "Not ready"),
                recovery_action="Approve or reject" if planes["READY_TO_UPLOAD"] and not planes["APPROVED"] else "None",
            )
        )
        stages.append(
            stage_record(
                stage="PUBLISHABILITY",
                state="PUBLISHABLE" if planes["PUBLISHABLE"] else "NOT_PUBLISHABLE",
                authoritative_source="pipeline.quality.publishability.evaluate_publishability",
                customer_visible_label="Publishable" if planes["PUBLISHABLE"] else "Not publishable",
            )
        )
        pstat = str(job.get("publish_status") or "NOT_STARTED")
        stages.append(
            stage_record(
                stage="PUBLISH",
                state=pstat,
                authoritative_source="customer_publish.publish_customer_job",
                customer_visible_label=pstat,
                recovery_action="Publish" if planes["APPROVED"] and planes["READY_TO_UPLOAD"] else "None",
                terminal=pstat in ("PUBLISHED", "FAILED"),
            )
        )
        stages.append(
            stage_record(
                stage="REMOTE_PROCESSING",
                state="REMOTE_PROCESSING" if planes["REMOTE_PROCESSING"] else ("DONE" if planes["PUBLISHED"] else "IDLE"),
                authoritative_source="customer_publish.refresh_publish_status",
                customer_visible_label="Remote processing" if planes["REMOTE_PROCESSING"] else "Idle",
            )
        )
        stages.append(
            stage_record(
                stage="PUBLISHED",
                state="PUBLISHED" if planes["PUBLISHED"] else "NOT_PUBLISHED",
                authoritative_source="customer_publish observe",
                customer_visible_label="Published" if planes["PUBLISHED"] else "Not published",
                terminal=planes["PUBLISHED"],
            )
        )

    # Schedule panel
    try:
        from app.customer_publish_schedule import project_schedule_panel

        sch = project_schedule_panel(login_id, channel_ids=channel_ids, job_id=job_id)
        active = sch.get("active")
        planes["SCHEDULED"] = bool(active and active.get("status") == "SCHEDULED")
        stages.append(
            stage_record(
                stage="SCHEDULE",
                state=(active or {}).get("status") or "NOT_SCHEDULED",
                authoritative_source="customer_publish_schedule",
                customer_visible_label=(active or {}).get("status") or "Not scheduled",
                recovery_action="Schedule publish" if planes.get("PUBLISHED") or planes.get("APPROVED") else "None",
            )
        )
    except Exception:
        stages.append(
            stage_record(
                stage="SCHEDULE",
                state="UNAVAILABLE",
                authoritative_source="customer_publish_schedule",
                customer_visible_label="Schedule unavailable",
            )
        )

    # Monitor
    mon = None
    if job_id:
        try:
            from app.customer_production_monitor import project_production_monitor

            mon = project_production_monitor(login_id, int(job_id), channel_ids=channel_ids)
            stages.append(
                stage_record(
                    stage="MONITOR_RECOVERY",
                    state=str(mon.get("monitor_state") or "UNKNOWN"),
                    authoritative_source="customer_production_monitor.infer_monitor_state",
                    customer_visible_label=str((mon.get("state_contract") or {}).get("label") or mon.get("monitor_state")),
                    recovery_action=str((mon.get("state_contract") or {}).get("action") or "None"),
                )
            )
        except Exception:
            pass

    return {
        "ok": True,
        "contract": CONTRACT_VERSION,
        "login_id": login_id,
        "job_id": job_id,
        "stages": stages,
        "planes": planes,
        "plane_distinctions": assert_planes_distinct(),
        "legacy_paths": LEGACY_PATH_CLASSIFICATION,
        "failure_matrix": FAILURE_MATRIX,
        "monitor": mon,
        "admission": {
            "auth": auth_ok,
            "entitlement": ent_ok,
            "channel_owned": owned,
            "production_access": bool(ident.get("production_access")),
        },
        "note": (
            "Certification projection only — does not own job/quality/publish/schedule. "
            "GENERATED≠VERIFIED≠PUBLISHABLE≠APPROVED≠READY_TO_UPLOAD≠"
            "UPLOAD_ACCEPTED≠REMOTE_PROCESSING≠PUBLISHED≠SCHEDULED"
        ),
        "paid_api_calls": 0,
        "orchestrates_new_engine": False,
    }


def classify_failure(code: str) -> Dict[str, Any]:
    row = FAILURE_MATRIX.get(str(code).upper())
    if not row:
        return {
            "ok": False,
            "error": "unknown_failure_code",
            "false_success": False,
            "manual_action": True,
        }
    return {"ok": True, "code": code.upper(), **row, "false_success": False}


def certify_offline_media_probe(path: str) -> Dict[str, Any]:
    """Minimal real-media probe via existing compose discovery — no new FFmpeg manager."""
    from pipeline.compose import probe_media_tool_capability

    cap = probe_media_tool_capability()
    exists = bool(path) and os.path.isfile(path)
    return {
        "ok": True,
        "path_exists": exists,
        "media_tools": cap,
        "paid_api_calls": 0,
        "note": "Uses existing pipeline.compose discovery only",
        "authoritative_source": "pipeline.compose.probe_media_tool_capability / ffmpeg_bin",
    }


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat, label in (
        (r"(?m)^\s*class\s+SchedulerService\b", "SchedulerService"),
        (r"(?m)^\s*def\s+generate_video\s*\(", "generate_video"),
        (r"(?m)^\s*def\s+evaluate_publishability\s*\(", "evaluate_publishability"),
        (r"(?m)^\s*class\s+IdempotencyStore\b", "IdempotencyStore"),
        (r"(?m)^\s*def\s+compute_fingerprint\s*\(", "compute_fingerprint"),
        (r"(?m)^\s*class\s+JobEngine\b", "JobEngine"),
        (r"(?m)^\s*class\s+QualityEngine\b", "QualityEngine"),
    ):
        if _re.search(pat, source):
            bad.append(label)
    return bad


AUTHORITY_SINGULARITY = {
    "job": "app.customer_job / customer_job_automation",
    "queue": "app.customer_job_automation",
    "scheduler": "app.scheduler_service.SchedulerService",
    "retry": "app.customer_job_automation classify/backoff",
    "idempotency": "pipeline.idempotency (BUILD-03)",
    "generation": "pipeline.video_pipeline.generate_video (+ mock/handoff)",
    "quality": "pipeline.quality.publishability / bridge",
    "repair": "pipeline.av_self_repair_agent + BUILD-04F",
    "continuity": "C05 continuity / video_pipeline gates",
    "render_ffmpeg": "pipeline.compose + render_bridge",
    "publishing": "app.customer_publish",
    "ownership": "customer_auth + customer_config + job_owned_by_channels",
    "monitoring": "app.customer_production_monitor",
}
