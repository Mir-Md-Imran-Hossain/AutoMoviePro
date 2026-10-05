"""SaaS bridge: create / poll / cancel custom_pipeline jobs from app/.

Opt-in via AMP_CUSTOM_PIPELINE=1 (or pipeline_engine=custom on the job).
Does not replace the legacy TRS generate_video path unless explicitly selected.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

_jobs_lock = threading.Lock()
_active: Dict[str, threading.Thread] = {}


def custom_pipeline_enabled(*, job_meta: Optional[Dict[str, Any]] = None) -> bool:
    meta = job_meta or {}
    engine = str(meta.get("pipeline_engine") or meta.get("engine") or "").strip().lower()
    if engine in ("custom", "custom_pipeline", "industrial"):
        return True
    env = (os.environ.get("AMP_CUSTOM_PIPELINE") or "").strip().lower()
    return env in ("1", "true", "yes", "on")


def _jobs_root() -> Path:
    root = DATA_DIR / "custom_pipeline_jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_record_path(job_key: str) -> Path:
    return _jobs_root() / f"{job_key}.json"


def save_job_record(job_key: str, record: Dict[str, Any]) -> Path:
    path = job_record_path(job_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    record["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_job_record(job_key: str) -> Optional[Dict[str, Any]]:
    path = job_record_path(job_key)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def start_custom_pipeline_job(
    *,
    niche: str,
    video_type: str = "short",
    audience: str = "সাধারণ দর্শক",
    languages: Optional[Sequence[str]] = None,
    login_id: str = "",
    customer_job_id: Optional[int] = None,
    resume_package: Optional[str] = None,
    force: bool = False,
    require_approval: bool = False,
) -> Dict[str, Any]:
    """Spawn custom pipeline in a background thread; return pollable job key."""
    job_key = f"cp-{uuid.uuid4().hex[:12]}"
    record: Dict[str, Any] = {
        "job_key": job_key,
        "status": "queued",
        "niche": niche,
        "video_type": video_type,
        "audience": audience,
        "languages": list(languages or []),
        "login_id": login_id,
        "customer_job_id": customer_job_id,
        "package_root": resume_package,
        "created_at": datetime.now().isoformat(),
        "progress_pct": 0,
        "progress_message": "queued",
        "result": None,
        "error": None,
    }
    save_job_record(job_key, record)

    def _run() -> None:
        rec = load_job_record(job_key) or record
        rec["status"] = "running"
        save_job_record(job_key, rec)
        try:
            from pipeline.custom_pipeline.runner import run_pipeline
            from pipeline.custom_pipeline.pipeline_control import request_cancel

            def _progress(pct: float, msg: str) -> None:
                r = load_job_record(job_key) or {}
                r["progress_pct"] = pct
                r["progress_message"] = msg
                if r.get("cancel_requested"):
                    pkg = r.get("package_root")
                    if pkg:
                        request_cancel(pkg)
                save_job_record(job_key, r)

            result = run_pipeline(
                video_type=video_type,
                niche=niche,
                audience=audience,
                languages=languages,
                resume_package=Path(resume_package) if resume_package else None,
                force=force,
                require_approval=require_approval,
                progress_cb=_progress,
            )
            rec = load_job_record(job_key) or {}
            rec["status"] = (
                "succeeded"
                if result.get("shippable") or result.get("ok")
                else ("partial" if result.get("partial") else "failed")
            )
            rec["package_root"] = result.get("package_root")
            rec["result"] = {
                "ok": result.get("ok"),
                "shippable": result.get("shippable"),
                "partial": result.get("partial"),
                "package_root": result.get("package_root"),
                "outputs": result.get("outputs"),
                "degraded": result.get("degraded"),
                "session_id": result.get("session_id"),
            }
            rec["progress_pct"] = 100
            rec["progress_message"] = rec["status"]
            save_job_record(job_key, rec)
        except Exception as exc:
            logger.exception("custom pipeline job %s failed", job_key)
            rec = load_job_record(job_key) or {}
            rec["status"] = "failed"
            rec["error"] = str(exc)[:500]
            save_job_record(job_key, rec)
        finally:
            with _jobs_lock:
                _active.pop(job_key, None)

    t = threading.Thread(target=_run, name=f"custom-pipeline-{job_key}", daemon=True)
    with _jobs_lock:
        _active[job_key] = t
    t.start()
    return {"ok": True, "job_key": job_key, "status": "queued"}


def cancel_custom_pipeline_job(job_key: str) -> Dict[str, Any]:
    rec = load_job_record(job_key)
    if not rec:
        return {"ok": False, "error": "job_not_found"}
    rec["cancel_requested"] = True
    save_job_record(job_key, rec)
    pkg = rec.get("package_root")
    if pkg:
        from pipeline.custom_pipeline.pipeline_control import request_cancel

        request_cancel(pkg)
    return {"ok": True, "job_key": job_key, "cancel_requested": True}


def get_custom_pipeline_job(job_key: str) -> Dict[str, Any]:
    rec = load_job_record(job_key)
    if not rec:
        return {"ok": False, "error": "job_not_found"}
    # Merge live package job_state if present
    pkg = rec.get("package_root")
    if pkg:
        try:
            from pipeline.custom_pipeline.job_state import load_job_state

            state = load_job_state(Path(pkg))
            if state:
                rec["job_state"] = {
                    "status": state.get("status"),
                    "progress_pct": state.get("progress_pct"),
                    "progress_message": state.get("progress_message"),
                    "shippable": state.get("shippable"),
                    "partial": state.get("partial"),
                    "degraded": state.get("degraded"),
                    "stages": state.get("stages"),
                }
                rec["progress_pct"] = state.get("progress_pct", rec.get("progress_pct"))
                rec["progress_message"] = state.get("progress_message", rec.get("progress_message"))
        except Exception:
            pass
    return {"ok": True, **rec}


def run_custom_pipeline_for_customer_job(
    *,
    niche: str,
    video_type: str,
    work_dir: Path | str,
    languages: Optional[Sequence[str]] = None,
    audience: str = "সাধারণ দর্শক",
    progress_cb=None,
    output_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Synchronous entry used by customer_job_automation when engine=custom."""
    from pipeline.custom_pipeline.runner import run_pipeline

    # Canonical Output folder (Output/Short/00X_... or Output/Long/00X_...)
    root = Path(output_root) if output_root else None
    result = run_pipeline(
        video_type=video_type or "short",
        niche=niche or "general",
        audience=audience,
        languages=languages,
        output_root=root,
        progress_cb=progress_cb,
    )
    # Normalize to mark_from_pipeline_result shape
    pkg_root = Path(result.get("package_root") or "")
    stage5 = result.get("stage5_media") or {}
    compose = stage5.get("compose") or {}
    finals = compose.get("finals") or {}
    local_path = None
    if "BN" in finals and isinstance(finals["BN"], dict) and finals["BN"].get("path"):
        local_path = finals["BN"]["path"]
    else:
        for _lang, item in finals.items():
            if isinstance(item, dict) and item.get("path"):
                local_path = item["path"]
                break
    if not local_path and pkg_root.is_dir():
        bn_cand = pkg_root / "Video" / "Final Video" / "BN" / "final_BN.mp4"
        if bn_cand.is_file():
            local_path = str(bn_cand)
        else:
            all_finals = list(pkg_root.glob("Video/Final Video/*/*.mp4"))
            if all_finals:
                local_path = str(all_finals[0])
            else:
                local_path = str(pkg_root)

    return {
        "ok": bool(result.get("ok") or result.get("shippable")),
        "shippable": result.get("shippable"),
        "partial": result.get("partial"),
        "upload_status": "ready_to_upload" if result.get("shippable") else "generated",
        "local_path": local_path,
        "artifact_path": local_path,
        "title": niche,
        "package_root": str(pkg_root),
        "custom_pipeline": True,
        "degraded": result.get("degraded"),
        "raw": result,
    }
