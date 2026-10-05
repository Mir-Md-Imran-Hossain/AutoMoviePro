#!/usr/bin/env python
"""Fresh short E2E after TTS + product-matched footage fixes."""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("short_e2e_v4")

UPLOAD_READY = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v4"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"
REPORT = ROOT / "output" / "SHORT_E2E_V4_REPORT.json"


def main() -> int:
    ctx: dict = {"started_at": datetime.now().isoformat()}
    try:
        from app import db as store
        from pipeline import product_registry as preg
        from pipeline.compose import ffmpeg_bin, ffprobe_bin
        from pipeline.media_assets import generate_thumbnail
        from pipeline.package_export import export_upload_package
        from pipeline.trending_search import find_trending_gadgets
        from pipeline.video_pipeline import generate_video
        import subprocess

        store.init_db()
        preg.ensure_schema()
        subprocess.run([ffmpeg_bin(), "-version"], check=True, capture_output=True)

        channel = store.list_channels()[0]
        if (ASSETS / "logo.png").exists():
            channel["logo_path"] = str(ASSETS / "logo.png")
        if (ASSETS / "intro.mp4").exists():
            channel["intro_path"] = str(ASSETS / "intro.mp4")

        # Keep prior reviewed products blocked
        for name in ["Nothing Phone (3)", "Samsung Galaxy Buds 4", "Google Pixel 9a"]:
            preg.register_product(
                name,
                channel_id=channel.get("id"),
                niche=channel.get("niche") or "Gadget Review",
                video_type="seed",
            )
        blocked = preg.blocked_names(channel_id=channel.get("id"))
        google_keys = [k for k in [channel.get("google_api_1"), channel.get("google_api_2")] if k]

        gadgets = find_trending_gadgets(google_keys, count=1, exclude_names=blocked, fetch_multiplier=6)
        if not gadgets:
            raise RuntimeError("No fresh gadget")
        gadget = gadgets[0]
        logger.info("Topic: %s", gadget["name"])

        UPLOAD_READY.mkdir(parents=True, exist_ok=True)
        work = UPLOAD_READY / "_work" / datetime.now().strftime("%Y%m%d_%H%M%S")
        work.mkdir(parents=True, exist_ok=True)

        result = generate_video(
            channel,
            video_type="short",
            topic=gadget["name"],
            research_notes=json.dumps(gadget, ensure_ascii=False),
            work_dir=work,
        )
        # Require product AI sources for scenes
        sources = list(work.glob("scene_*_source.txt"))
        product_clips = list(work.glob("productclip_*.mp4")) + list(work.glob("product_*.png"))
        ctx["visual_sources"] = [p.read_text(encoding="utf-8") for p in sources]
        ctx["product_assets"] = [p.name for p in product_clips]
        if not product_clips:
            logger.warning("No product_* assets — visuals may still be weak")

        thumb = work / "thumbnail.png"
        generate_thumbnail(
            result["title"],
            result.get("topic") or gadget["name"],
            thumb,
            pollinations_key=channel.get("pollinations_api") or "",
            logo_path=Path(channel["logo_path"]) if channel.get("logo_path") else None,
            google_api_keys=google_keys,
        )
        pkg = export_upload_package(
            dest_root=UPLOAD_READY,
            channel_name=channel.get("youtube_name") or "গেজেট রিভিউ সোসাইটি",
            gadget=gadget,
            video_type="short",
            video_path=Path(result["path"]),
            title=result["title"],
            description=result["description"],
            tags=result.get("tags") or [],
            thumbnail_path=thumb if thumb.exists() else None,
            extra={
                "duration": result.get("duration"),
                "tts": "google_ai_studio",
                "director": result.get("director_provider"),
                "topic": result.get("topic"),
                "product_visual_assets": ctx["product_assets"],
            },
        )
        ctx.update(
            {
                "ok": True,
                "package": str(pkg),
                "topic": result.get("topic"),
                "title": result.get("title"),
                "duration": result.get("duration"),
                "director_provider": result.get("director_provider"),
                "finished_at": datetime.now().isoformat(),
            }
        )
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("SUCCESS", pkg)
        print("TOPIC", result.get("topic"), "DUR", result.get("duration"))
        print("PRODUCT_ASSETS", ctx["product_assets"])
        return 0
    except Exception as exc:
        ctx["ok"] = False
        ctx["fatal_error"] = str(exc)
        ctx["fatal_trace"] = traceback.format_exc()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("FAILED", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
