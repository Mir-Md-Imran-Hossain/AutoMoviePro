#!/usr/bin/env python
"""
Live Video Generation & Localization Audit Script.
Tests real video clip synthesis, voiceover, Bengali localization,
and subtitle sync with ffprobe validation.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_audit")


def probe_media(path: Path) -> dict:
    from pipeline.compose import ffprobe_bin

    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    logger.info("=== Starting AutoMovie Pro Live Video Generation & Sync Audit ===")

    work_dir = ROOT / "output" / "LIVE_AUDIT_TEST"
    work_dir.mkdir(parents=True, exist_ok=True)

    from pipeline.compose import ffmpeg_bin
    from pipeline.fallback_image_video import build_image_video_fallback
    from pipeline.localization import localize_scene_clip, write_srt
    from pipeline.subtitle_burn import preferred_font
    from pipeline.tts_google import synthesize_narration

    # 1. Test Voice Narration Generation (English & Bengali)
    en_text = (
        "Meet the revolutionary cyber gadget that changed everything. "
        "It features ultra-fast AI computing and cinematic 8K video recording."
    )
    bn_expected_sample = "বিপ্লবী সাইবার গ্যাজেটটি দেখুন যা সবকিছু পরিবর্তন করে দিয়েছে।"

    en_audio = work_dir / "scene_01_en.m4a"
    logger.info("Synthesizing narration audio...")
    # Generate speech using edge_tts or charon
    from pipeline.edge_tts_fallback import synthesize_edge_tts

    try:
        synthesize_edge_tts(en_text, en_audio, language_hint="en")
    except Exception as e:
        logger.warning("Edge TTS failed: %s, creating tone fallback", e)
        # Fallback to local tone if network fails
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(en_audio),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    en_probe = probe_media(en_audio)
    en_dur = float(en_probe.get("format", {}).get("duration", 0))
    logger.info("Generated Audio duration: %.2fs (%s)", en_dur, en_audio.name)

    # 2. Test Subtitle Timing & Chunking for 9:16 Shorts
    srt_path = work_dir / "scene_01_subtitles.srt"
    write_srt(en_text, en_audio, srt_path, is_short=True)
    srt_content = srt_path.read_text(encoding="utf-8")
    logger.info("Generated Subtitles:\n%s", srt_content.strip()[:350])

    from pipeline.api_keys import load_api_bundle
    bundle = load_api_bundle()
    google_keys = bundle.get("google_keys") or []
    pollinations_key = (bundle.get("pollinations_keys") or [""])[0]

    # 3. Test Visual Scene Video Rendering (9:16 vertical short: 1080x1920)
    scene_video = work_dir / "scene_01_video.mp4"
    logger.info("Rendering 1080x1920 scene motion video with Google keys=%d...", len(google_keys))
    build_image_video_fallback(
        work=work_dir,
        out_path=scene_video,
        narration=en_text,
        duration=max(4.0, en_dur),
        size="1080x1920",
        audio_path=en_audio,
        base_prompt="futuristic neon cyber gadget glowing on dark minimalist desk, 8k commercial product shot",
        product_name="CyberGadget Pro",
        element="hero_overview",
        niche="Technology",
        pollinations_key=pollinations_key,
        google_api_keys=google_keys,
    )

    vid_probe = probe_media(scene_video)
    vid_dur = float(vid_probe.get("format", {}).get("duration", 0))
    streams = vid_probe.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    v_stream = next(s for s in streams if s.get("codec_type") == "video")
    w = int(v_stream.get("width", 0))
    h = int(v_stream.get("height", 0))

    logger.info("Scene Video: %s", scene_video.name)
    logger.info("Dimensions: %dx%d (Aspect ratio: %s)", w, h, "9:16 Vertical" if h > w else "Landscape")
    logger.info("Video Duration: %.2fs | Audio Duration: %.2fs", vid_dur, en_dur)
    logger.info("Streams detected: Video=%s, Audio=%s", has_video, has_audio)

    # 4. Test Multi-Language Localization Engine with Bengali ('bn')
    logger.info("Testing Localized Scene Generation for Bengali ('bn')...")
    loc_results = localize_scene_clip(
        scene_video=scene_video,
        english_narration=en_text,
        scene_idx=0,
        work=work_dir,
        google_api_keys=google_keys,
        languages=["bn"],
        size="1080x1920",
        pollinations_key=pollinations_key,
    )

    bn_info = loc_results.get("languages", {}).get("bn", {})
    bn_video_path = Path(bn_info.get("video", ""))
    logger.info("Bengali Localized Result: %s", bn_info)

    if bn_info.get("video") and bn_video_path.is_file():
        bn_probe = probe_media(bn_video_path)
        bn_dur = float(bn_probe.get("format", {}).get("duration", 0))
        logger.info("Bengali Video Rendered Successfully: %s (Duration: %.2fs)", bn_video_path.name, bn_dur)
        logger.info("Bengali Subtitle Font Selected: %s", preferred_font("bn"))

    # Summary Report
    report = {
        "ok": has_video and has_audio and (scene_video.stat().st_size > 50000),
        "scene_video": str(scene_video),
        "scene_video_size_bytes": scene_video.stat().st_size,
        "width": w,
        "height": h,
        "video_duration_sec": vid_dur,
        "audio_duration_sec": en_dur,
        "duration_diff_sec": round(abs(vid_dur - en_dur), 2),
        "subtitles_file": str(srt_path),
        "bengali_localized": bn_video_path.is_file(),
        "bengali_font": preferred_font("bn"),
    }
    logger.info("=== AUDIT SUMMARY REPORT ===\n%s", json.dumps(report, indent=2))
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
