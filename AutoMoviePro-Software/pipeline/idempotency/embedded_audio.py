"""Embedded English audio detection (BUILD-04B)."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional


class AudioSource(str, Enum):
    EMBEDDED = "EMBEDDED"
    EXTERNAL = "EXTERNAL"
    BOTH = "BOTH"
    NONE = "NONE"


def detect_embedded_english_audio(
    work_dir: Path,
    scene_id: int,
    *,
    scene_clip: Optional[Path] = None,
    agnes_master: Optional[Path] = None,
) -> tuple[AudioSource, Optional[Path]]:
    """
    Inspect pipeline state before generating English TTS.
    Does not call external APIs.
    """
    work = Path(work_dir)
    candidates = []
    if scene_clip and Path(scene_clip).is_file() and Path(scene_clip).stat().st_size > 8000:
        candidates.append(Path(scene_clip))
    clip = work / f"scene_{scene_id:02d}_feature.mp4"
    if clip.is_file() and clip.stat().st_size > 8000:
        candidates.append(clip)
    agnes = agnes_master or work / "narration_en_from_agnes.m4a"
    if agnes.is_file() and agnes.stat().st_size > 800:
        return AudioSource.EXTERNAL, agnes
    if candidates:
        return AudioSource.EMBEDDED, candidates[0]
    return AudioSource.NONE, None


def should_skip_english_tts_generation(
    work_dir: Path,
    scene_id: int,
    *,
    prefer_embedded: bool = True,
    embedded_clip: Optional[Path] = None,
) -> tuple[bool, str, Optional[Path]]:
    source, path = detect_embedded_english_audio(work_dir, scene_id, scene_clip=embedded_clip)
    if prefer_embedded and source == AudioSource.EXTERNAL and path:
        return True, "authoritative_external_agnes_master", path
    if prefer_embedded and source == AudioSource.EMBEDDED and path:
        return True, "embedded_in_visual_clip", path
    return False, "tts_required", None
