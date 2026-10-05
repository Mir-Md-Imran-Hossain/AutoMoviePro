"""Build one master clip from multiple seed-locked stills (Ken Burns + concat)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.compose import ffmpeg_bin
from pipeline.custom_pipeline.media_providers import ken_burns_from_image
from pipeline.custom_pipeline.motion_presets import pick_motion_preset

logger = logging.getLogger(__name__)


def upscale_still_to_canvas(image: Path, out: Path, *, w: int, h: int) -> Optional[Path]:
    """Lanczos upscale + light unsharp so Pollinations stills don't look soft vs Agnes."""
    image = Path(image)
    out = Path(out)
    if not image.is_file():
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={w}:{h},"
        f"unsharp=5:5:0.6:5:5:0.0,"
        f"eq=contrast=1.05:saturation=1.05,"
        f"format=yuv420p"
    )
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(image),
        "-vf",
        vf,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out),
    ]
    # Prefer PNG for quality
    if out.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        out = out.with_suffix(".png")
        cmd[-1] = str(out)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and out.is_file() and out.stat().st_size > 2000:
        return out
    logger.warning("upscale still failed: %s", (r.stderr or "")[:160])
    return None


def probe_image_min_edge(path: Path) -> int:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return min(im.size)
    except Exception:
        # fallback: file size heuristic
        try:
            return 1080 if path.stat().st_size > 80_000 else 512
        except Exception:
            return 0


def concat_silent_clips(clips: Sequence[Path], out: Path) -> Optional[Path]:
    usable = [Path(c) for c in clips if c and Path(c).is_file()]
    if not usable:
        return None
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(usable) == 1:
        import shutil

        shutil.copy2(usable[0], out)
        return out
    tmp = Path(tempfile.mkdtemp(prefix="amp_multi_still_"))
    try:
        list_file = tmp / "list.txt"
        mapped: List[Path] = []
        for i, c in enumerate(usable):
            dest = tmp / f"p{i:02d}.mp4"
            # normalize then concat
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(c),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "25",
                str(dest),
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if r.returncode == 0 and dest.is_file():
                mapped.append(dest)
        if not mapped:
            return None
        list_file.write_text(
            "\n".join(f"file '{m.as_posix()}'" for m in mapped) + "\n",
            encoding="ascii",
        )
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-an",
            "-movflags",
            "+faststart",
            str(out),
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0 and out.is_file() and out.stat().st_size > 5000:
            return out
        # re-encode concat
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-an",
            "-movflags",
            "+faststart",
            str(out),
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0 and out.is_file():
            return out
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return None


def build_multi_still_master(
    stills: Sequence[Path],
    out_video: Path,
    *,
    total_duration: float,
    w: int,
    h: int,
    shot_number: int = 1,
    motion_preset: str = "",
) -> Dict[str, Any]:
    """Ken-burns each still for equal time slice, concat → silent master."""
    paths = [Path(p) for p in stills if p and Path(p).is_file()]
    if not paths:
        return {"ok": False, "error": "no stills"}
    n = len(paths)
    dur = max(2.0, float(total_duration or 6.0))
    slice_dur = max(1.6, dur / n)
    tmp = Path(tempfile.mkdtemp(prefix="amp_kb_slices_"))
    slices: List[Path] = []
    try:
        for i, still in enumerate(paths):
            # Upscale first
            hq = tmp / f"hq_{i:02d}.png"
            up = upscale_still_to_canvas(still, hq, w=w, h=h) or still
            preset = motion_preset or pick_motion_preset(
                shot_number + i, preferred=""
            )
            # Force variety across frames in same shot
            from pipeline.custom_pipeline.motion_presets import MOTION_PRESET_IDS

            preset = MOTION_PRESET_IDS[(shot_number + i - 1) % len(MOTION_PRESET_IDS)][0]
            part = tmp / f"kb_{i:02d}.mp4"
            kb = ken_burns_from_image(
                up,
                part,
                duration=slice_dur,
                w=w,
                h=h,
                motion_preset=preset,
                shot_number=shot_number + i,
            )
            if kb:
                slices.append(Path(kb))
        if not slices:
            return {"ok": False, "error": "kenburns_all_failed"}
        got = concat_silent_clips(slices, out_video)
        return {
            "ok": bool(got),
            "path": str(got) if got else None,
            "frame_count": len(slices),
            "slice_duration": round(slice_dur, 2),
        }
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
