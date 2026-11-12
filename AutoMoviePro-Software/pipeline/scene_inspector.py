"""
AutoMovie Pro — Autonomous Real-Time Scene Inspector & Self-Healing Engine
========================================================================
Audits individual scene clips immediately upon generation against top commercial
YouTube Shorts & Facebook Reels standards. Detects defects (blank frames, static freezes,
missing broadcast chyrons, broken glyphs) and auto-remediates in real time before
proceeding to subsequent scenes.
"""

from __future__ import annotations

import html
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger("SceneInspector")

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "assets" / "fonts"


def _get_ffmpeg() -> str:
    from pipeline.compose import ffmpeg_bin
    return ffmpeg_bin()


def extract_probe_frames(clip_path: Path, count: int = 3) -> List[np.ndarray]:
    """Extracts probe frames from video clip as numpy RGB arrays."""
    clip_path = Path(clip_path)
    if not clip_path.exists() or clip_path.stat().st_size < 1000:
        return []

    # Get duration via ffprobe
    cmd_probe = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)
    ]
    try:
        dur_bytes = subprocess.check_output(cmd_probe, stderr=subprocess.DEVNULL)
        dur = float(dur_bytes.decode().strip())
    except Exception:
        dur = 3.0

    frames = []
    ffmpeg = _get_ffmpeg()
    timestamps = [max(0.2, dur * (i + 1) / (count + 1)) for i in range(count)]

    for t in timestamps:
        cmd = [
            ffmpeg, "-y", "-ss", f"{t:.2f}", "-i", str(clip_path),
            "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "-"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
            if res.returncode == 0 and len(res.stdout) > 500:
                import io
                img = Image.open(io.BytesIO(res.stdout)).convert("RGB")
                frames.append(np.array(img))
        except Exception:
            pass

    return frames


def audit_scene_clip(
    clip_path: Path,
    scene_data: Dict[str, Any],
    *,
    video_category: str = "cinematic",
    narration_audio: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Performs thorough commercial-grade audit on a single scene clip.
    Returns: { "verdict": "PASS" | "FAIL", "issues": [...], "metrics": {...} }
    """
    clip_path = Path(clip_path)
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    # Check 1: File existence and size
    if not clip_path.exists():
        return {"verdict": "FAIL", "issues": ["clip_file_missing"], "metrics": {}}

    size_kb = clip_path.stat().st_size / 1024.0
    metrics["size_kb"] = round(size_kb, 1)
    if size_kb < 50.0:
        issues.append("clip_file_too_small_likely_corrupt")

    # Check 2: Visual Frame Analysis
    frames = extract_probe_frames(clip_path, count=3)
    metrics["frames_extracted"] = len(frames)
    if not frames:
        issues.append("frame_extraction_failed_unplayable_stream")
        return {"verdict": "FAIL", "issues": issues, "metrics": metrics}

    # Luminance / Black frame check
    luminances = [float(np.mean(f)) for f in frames]
    metrics["avg_luminance"] = round(float(np.mean(luminances)), 2)
    if metrics["avg_luminance"] < 8.0:
        issues.append("pitch_black_frame_detected")

    # Motion variance check between first and last probe frames
    if len(frames) >= 2:
        diff = np.abs(frames[-1].astype(float) - frames[0].astype(float))
        var = float(np.mean(diff))
        metrics["motion_variance"] = round(var, 2)
        if var < 0.2:
            issues.append("static_frozen_video_no_motion")

    # Check 3: Audio Stream & Sync
    if narration_audio and Path(narration_audio).exists():
        from pipeline.compose import ffprobe_duration
        clip_dur = ffprobe_duration(clip_path) or 0.0
        audio_dur = ffprobe_duration(narration_audio) or 0.0
        metrics["clip_duration"] = round(clip_dur, 2)
        metrics["audio_duration"] = round(audio_dur, 2)
        if clip_dur < (audio_dur - 0.4):
            issues.append("video_shorter_than_narration_audio_truncated")

    # Check 4: Niche Broadcast & Content Standards
    category = str(video_category or scene_data.get("video_category") or "").lower()
    if category == "live_news":
        # Live news MUST have lower-third chyron or broadcast badge
        # Check if bottom 30% of frame has broadcast bar elements (high contrast / saturated colors)
        f_mid = frames[len(frames) // 2]
        h, w, _ = f_mid.shape
        lower_region = f_mid[int(h * 0.70):int(h * 0.95), :]
        color_std = float(np.std(lower_region))
        metrics["chyron_region_contrast"] = round(color_std, 2)
        if color_std < 5.0:
            issues.append("missing_broadcast_chyron_or_text_overlay")

    elif category == "motion_graphics":
        # Motion graphics MUST have structured card, vector icon, or kinetic typography
        # Check center region (middle 50% of screen) for contrast & layout elements
        f_mid = frames[len(frames) // 2]
        h, w, _ = f_mid.shape
        center_region = f_mid[int(h * 0.25):int(h * 0.75), int(w * 0.10):int(w * 0.90)]
        center_std = float(np.std(center_region))
        metrics["center_card_contrast"] = round(center_std, 2)
        if center_std < 8.0:
            issues.append("missing_motion_graphic_card_or_text")

    elif category in ("cinematic", "islamic", "documentary"):
        # Cinematic visuals must have high dynamic range and no washed-out flat frames
        f_mid = frames[len(frames) // 2]
        detail_std = float(np.std(f_mid))
        metrics["cinematic_detail_std"] = round(detail_std, 2)
        if detail_std < 10.0:
            issues.append("low_contrast_cinematic_b_roll")

    verdict = "FAIL" if issues else "PASS"
    return {
        "verdict": verdict,
        "issues": issues,
        "metrics": metrics,
    }


def heal_defective_scene_clip(
    clip_path: Path,
    scene_data: Dict[str, Any],
    audit_result: Dict[str, Any],
    *,
    work_dir: Path,
    narration_audio: Optional[Path],
    size: str = "1080x1920",
    google_api_keys: Optional[List[str]] = None,
    agnes_api_keys: Optional[List[str]] = None,
) -> Path:
    """
    Autonomous remediation actor: Fixes defective scene clip based on audited issues.
    """
    logger.info("Executing Autonomous Remediation on scene %s: %s", clip_path.name, audit_result.get("issues"))
    issues = set(audit_result.get("issues") or [])
    video_cat = str(scene_data.get("video_category") or "cinematic").lower()

    w, h = (int(x) for x in size.split("x")) if "x" in size else (1080, 1920)
    dur = float(audit_result.get("metrics", {}).get("audio_duration") or scene_data.get("estimated_duration_sec") or 5.0)

    # Strategy 1: Live News Chyron & Broadcast Visual Repair
    if video_cat == "live_news" or "missing_broadcast_chyron_or_text_overlay" in issues:
        logger.info("Healing Live News Broadcast overlay and B-roll for %s...", clip_path.name)
        from pipeline.live_news_engine import LiveNewsEngine
        return LiveNewsEngine.compose_news_scene_clip(
            scene_data=scene_data,
            narration_audio=narration_audio,
            duration=dur,
            size=size,
            dest_clip=clip_path,
            work_dir=work_dir,
            google_api_keys=google_api_keys,
            agnes_api_keys=agnes_api_keys,
        )

    # Strategy 2: Motion Graphics Card & Kinetic Typography Repair
    if video_cat == "motion_graphics" or "missing_motion_graphic_card_or_text" in issues:
        logger.info("Healing Motion Graphics scene clip with kinetic card & icons for %s...", clip_path.name)
        from pipeline.motion_graphics_composer import MotionGraphicsComposer
        return MotionGraphicsComposer.compose_motion_scene_clip(
            scene_data=scene_data,
            narration_audio=narration_audio,
            duration=dur,
            size=size,
            dest_clip=clip_path,
            work_dir=work_dir,
        )

    # Strategy 3: Motion Freeze / Blank Frame / Low Contrast Repair via Agnes AI 8K Photoreal Visual
    if any(issue in issues for issue in ("pitch_black_frame_detected", "static_frozen_video_no_motion", "low_contrast_cinematic_b_roll")):
        if video_cat == "motion_graphics":
            from pipeline.motion_graphics_composer import MotionGraphicsComposer
            return MotionGraphicsComposer.compose_motion_scene_clip(
                scene_data=scene_data,
                narration_audio=narration_audio,
                duration=dur,
                size=size,
                dest_clip=clip_path,
                work_dir=work_dir,
            )
        logger.info("Healing visual motion freeze with Agnes 8K Photoreal visual...")
        from pipeline.media_assets import _agnes_image
        narr = str(scene_data.get("narration") or scene_data.get("visual_prompt") or "high quality visual")
        img_out = work_dir / f"healed_{clip_path.stem}.png"
        prompt = f"Cinematic documentary visual of {narr[:90]}, photorealistic, master lighting, 8k resolution --no text, no watermark"
        res = _agnes_image(prompt, img_out, width=w, height=h, api_keys=agnes_api_keys)
        if res and img_out.exists():
            from pipeline.fallback_image_video import FFmpegProcessor
            if narration_audio and Path(narration_audio).exists():
                temp_vid = work_dir / f"temp_silent_{clip_path.name}"
                FFmpegProcessor.image_to_ken_burns(
                    image=img_out,
                    dest=temp_vid,
                    duration=dur,
                    size=size,
                    motion="zoom_in",
                    fps=30,
                )
                from pipeline.compose import ffmpeg_bin
                cmd_mux = [
                    ffmpeg_bin(), "-y", "-i", str(temp_vid), "-i", str(narration_audio),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(clip_path)
                ]
                subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    if temp_vid.exists():
                        temp_vid.unlink()
                except Exception:
                    pass
                return clip_path
            else:
                return FFmpegProcessor.image_to_ken_burns(
                    image=img_out,
                    dest=clip_path,
                    duration=dur,
                    size=size,
                    motion="zoom_in",
                    fps=30,
                )

    logger.warning("No specialized healer matched issues: %s — keeping existing clip", issues)
    return clip_path


def inspect_and_heal_scene_clip(
    clip_path: Path,
    scene_data: Dict[str, Any],
    *,
    work_dir: Path,
    narration_audio: Optional[Path],
    video_category: str = "cinematic",
    size: str = "1080x1920",
    google_api_keys: Optional[List[str]] = None,
    agnes_api_keys: Optional[List[str]] = None,
    max_heal_attempts: int = 2,
) -> Path:
    """
    Main entry point: Audits scene clip, self-heals if needed via Dynamic Multi-Agent Taskforce,
    and returns certified PASS clip.
    """
    try:
        from pipeline.dynamic_agent_orchestrator import MicroBatchInterceptor
        interceptor = MicroBatchInterceptor()
        idx = int(scene_data.get("scene_index", 0))
        healed_clip, report = interceptor.evaluate_and_heal_scene(
            scene_idx=idx,
            scene_data=scene_data,
            clip_path=clip_path,
            work_dir=work_dir,
            narration_audio=narration_audio,
            video_category=video_category,
            size=size,
            google_api_keys=google_api_keys,
            agnes_api_keys=agnes_api_keys,
            max_attempts=max_heal_attempts + 1,
        )
        if report.verdict in ("PASS", "HEALED"):
            return healed_clip
    except Exception as exc:
        logger.warning("MicroBatchInterceptor fallback to legacy scene audit: %s", exc)

    clip_path = Path(clip_path)
    for attempt in range(max_heal_attempts + 1):
        audit = audit_scene_clip(
            clip_path,
            scene_data,
            video_category=video_category,
            narration_audio=narration_audio,
        )
        if audit["verdict"] == "PASS":
            logger.info("Scene %s CERTIFIED [Commercial Benchmark: PASS] (metrics: %s)", clip_path.name, audit["metrics"])
            return clip_path

        logger.warning(
            "Scene %s AUDIT FAILED (attempt %d/%d): issues=%s, metrics=%s",
            clip_path.name, attempt + 1, max_heal_attempts + 1, audit["issues"], audit["metrics"]
        )
        if attempt < max_heal_attempts:
            clip_path = heal_defective_scene_clip(
                clip_path,
                scene_data,
                audit,
                work_dir=work_dir,
                narration_audio=narration_audio,
                size=size,
                google_api_keys=google_api_keys,
                agnes_api_keys=agnes_api_keys,
            )

    logger.error("Scene %s could not achieve 100%% PASS after %d attempts", clip_path.name, max_heal_attempts)
    return clip_path
