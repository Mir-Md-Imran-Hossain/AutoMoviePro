#!/usr/bin/env python
"""Resume Agnes short rebuild from scene 5 (battery) then package."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agnes_resume")

UPLOAD = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v5"
WORK = UPLOAD / "_work"


def main() -> int:
    from app import db as store
    from pipeline.compose import ffprobe_duration
    from pipeline.media_assets import generate_thumbnail
    from pipeline.package_export import export_upload_package
    from pipeline.scene_builder import build_dialogue_clip, concat_av_clips, mix_logo_safe
    from pipeline.tts_google import synthesize_narration
    from pipeline.video_pipeline import _has_audio, _trim_reencode

    store.init_db()
    ch = store.list_channels()[0]
    keys = [k for k in [ch.get("google_api_1"), ch.get("google_api_2")] if k]
    product = "OnePlus 13"
    size = "1080x1920"
    assets = ROOT / "assets" / "channels" / "gadget_review_society"

    # Wait for TTS minute window
    logger.info("Waiting 45s for Google TTS window...")
    time.sleep(45)

    i = 4
    el = "battery"
    narr = "ব্যাটারি ও ফাস্ট চার্জ রোজকার ব্যবহারের আরাম নির্ধারণ করে।"
    vprompt = "OnePlus 13 plugged into charger cable, subtle charging glow, product clearly visible"

    audio = synthesize_narration(narr, WORK / f"narr_{i:02d}", google_api_keys=keys)
    scene = build_dialogue_clip(
        work=WORK,
        idx=i,
        narration_audio=audio,
        visual_query=f"{product} {el}",
        visual_prompt=vprompt,
        element=el,
        size=size,
        product_name=product,
        pexels_api=ch.get("pexels_api") or "",
        agnes_api=ch.get("agnes_api") or "",
        google_api_keys=keys,
        subtitle_text=narr,
        require_agnes=True,
    )
    logger.info("Battery scene done: %s", scene)

    clips = []
    intro = WORK / "intro_av.mp4"
    if intro.exists():
        clips.append(intro)
    for idx, name in enumerate(["intro", "design", "display", "camera", "battery"]):
        p = WORK / f"scene_{idx:02d}_{name}.mp4"
        if not p.exists():
            raise RuntimeError(f"missing {p}")
        clips.append(p)

    agnes_files = [p.name for p in sorted(WORK.glob("agnes_*.mp4"))]
    if len(agnes_files) < 5:
        raise RuntimeError(f"expected 5 Agnes clips, got {agnes_files}")

    body = WORK / "body.mp4"
    concat_av_clips(clips, body, size)
    branded = WORK / "branded.mp4"
    logo = assets / "logo.png"
    mix_logo_safe(body, logo if logo.exists() else None, branded)
    final = WORK / "final_short.mp4"
    _trim_reencode(branded if branded.exists() else body, final, 120, size)
    if not _has_audio(final):
        raise RuntimeError("no audio")

    thumb = WORK / "thumb.png"
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
        description="OnePlus 13 short\nVisuals: Agnes AI video per dialogue beat\n#OnePlus13 #GadgetReview",
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
