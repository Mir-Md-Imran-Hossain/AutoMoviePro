"""Perceptual quality observation via FFmpeg libvmaf (optional filter).

Does NOT replace FFmpeg/render authority. Emits VMAF evidence only.
No reference → UNKNOWN (never invented PASS).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.observation.common import (
    SCHEMA_VMAF,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
    unavailable,
)

logger = logging.getLogger(__name__)

TOOL = "ffmpeg_libvmaf"


def vmaf_tool_available() -> Dict[str, Any]:
    try:
        from pipeline.compose import ffmpeg_bin

        r = subprocess.run(
            [ffmpeg_bin(), "-filters"],
            capture_output=True,
            text=True,
            errors="ignore",
        )
        blob = (r.stdout or "") + (r.stderr or "")
        ok = "libvmaf" in blob
        return {"available": ok, "tool": TOOL, "ffmpeg": ffmpeg_bin()}
    except Exception as exc:
        return {"available": False, "tool": TOOL, "error": str(exc)[:200]}


def observe_perceptual_quality(
    distorted_path: Path | str,
    *,
    reference_path: Optional[Path | str] = None,
    n_threads: int = 2,
) -> Dict[str, Any]:
    """Compute VMAF of distorted vs reference via existing FFmpeg binary.

    If reference is missing → status UNKNOWN (observation not possible).
    """
    dist = Path(distorted_path)
    if not dist.is_file() or dist.stat().st_size < 1000:
        return {
            **unavailable(
                schema=SCHEMA_VMAF,
                tool=TOOL,
                reason="missing_or_tiny_distorted",
                detail=str(dist),
            ),
            "status": STATUS_FAIL,
            "issues": ["missing_or_tiny_distorted"],
        }

    if reference_path is None or not Path(reference_path).is_file():
        return {
            "schema": SCHEMA_VMAF,
            "status": STATUS_UNKNOWN,
            "observation_executed": False,
            "provider_verified": False,
            "tool": TOOL,
            "reason": "reference_media_unavailable",
            "issues": ["vmaf_reference_unavailable"],
            "unknown_as_pass": False,
            "authority": "observation_only",
            "does_not_replace": ["FFmpeg", "compose", "rendering_integrity"],
            "distorted_path": str(dist),
            "reference_path": None,
        }

    ref = Path(reference_path)
    avail = vmaf_tool_available()
    if not avail.get("available"):
        return unavailable(
            schema=SCHEMA_VMAF,
            tool=TOOL,
            reason="libvmaf_filter_unavailable",
            detail=str(avail.get("error") or "libvmaf_not_in_ffmpeg_filters"),
        )

    from pipeline.compose import ffmpeg_bin

    with tempfile.TemporaryDirectory() as td:
        # Prefer ASCII path without drive-colon issues for libvmaf log_path
        log_path = Path(td) / "vmaf.json"
        log_arg = str(log_path.resolve()).replace("\\", "/")
        if len(log_arg) >= 2 and log_arg[1] == ":":
            log_arg = log_arg[0] + "\\:" + log_arg[2:]
        filt = (
            f"[0:v]scale=1280:720:flags=bicubic,setsar=1[ref];"
            f"[1:v]scale=1280:720:flags=bicubic,setsar=1[dist];"
            f"[ref][dist]libvmaf=log_fmt=json:log_path={log_arg}:"
            f"n_threads={max(1, int(n_threads))}"
        )
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(ref),
            "-i",
            str(dist),
            "-lavfi",
            filt,
            "-f",
            "null",
            "-",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=180)
        except subprocess.TimeoutExpired as exc:
            return unavailable(
                schema=SCHEMA_VMAF,
                tool=TOOL,
                reason="runtime_timeout",
                detail=str(exc)[:200],
            )
        except Exception as exc:
            return unavailable(
                schema=SCHEMA_VMAF,
                tool=TOOL,
                reason="runtime_failed",
                detail=str(exc)[:300],
            )

        if r.returncode != 0 and not log_path.is_file():
            err = (r.stderr or "")[-400:]
            return unavailable(
                schema=SCHEMA_VMAF,
                tool=TOOL,
                reason="ffmpeg_libvmaf_failed",
                detail=err,
            )

        vmaf_score = None
        metrics: Dict[str, Any] = {}
        if log_path.is_file():
            try:
                data = json.loads(log_path.read_text(encoding="utf-8"))
                pooled = data.get("pooled_metrics") or {}
                vmaf_block = pooled.get("vmaf") or {}
                vmaf_score = vmaf_block.get("min")  # prefer mean if present
                if "mean" in vmaf_block:
                    vmaf_score = vmaf_block.get("mean")
                metrics = {"pooled_metrics": pooled}
            except Exception as exc:
                # Fallback parse from stderr
                m = re.search(r"VMAF score:\s*([0-9.]+)", r.stderr or "")
                if m:
                    vmaf_score = float(m.group(1))
                else:
                    return unavailable(
                        schema=SCHEMA_VMAF,
                        tool=TOOL,
                        reason="vmaf_log_parse_failed",
                        detail=str(exc)[:200],
                    )
        else:
            m = re.search(r"VMAF score:\s*([0-9.]+)", r.stderr or "")
            if m:
                vmaf_score = float(m.group(1))

    if vmaf_score is None:
        return {
            "schema": SCHEMA_VMAF,
            "status": STATUS_UNKNOWN,
            "observation_executed": True,
            "provider_verified": False,
            "tool": TOOL,
            "issues": ["vmaf_score_unobserved"],
            "unknown_as_pass": False,
            "authority": "observation_only",
            "distorted_path": str(dist),
            "reference_path": str(ref),
        }

    score = float(vmaf_score)
    issues: list[str] = []
    # Observation quality band — does NOT alone approve publishability
    if score >= 70:
        status = STATUS_PASS
    elif score >= 40:
        status = STATUS_UNKNOWN
        issues = [f"vmaf_marginal:{score:.2f}"]
    else:
        status = STATUS_FAIL
        issues = [f"vmaf_low:{score:.2f}"]

    return {
        "schema": SCHEMA_VMAF,
        "status": status,
        "observation_executed": True,
        "provider_verified": True,
        "tool": TOOL,
        "vmaf": score,
        "metrics": metrics,
        "issues": issues,
        "unknown_as_pass": False,
        "authority": "observation_only",
        "does_not_replace": ["FFmpeg", "compose", "rendering_integrity"],
        "creates_render_engine": False,
        "distorted_path": str(dist),
        "reference_path": str(ref),
    }
