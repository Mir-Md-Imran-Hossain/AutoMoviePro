"""Scene/cut boundary observation via PySceneDetect (optional) with FFmpeg fallback.

Does NOT replace Director Plan, C05-S DirectedVisualBeat, or ContinuityTracker.
Emits evidence only — no final gate.

T1-A: distinguish HARD FAILURE vs SOFT OBSERVATION / DOCUMENTARY HOLD
so Ken Burns / slideshow holds do not falsely FAIL while remaining visible.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pipeline.observation.common import (
    SCHEMA_SCENE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
    unavailable,
)

logger = logging.getLogger(__name__)

TOOL_PRIMARY = "pyscenedetect"
TOOL_FALLBACK = "ffmpeg_scene"
SCHEMA_VERSION = "amp_observation_scene_boundary_v1.1"

# Soft observation / documentary hold — visible, must not alone force hard FAIL
SOFT_ISSUE_MARKERS: Tuple[str, ...] = (
    "excessive_static_hold",
    "documentary_hold",
    "ken_burns",
    "slideshow_still",
    "unexpected_cut_density",
    "missing_cut:",
    "planned_vs_actual_boundary_delta",
    "planned_vs_actual_boundary_missing_obs",
    "micro_segment_possible_false_cut",
)

# Genuine hard problems
HARD_ISSUE_MARKERS: Tuple[str, ...] = (
    "missing_or_tiny_video",
    "unreadable_media",
    "malformed_media",
    "invalid_media",
    "detector_hard_failure",
)


def scene_tool_available() -> Dict[str, Any]:
    try:
        import scenedetect

        ver = getattr(scenedetect, "__version__", None) or "unknown"
        return {
            "available": True,
            "tool": TOOL_PRIMARY,
            "import_ok": True,
            "tool_version": ver,
        }
    except Exception as exc:
        return {
            "available": False,
            "tool": TOOL_PRIMARY,
            "import_ok": False,
            "error": str(exc)[:200],
            "fallback": TOOL_FALLBACK,
            "tool_version": None,
        }


def source_media_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def classify_boundary_issue(issue: str) -> str:
    """Return 'hard' | 'soft' for a single issue string."""
    s = str(issue or "")
    for m in HARD_ISSUE_MARKERS:
        if m in s:
            return "hard"
    for m in SOFT_ISSUE_MARKERS:
        if m in s:
            return "soft"
    # Default: treat unknown structural compare issues as soft documentary-adjacent
    # unless clearly a media/detector failure (handled above).
    if s.startswith("soft:"):
        return "soft"
    return "soft" if s else "soft"


def classify_boundary_issues(issues: Sequence[str]) -> Dict[str, Any]:
    hard: List[str] = []
    soft: List[str] = []
    for i in issues or []:
        kind = classify_boundary_issue(str(i))
        if kind == "hard":
            hard.append(str(i))
        else:
            soft.append(str(i))
    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "has_hard": bool(hard),
        "has_soft": bool(soft),
    }


def _ffmpeg_scene_cuts(video_path: Path) -> List[Dict[str, Any]]:
    from pipeline.compose import ffmpeg_bin

    cmd = [
        ffmpeg_bin(),
        "-i",
        str(video_path),
        "-filter:v",
        "select='gt(scene,0.4)',showinfo",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
    cuts: List[Dict[str, Any]] = []
    for line in (r.stderr or "").splitlines():
        if "pts_time:" in line and "showinfo" in line:
            try:
                part = line.split("pts_time:")[1].split(" ")[0]
                t = float(part)
                cuts.append({"time_sec": t, "method": TOOL_FALLBACK})
            except Exception:
                continue
    return cuts


def _pyscenedetect_cuts(video_path: Path, threshold: float = 27.0) -> List[Dict[str, Any]]:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video = open_video(str(video_path))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=float(threshold)))
    sm.detect_scenes(video)
    scene_list = sm.get_scene_list()
    cuts: List[Dict[str, Any]] = []
    for i, (start, end) in enumerate(scene_list):
        cuts.append(
            {
                "index": i,
                "start_sec": float(getattr(start, "seconds", None) if getattr(start, "seconds", None) is not None else start.get_seconds()),
                "end_sec": float(getattr(end, "seconds", None) if getattr(end, "seconds", None) is not None else end.get_seconds()),
                "method": TOOL_PRIMARY,
            }
        )
    return cuts


def observe_scene_boundaries(
    video_path: Path | str,
    *,
    threshold: float = 27.0,
    allow_ffmpeg_fallback: bool = True,
) -> Dict[str, Any]:
    path = Path(video_path)
    observed_at = datetime.now(timezone.utc).isoformat()
    if not path.is_file() or path.stat().st_size < 1000:
        return {
            **unavailable(
                schema=SCHEMA_SCENE,
                tool=TOOL_PRIMARY,
                reason="INVALID_MEDIA",
                detail=str(path),
            ),
            "status": STATUS_FAIL,
            "reason": "INVALID_MEDIA",
            "issues": ["missing_or_tiny_video"],
            "hard_issues": ["missing_or_tiny_video"],
            "soft_issues": [],
            "observed_at": observed_at,
            "scenes": [],
            "metrics": {},
            "provenance": {"video_path": str(path)},
            "schema_version": SCHEMA_VERSION,
        }

    avail = scene_tool_available()
    method = TOOL_PRIMARY
    cuts: List[Dict[str, Any]] = []
    detail = ""
    tool_version = str(avail.get("tool_version") or "unknown")

    try:
        src_hash = source_media_hash(path)
    except Exception as exc:
        src_hash = f"hash_failed:{exc}"[:64]

    if avail.get("available"):
        try:
            import scenedetect

            tool_version = str(getattr(scenedetect, "__version__", None) or tool_version)
            cuts = _pyscenedetect_cuts(path, threshold=threshold)
        except Exception as exc:
            detail = str(exc)[:300]
            if not allow_ffmpeg_fallback:
                out = unavailable(
                    schema=SCHEMA_SCENE,
                    tool=TOOL_PRIMARY,
                    reason="DETECTOR_UNAVAILABLE",
                    detail=detail,
                )
                out["reason"] = "DETECTOR_UNAVAILABLE"
                out["observed_at"] = observed_at
                out["source_hash"] = src_hash
                out["tool_version"] = tool_version
                out["hard_issues"] = ["detector_hard_failure"]
                out["soft_issues"] = []
                return out
            method = TOOL_FALLBACK
    else:
        if not allow_ffmpeg_fallback:
            out = unavailable(
                schema=SCHEMA_SCENE,
                tool=TOOL_PRIMARY,
                reason="DETECTOR_UNAVAILABLE",
                detail=str(avail.get("error") or "scenedetect_not_importable"),
            )
            out["reason"] = "DETECTOR_UNAVAILABLE"
            out["observed_at"] = observed_at
            out["source_hash"] = src_hash
            return out
        method = TOOL_FALLBACK

    if method == TOOL_FALLBACK:
        try:
            raw = _ffmpeg_scene_cuts(path)
            cuts = []
            times = [0.0] + [float(c["time_sec"]) for c in raw]
            from pipeline.compose import ffprobe_duration

            dur = float(ffprobe_duration(path) or 0)
            if dur > 0 and (not times or times[-1] < dur):
                times.append(dur)
            for i in range(len(times) - 1):
                cuts.append(
                    {
                        "index": i,
                        "start_sec": times[i],
                        "end_sec": times[i + 1],
                        "method": TOOL_FALLBACK,
                    }
                )
            if not cuts and dur > 0:
                cuts = [{"index": 0, "start_sec": 0.0, "end_sec": dur, "method": TOOL_FALLBACK}]
        except Exception as exc:
            out = unavailable(
                schema=SCHEMA_SCENE,
                tool=method,
                reason="DETECTOR_UNAVAILABLE",
                detail=str(exc)[:300] or detail,
            )
            out["reason"] = "DETECTOR_UNAVAILABLE"
            out["observed_at"] = observed_at
            out["source_hash"] = src_hash
            return out

    boundary_times = sorted(
        {round(float(c.get("start_sec") or 0), 3) for c in cuts}
        | {round(float(c.get("end_sec") or 0), 3) for c in cuts}
    )
    duration_sec = 0.0
    if cuts:
        try:
            duration_sec = max(float(c.get("end_sec") or 0) for c in cuts)
        except Exception:
            duration_sec = 0.0

    issues: List[str] = [] if cuts else ["no_scenes_detected"]
    status = STATUS_PASS if cuts else STATUS_UNKNOWN
    reason = "observed" if cuts else "no_scenes_detected"

    metrics = {
        "scene_count": len(cuts),
        "boundary_count": len(boundary_times),
        "duration_sec": round(duration_sec, 3),
        "threshold": float(threshold),
        "method": method,
    }
    provenance = {
        "video_path": str(path.resolve()) if path.exists() else str(path),
        "source_hash": src_hash,
        "tool": method,
        "tool_version": tool_version,
        "threshold": float(threshold),
        "observed_at": observed_at,
        "schema_version": SCHEMA_VERSION,
        "pyscenedetect_available": bool(avail.get("available")),
    }

    return {
        "schema": SCHEMA_SCENE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "observation_executed": True,
        "provider_verified": method == TOOL_PRIMARY,
        "tool": method,
        "tool_version": tool_version,
        "pyscenedetect_available": bool(avail.get("available")),
        "video_path": str(path),
        "source_hash": src_hash,
        "observed_at": observed_at,
        "scenes": cuts,
        "boundary_times_sec": boundary_times,
        "scene_count": len(cuts),
        "issues": issues,
        "hard_issues": [],
        "soft_issues": [],
        "metrics": metrics,
        "provenance": provenance,
        "unknown_as_pass": False,
        "authority": "observation_only",
        "does_not_replace": ["DirectorPlan", "DirectedVisualBeat", "ContinuityTracker"],
        "creates_final_gate": False,
    }


def compare_planned_beats_vs_boundaries(
    *,
    planned_beats: Sequence[Dict[str, Any]],
    observed: Dict[str, Any],
    static_hold_sec: float = 10.5,
    boundary_tolerance_sec: float = 1.75,
) -> Dict[str, Any]:
    """Compare C05-S / director beat timeline to observed cuts (evidence only).

    Hard FAIL only when hard_issues present.
    Soft documentary / Ken Burns issues remain visible but do not alone FAIL.
    """
    if not observed or observed.get("status") == STATUS_UNAVAILABLE:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": observed.get("reason") if observed else "observation_missing",
            "issues": ["scene_boundary_observation_unavailable"],
            "hard_issues": ["scene_boundary_observation_unavailable"],
            "soft_issues": [],
            "unknown_as_pass": False,
            "creates_final_gate": False,
        }
    if not observed.get("observation_executed"):
        return {
            "status": STATUS_UNKNOWN,
            "reason": "scene_boundary_not_executed",
            "issues": ["scene_boundary_not_executed"],
            "hard_issues": [],
            "soft_issues": ["scene_boundary_not_executed"],
            "unknown_as_pass": False,
            "creates_final_gate": False,
        }

    issues: List[str] = []
    scenes = list(observed.get("scenes") or [])
    planned = list(planned_beats or [])

    planned_bounds: List[float] = [0.0]
    t = 0.0
    for b in planned:
        dur = float(b.get("duration_sec") or b.get("duration") or b.get("duration_target_sec") or 0)
        start = b.get("start_sec")
        end = b.get("end_sec")
        if start is not None and end is not None:
            planned_bounds.append(float(end))
            t = float(end)
        elif dur > 0:
            t += dur
            planned_bounds.append(t)
    planned_bounds = sorted(set(round(x, 3) for x in planned_bounds))

    obs_bounds = [float(x) for x in (observed.get("boundary_times_sec") or [])]

    if planned and len(planned) > 1 and len(scenes) <= 1:
        # Documentary / single-shot still may lack mid-cuts — soft hold, not hard FAIL
        issues.append("missing_cut:expected_multi_beat_single_observed_scene")
        issues.append("documentary_hold:single_scene_multi_beat")

    false_cut_candidates: List[Dict[str, Any]] = []
    if planned and len(scenes) > max(3, len(planned) * 2):
        issues.append(f"unexpected_cut_density:observed={len(scenes)}_planned={len(planned)}")
        false_cut_candidates.append(
            {
                "reason": "cut_density_above_2x_planned",
                "observed_scene_count": len(scenes),
                "planned_beat_count": len(planned),
                "classification": "soft",
            }
        )

    for sc in scenes:
        hold = float(sc.get("end_sec") or 0) - float(sc.get("start_sec") or 0)
        if hold >= static_hold_sec:
            # Long still / slideshow / documentary — soft observation
            issues.append(f"excessive_static_hold:{hold:.1f}s")
            issues.append(f"documentary_hold:static:{hold:.1f}s")
        if 0 < hold < 0.35:
            issues.append(f"ken_burns_or_false_flash:micro_segment:{hold:.3f}s")
            false_cut_candidates.append(
                {
                    "reason": "micro_segment_possible_false_cut",
                    "start_sec": sc.get("start_sec"),
                    "end_sec": sc.get("end_sec"),
                    "hold_sec": round(hold, 3),
                    "classification": "soft",
                    "hint": "ken_burns_or_flash",
                }
            )

    for pb in planned_bounds[1:-1] if len(planned_bounds) > 2 else []:
        if not obs_bounds:
            issues.append("planned_vs_actual_boundary_missing_obs")
            break
        nearest = min(obs_bounds, key=lambda x: abs(x - pb))
        if abs(nearest - pb) > boundary_tolerance_sec:
            issues.append(f"planned_vs_actual_boundary_delta:{pb:.2f}->{nearest:.2f}")

    if not planned:
        issues.append("no_planned_beats")

    # Deduplicate while preserving order
    issues = list(dict.fromkeys(issues))
    classified = classify_boundary_issues(issues)
    hard = list(classified["hard_issues"])
    soft = list(classified["soft_issues"])

    # no_planned_beats alone is soft informational
    if "no_planned_beats" in soft or "no_planned_beats" in hard:
        soft = [i for i in soft if i != "no_planned_beats"] + (
            ["no_planned_beats"] if "no_planned_beats" in issues else []
        )
        hard = [i for i in hard if i != "no_planned_beats"]

    if hard:
        status = STATUS_FAIL
        reason = "hard_boundary_issues"
    elif soft and not scenes:
        status = STATUS_UNKNOWN
        reason = "soft_issues_without_scenes"
    elif soft:
        # Soft documentary / Ken Burns — PASS observation with soft issues visible
        status = STATUS_PASS
        reason = "soft_documentary_or_motion_hold"
    elif scenes:
        status = STATUS_PASS
        reason = "observed_ok"
    else:
        status = STATUS_UNKNOWN
        reason = "no_scenes"

    return {
        "status": status,
        "reason": reason,
        "issues": issues,
        "hard_issues": hard,
        "soft_issues": soft,
        "soft_issue_visible": bool(soft),
        "classification": classified,
        "planned_beat_count": len(planned),
        "observed_scene_count": len(scenes),
        "planned_bounds_sec": planned_bounds,
        "observed_bounds_sec": obs_bounds,
        "false_cut_candidates": false_cut_candidates,
        "unknown_as_pass": False,
        "creates_final_gate": False,
        "method": "PLANNED_BEATS_VS_SCENEDETECT",
        "does_not_replace": ["DirectorPlan", "DirectedVisualBeat", "ContinuityTracker"],
    }
