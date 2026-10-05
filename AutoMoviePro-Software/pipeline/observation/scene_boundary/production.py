"""Production scene-boundary observation gate (PySceneDetect / FFmpeg).

Evidence only — does NOT replace Director Plan, C05-S, or ContinuityTracker.
UNKNOWN ≠ PASS. Does not hard-block publish (observation layer).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional, Sequence

logger = logging.getLogger(__name__)

GATE_NAME = "SCENE_BOUNDARY_OBSERVATION_GATE.json"
EVIDENCE_NAME = "SCENE_BOUNDARY_EVIDENCE.json"


def _pick_video(work_dir: Path, final_path: Optional[Path]) -> Optional[Path]:
    work_dir = Path(work_dir)
    cands: List[Path] = []
    if final_path and Path(final_path).is_file():
        cands.append(Path(final_path))
    for name in ("final_short.mp4", "body_av.mp4", "branded_av.mp4", "master.mp4", "final.mp4"):
        p = work_dir / name
        if p.is_file() and p.stat().st_size > 8000:
            cands.append(p)
    return cands[0] if cands else None


def _planned_beats(scenes: Optional[Sequence[Any]]) -> List[dict]:
    out: List[dict] = []
    for i, sc in enumerate(scenes or []):
        if not isinstance(sc, dict):
            continue
        start = float(sc.get("start_sec") or 0.0)
        dur = float(sc.get("duration_sec") or 0.0)
        end = float(sc.get("end_sec") or (start + dur) or 0.0)
        out.append(
            {
                "beat_id": str(sc.get("beat_id") or sc.get("c05s_visual_beat_id") or f"beat-{i}"),
                "scene_id": str(sc.get("scene_id") or f"scene-{i}"),
                "start_sec": start,
                "end_sec": end,
                "duration_sec": max(0.0, end - start) if end > start else dur,
            }
        )
    return out


def run_production_scene_boundary_gate(
    work_dir: Path,
    *,
    job_id: str = "",
    final_path: Optional[Path] = None,
    scenes: Optional[Sequence[Any]] = None,
) -> dict[str, Any]:
    """Observe final cuts; compare to planned beats; persist evidence."""
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    video = _pick_video(work_dir, Path(final_path) if final_path else None)
    planned = _planned_beats(scenes)

    gate: dict[str, Any] = {
        "schema": "amp_scene_boundary_observation_gate_v1",
        "job_id": job,
        "status": "UNKNOWN",
        "authority": "observation_only",
        "is_production_authority": False,
        "does_not_replace": ["DirectorPlan", "DirectedVisualBeat", "ContinuityTracker"],
        "creates_final_gate": False,
        "unknown_as_pass": False,
        "video_path": str(video) if video else "",
        "planned_beat_count": len(planned),
        "issues": [],
    }

    if video is None:
        gate["issues"].append("no_video_for_scene_boundary")
        gate["status"] = "UNKNOWN"
        _persist(work_dir, gate, {})
        return gate

    try:
        from pipeline.observation.scene_boundary import (
            compare_planned_beats_vs_boundaries,
            observe_scene_boundaries,
            scene_tool_available,
        )

        avail = scene_tool_available()
        gate["pyscenedetect_available"] = bool(avail.get("available"))
        obs = observe_scene_boundaries(video)
        comparison = compare_planned_beats_vs_boundaries(
            planned_beats=planned,
            observed=obs,
        )
        evidence = {
            "observation": obs,
            "planned_vs_observed": comparison,
            "tool_available": avail,
        }
        st = str(comparison.get("status") or obs.get("status") or "UNKNOWN").upper()
        if st not in ("PASS", "FAIL", "UNKNOWN", "UNAVAILABLE"):
            st = "UNKNOWN"
        if st == "UNAVAILABLE":
            st = "UNKNOWN"
        gate["status"] = st
        gate["observed_scene_count"] = int(obs.get("scene_count") or 0)
        gate["tool"] = str(obs.get("tool") or "")
        gate["tool_version"] = str(obs.get("tool_version") or "")
        gate["source_hash"] = str(obs.get("source_hash") or "")
        gate["provider_verified"] = bool(obs.get("provider_verified"))
        hard = list(comparison.get("hard_issues") or [])
        soft = list(comparison.get("soft_issues") or [])
        all_issues = list(comparison.get("issues") or obs.get("issues") or [])
        gate["hard_issues"] = hard
        gate["soft_issues"] = soft
        gate["false_cut_hints"] = list(comparison.get("false_cut_candidates") or [])
        # T1-A: compare already classifies soft documentary/Ken Burns as PASS+soft.
        # Keep soft issues visible; never convert UNKNOWN→PASS here.
        if hard:
            gate["status"] = "FAIL"
            gate["issues"] = hard + [f"soft:{i}" for i in soft[:8]]
        elif soft:
            gate["status"] = "PASS" if st in ("PASS", "FAIL") else st
            # If compare already PASS with soft, preserve; never upgrade UNKNOWN
            if st == "UNKNOWN":
                gate["status"] = "UNKNOWN"
            else:
                gate["status"] = "PASS"
            gate["softened"] = True
            gate["softened_issues"] = soft
            gate["issues"] = [f"soft:{i}" for i in soft[:12]]
        else:
            gate["issues"] = all_issues
        if gate["status"] == "UNKNOWN":
            gate["reason"] = comparison.get("reason") or obs.get("reason") or "UNKNOWN"
        _persist(work_dir, gate, evidence)
        return gate
    except Exception as exc:
        logger.warning("Scene boundary production gate error: %s", exc)
        gate["status"] = "UNKNOWN"
        gate["issues"].append(f"scene_boundary_exception:{str(exc)[:180]}")
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


def load_scene_boundary_gate_status(work_dir: Path) -> str:
    p = Path(work_dir) / GATE_NAME
    if not p.is_file():
        return "ABSENT"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("status") or "ABSENT").strip().upper() or "ABSENT"
    except Exception:
        return "UNKNOWN"
