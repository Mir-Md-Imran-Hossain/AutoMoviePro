"""Final-master Gemini video understanding observation (evidence layer).

Does not replace MASTER_SHIP_GATE / publishability hard authorities.
Provider failure → UNKNOWN (never silent PASS).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)

GATE_NAME = "FINAL_VIDEO_GEMINI_REVIEW_GATE.json"
EVIDENCE_NAME = "FINAL_VIDEO_GEMINI_REVIEW.json"
# Prefer File API / upload for larger masters; below this still attempt upload first.
FILE_API_PREFERRED_BYTES = 100 * 1024 * 1024


def run_final_video_gemini_review(
    work_dir: Path,
    *,
    final_path: Optional[Path] = None,
    google_api_keys: Optional[Sequence[str]] = None,
    job_id: str = "",
) -> dict[str, Any]:
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    video = Path(final_path) if final_path else None
    if video is None or not video.is_file():
        for name in ("final_short.mp4", "body_av.mp4", "branded_av.mp4", "master.mp4", "final.mp4"):
            p = work_dir / name
            if p.is_file() and p.stat().st_size > 8000:
                video = p
                break

    gate: dict[str, Any] = {
        "schema": "amp_final_video_gemini_review_v1",
        "job_id": job,
        "status": "UNKNOWN",
        "unknown_as_pass": False,
        "creates_final_gate": False,
        "does_not_replace": ["MASTER_SHIP_GATE", "publishability", "semantic_coverage"],
        "video_path": str(video) if video else "",
        "strategy": "",
        "issues": [],
        "timestamp_questions": [],
    }

    if video is None:
        gate["issues"].append("no_final_video")
        _persist(work_dir, gate, {})
        return gate

    keys = [str(k).strip() for k in (google_api_keys or []) if str(k).strip()]
    if not keys:
        try:
            from app.config import settings

            raw = getattr(settings, "google_api_keys", None) or getattr(settings, "GOOGLE_API_KEYS", None)
            if isinstance(raw, str):
                keys = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
            elif isinstance(raw, (list, tuple)):
                keys = [str(x).strip() for x in raw if str(x).strip()]
        except Exception:
            keys = []

    size = int(video.stat().st_size)
    gate["video_bytes"] = size
    use_file_api_note = size >= FILE_API_PREFERRED_BYTES
    gate["file_api_preferred"] = use_file_api_note

    # Timestamp-targeted forensic prompts (short documentary masters)
    ts_prompts = [
        "At 0–5 seconds: what subject and setting are visible?",
        "At mid-duration: does the visual still match a lunar/documentary science niche?",
        "In the final 5 seconds: is there a talking-head or unrelated b-roll?",
    ]
    gate["timestamp_questions"] = list(ts_prompts)

    if not keys:
        gate["issues"].append("no_google_api_keys")
        gate["status"] = "UNKNOWN"
        _persist(work_dir, gate, {"reason": "no_keys"})
        return gate

    try:
        from pipeline.av_sync_critic import critique_scene_clip

        narration = (
            "Final master forensic review. Answer visibility of subject continuity across the timeline."
        )
        critique = critique_scene_clip(
            video_path=video,
            audio_path=video,
            narration_bn=narration,
            keyword_triggers=["documentary", "subject", "continuity"],
            exact_ai_video_prompt=" | ".join(ts_prompts),
            niche="final_master_review",
            element="final",
            google_api_keys=keys,
            product_name="final_master",
        )
        gate["strategy"] = "video_upload_then_frames_fallback"
        if size >= FILE_API_PREFERRED_BYTES:
            gate["strategy"] = "large_file_upload_or_sampled_frames"
        raw = critique.get("raw") or {}
        if raw.get("fallback") or raw.get("local_gates_only"):
            gate["status"] = "UNKNOWN"
            gate["issues"].append("provider_fallback_or_outage")
        elif critique.get("passed") is True:
            gate["status"] = "PASS"
        elif critique.get("passed") is False and not raw.get("fallback"):
            # Hard visual fails on final → FAIL evidence (ship gate still separate)
            hard = set(critique.get("critical_issues") or []) & {
                "wrong_subject",
                "unrelated_broll",
                "talking_head",
            }
            gate["status"] = "FAIL" if hard else "UNKNOWN"
            gate["issues"].extend(list(critique.get("critical_issues") or [])[:8])
        else:
            gate["status"] = "UNKNOWN"
            gate["issues"].append("inconclusive_critique")
        evidence = {
            "critique": critique,
            "timestamp_questions": ts_prompts,
            "file_api_preferred": use_file_api_note,
            "video_bytes": size,
        }
        _persist(work_dir, gate, evidence)
        return gate
    except Exception as exc:
        logger.warning("Final Gemini review UNKNOWN: %s", exc)
        gate["status"] = "UNKNOWN"
        gate["issues"].append(f"review_exception:{str(exc)[:180]}")
        _persist(work_dir, gate, {"error": str(exc)[:300]})
        return gate


def _persist(work_dir: Path, gate: dict[str, Any], evidence: dict[str, Any]) -> None:
    work_dir = Path(work_dir)
    (work_dir / GATE_NAME).write_text(
        json.dumps(gate, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (work_dir / EVIDENCE_NAME).write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
