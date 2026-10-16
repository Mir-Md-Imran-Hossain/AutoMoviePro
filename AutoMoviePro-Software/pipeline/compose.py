from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

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


def ensure_portable_ffmpeg_in_path() -> Optional[str]:
    """Auto-detect bundled portable builds (ffmpeg-8.1.1-full_build or local bin).

    If PATH is missing ffmpeg, injects the bundled bin directory into os.environ['PATH'],
    and sets AMP_FFMPEG_BIN, AMP_FFPROBE_BIN, FFMPEG_BINARY so external libraries work seamlessly.
    """
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"

    bin_dir: Optional[Path] = None
    for root in _project_roots():
        # Check explicit bin folders
        for cand in (
            root / "bin",
            root / "tools" / "ffmpeg" / "bin",
            root / "tools" / "ffmpeg",
        ):
            if (cand / exe_name).is_file():
                bin_dir = cand
                break
        if bin_dir:
            break

        # Check ffmpeg-* distributions (e.g. ffmpeg-8.1.1-full_build)
        for dist in sorted(root.glob("ffmpeg-*")):
            if not dist.is_dir():
                continue
            for cand in (dist / "bin",):
                if (cand / exe_name).is_file():
                    bin_dir = cand
                    break
            if bin_dir:
                break
            for nested in sorted(dist.rglob("bin")):
                if (nested / exe_name).is_file():
                    bin_dir = nested
                    break
            if bin_dir:
                break
            if (dist / exe_name).is_file():
                bin_dir = dist
                break
        if bin_dir:
            break

    if bin_dir and bin_dir.is_dir():
        bin_dir_str = str(bin_dir.resolve())
        current_path = os.environ.get("PATH", "")
        path_parts = [p.strip() for p in current_path.split(os.pathsep) if p.strip()]
        if bin_dir_str not in path_parts:
            os.environ["PATH"] = bin_dir_str + os.pathsep + current_path
            logger.info("Auto-injected portable FFmpeg to PATH: %s", bin_dir_str)

        ff_exe = bin_dir / exe_name
        ff_probe = bin_dir / probe_name
        if ff_exe.is_file():
            os.environ.setdefault("AMP_FFMPEG_BIN", str(ff_exe.resolve()))
            os.environ.setdefault("FFMPEG_BINARY", str(ff_exe.resolve()))
        if ff_probe.is_file():
            os.environ.setdefault("AMP_FFPROBE_BIN", str(ff_probe.resolve()))
        os.environ.setdefault("AMP_FFMPEG_ROOT", str(bin_dir.parent.resolve()))
        return bin_dir_str

    return None


def ffmpeg_bin() -> str:
    """Prefer AMP_FFMPEG_BIN / AMP_FFMPEG_ROOT/bin, then bundled distributions, then PATH."""
    ensure_portable_ffmpeg_in_path()
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
            creationflags=_WIN_NO_WINDOW,
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
            creationflags=_WIN_NO_WINDOW,
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
            creationflags=_WIN_NO_WINDOW,
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
_HW_ACCEL_INFO: Optional[dict] = None


