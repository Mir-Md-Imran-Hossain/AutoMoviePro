#!/usr/bin/env python
"""Rebuild short: Google TTS + Agnes VIDEO clip per dialogue (no still slideshow)."""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agnes_rebuild")

UPLOAD = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v5"


def main() -> int:
    from app import db as store
    from pipeline.compose import ffprobe_duration
    from pipeline.media_assets import generate_thumbnail
    from pipeline.package_export import export_upload_package
    from pipeline.scene_builder import build_dialogue_clip, concat_av_clips, mix_logo_safe
    from pipeline.tts_google import synthesize_narration
    from pipeline.video_pipeline import _has_audio, _intro_with_silence, _trim_reencode

    store.init_db()
    ch = store.list_channels()[0]
    if not (ch.get("agnes_api") or "").strip():
        raise RuntimeError("Channel missing Agnes API key")
    keys = [k for k in [ch.get("google_api_1"), ch.get("google_api_2")] if k]

    if UPLOAD.exists():
        shutil.rmtree(UPLOAD, ignore_errors=True)
    work = UPLOAD / "_work"
    work.mkdir(parents=True)

    product = "OnePlus 13"
    size = "1080x1920"
    scenes = [
        (
            "intro",
            "আজকের রিভিউতে আছে OnePlus 13 — ফ্ল্যাগশিপ কেন এত আলোচনায়, এক নজরে দেখি।",
            "cinematic hero orbit of OnePlus 13 on dark desk, Hasselblad camera island visible",
        ),
        (
            "design",
            "ডিজাইনে Hasselblad ক্যামেরা আইল্যান্ড আর প্রিমিয়াম গ্লাস ব্যাক চোখে পড়ে।",
            "slow macro pan across OnePlus 13 back glass and circular camera module",
        ),
        (
            "display",
            "ডিসপ্লে উজ্জ্বল ও স্মুথ — স্ক্রলিং অভিজ্ঞতা দৈনন্দিন ব্যবহারে আরাম দেয়।",
            "OnePlus 13 front display ON with colorful UI, gentle push-in camera move",
        ),
        (
            "camera",
            "ক্যামেরা মডিউল ম্যাক্রোতেই বোঝা যায় — ডেলাইট ও পোর্ট্রেট শটের জন্য তৈরি।",
            "extreme close-up video of OnePlus 13 Hasselblad triple camera lenses",
        ),
        (
            "battery",
            "ব্যাটারি ও ফাস্ট চার্জ রোজকার ব্যবহারের আরাম নির্ধারণ করে।",
            "OnePlus 13 plugged into charger cable, subtle charging glow, product clearly visible",
        ),
    ]

    clips = []
    assets = ROOT / "assets" / "channels" / "gadget_review_society"
    intro = assets / "intro.mp4"
    if intro.exists():
        intro_av = work / "intro_av.mp4"
        _intro_with_silence(intro, intro_av, size, seconds=2.0)
        if intro_av.exists():
            clips.append(intro_av)

    agnes_files = []
    for i, (el, narr, vprompt) in enumerate(scenes):
        logger.info("=== Scene %s/%s %s ===", i + 1, len(scenes), el)
        audio = synthesize_narration(narr, work / f"narr_{i:02d}", google_api_keys=keys)
        scene = build_dialogue_clip(
            work=work,
            idx=i,
            narration_audio=audio,
            visual_query=f"{product} {el}",
            visual_prompt=vprompt,
            element=el,
            size=size,
            product_name=product,
            pexels_api=ch.get("pexels_api") or "",
            pollinations_key=ch.get("pollinations_api") or "",
            agnes_api=ch.get("agnes_api") or "",
            google_api_keys=keys,
            subtitle_text=narr,
            require_agnes=True,
        )
        clips.append(scene)
        agnes_clip = work / f"agnes_{i:02d}_{el}.mp4"
        if agnes_clip.exists():
            agnes_files.append(agnes_clip.name)
            logger.info("Agnes file OK: %s (%s bytes)", agnes_clip.name, agnes_clip.stat().st_size)
        else:
            raise RuntimeError(f"Missing Agnes clip for scene {i} {el}")

    body = work / "body.mp4"
    concat_av_clips(clips, body, size)
    branded = work / "branded.mp4"
    logo = assets / "logo.png"
    mix_logo_safe(body, logo if logo.exists() else None, branded)
    final = work / "final_short.mp4"
    _trim_reencode(branded if branded.exists() else body, final, 120, size)
    if not _has_audio(final):
        raise RuntimeError("no audio")

    thumb = work / "thumb.png"
    generate_thumbnail(
        "OnePlus 13 Review 2026",
        product,
        thumb,
        google_api_keys=keys,
        logo_path=logo if logo.exists() else None,
    )
    pkg = export_upload_package(
        dest_root=UPLOAD,
        channel_name=ch.get("youtube_name") or "গেজেট রিভিউ সোসাইটি",
        gadget={"name": product, "source": "agnes_dialogue_video"},
        video_type="short",
        video_path=final,
        title="OnePlus 13 Review 2026 — Agnes dialogue visuals",
        description="OnePlus 13 short review\nVisuals: Agnes AI video per dialogue\n#OnePlus13 #GadgetReview",
        tags=["OnePlus 13", "Agnes", "review", "2026"],
        thumbnail_path=thumb if thumb.exists() else None,
        extra={
            "tts": "google_ai_studio",
            "visual": "agnes_video_per_dialogue",
            "agnes_clips": agnes_files,
            "duration": ffprobe_duration(final),
        },
    )
    print("SUCCESS", pkg)
    print("AGNES_CLIPS", agnes_files)
    print("DURATION", ffprobe_duration(final))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
