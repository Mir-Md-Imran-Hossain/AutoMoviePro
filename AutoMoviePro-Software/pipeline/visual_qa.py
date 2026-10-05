"""Visual QA with mandatory pixel evidence (PASS / FAIL / UNKNOWN).

Protocol:
- Extract frames at 0% / 25% / 50% / 75% / 95%
- No actual pixel evidence → UNKNOWN (never PASS)
- No VLM → subject/claim match UNKNOWN (never visual PASS)
- Hard FAIL: static_visual, black frames, missing media
"""
from __future__ import annotations

import json
import logging
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

FRAME_PCTS = (0.0, 0.25, 0.50, 0.75, 0.95)
MOTION_FAIL_THRESHOLD = 0.012  # mean abs diff ratio across sample pairs
BLACK_LUMA_MAX = 18  # 0-255 mean luma treated as black


def _ffmpeg() -> str:
    from pipeline.compose import ffmpeg_bin

    return ffmpeg_bin()


def _ffprobe_duration(path: Path) -> float:
    from pipeline.compose import ffprobe_duration

    return float(ffprobe_duration(path) or 0.0)


def extract_evidence_frames(
    media: Path,
    dest_dir: Path,
    *,
    pcts: Sequence[float] = FRAME_PCTS,
) -> Dict[str, Any]:
    """Extract JPEG frames at percentages. Returns paths + probe meta."""
    media = Path(media)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dur = max(0.0, _ffprobe_duration(media))
    if not media.exists() or dur < 0.05:
        return {
            "ok": False,
            "verdict": "FAIL",
            "issues": ["missing_or_zero_duration"],
            "frames": [],
            "duration": dur,
        }
    frames: List[Dict[str, Any]] = []
    for i, pct in enumerate(pcts):
        t = max(0.0, min(dur - 0.04, dur * float(pct)))
        out = dest_dir / f"frame_{i:02d}_{int(pct * 100):02d}pct.jpg"
        cmd = [
            _ffmpeg(),
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(out),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            ok = r.returncode == 0 and out.exists() and out.stat().st_size > 200
            frames.append(
                {
                    "pct": pct,
                    "t": round(t, 3),
                    "path": str(out) if ok else "",
                    "ok": ok,
                    "bytes": out.stat().st_size if out.exists() else 0,
                }
            )
        except Exception as exc:
            frames.append({"pct": pct, "t": round(t, 3), "path": "", "ok": False, "error": str(exc)[:120]})
    ok_n = sum(1 for f in frames if f.get("ok"))
    return {
        "ok": ok_n >= 3,
        "verdict": "PASS" if ok_n >= 3 else "FAIL",
        "issues": [] if ok_n >= 3 else ["insufficient_frame_evidence"],
        "frames": frames,
        "duration": round(dur, 3),
        "extracted": ok_n,
    }


def _read_jpeg_gray_approx(path: Path, sample: int = 32) -> Optional[List[int]]:
    """Decode via ffmpeg to raw gray; return flattened sample grid."""
    path = Path(path)
    if not path.exists():
        return None
    raw = path.with_suffix(".gray.raw")
    try:
        cmd = [
            _ffmpeg(),
            "-y",
            "-i",
            str(path),
            "-vf",
            f"scale={sample}:{sample},format=gray",
            "-f",
            "rawvideo",
            str(raw),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if r.returncode != 0 or not raw.exists():
            return None
        data = raw.read_bytes()
        if len(data) < sample * sample:
            return None
        return list(data[: sample * sample])
    except Exception:
        return None
    finally:
        try:
            raw.unlink(missing_ok=True)
        except Exception:
            pass


def _mean_luma(gray: Sequence[int]) -> float:
    if not gray:
        return 0.0
    return sum(gray) / float(len(gray))


def _frame_diff_ratio(a: Sequence[int], b: Sequence[int]) -> float:
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    s = sum(abs(int(a[i]) - int(b[i])) for i in range(n))
    return s / float(n * 255)


def analyze_frames(frame_paths: Sequence[Path]) -> Dict[str, Any]:
    grays: List[List[int]] = []
    paths_ok: List[str] = []
    for p in frame_paths:
        g = _read_jpeg_gray_approx(Path(p))
        if g:
            grays.append(g)
            paths_ok.append(str(p))
    if len(grays) < 2:
        return {
            "motion_score": 0.0,
            "motion_present": False,
            "static_visual": True,
            "black_frames": 0,
            "artifact_detected": True,
            "pixel_evidence": False,
            "issues": ["no_pixel_evidence"],
        }
    diffs = [_frame_diff_ratio(grays[i], grays[i + 1]) for i in range(len(grays) - 1)]
    motion = sum(diffs) / max(1, len(diffs))
    black_n = sum(1 for g in grays if _mean_luma(g) <= BLACK_LUMA_MAX)
    static = motion < MOTION_FAIL_THRESHOLD
    return {
        "motion_score": round(motion, 5),
        "motion_present": not static,
        "static_visual": static,
        "black_frames": black_n,
        "artifact_detected": False,
        "pixel_evidence": True,
        "pair_diffs": [round(d, 5) for d in diffs],
        "issues": [],
        "frames_analyzed": len(grays),
    }


def evaluate_visual_qa(
    media: Any,
    *,
    work_dir: Any = None,
    contract: Optional[Dict[str, Any]] = None,
    dialogue: str = "",
    vlm_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Visual critic output schema (protocol §43) + verdict PASS|FAIL|UNKNOWN.
    """
    path = Path(str(media)) if media else None
    result: Dict[str, Any] = {
        "check": "visual_qa",
        "subject_match": None,
        "action_match": None,
        "claim_match": None,
        "continuity_match": None,
        "motion_present": False,
        "wrong_subject": False,
        "generic_broll": False,
        "static_visual": False,
        "artifact_detected": False,
        "verdict": "UNKNOWN",
        "passed": False,
        "issues": [],
        "critical_issues": [],
        "frames": [],
        "pixel_evidence": False,
        "vlm_used": bool(vlm_result),
    }
    if path is None or not path.exists():
        result["issues"] = ["missing_media"]
        result["critical_issues"] = ["visual_qa_fail"]
        result["verdict"] = "FAIL"
        return result

    dest = Path(str(work_dir)) if work_dir else path.parent / "_visual_qa"
    dest = dest / f"qa_{path.stem}"
    extract = extract_evidence_frames(path, dest)
    result["frames"] = extract.get("frames") or []
    if not extract.get("ok"):
        result["issues"] = list(extract.get("issues") or ["frame_extract_failed"])
        result["critical_issues"] = ["visual_qa_fail"]
        result["verdict"] = "FAIL"
        result["artifact_detected"] = True
        return result

    frame_paths = [Path(f["path"]) for f in result["frames"] if f.get("ok") and f.get("path")]
    analysis = analyze_frames(frame_paths)
    result["pixel_evidence"] = bool(analysis.get("pixel_evidence"))
    result["motion_present"] = bool(analysis.get("motion_present"))
    result["static_visual"] = bool(analysis.get("static_visual"))
    result["motion_score"] = analysis.get("motion_score")
    result["artifact_detected"] = bool(analysis.get("artifact_detected"))
    if int(analysis.get("black_frames") or 0) >= 3:
        result["issues"].append("black_frame_majority")
        result["critical_issues"] = ["visual_qa_fail"]
        result["verdict"] = "FAIL"
        return result
    if analysis.get("static_visual"):
        result["issues"].append(f"static_visual:motion={analysis.get('motion_score')}")
        result["critical_issues"] = ["static_visual"]
        result["verdict"] = "FAIL"
        result["passed"] = False
        return result
    if not analysis.get("pixel_evidence"):
        result["issues"].append("NO_ACTUAL_PIXEL_EVIDENCE")
        result["verdict"] = "UNKNOWN"
        return result

    # VLM optional — without it subject/claim stay UNKNOWN → no visual PASS
    if vlm_result and isinstance(vlm_result, dict):
        result["subject_match"] = float(vlm_result.get("subject_match") or 0.0)
        result["action_match"] = float(vlm_result.get("action_match") or 0.0)
        result["claim_match"] = float(vlm_result.get("claim_match") or 0.0)
        result["continuity_match"] = float(vlm_result.get("continuity_match") or 0.0)
        result["wrong_subject"] = bool(vlm_result.get("wrong_subject"))
        result["generic_broll"] = bool(vlm_result.get("generic_broll"))
        if result["wrong_subject"] or result["generic_broll"]:
            result["verdict"] = "FAIL"
            result["critical_issues"] = ["wrong_subject" if result["wrong_subject"] else "generic_broll"]
            return result
        if min(result["subject_match"], result["claim_match"]) < 0.45:
            result["verdict"] = "FAIL"
            result["issues"].append("claim_or_subject_mismatch")
            result["critical_issues"] = ["claim_mismatch"]
            return result
        result["verdict"] = "PASS"
        result["passed"] = True
        return result

    # Pixel motion OK but no VLM → UNKNOWN (protocol §45)
    result["issues"].append("vlm_unavailable_subject_unverified")
    result["verdict"] = "UNKNOWN"
    result["passed"] = False
    # Contract hints stored for later VLM
    if contract:
        result["contract_claim"] = str(contract.get("primary_claim") or "")[:160]
        result["contract_must_show"] = (contract.get("visual_evidence") or {}).get("must_show")
    if dialogue:
        result["dialogue_sample"] = dialogue[:120]
    return result


def visual_qa_blocks_ship(qa: Dict[str, Any]) -> bool:
    """FAIL always blocks; UNKNOWN blocks (no visual PASS without evidence/VLM)."""
    v = str(qa.get("verdict") or "UNKNOWN").upper()
    return v != "PASS"