def detect_hardware_acceleration(force_refresh: bool = False) -> dict:
    """
    Auto-detect hardware accelerated video encoder across all major GPU vendors:
    1. h264_nvenc (NVIDIA)
    2. h264_qsv (Intel Quick Sync)
    3. h264_amf (AMD AMF)
    Fallback: optimized libx264 with multi-core CPU thread allocation.
    """
    global _BEST_H264_ENCODER, _HW_ACCEL_INFO
    if _HW_ACCEL_INFO is not None and not force_refresh:
        return _HW_ACCEL_INFO

    cpu_count = os.cpu_count() or 4
    cpu_threads = max(2, min(16, cpu_count))

    forced = (os.environ.get("AMP_VIDEO_ENCODER") or "").strip()
    if forced:
        _BEST_H264_ENCODER = forced
        _HW_ACCEL_INFO = {
            "encoder": forced,
            "hw_type": "forced",
            "is_hw_accelerated": forced != "libx264",
            "cpu_threads": cpu_threads,
            "extra_args": [] if forced != "libx264" else ["-threads", str(cpu_threads), "-preset", "faster"],
        }
        return _HW_ACCEL_INFO

    fb = ffmpeg_bin()
    candidates = [
        ("h264_nvenc", "nvenc", ["-preset", "p4"]),
        ("h264_qsv", "qsv", ["-preset", "faster"]),
        ("h264_amf", "amf", ["-quality", "speed"]),
    ]

    for enc_name, hw_type, extra_args in candidates:
        try:
            r = subprocess.run(
                [fb, "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-c:v", enc_name, "-f", "null", "-"],
                capture_output=True,
                timeout=3,
                creationflags=_WIN_NO_WINDOW,
            )
            if r.returncode == 0:
                logger.info("Hardware GPU acceleration active: using %s encoder (%s)", enc_name, hw_type)
                _BEST_H264_ENCODER = enc_name
                _HW_ACCEL_INFO = {
                    "encoder": enc_name,
                    "hw_type": hw_type,
                    "is_hw_accelerated": True,
                    "cpu_threads": cpu_threads,
                    "extra_args": extra_args,
                }
                return _HW_ACCEL_INFO
        except Exception as exc:
            logger.debug("Hardware encoder detection skipped for %s: %s", enc_name, exc)

    logger.info("Hardware acceleration not available; falling back to optimized libx264 with %d threads", cpu_threads)
    _BEST_H264_ENCODER = "libx264"
    _HW_ACCEL_INFO = {
        "encoder": "libx264",
        "hw_type": "cpu",
        "is_hw_accelerated": False,
        "cpu_threads": cpu_threads,
        "extra_args": ["-threads", str(cpu_threads), "-preset", "faster"],
    }
    return _HW_ACCEL_INFO


def get_h264_encoder() -> str:
    """Auto-detect hardware accelerated video encoder (NVENC -> QSV -> AMF -> libx264)."""
    info = detect_hardware_acceleration()
    return info["encoder"]


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
    subprocess.run(cmd, check=False, capture_output=True, creationflags=_WIN_NO_WINDOW)
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
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_WIN_NO_WINDOW)
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
        subprocess.run(cmd, check=False, capture_output=True, creationflags=_WIN_NO_WINDOW)
    return dest


def prepend_intro(intro: Optional[Path], main: Path, dest: Path) -> Path:
    if intro and intro.exists():
        return concat_clips([intro, main], dest)
    shutil.copy2(main, dest)
    return dest


def ffprobe_dimensions(path: Path) -> tuple[int, int]:
    """Retrieve video dimensions (width, height) via ffprobe. Defaults to (1920, 1080)."""
    p = Path(path)
    if not p.is_file():
        return 1920, 1080
    fb = ffprobe_bin()
    cmd = [
        fb,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(p),
    ]
    try:
        out = subprocess.check_output(cmd, text=True, timeout=8, creationflags=_WIN_NO_WINDOW).strip()
        if "x" in out:
            parts = out.split("x")
            return max(1, int(parts[0])), max(1, int(parts[1]))
    except Exception:
        pass
    return 1920, 1080


