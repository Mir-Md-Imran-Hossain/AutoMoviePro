"""
Asset-decoupled vault — Audio / Visual / Metadata as independent modules.

Every packaged asset writes:
  {asset_id}_audio.(m4a|opus|mp3)
  {asset_id}_video.(mp4)          # picture-only preferred, muxed OK if strip fails
  {asset_id}_metadata.json

Enables hot-swap later (same audio + new video) without rewriting the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR, OUTPUT_DIR
from pipeline.compose import ffmpeg_bin, ffprobe_duration

logger = logging.getLogger(__name__)

VAULT_ROOT = OUTPUT_DIR / "asset_vault"


def _safe_id(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", (raw or "asset").strip())[:80]
    return s or "asset"


def vault_dir(asset_id: str) -> Path:
    d = VAULT_ROOT / _safe_id(asset_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_audio_track(video: Path, dest: Path, *, bitrate: str = "96k") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        bitrate,
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 400:
        raise RuntimeError(f"extract_audio_failed: {(r.stderr or '')[-200:]}")
    return dest


def extract_video_silent(video: Path, dest: Path) -> Path:
    """Picture-only stream (no audio) for hot-swap visuals."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-an",
        "-c:v",
        "copy",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        # Re-encode fallback
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(video),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not dest.exists():
            raise RuntimeError(f"extract_silent_video_failed: {(r.stderr or '')[-200:]}")
    return dest


def write_metadata(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data.setdefault("schema", "amp_asset_v1")
    data.setdefault("written_at", datetime.now().isoformat())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def package_decoupled_asset(
    *,
    asset_id: str,
    source_video: Path,
    source_audio: Optional[Path] = None,
    script: str = "",
    visual_tags: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    lang_code: str = "en",
    channel_id: int = 0,
    user_login: str = "",
    niche: str = "",
    element: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Split a finished muxed clip into modular audio / silent-video / metadata.
    Returns paths + migration_ready=False until archive upload succeeds.
    """
    aid = _safe_id(asset_id)
    root = vault_dir(aid)
    src = Path(source_video)
    if not src.exists():
        raise FileNotFoundError(str(src))

    audio_out = root / f"{aid}_audio.m4a"
    video_out = root / f"{aid}_video.mp4"
    meta_out = root / f"{aid}_metadata.json"

    if source_audio and Path(source_audio).exists():
        # Prefer dedicated narration audio
        try:
            extract_audio_track(Path(source_audio), audio_out) if Path(source_audio).suffix.lower() in (
                ".mp4",
                ".mov",
                ".mkv",
            ) else None
        except Exception:
            pass
        if not audio_out.exists() or audio_out.stat().st_size < 400:
            import shutil

            # copy/re-encode audio file
            cmd = [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(source_audio),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                str(audio_out),
            ]
            subprocess.run(cmd, capture_output=True)
            if not audio_out.exists():
                shutil.copy2(source_audio, audio_out)
    else:
        extract_audio_track(src, audio_out)

    extract_video_silent(src, video_out)

    meta = {
        "asset_id": aid,
        "lang_code": lang_code,
        "channel_id": channel_id,
        "user_login": user_login,
        "niche": niche,
        "element": element,
        "script": (script or "")[:8000],
        "visual_description_tags": list(visual_tags or []),
        "keywords": list(keywords or []),
        "source_video": str(src),
        "duration_sec": ffprobe_duration(src),
        "audio_file": audio_out.name,
        "video_file": video_out.name,
        "migration_ready": False,
        "generated_at": datetime.now().isoformat(),
    }
    if extra:
        meta["extra"] = extra
    write_metadata(meta_out, meta)

    manifest = {
        "ok": True,
        "asset_id": aid,
        "vault_dir": str(root),
        "audio": str(audio_out),
        "video": str(video_out),
        "metadata": str(meta_out),
        "migration_ready": False,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Decoupled asset %s → %s", aid, root)
    return manifest
