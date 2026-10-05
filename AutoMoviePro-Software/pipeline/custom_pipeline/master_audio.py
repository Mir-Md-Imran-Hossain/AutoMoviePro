"""Master-clip audio hygiene for Agnes (and other talking video models).

Problem: Agnes returns MP4 with burned English speech. If compose muxes
without explicit -map, that English bleeds under Bangla/Hindi TTS.

Policy:
  1) After any AI video save: extract native audio (if any) → side folder
  2) Rewrite master as VIDEO-ONLY (-an)
  3) EN can reuse native audio instead of TTS; other langs always use TTS
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.compose import ffmpeg_bin, ffprobe_bin

logger = logging.getLogger(__name__)


def probe_has_audio(path: Path) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(p),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "audio" in (r.stdout or "").lower()


def extract_audio_track(video: Path, out_audio: Path) -> Optional[Path]:
    """Extract first audio stream → m4a/aac. Returns path or None."""
    video = Path(video)
    out_audio = Path(out_audio)
    if not video.is_file() or not probe_has_audio(video):
        return None
    out_audio.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out_audio),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and out_audio.is_file() and out_audio.stat().st_size > 500:
        return out_audio
    logger.warning("extract audio failed %s: %s", video.name, (r.stderr or "")[:160])
    return None


def strip_audio_inplace(video: Path) -> bool:
    """Rewrite MP4 as video-only (no audio stream)."""
    video = Path(video)
    if not video.is_file():
        return False
    if not probe_has_audio(video):
        return True  # already clean
    tmp = video.with_suffix(".silent.tmp.mp4")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1000:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        # Re-encode fallback (copy can fail on odd containers)
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-an",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not tmp.is_file():
            logger.warning("strip audio failed %s: %s", video.name, (r.stderr or "")[:160])
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return False
    try:
        tmp.replace(video)
    except Exception:
        import shutil

        shutil.copy2(tmp, video)
        tmp.unlink(missing_ok=True)
    return not probe_has_audio(video)


def native_audio_dir(video_clips_dir: Path) -> Path:
    d = Path(video_clips_dir) / "_native_audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sanitize_master_clip(
    master_video: Path,
    *,
    shot_key: str,
    video_clips_dir: Path,
    provider: str = "",
) -> Dict[str, Any]:
    """Extract native audio (if any), strip master to silent. Idempotent."""
    master_video = Path(master_video)
    result: Dict[str, Any] = {
        "had_audio": False,
        "stripped": False,
        "native_audio_path": None,
        "provider": provider,
        "shot_key": shot_key,
    }
    if not master_video.is_file():
        return result
    if not probe_has_audio(master_video):
        result["stripped"] = True
        return result

    result["had_audio"] = True
    out_a = native_audio_dir(video_clips_dir) / f"{shot_key}.m4a"
    extracted = extract_audio_track(master_video, out_a)
    if extracted:
        result["native_audio_path"] = str(extracted)
        logger.info(
            "Native audio saved %s provider=%s → %s",
            shot_key,
            provider or "?",
            extracted.name,
        )
    result["stripped"] = strip_audio_inplace(master_video)
    if result["stripped"]:
        logger.info("Master silenced %s (Agnes/EN bleed prevention)", shot_key)
    return result


def find_native_audio(video_clips_dir: Path, shot_number: int) -> Optional[Path]:
    d = Path(video_clips_dir) / "_native_audio"
    for name in (f"S{shot_number:02d}.m4a", f"S{shot_number:02d}.wav", f"S{shot_number:02d}.mp3"):
        p = d / name
        if p.is_file() and p.stat().st_size > 500:
            return p
    return None