def preprocess_logo_for_branding(
    logo_path: Path,
    out_path: Optional[Path] = None,
    *,
    opacity: float = 0.82,
    remove_bg: bool = True,
    autocrop: bool = True,
) -> Path:
    """Preprocess a logo image for cinematic broadcast branding.

    Key capabilities:
    1. Removes flat/solid backgrounds (white, black, or uniform corner canvas)
       so only the core emblem remains.
    2. Isolates the core emblem with smooth, anti-aliased alpha edge feathering.
    3. Auto-crops extraneous padding so the emblem scales accurately.
    4. Applies cinematic broadcast opacity (default 0.82) so the watermark
       harmonizes with the video and never degrades visual aesthetics.
    5. Graceful fallback to original logo_path if PIL processing fails.
    """
    if not logo_path or not Path(logo_path).is_file():
        return logo_path

    try:
        from PIL import Image

        src = Path(logo_path)
        with Image.open(src) as opened_img:
            img = opened_img.convert("RGBA")
        w, h = img.size
        if h <= 2 or w <= 2:
            return logo_path

        r, g, b, a = img.split()
        extrema = a.getextrema()
        has_transparency = bool(extrema[0] < 250)

        clamped_opacity = max(0.1, min(1.0, float(opacity)))

        try:
            import numpy as np
            has_np = True
        except ImportError:
            has_np = False

        if has_np:
            arr = np.array(img, dtype=np.float32)
            if remove_bg and not has_transparency:
                corners = np.array([
                    arr[0, 0, :3],
                    arr[0, -1, :3],
                    arr[-1, 0, :3],
                    arr[-1, -1, :3],
                ])
                corner_mean = np.mean(corners, axis=0)
                corner_std = np.std(corners, axis=0)
                is_uniform_corners = bool(np.max(corner_std) < 30.0)
                is_near_white = bool(np.all(corner_mean > 225.0))
                is_near_black = bool(np.all(corner_mean < 30.0))

                if is_uniform_corners or is_near_white or is_near_black:
                    diff = np.linalg.norm(arr[:, :, :3] - corner_mean, axis=2)
                    inner_thresh = 18.0
                    outer_thresh = 52.0
                    ramp = np.clip((diff - inner_thresh) / (outer_thresh - inner_thresh), 0.0, 1.0)
                    arr[:, :, 3] = ramp * 255.0

            arr[:, :, 3] = arr[:, :, 3] * clamped_opacity
            out_img = Image.fromarray(np.uint8(np.round(arr)), mode="RGBA")
        else:
            # Pure PIL processing without numpy
            if remove_bg and not has_transparency:
                c_tl = img.getpixel((0, 0))[:3]
                c_tr = img.getpixel((w - 1, 0))[:3]
                c_bl = img.getpixel((0, h - 1))[:3]
                c_br = img.getpixel((w - 1, h - 1))[:3]
                bg_r = (c_tl[0] + c_tr[0] + c_bl[0] + c_br[0]) // 4
                bg_g = (c_tl[1] + c_tr[1] + c_bl[1] + c_br[1]) // 4
                bg_b = (c_tl[2] + c_tr[2] + c_bl[2] + c_br[2]) // 4

                is_near_white = (bg_r > 225 and bg_g > 225 and bg_b > 225)
                is_near_black = (bg_r < 30 and bg_g < 30 and bg_b < 30)

                pix = img.load()
                alpha_bytes = bytearray(w * h)
                idx = 0
                for y in range(h):
                    for x in range(w):
                        pr, pg, pb, _ = pix[x, y]
                        dr, dg, db = pr - bg_r, pg - bg_g, pb - bg_b
                        dist = (dr * dr + dg * dg + db * db) ** 0.5
                        if dist <= 18:
                            val = 0
                        elif dist >= 52:
                            val = int(255 * clamped_opacity)
                        else:
                            ramp = (dist - 18) / (52 - 18)
                            val = int(ramp * 255 * clamped_opacity)
                        alpha_bytes[idx] = val
                        idx += 1
                new_alpha = Image.frombytes("L", (w, h), bytes(alpha_bytes))
                img.putalpha(new_alpha)
            else:
                if clamped_opacity < 1.0:
                    new_a = a.point(lambda p: int(p * clamped_opacity))
                    img.putalpha(new_a)
            out_img = img

        # Auto-crop to non-transparent bounding box so scale is accurate
        if autocrop:
            bbox = out_img.getbbox()
            if bbox:
                pad = 4
                crop_box = (
                    max(0, bbox[0] - pad),
                    max(0, bbox[1] - pad),
                    min(w, bbox[2] + pad),
                    min(h, bbox[3] + pad),
                )
                out_img = out_img.crop(crop_box)

        if out_path is None:
            dest_file = src.parent / f"{src.stem}_cinematic_brand.png"
        else:
            dest_file = Path(out_path)

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        out_img.save(dest_file, format="PNG")
        return dest_file

    except Exception as exc:
        logger.warning("preprocess_logo_for_branding fallback due to: %s", exc)
        return logo_path


