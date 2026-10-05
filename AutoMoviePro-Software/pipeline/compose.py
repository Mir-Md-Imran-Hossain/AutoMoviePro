from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# H3 DEF-H3-004: process-local ffprobe duration cache (path+mtime+size)
_FFPROBE_DURATION_CACHE: dict[str, float] = {}


def _project_roots() -> list[Path]:
    """Search roots for bundled media tools (source tree + PyInstaller frozen).

    Preserves Phase-10 project-relative discovery; adds frozen exe/_MEIPASS roots.
    """
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(str(meipass)))
    roots.append(Path(__file__).resolve().parents[1])
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _project_root() -> Path:
    return _project_roots()[0]


def _env_bin(keys: tuple[str, ...]) -> Optional[str]:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v and Path(v).is_file():
            return str(Path(v).resolve())
    return None


def _root_bin(exe_name: str) -> Optional[str]:
    root = (os.environ.get("AMP_FFMPEG_ROOT") or os.environ.get("FFMPEG_ROOT") or "").strip()
    if not root:
        return None
    base = Path(root)
    for cand in (base / "bin" / exe_name, base / exe_name):
        if cand.is_file():
            return str(cand.resolve())
    return None


def _bundled_bin(exe_name: str) -> Optional[str]:
    """Locate project-bundled FFmpeg distributions (no machine-specific absolute paths).

    Search order (relative to each project root):
    1. tools/ffmpeg/**
    2. ffmpeg-*/**/bin/<exe>  (e.g. ffmpeg-8.1.1-full_build)
    """
    for root in _project_roots():
        tools = root / "tools" / "ffmpeg"
        if tools.is_dir():
            hits = sorted(tools.rglob(exe_name))
            if hits:
                return str(hits[0].resolve())
        for dist in sorted(root.glob("ffmpeg-*")):
            if not dist.is_dir():
                continue
            for cand in (dist / "bin" / exe_name,):
                if cand.is_file():
                    return str(cand.resolve())
            nested = sorted(dist.rglob(f"bin/{exe_name}"))
            if nested:
                return str(nested[0].resolve())
            hits = sorted(dist.rglob(exe_name))
            if hits:
                return str(hits[0].resolve())
    return None


