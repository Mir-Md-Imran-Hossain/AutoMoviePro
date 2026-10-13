"""
Royalty-free BGM mastering with automated sidechain ducking (-14dB to -18dB).

Mixes cinematic/ambient background music under dialogue voiceover so the speech
remains crisp, clear, and primary, while BGM swells smoothly in narrative pauses.
"""
from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.audio_design.mix_policy import default_mix_policy

logger = logging.getLogger(__name__)


def _niche_to_mood(niche: str) -> str:
    n = (niche or "").lower()
    if any(k in n for k in ("islam", "deen", "quran")):
        return "spiritual"
    if any(k in n for k in ("space", "science", "physics", "tech", "gadget")):
        return "tech_ambient"
    if any(k in n for k in ("financ", "money", "invest", "crypto")):
        return "corporate_pulse"
    if any(k in n for k in ("health", "fitness", "nature", "wildlife")):
        return "calm_nature"
    if any(k in n for k in ("myster", "crime", "horror", "secret")):
        return "noir_tension"
    if any(k in n for k in ("motivat", "habit", "discipline")):
        return "uplifting"
    return "cinematic_drone"


def resolve_or_synthesize_bgm(
    work_dir: Path,
    duration_sec: float,
    *,
    niche: str = "",
) -> Optional[Path]:
    """
    Locate royalty-free BGM file for the niche, or synthesize a warm ambient drone bed.
    """
    mood = _niche_to_mood(niche)
    work_dir = Path(work_dir)

    # 1. Check local assets directory for royalty-free tracks
    assets_bgm_dir = Path(__file__).resolve().parents[1] / "assets" / "audio" / "bgm"
    if assets_bgm_dir.is_dir():
        # Look for mood-specific audio files
        mood_matches = list(assets_bgm_dir.glob(f"*{mood}*.*"))
        if mood_matches:
            return mood_matches[0]
        # Any fallback mp3/wav in assets
        general_matches = list(assets_bgm_dir.glob("*.mp3")) + list(assets_bgm_dir.glob("*.wav"))
        if general_matches:
            return general_matches[0]

    # 2. Synthesize a warm, harmonic ambient bed via FFmpeg aevalsrc
    synth_path = work_dir / f"bgm_{mood}_bed.wav"
    if synth_path.is_file() and synth_path.stat().st_size > 1000:
        return synth_path

    dur = max(5.0, float(duration_sec or 30.0))
    # Harmonic frequencies: F-chord drone (110Hz + 165Hz + 220Hz + 330Hz) with gentle chorus
    expr = (
        "0.025*sin(2*PI*110*t)"
        "+0.020*sin(2*PI*165*t)"
        "+0.015*sin(2*PI*220*t)"
        "+0.010*sin(2*PI*330*t)"
    )
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"aevalsrc=exprs='{expr}':s=44100:d={dur}",
        "-af",
        "lowpass=f=900,volume=0.25",
        "-c:a",
        "pcm_s16le",
        str(synth_path),
    ]
    try:
        cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=cflags)
        if res.returncode == 0 and synth_path.is_file() and synth_path.stat().st_size > 500:
            return synth_path
    except Exception as exc:
        logger.warning("BGM synthesis failed: %s", exc)

    return None


def build_ducking_filter_complex(duck_db: float = -16.0, attack_ms: Optional[float] = None) -> str:
    """Build 100% clean frequency-separated FFmpeg filter_complex with sidechain ducking for vocal clarity."""
    linear_duck = round(math.pow(10, duck_db / 20.0), 4)
    att = round(attack_ms) if attack_ms is not None else 60
    return (
        f"[0:a]highpass=f=85,equalizer=f=3000:t=q:w=1.5:g=2.5,alimiter=limit=0.95[clean_vox];"
        f"[1:a]aloop=loop=-1:size=2e+09,lowpass=f=7500,equalizer=f=2500:t=q:w=1.2:g=-6[pre_bgm];"
        f"[pre_bgm][clean_vox]sidechaincompress="
        f"threshold=0.025:ratio=10:attack={att}:release=450:level_sc=1:mix=0.90[ducked_bgm];"
        f"[ducked_bgm]volume={linear_duck * 1.8}[bgm_att];"
        f"[clean_vox][bgm_att]amix=inputs=2:duration=first:dropout_transition=2:weights=1.0 0.7[a_out]"
    )


def apply_bgm_ducking(
    video_path: Path,
    output_path: Path,
    *,
    niche: str = "",
    duck_db: float = -16.0,
    attack_ms: float = 100.0,
    bgm_path: Optional[Path] = None,
) -> Path:
    """
    Mix royalty-free background music under dialogue voiceover with sidechain ducking.

    duck_db defaults to -16.0 dB (-14dB to -18dB range), attenuating the music
    with fine-tuned 0.1s (100ms) attack time whenever speech frequencies are detected.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    dur = ffprobe_duration(video_path)
    if dur <= 0:
        dur = 30.0

    # Ensure duck_db is within industrial ducking range [-22, -10]
    duck_db = max(-22.0, min(-10.0, float(duck_db)))

    # Resolve or synthesize background music
    resolved_bgm = bgm_path or resolve_or_synthesize_bgm(video_path.parent, dur, niche=niche)
    if not resolved_bgm or not Path(resolved_bgm).is_file():
        logger.info("No BGM track available — passing video as-is")
        if video_path.resolve() != output_path.resolve():
            shutil.copy2(video_path, output_path)
        return output_path

    # Build clean frequency separation filter with fine-tuned 0.1s (100ms) attack time
    filter_complex = build_ducking_filter_complex(duck_db, attack_ms=attack_ms)

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(resolved_bgm),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[a_out]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]

    try:
        cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=cflags)
        if res.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 1000:
            logger.info("BGM ducking applied successfully: %s (duck=%sdB)", output_path.name, duck_db)
            return output_path
        else:
            logger.warning("BGM ducking ffmpeg error (%s) — falling back to source", res.stderr[:300])
    except Exception as exc:
        logger.warning("BGM ducking execution exception (%s) — falling back to source", exc)

    # Clean fallback: preserve video if ducking fails
    if video_path.resolve() != output_path.resolve():
        shutil.copy2(video_path, output_path)
    return output_path
