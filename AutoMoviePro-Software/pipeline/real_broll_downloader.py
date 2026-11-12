"""
AutoMovie Pro — Real Contextual B-Roll Video Downloader & Normalizer
=====================================================================
Downloads genuine 4K / Full HD stock footage from Pexels Video API based on
scene keywords, inspects with ffprobe, normalizes to 1080x1920 @ 30fps,
and provides verified real video assets for scene composition.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pipeline.api_keys import load_api_bundle
from pipeline.compose import ffmpeg_bin

logger = logging.getLogger("RealBrollDownloader")

BASE_DIR = Path(__file__).resolve().parent.parent


def _get_ffprobe() -> str:
    from pipeline.compose import ffmpeg_bin
    p = Path(ffmpeg_bin()).parent / "ffprobe.exe"
    if p.exists():
        return str(p)
    return "ffprobe"


def inspect_video_stream(video_path: Path) -> Dict[str, Any]:
    """Inspects video stream with ffprobe, returning resolution, codec, duration, and fps."""
    ffprobe = _get_ffprobe()
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate,duration,bit_rate",
        "-of", "json", str(video_path)
    ]
    try:
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(res.decode("utf-8"))
        streams = data.get("streams", [])
        if streams:
            st = streams[0]
            return {
                "width": int(st.get("width", 0)),
                "height": int(st.get("height", 0)),
                "codec": st.get("codec_name", "unknown"),
                "fps": st.get("r_frame_rate", "30/1"),
                "duration": float(st.get("duration") or 0.0),
                "file_size_mb": round(video_path.stat().st_size / (1024.0 * 1024.0), 2)
            }
    except Exception as exc:
        logger.warning("ffprobe inspection error: %s", exc)
    return {}


def download_and_normalize_broll(
    query: str,
    dest_path: Path,
    *,
    duration: float = 5.0,
    size: str = "1080x1920",
    orientation: str = "portrait",
) -> Optional[Dict[str, Any]]:
    """
    Downloads genuine stock video footage from Pexels, normalizes to exact size and duration,
    and returns metadata inspection dictionary.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    raw_dest = dest_path.parent / f"raw_download_{dest_path.name}"

    keys = (load_api_bundle() or {}).get("pexels_keys") or []
    if not keys:
        logger.warning("No Pexels API key available for B-roll download")
        return None

    api_key = keys[0]
    from pipeline.ai_providers import fetch_pexels_videos
    
    urls = fetch_pexels_videos(api_key=api_key, query=query, per_page=3, orientation=orientation)
    if not urls:
        # Fallback broader query
        urls = fetch_pexels_videos(api_key=api_key, query="technology server room hardware datacenter", per_page=2, orientation=orientation)
    
    if not urls:
        logger.warning("No video URLs found on Pexels for query: %s", query)
        return None

    video_url = urls[0]
    logger.info("Downloading genuine B-roll video from: %s", video_url[:70])

    try:
        req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=40) as resp, open(raw_dest, "wb") as f:
            f.write(resp.read())
    except Exception as exc:
        logger.error("B-roll video download failed: %s", exc)
        return None

    if not raw_dest.exists() or raw_dest.stat().st_size < 10000:
        logger.error("Downloaded file is empty or corrupted")
        return None

    raw_meta = inspect_video_stream(raw_dest)
    logger.info("Raw B-roll downloaded successfully: %dx%d, %.2f MB",
                raw_meta.get("width", 0), raw_meta.get("height", 0), raw_meta.get("file_size_mb", 0))

    # Normalize to 1080x1920 @ 30fps with target duration
    w, h = (int(x) for x in size.split("x")) if "x" in size else (1080, 1920)
    ffmpeg = ffmpeg_bin()

    scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30"
    cmd = [
        ffmpeg, "-y",
        "-ss", "0.5",
        "-i", str(raw_dest),
        "-t", f"{duration:.2f}",
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-an",
        str(dest_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    try:
        if raw_dest.exists():
            raw_dest.unlink()
    except Exception:
        pass

    if dest_path.exists() and dest_path.stat().st_size > 10000:
        final_meta = inspect_video_stream(dest_path)
        final_meta["file_path"] = str(dest_path.resolve())
        final_meta["query"] = query
        logger.info("Normalized B-roll ready: %s (%.2f MB, %dx%d @ %s fps)",
                    dest_path.name, final_meta.get("file_size_mb", 0),
                    final_meta.get("width", 0), final_meta.get("height", 0), final_meta.get("fps", ""))
        return final_meta

    return None
