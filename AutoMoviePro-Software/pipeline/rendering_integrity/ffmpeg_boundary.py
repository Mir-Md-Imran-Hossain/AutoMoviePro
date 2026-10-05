"""Canonical FFmpeg execution boundary for Phase-08 provenance.

Promotes pipeline.ffmpeg_exec to production-documented authority.
Does NOT replace scene_builder compose internals in one rewrite —
new/validated compositions SHOULD call run_controlled_ffmpeg.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Sequence

from pipeline.ffmpeg_exec import FFmpegResult, run_ffmpeg, run_ffprobe
from pipeline.rendering_integrity.filtergraph import build_explicit_ffmpeg_args

logger = logging.getLogger(__name__)


def run_controlled_ffmpeg(
    args: Sequence[str],
    *,
    timeout_sec: float = 300.0,
    work_dir: Optional[Path] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Structured argv only — capture provenance without secrets."""
    result: FFmpegResult = run_ffmpeg(args, timeout_sec=timeout_sec, cwd=str(work_dir) if work_dir else None)
    # Redact obvious secret-like tokens from command log
    safe_cmd = []
    for a in result.command:
        s = str(a)
        if any(k in s.lower() for k in ("api_key", "token=", "password", "secret")):
            safe_cmd.append("[REDACTED]")
        else:
            safe_cmd.append(s)
    out = {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "classified": result.classified,
        "elapsed_sec": result.elapsed_sec,
        "stderr_summary": (result.stderr or "")[-1500:],
        "command": safe_cmd,
        "provenance": dict(provenance or {}),
        "authority": "ffmpeg_exec.run_ffmpeg",
    }
    if work_dir is not None:
        try:
            import json

            p = Path(work_dir) / "ffmpeg_run_provenance.json"
            p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("ffmpeg provenance persist skipped: %s", exc)
    return out


def compose_args_from_inputs(
    inputs: list[str],
    output: str,
    *,
    filter_complex: str = "",
    map_video: str = "[vout]",
    map_audio: str = "[aout]",
) -> list[str]:
    return build_explicit_ffmpeg_args(
        inputs=inputs,
        filter_complex=filter_complex,
        output=output,
        map_video=map_video,
        map_audio=map_audio,
    )


def probe_version(work_dir: Optional[Path] = None) -> dict[str, Any]:
    r = run_ffprobe(["-version"], timeout_sec=10.0)
    # ffprobe -version writes to stdout typically via ffmpeg style; try ffmpeg
    from pipeline.ffmpeg_exec import run_ffmpeg as _rf

    v = _rf(["-version"], timeout_sec=10.0, include_bin=True)
    version_line = (v.stdout or v.stderr or "").splitlines()[0] if (v.stdout or v.stderr) else "unknown"
    return {"ffmpeg_version_line": version_line[:200], "ok": v.ok or r.ok}