def overlay_logo(
    video: Path,
    logo: Optional[Path],
    dest: Path,
    *,
    position: str = "auto",
    scale_ratio: Optional[float] = None,
    opacity: float = 0.82,
    encoder: Optional[str] = None,
    remove_bg: bool = True,
) -> Path:
    """Overlays channel branding logo onto video with zero quality degradation.

    Enhancements:
    1. Logo Preprocessing: Automatically strips solid black/white/flat background boxes,
       extracts the core emblem with anti-aliased edge feathering, and sets broadcast opacity.
    2. Responsive Scaling: Proportionally scales logo based on video resolution (7-12% of width)
       rather than an arbitrary fixed pixel size.
    3. Safe Margin Placement: Automatically respects mobile / social UI safe zones (top-left for
       vertical Shorts/Reels to avoid UI icons; top-right for landscape).
    4. Zero Quality Degradation: Preserves full visual fidelity using hardware acceleration
       (NVENC/QSV) with visually lossless CRF / high-bitrate settings and libx264 fallback,
       stream-copying audio lossless.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not logo or not Path(logo).exists():
        shutil.copy2(video, dest)
        return dest

    vid_path = Path(video)
    if not vid_path.is_file():
        return dest

    # 1. Preprocess logo to clean transparent RGBA PNG
    clean_logo = preprocess_logo_for_branding(
        Path(logo),
        dest.parent / f"{dest.stem}_logo_brand.png",
        opacity=opacity,
        remove_bg=remove_bg,
    )

    # 2. Probe dimensions for responsive layout & safe margins
    vid_w, vid_h = ffprobe_dimensions(vid_path)
    is_vertical = vid_h > vid_w

    if is_vertical:
        # Vertical Shorts / Reels (e.g. 1080x1920)
        # Avoid UI icons on right, title on bottom -> Top-Left is safest zone
        ratio = scale_ratio if scale_ratio is not None else 0.11
        target_w = max(80, min(int(vid_w * ratio), 220))
        margin_x = max(16, int(vid_w * 0.05))
        margin_y = max(16, int(vid_h * 0.045))
        pos = "top_left" if position in ("auto", "top_left") else position
    else:
        # Horizontal / Landscape (e.g. 1920x1080, 4K)
        ratio = scale_ratio if scale_ratio is not None else 0.08
        target_w = max(90, min(int(vid_w * ratio), 320))
        margin_x = max(20, int(vid_w * 0.035))
        margin_y = max(20, int(vid_h * 0.045))
        pos = "top_right" if position in ("auto", "top_right") else position

    # 3. Calculate overlay coordinates
    if pos == "top_left":
        overlay_coord = f"{margin_x}:{margin_y}"
    elif pos == "bottom_left":
        overlay_coord = f"{margin_x}:H-h-{margin_y}"
    elif pos == "bottom_right":
        overlay_coord = f"W-w-{margin_x}:H-h-{margin_y}"
    else:  # top_right
        overlay_coord = f"W-w-{margin_x}:{margin_y}"

    # Filter graph: Scale logo, preserve transparency format, blend over video
    filter_complex = (
        f"[1:v]format=rgba,scale={target_w}:-1[logo];"
        f"[0:v][logo]overlay={overlay_coord}:format=auto"
    )

    # 4. Choose encoder and high-fidelity video quality flags
    selected_enc = (encoder or get_h264_encoder()).strip().lower()

    def _build_enc_args(enc: str) -> list[str]:
        if "nvenc" in enc:
            return ["-c:v", enc, "-preset", "p6", "-cq", "17", "-b:v", "18M", "-maxrate", "25M", "-pix_fmt", "yuv420p"]
        elif "qsv" in enc:
            return ["-c:v", enc, "-global_quality", "18", "-b:v", "18M", "-maxrate", "25M", "-pix_fmt", "yuv420p"]
        else:
            return ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p"]

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i", str(vid_path),
        "-i", str(clean_logo),
        "-filter_complex", filter_complex,
        *_build_enc_args(selected_enc),
        "-c:a", "copy",
        str(dest),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_WIN_NO_WINDOW)
    if result.returncode != 0:
        # Fallback 1: Try CPU libx264 visually lossless
        if selected_enc != "libx264":
            cmd_fallback = [
                ffmpeg_bin(),
                "-y",
                "-i", str(vid_path),
                "-i", str(clean_logo),
                "-filter_complex", filter_complex,
                "-c:v", "libx264",
                "-crf", "17",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(dest),
            ]
            result = subprocess.run(cmd_fallback, capture_output=True, text=True, creationflags=_WIN_NO_WINDOW)

        # Fallback 2: If FFmpeg overlay fails entirely, copy original
        if result.returncode != 0:
            logger.warning("overlay_logo failed (%s), keeping original video", result.stderr[:200])
            shutil.copy2(video, dest)

    # Clean up temp preprocessed logo if created
    if clean_logo != logo and clean_logo.exists():
        try:
            clean_logo.unlink()
        except Exception:
            pass

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
