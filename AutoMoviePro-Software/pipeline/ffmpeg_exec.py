"""Central FFmpeg executor with timeout, kill, probe, and structured result."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class FFmpegResult:
    ok: bool
    command: List[str]
    exit_code: Optional[int]
    stdout: str
    stderr: str
    elapsed_sec: float
    timed_out: bool = False
    killed: bool = False
    pid: Optional[int] = None
    classified: str = "ok"  # ok|timeout|nonzero|spawn_error

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _bin(kind: str = "ffmpeg") -> str:
    from pipeline.compose import ffmpeg_bin, ffprobe_bin

    return ffmpeg_bin() if kind == "ffmpeg" else ffprobe_bin()


def _kill_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
    except Exception as exc:
        logger.warning("ffmpeg kill failed: %s", exc)
        try:
            proc.kill()
        except Exception:
            pass


def run_ffmpeg(
    args: Sequence[str],
    *,
    timeout_sec: float = 120.0,
    cwd: Optional[str] = None,
    include_bin: bool = True,
) -> FFmpegResult:
    """
    Run ffmpeg with hard deadline. On hang: terminate → kill tree → classify timeout.
    """
    cmd: List[str] = ([_bin("ffmpeg")] if include_bin else []) + [str(a) for a in args]
    started = time.monotonic()
    try:
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": cwd,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except Exception as exc:
        return FFmpegResult(
            ok=False,
            command=cmd,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            elapsed_sec=0.0,
            classified="spawn_error",
        )

    timed_out = False
    killed = False
    try:
        stdout, stderr = proc.communicate(timeout=max(0.5, float(timeout_sec)))
    except subprocess.TimeoutExpired:
        timed_out = True
        killed = True
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
    elapsed = time.monotonic() - started
    code = proc.returncode
    if timed_out:
        classified = "timeout"
        ok = False
    elif code == 0:
        classified = "ok"
        ok = True
    else:
        classified = "nonzero"
        ok = False
    return FFmpegResult(
        ok=ok,
        command=cmd,
        exit_code=code,
        stdout=(stdout or "")[-4000:],
        stderr=(stderr or "")[-8000:],
        elapsed_sec=round(elapsed, 3),
        timed_out=timed_out,
        killed=killed,
        pid=proc.pid,
        classified=classified,
    )


def run_ffprobe(
    args: Sequence[str],
    *,
    timeout_sec: float = 30.0,
) -> FFmpegResult:
    cmd: List[str] = [_bin("ffprobe")] + [str(a) for a in args]
    started = time.monotonic()
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(0.5, float(timeout_sec)),
        )
        ok = r.returncode == 0
        return FFmpegResult(
            ok=ok,
            command=cmd,
            exit_code=r.returncode,
            stdout=(r.stdout or "")[-4000:],
            stderr=(r.stderr or "")[-4000:],
            elapsed_sec=round(time.monotonic() - started, 3),
            classified="ok" if ok else "nonzero",
        )
    except subprocess.TimeoutExpired as exc:
        return FFmpegResult(
            ok=False,
            command=cmd,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            elapsed_sec=round(time.monotonic() - started, 3),
            timed_out=True,
            killed=True,
            classified="timeout",
        )
    except Exception as exc:
        return FFmpegResult(
            ok=False,
            command=cmd,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            elapsed_sec=0.0,
            classified="spawn_error",
        )


def safe_ffprobe_duration(path: Path, *, timeout_sec: float = 30.0) -> float:
    """Always initializes duration; exception path returns 0.0."""
    path = Path(path)
    if not path.exists():
        return 0.0
    r = run_ffprobe(
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout_sec=timeout_sec,
    )
    try:
        return float((r.stdout or "").strip() or 0.0) if r.ok else 0.0
    except Exception:
        return 0.0
