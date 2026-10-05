#!/usr/bin/env python
"""Rebuild OnePlus short using REAL product photos + Google TTS."""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rebuild_real")

UPLOAD = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v4"


def main() -> int:
    from app import db as store
    from pipeline.compose import ffmpeg_bin, ffprobe_duration
    from pipeline.media_assets import generate_product_still, generate_thumbnail
    from pipeline.package_export import export_upload_package
    from pipeline.scene_builder import _image_to_motion, concat_av_clips, mix_logo_safe
    from pipeline.tts_google import synthesize_narration
    from pipeline.video_pipeline import _has_audio, _intro_with_silence, _trim_reencode

    store.init_db()
    ch = store.list_channels()[0]
    keys = [k for k in [ch.get("google_api_1"), ch.get("google_api_2")] if k]
    # wipe prior v4 packages
    if UPLOAD.exists():
        for p in UPLOAD.iterdir():
            if p.is_dir() and p.name.startswith("short_"):
                shutil.rmtree(p, ignore_errors=True)
            if p.name.startswith("_"):
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    work = UPLOAD / "_work_real"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    product = "OnePlus 13"
    size = "1080x1920"
    scenes = [
        ("intro", "আজকের রিভিউতে আছে OnePlus 13 — ফ্ল্যাগশিপ কেন এত আলোচনায়, এক নজরে দেখি।"),
        ("design", "ডিজাইনে Hasselblad ক্যামেরা আইল্যান্ড আর প্রিমিয়াম গ্লাস ব্যাক চোখে পড়ে।"),
        ("display", "ডিসপ্লে উজ্জ্বল ও স্মুথ — স্ক্রলিং অভিজ্ঞতা দৈনন্দিন ব্যবহারে আরাম দেয়।"),
        ("camera", "ক্যামেরা মডিউল ম্যাক্রোতেই বোঝা যায় — ডেলাইট ও পোর্ট্রেট শটের জন্য তৈরি।"),
        ("battery", "ব্যাটারি ও ফাস্ট চার্জ রোজকার ব্যবহারের আরাম নির্ধারণ করে।"),
    ]

    clips = []
    assets = ROOT / "assets" / "channels" / "gadget_review_society"
    intro = assets / "intro.mp4"
    if intro.exists():
        intro_av = work / "intro_av.mp4"
        _intro_with_silence(intro, intro_av, size, seconds=2.5)
        if intro_av.exists():
            clips.append(intro_av)

    for i, (el, narr) in enumerate(scenes):
        audio = synthesize_narration(narr, work / f"narr_{i:02d}", google_api_keys=keys)
        still = work / f"product_{i:02d}_{el}.png"
        generate_product_still(product, el, still, width=1080, height=1920, google_api_keys=keys)
        # ensure png readable
        if not still.exists():
            jpg = still.with_suffix(".jpg")
            if jpg.exists():
                still = jpg
        motion = work / f"productclip_{i:02d}.mp4"
        dur = max(2.0, ffprobe_duration(audio) + 0.25)
        _image_to_motion(still, motion, dur, size, element=el)
        target = work / f"scene_{i:02d}_{el}.mp4"
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=25,format=yuv420p"
        subprocess.run(
            [
                ffmpeg_bin(),
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(motion),
                "-i",
                str(audio),
                "-t",
                f"{dur:.3f}",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(target),
            ],
            capture_output=True,
        )
        clips.append(target)
        logger.info("scene %s still=%s bytes", el, still.stat().st_size)

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
        gadget={"name": product, "source": "real_product_photo"},
        video_type="short",
        video_path=final,
        title="OnePlus 13 Review 2026 — ডিজাইন, ডিসপ্লে, ক্যামেরা",
        description="OnePlus 13 gadget review\n#OnePlus13 #GadgetReview #TechBD",
        tags=["OnePlus 13", "review", "2026", "Hasselblad"],
        thumbnail_path=thumb if thumb.exists() else None,
        extra={
            "tts": "google_ai_studio",
            "visual": "real_catalog_product_photos",
            "duration": ffprobe_duration(final),
        },
    )
    print("SUCCESS", pkg)
    print("DURATION", ffprobe_duration(final))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
