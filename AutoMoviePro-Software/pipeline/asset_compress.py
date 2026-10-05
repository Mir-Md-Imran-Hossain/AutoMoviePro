"""
High-compression derivatives before cloud archive.

Video: libx265 (HEVC) CRF 28–32, fallback libx264
Audio: AAC 64–96k (speech) or Opus when encoder available
Images: WebP
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from pipeline.compose import ffmpeg_bin

logger = logging.getLogger(__name__)


def compress_video_hevc(
    src: Path,
    dest: Path,
    *,
    crf: int = 30,
    preset: str = "medium",
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    crf = max(28, min(32, int(crf)))
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-an",
        "-c:v",
        "libx265",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-tag:v",
        "hvc1",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1000:
        return dest
    logger.warning("HEVC failed — falling back to x264: %s", (r.stderr or "")[-160:])
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        str(dest.with_suffix(".mp4")),
    ]
    dest2 = dest if dest.suffix.lower() == ".mp4" else dest.with_suffix(".mp4")
    cmd[-1] = str(dest2)
    r2 = subprocess.run(cmd, capture_output=True, text=True)
    if r2.returncode != 0 or not dest2.exists():
        raise RuntimeError(f"compress_video_failed: {(r2.stderr or '')[-220:]}")
    return dest2


def compress_audio_speech(
    src: Path,
    dest: Path,
    *,
    bitrate: str = "80k",
    prefer_opus: bool = True,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if prefer_opus:
        opus_dest = dest.with_suffix(".opus") if dest.suffix.lower() != ".opus" else dest
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-vn",
            "-c:a",
            "libopus",
            "-b:a",
            bitrate,
            str(opus_dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and opus_dest.exists() and opus_dest.stat().st_size > 200:
            return opus_dest
        logger.info("Opus unavailable — AAC speech encode")
    aac_dest = dest.with_suffix(".m4a")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        bitrate,
        str(aac_dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not aac_dest.exists():
        raise RuntimeError(f"compress_audio_failed: {(r.stderr or '')[-200:]}")
    return aac_dest


def compress_image_webp(src: Path, dest: Path, *, quality: int = 78) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = dest if dest.suffix.lower() == ".webp" else dest.with_suffix(".webp")
    try:
        from PIL import Image

        im = Image.open(src).convert("RGB")
        im.save(out, "WEBP", quality=max(60, min(90, quality)), method=6)
        return out
    except Exception:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-q:v",
            str(max(2, min(8, int((100 - quality) / 12)))),
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"webp_failed: {(r.stderr or '')[-160:]}")
        return out


def build_compressed_bundle(vault_manifest: dict, *, crf: int = 30) -> dict:
    """Create compressed/ siblings next to vault files."""
    from pathlib import Path

    root = Path(vault_manifest["vault_dir"])
    aid = vault_manifest["asset_id"]
    comp = root / "compressed"
    comp.mkdir(parents=True, exist_ok=True)
    v_src = Path(vault_manifest["video"])
    a_src = Path(vault_manifest["audio"])
    out = {
        "video": str(compress_video_hevc(v_src, comp / f"{aid}_video_hevc.mp4", crf=crf)),
        "audio": str(compress_audio_speech(a_src, comp / f"{aid}_audio", bitrate="80k")),
        "metadata": vault_manifest.get("metadata"),
    }
    # Optional poster from first frame
    poster = comp / f"{aid}_poster.webp"
    try:
        frame = comp / f"{aid}_frame.jpg"
        subprocess.run(
            [ffmpeg_bin(), "-y", "-ss", "0.4", "-i", str(v_src), "-frames:v", "1", str(frame)],
            capture_output=True,
        )
        if frame.exists():
            out["poster"] = str(compress_image_webp(frame, poster))
    except Exception as exc:
        logger.debug("poster skip: %s", exc)
    (comp / "bundle.json").write_text(
        __import__("json").dumps(out, indent=2), encoding="utf-8"
    )
    return out
