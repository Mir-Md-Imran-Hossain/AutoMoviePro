#!/usr/bin/env python
"""Resume short E2E from partial work dir (reuse TTS/scenes) → finish package."""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("short_resume")

UPLOAD_READY = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_short_v3"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"
REPORT = ROOT / "output" / "SHORT_E2E_TEST_REPORT.json"
WORK = UPLOAD_READY / "_work" / "20260731_202318" / "attempt_1"


def main() -> int:
    ctx = {"started_at": datetime.now().isoformat(), "mode": "resume"}
    try:
        from app import db as store
        from pipeline import product_registry as preg
        from pipeline.media_assets import generate_thumbnail
        from pipeline.package_export import export_upload_package
        from pipeline.video_pipeline import generate_video

        store.init_db()
        preg.ensure_schema()
        channel = store.list_channels()[0]
        if (ASSETS / "logo.png").exists():
            channel["logo_path"] = str(ASSETS / "logo.png")
        if (ASSETS / "intro.mp4").exists():
            channel["intro_path"] = str(ASSETS / "intro.mp4")

        plan = json.loads((WORK / "director_plan.json").read_text(encoding="utf-8"))
        topic = plan.get("topic") or "Google Pixel 9a"
        gadget = {
            "name": topic,
            "why_trending": "Resume of short E2E after Google TTS quota backoff",
            "search_query": f"{topic} review",
            "category": (plan.get("analysis") or {}).get("product_category") or "phone",
            "source": "resume",
        }
        # Wait for free-tier minute window to recover
        logger.info("Waiting 70s for Google AI Studio TTS quota window...")
        time.sleep(70)

        result = generate_video(
            channel,
            video_type="short",
            topic=topic,
            research_notes=json.dumps({"resume": True, "blocklist": preg.blocked_names(channel_id=channel.get("id"))}, ensure_ascii=False),
            work_dir=WORK,
        )
        logger.info("Generated: %s (%.1fs)", result.get("topic"), result.get("duration"))

        thumb = WORK / "thumbnail.png"
        generate_thumbnail(
            result["title"],
            result.get("topic") or topic,
            thumb,
            pollinations_key=channel.get("pollinations_api") or "",
            logo_path=Path(channel["logo_path"]) if channel.get("logo_path") else None,
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
                "job_id": result.get("job_id"),
                "director_provider": result.get("director_provider"),
                "tts": "google_ai_studio",
                "resume": True,
                "duplicate_guard": True,
            },
        )
        dup, matched = preg.is_duplicate(topic, channel_id=channel.get("id"))
        ctx.update(
            {
                "ok": True,
                "package": str(pkg),
                "topic": result.get("topic"),
                "title": result.get("title"),
                "duration": result.get("duration"),
                "director_provider": result.get("director_provider"),
                "duplicate_self_test": {"is_duplicate": dup, "matched": matched},
                "finished_at": datetime.now().isoformat(),
            }
        )
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("\n========== SHORT E2E SUCCESS (resume) ==========")
        print("Topic:", result.get("topic"))
        print("Duration:", result.get("duration"))
        print("Package:", pkg)
        return 0
    except Exception as exc:
        ctx["ok"] = False
        ctx["fatal_error"] = str(exc)
        ctx["fatal_trace"] = traceback.format_exc()
        ctx["finished_at"] = datetime.now().isoformat()
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("\n========== SHORT E2E FAILED (resume) ==========")
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
