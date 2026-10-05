"""Production creative-plan wiring (AMP-004 Phase-07)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.creative_production.camera import validate_camera_continuity
from pipeline.creative_production.contract import build_creative_production_plan
from pipeline.creative_production.gate import persist_creative_plan, persist_creative_production_gate
from pipeline.creative_production.preflight import CreativePreflightError, preflight_creative_generation
from pipeline.creative_production.prompt_policy import enrich_scene_intent
from pipeline.creative_production.retention import validate_retention_structure, validate_title_video_consistency
from pipeline.creative_production.transitions import validate_music_emotion, validate_sfx_purpose
from pipeline.retention_architecture import attach_retention_to_plan

logger = logging.getLogger(__name__)


def apply_production_creative_plan(
    work_dir: Path,
    handoff_scenes: list[dict[str, Any]],
    *,
    job_id: str,
    plan: Optional[dict[str, Any]] = None,
    block_on_critical: bool = True,
) -> list[dict[str, Any]]:
    """PRE-generation: attach purpose/retention, preflight, persist plan. Fail-closed."""
    work_dir = Path(work_dir)
    src = attach_retention_to_plan(dict(plan or {}))
    if not src.get("scenes") and handoff_scenes:
        src["scenes"] = list(handoff_scenes)
        src.setdefault("topic", job_id)
    merged_rows = []
    for i, sc in enumerate(handoff_scenes):
        row = dict(sc)
        if i < len(src.get("scenes") or []) and isinstance(src["scenes"][i], dict):
            ret = src["scenes"][i].get("retention")
            if ret:
                row["retention"] = ret
        merged_rows.append(row)
    cpp = build_creative_production_plan(job_id=job_id, plan=src, scenes=merged_rows)
    pf = preflight_creative_generation(plan=src, cpp=cpp, scenes=merged_rows, block=block_on_critical)
    shots = []
    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(merged_rows):
        sp = cpp.scenes[i] if i < len(cpp.scenes) else None
        enriched = dict(row)
        if sp:
            enriched["purpose"] = sp.purpose
            enriched["narrative_role"] = sp.narrative_role
            enriched["shot_type"] = sp.shot_type
            enriched["shot_purpose"] = sp.shot_purpose
            enriched["transition_intent"] = sp.transition_intent
            enriched["creative_plan_fingerprint"] = cpp.plan_fingerprint
        shots.append(
            {
                "shot_type": enriched.get("shot_type") or "",
                "shot_purpose": enriched.get("shot_purpose") or "",
                "camera_motion": enriched.get("camera_motion") or "",
            }
        )
        out_rows.append(enriched)
    cam = validate_camera_continuity(shots)
    if cam.get("status") == "BLOCK" and block_on_critical:
        raise CreativePreflightError("camera_continuity_blocked", issues=list(cam.get("issues") or []))
    persist_creative_plan(work_dir, cpp.to_dict(), key=job_id or "plan")
    raw_status = str(pf.get("status") or "PASS").upper()
    gate_status = "FAIL" if raw_status in ("BLOCK", "BLOCKED", "FAIL") else raw_status
    gate = {
        "status": gate_status,
        "verdict": raw_status,
        "issues": list(pf.get("issues") or []) + list(cam.get("issues") or []),
        "plan_fingerprint": cpp.plan_fingerprint,
        "job_id": job_id,
        "stage": "pre_generation",
        "method": "DETERMINISTIC",
        "scene_count": len(out_rows),
    }
    if cam.get("status") == "WARN":
        gate.setdefault("warnings", []).extend(cam.get("issues") or [])
    persist_creative_production_gate(work_dir, gate)
    logger.info("creative production plan applied job=%s scenes=%s fp=%s", job_id, len(out_rows), cpp.plan_fingerprint)
    return out_rows


def run_production_creative_gate(
    work_dir: Path,
    *,
    job_id: str,
    plan: Optional[dict[str, Any]] = None,
    final_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Post-generation gate: title honesty, music/SFX purpose, persist. Artifact observe remains P04."""
    work_dir = Path(work_dir)
    src = dict(plan or {})
    if not src:
        p = work_dir / "creative_plans" / f"{job_id}.json"
        if p.is_file():
            import json

            try:
                src = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                src = {}
    issues: list[str] = []
    status = "PASS"
    if not src:
        # Pre-gen gate may already exist
        from pipeline.creative_production.gate import load_creative_production_gate

        existing = load_creative_production_gate(work_dir)
        if existing:
            st = str(existing.get("status") or "UNKNOWN").upper()
            if st in ("BLOCK", "BLOCKED", "FAIL"):
                return existing
            # Re-verify title if plan missing from disk but gate passed pre-gen
            status = st if st in ("PASS", "WARN") else "UNKNOWN"
        else:
            status = "UNKNOWN"
            issues.append("creative_plan_absent")
    else:
        narrations = [
            str(s.get("narration") or s.get("dialogue_intent") or "")
            for s in (src.get("scenes") or [])
            if isinstance(s, dict)
        ]
        title = str(src.get("title") or "")
        topic = str(src.get("topic") or "")
        tv = validate_title_video_consistency(
            title=title,
            topic=topic,
            narrations=narrations,
            thumbnail_claim=str(src.get("thumbnail_claim") or title),
        )
        issues.extend(tv.get("issues") or [])
        ret = validate_retention_structure(src if src.get("scenes") else {"scenes": src.get("scenes") or [], "topic": topic, "video_type": src.get("video_type") or "short"})
        if src.get("scenes"):
            issues.extend(ret.get("issues") or [])
        for s in src.get("scenes") or []:
            if not isinstance(s, dict):
                continue
            emo = str(s.get("emotion_intent") or s.get("emotional_objective") or src.get("emotional_objective") or "")
            music = ""
            audio = s.get("audio") or s.get("audio_plan") or {}
            if isinstance(audio, dict):
                music = str((audio.get("music") or {}).get("mood") or audio.get("music_mood") or "")
                issues.extend(validate_sfx_purpose(list(audio.get("sfx_events") or []), narration=str(s.get("narration") or "")).get("issues") or [])
            issues.extend(validate_music_emotion(music_mood=music, scene_emotion=emo).get("issues") or [])
        if any(
            i.startswith("clickbait") or i.startswith("thumbnail_promise") or i.startswith("title_not") or i == "unsupported_title_claim" or i == "music_emotional_mismatch"
            for i in issues
        ):
            status = "FAIL"
        elif issues:
            status = "WARN"
        # UNKNOWN must not become PASS
        if status == "UNKNOWN":
            pass
    if status == "UNKNOWN":
        gate = {
            "status": "UNKNOWN",
            "verdict": "UNKNOWN",
            "issues": issues or ["creative_unverified"],
            "job_id": job_id,
            "stage": "post_generation",
            "final_observed": bool(final_path and Path(final_path).exists()) if final_path else False,
            "method": "DETERMINISTIC",
        }
        persist_creative_production_gate(work_dir, gate)
        return gate
    gate = {
        "status": status if status != "WARN" else "PASS",
        "verdict": status,
        "issues": issues,
        "job_id": job_id,
        "stage": "post_generation",
        "warnings": issues if status == "WARN" else [],
        "final_observed": bool(final_path and Path(final_path).exists()) if final_path else False,
        "method": "DETERMINISTIC",
        "unknown_as_pass": False,
    }
    if status == "FAIL":
        gate["status"] = "FAIL"
    persist_creative_production_gate(work_dir, gate)
    return gate


# Re-export enrich for continuity_runtime
__all__ = [
    "apply_production_creative_plan",
    "run_production_creative_gate",
    "enrich_scene_intent",
]