def ffmpeg_bin() -> str:
    """Prefer AMP_FFMPEG_BIN / AMP_FFMPEG_ROOT/bin, then bundled distributions, then PATH."""
    env = _env_bin(("AMP_FFMPEG_BIN", "FFMPEG_BINARY", "FFMPEG_PATH"))
    if env:
        return env
    rooted = _root_bin("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if rooted:
        return rooted
    bundled = _bundled_bin("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if bundled:
        return bundled
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    """Prefer AMP_FFPROBE_BIN / AMP_FFMPEG_ROOT/bin, then bundled distributions, then PATH.

    FFmpeg and ffprobe are discovered independently — never treat them as one capability.
    """
    env = _env_bin(("AMP_FFPROBE_BIN", "FFPROBE_BINARY", "FFPROBE_PATH"))
    if env:
        return env
    rooted = _root_bin("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if rooted:
        return rooted
    bundled = _bundled_bin("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if bundled:
        return bundled
    return shutil.which("ffprobe") or "ffprobe"


def _bin_actually_runs(path: str, *, kind: str) -> bool:
    p = Path(path)
    if not p.is_file() and shutil.which(path) is None:
        # bare name may still resolve via PATH at exec time
        if path in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
            which = shutil.which(path.replace(".exe", "") if os.name != "nt" else path)
            if not which:
                return False
            path = which
        else:
            return False
    try:
        r = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        return r.returncode == 0
    except Exception:
        return False


def probe_media_tool_capability() -> dict:
    """Explicit, separate FFMPEG_AVAILABLE / FFPROBE_AVAILABLE (AMP-004 Phase-09)."""
    ff = ffmpeg_bin()
    fp = ffprobe_bin()
    ff_ok = _bin_actually_runs(ff, kind="ffmpeg")
    fp_ok = _bin_actually_runs(fp, kind="ffprobe")
    return {
        "FFMPEG_AVAILABLE": bool(ff_ok),
        "FFPROBE_AVAILABLE": bool(fp_ok),
        "ffmpeg_path": ff,
        "ffprobe_path": fp,
        "ffmpeg_source": _classify_source(ff, "ffmpeg"),
        "ffprobe_source": _classify_source(fp, "ffprobe"),
        "method": "DETERMINISTIC",
    }


def _tool_version_line(path: str) -> str:
    try:
        r = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode != 0:
            return "UNKNOWN"
        line = (r.stdout or r.stderr or "").splitlines()
        return (line[0] if line else "UNKNOWN").strip()[:200]
    except Exception:
        return "UNKNOWN"


def media_tool_versions() -> dict:
    """Safe version strings for release identity (no secrets)."""
    ff = ffmpeg_bin()
    fp = ffprobe_bin()
    return {
        "ffmpeg_version": _tool_version_line(ff) if _bin_actually_runs(ff, kind="ffmpeg") else "ABSENT",
        "ffprobe_version": _tool_version_line(fp) if _bin_actually_runs(fp, kind="ffprobe") else "ABSENT",
    }


def _classify_source(path: str, kind: str) -> str:
    p = str(path).lower().replace("\\", "/")
    if os.environ.get(f"AMP_{kind.upper()}_BIN") or os.environ.get(f"{kind.upper()}_BINARY"):
        return "env"
    if "tools/ffmpeg" in p or "/ffmpeg-" in p or "\\ffmpeg-" in p.replace("/", "\\"):
        return "bundled"
    if "ffmpeg-" in p and f"/{kind}" in p.replace("\\", "/"):
        return "bundled"
    if os.environ.get("AMP_FFMPEG_ROOT") or os.environ.get("FFMPEG_ROOT"):
        return "env_root"
    if path in (kind, f"{kind}.exe"):
        return "path_or_missing"
    return "path"


def ffprobe_duration(path: Path) -> float:
    """Return media duration seconds. H3: cache by path+mtime+size to avoid repeat probes."""
    p = Path(path)
    cache_key = ""
    try:
        st = p.stat()
        cache_key = f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}"
        hit = _FFPROBE_DURATION_CACHE.get(cache_key)
        if hit is not None:
            return float(hit)
    except Exception:
        cache_key = ""

    ffprobe = ffprobe_bin()
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            stderr=subprocess.STDOUT,
            text=True,
        )
        dur = float(out.strip() or 0)
    except Exception:
        dur = 0.0
    if cache_key:
        _FFPROBE_DURATION_CACHE[cache_key] = dur
        # Bound memory: drop oldest half if oversized
        if len(_FFPROBE_DURATION_CACHE) > 256:
            for k in list(_FFPROBE_DURATION_CACHE.keys())[:128]:
                _FFPROBE_DURATION_CACHE.pop(k, None)
    return dur


def clear_ffprobe_duration_cache() -> None:
    _FFPROBE_DURATION_CACHE.clear()


def download_file(url: str, dest: Path) -> Path:
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "AutoMoviePro/1.0 (documentary reference still; +https://localhost)",
        "Accept": "image/*,*/*",
    }
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


_BEST_H264_ENCODER: Optional[str] = None


def get_h264_encoder() -> str:
    """Auto-detect hardware accelerated video encoder (NVENC -> QSV -> libx264)."""
    global _BEST_H264_ENCODER
    if _BEST_H264_ENCODER is not None:
        return _BEST_H264_ENCODER

    forced = (os.environ.get("AMP_VIDEO_ENCODER") or "").strip()
    if forced:
        _BEST_H264_ENCODER = forced
        return _BEST_H264_ENCODER

    try:
        fb = ffmpeg_bin()
        # Test NVENC first (NVIDIA)
        r_nvenc = subprocess.run(
            [fb, "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True,
            timeout=3,
        )
        if r_nvenc.returncode == 0:
            logger.info("Hardware GPU acceleration active: using h264_nvenc encoder")
            _BEST_H264_ENCODER = "h264_nvenc"
            return _BEST_H264_ENCODER

        # Test QSV second (Intel)
        r_qsv = subprocess.run(
            [fb, "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-c:v", "h264_qsv", "-f", "null", "-"],
            capture_output=True,
            timeout=3,
        )
        if r_qsv.returncode == 0:
            logger.info("Hardware GPU acceleration active: using h264_qsv encoder")
            _BEST_H264_ENCODER = "h264_qsv"
            return _BEST_H264_ENCODER
    except Exception as exc:
        logger.debug("Hardware encoder detection skipped: %s", exc)

    _BEST_H264_ENCODER = "libx264"
    return _BEST_H264_ENCODER


def make_color_clip(dest: Path, seconds: float, size: str = "1920x1080") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoder = get_h264_encoder()
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x122028:s={size}:d={seconds}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        str(seconds),
        "-c:v",
        encoder,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(dest),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    return dest


def concat_clips(clips: List[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lst = dest.with_suffix(".txt")
    lst.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c",
        "copy",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # re-encode fallback
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dest),
        ]
        subprocess.run(cmd, check=False, capture_output=True)
    return dest


def prepend_intro(intro: Optional[Path], main: Path, dest: Path) -> Path:
    if intro and intro.exists():
        return concat_clips([intro, main], dest)
    shutil.copy2(main, dest)
    return dest


def overlay_logo(video: Path, logo: Optional[Path], dest: Path) -> Path:
    if not logo or not logo.exists():
        shutil.copy2(video, dest)
        return dest
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-i",
        str(logo),
        "-filter_complex",
        "[1:v]scale=120:-1[logo];[0:v][logo]overlay=W-w-20:20",
        "-c:a",
        "copy",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy2(video, dest)
    return dest


def trim_to_max(video: Path, max_seconds: int, dest: Path) -> Path:
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-t",
        str(max_seconds),
        "-c",
        "copy",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(video),
            "-t",
            str(max_seconds),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(dest),
        ]
        subprocess.run(cmd, check=False, capture_output=True)
    return dest


def burn_title_card(title: str, dest: Path, seconds: float = 3.0, size: str = "1920x1080") -> Path:
    safe = title.replace(":", " ").replace("'", "")[:80]
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0b1215:s={size}:d={seconds}",
        "-vf",
        f"drawtext=text='{safe}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    if not dest.exists():
        make_color_clip(dest, seconds, size)
    return dest
