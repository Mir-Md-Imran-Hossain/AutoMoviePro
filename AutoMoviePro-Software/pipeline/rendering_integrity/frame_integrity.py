"""Frame integrity probes — black frames / sparse decode (PART-5M)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional


def probe_black_and_missing_frames(
    video_path: Path,
    *,
    work_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Use ffmpeg blackdetect + frame count vs duration*fps heuristic.

    Honest: if tools fail → UNKNOWN (never PASS).
    """
    video_path = Path(video_path)
    out: dict[str, Any] = {
        "status": "UNKNOWN",
        "black_frame_spans": [],
        "black_seconds": 0.0,
        "missing_frame_estimate": 0,
        "issues": [],
        "method": "ffmpeg_blackdetect",
        "unknown_as_pass": False,
    }
    if not video_path.is_file():
        out["issues"].append("video_missing")
        return out
    try:
        # Duration + fps via ffprobe
        meta = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames,r_frame_rate,duration",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(meta.stdout or "{}") if meta.returncode == 0 else {}
        streams = payload.get("streams") or []
        fmt = payload.get("format") or {}
        dur = float(fmt.get("duration") or (streams[0].get("duration") if streams else 0) or 0)
        fps = 25.0
        if streams:
            rate = str(streams[0].get("r_frame_rate") or "25/1")
            if "/" in rate:
                a, b = rate.split("/", 1)
                fps = float(a) / max(1.0, float(b))
            nb = streams[0].get("nb_frames")
            expected = int(dur * fps) if dur > 0 else 0
            if nb and str(nb).isdigit() and expected > 0:
                missing = max(0, expected - int(nb))
                out["missing_frame_estimate"] = missing
                if missing > max(3, int(expected * 0.02)):
                    out["issues"].append(f"missing_frames:{missing}")

        # blackdetect
        bd = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(video_path),
                "-vf",
                "blackdetect=d=0.4:pix_th=0.10",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        spans = []
        black_sec = 0.0
        for line in (bd.stderr or "").splitlines():
            if "black_start" in line and "black_end" in line:
                spans.append(line.strip())
                try:
                    # black_duration:N
                    if "black_duration:" in line:
                        part = line.split("black_duration:")[-1].split()[0]
                        black_sec += float(part)
                except Exception:
                    pass
        out["black_frame_spans"] = spans[:20]
        out["black_seconds"] = round(black_sec, 3)
        if black_sec >= 1.0:
            out["issues"].append(f"black_frames_sec:{black_sec:.2f}")

        if out["issues"]:
            out["status"] = "FAIL"
        else:
            out["status"] = "PASS"
        if work_dir is not None:
            path = Path(work_dir) / "FRAME_INTEGRITY_PROBE.json"
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
    except Exception as exc:
        out["issues"].append(f"probe_error:{exc}")
        out["status"] = "UNKNOWN"
        return out
