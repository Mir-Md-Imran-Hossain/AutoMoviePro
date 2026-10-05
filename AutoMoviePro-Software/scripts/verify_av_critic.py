"""Verify AV-sync critic on an existing v5 scene; optional one regenerate loop."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("verify_av_critic")

from app import db as store
from pipeline.av_sync_critic import critique_scene_clip, persist_critique
from pipeline.scene_builder import build_dialogue_clip


def main() -> int:
    work_src = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v5" / "_work"
    video = work_src / "scene_02_display.mp4"
    audio = work_src / "narr_02.m4a"
    if not audio.exists():
        audio = work_src / "narr_02.wav"
    if not video.exists() or not audio.exists():
        logger.error("Missing scene/audio under %s", work_src)
        return 2

    channels = store.list_channels()
    if not channels:
        logger.error("No channels in DB")
        return 2
    ch = channels[0]
    keys = [ch.get("google_api_1") or "", ch.get("google_api_2") or ""]
    keys = [k for k in keys if k.strip()]
    if not keys:
        logger.error("No Google API keys on channel")
        return 2

    narration = (
        "ডিসপ্লেতে উজ্জ্বলতা আর স্ক্রল স্মুথনেস কন্টেন্ট দেখার অভিজ্ঞতাকে বদলে দেয়।"
    )
    keywords = ["display", "screen", "brightness", "scroll"]
    prompt = (
        "Cinematic close-up of OnePlus 13 AMOLED display with colorful scrolling UI, "
        "studio lighting, sharp focus, no text no watermark"
    )

    out = ROOT / "output" / "_av_critic_verify"
    out.mkdir(parents=True, exist_ok=True)

    logger.info("Running critic on %s ...", video.name)
    critique = critique_scene_clip(
        video_path=video,
        audio_path=audio,
        narration_bn=narration,
        keyword_triggers=keywords,
        exact_ai_video_prompt=prompt,
        niche="Gadget Review",
        element="display",
        google_api_keys=keys,
        product_name="OnePlus 13",
    )
    persist_critique(out, 2, 1, critique, prompt)
    summary = {
        "match_score": critique.get("match_score"),
        "passed": critique.get("passed"),
        "issues": critique.get("issues"),
        "critical_issues": critique.get("critical_issues"),
        "missed_keywords": critique.get("missed_keywords"),
        "provider": (critique.get("raw") or {}).get("_provider"),
        "has_revised_prompt": bool(critique.get("revised_prompt")),
    }
    (out / "verify_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Critic summary: %s", json.dumps(summary, ensure_ascii=False))

    # One regenerate loop if critic failed (or always do a single-attempt rebuild with revised prompt)
    if not critique.get("passed") and ch.get("agnes_api"):
        logger.info("Critic failed — running one regenerate attempt via build_dialogue_clip")
        regen_work = out / "regen_scene"
        regen_work.mkdir(parents=True, exist_ok=True)
        # copy audio into regen work with expected name pattern not required
        clip = build_dialogue_clip(
            work=regen_work,
            idx=2,
            narration_audio=audio,
            visual_query="OnePlus 13 display screen scrolling",
            visual_prompt=prompt,
            element="display",
            size="1080x1920",
            product_name="OnePlus 13",
            agnes_api=ch.get("agnes_api") or "",
            google_api_keys=keys,
            subtitle_text=narration,
            keyword_triggers=keywords,
            exact_ai_video_prompt=critique.get("revised_prompt") or prompt,
            niche="Gadget Review",
            max_av_retries=1,
            require_agnes=True,
        )
        logger.info("Regen clip: %s exists=%s size=%s", clip, clip.exists(), clip.stat().st_size if clip.exists() else 0)
        summary["regen_clip"] = str(clip)
        summary["regen_ok"] = bool(clip.exists() and clip.stat().st_size > 20000)
        (out / "verify_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif critique.get("passed"):
        logger.info("Critic passed — skipping regenerate")
        # Still exercise prompt rewrite path lightly by forcing a second critique persistence
        summary["regen_skipped"] = "passed"
        (out / "verify_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        logger.warning("Critic failed but no Agnes key — skip regenerate")
        summary["regen_skipped"] = "no_agnes"
        (out / "verify_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
