#!/usr/bin/env python
"""
Complete SHORT video E2E test:
  seed duplicates → trending (fresh) topic → director → Google AI Studio TTS
  → footage → compose → thumbnail → upload-ready package
"""
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
logger = logging.getLogger("short_e2e")

UPLOAD_READY = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_short_v3"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"
REPORT = ROOT / "output" / "SHORT_E2E_TEST_REPORT.json"

# Previously produced reviews — must never repeat
SEED_REVIEWED = [
    "Nothing Phone (3)",
    "Nothing Phone 3",
    "Samsung Galaxy Buds 4",
    "Galaxy Buds 4",
]


def main() -> int:
    ctx: dict = {"steps": [], "started_at": datetime.now().isoformat()}
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

        # FFmpeg
        subprocess.run([ffmpeg_bin(), "-version"], check=True, capture_output=True)
        subprocess.run([ffprobe_bin(), "-version"], check=True, capture_output=True)
        ctx["steps"].append({"step": "ffmpeg", "ok": True})

        channels = store.list_channels()
        if not channels:
            raise RuntimeError("No channel in local.db — run channel setup first")
        channel = channels[0]
        if not channel.get("google_api_1"):
            raise RuntimeError("Channel missing Google AI Studio API key")

        # Ensure logo/intro paths
        logo = Path(channel.get("logo_path") or ASSETS / "logo.png")
        intro = Path(channel.get("intro_path") or ASSETS / "intro.mp4")
        if not logo.exists() and (ASSETS / "logo.png").exists():
            logo = ASSETS / "logo.png"
            channel["logo_path"] = str(logo)
        if not intro.exists() and (ASSETS / "intro.mp4").exists():
            intro = ASSETS / "intro.mp4"
            channel["intro_path"] = str(intro)
        ctx["channel_id"] = channel.get("id")
        ctx["steps"].append({"step": "channel", "ok": True, "id": channel.get("id")})

        # Strong duplicate seed from prior tests
        seeded = preg.seed_from_names(
            SEED_REVIEWED,
            channel_id=channel.get("id"),
            niche=channel.get("niche") or "Gadget Review",
            video_type="seed",
        )
        blocked = preg.blocked_names(channel_id=channel.get("id"))
        ctx["seeded_new"] = seeded
        ctx["blocklist"] = blocked
        ctx["steps"].append({"step": "seed_duplicates", "ok": True, "blocked_count": len(blocked)})
        logger.info("Blocklist (%s): %s", len(blocked), blocked)

        google_keys = [channel.get("google_api_1") or "", channel.get("google_api_2") or ""]
        google_keys = [k for k in google_keys if k]

        gadgets = find_trending_gadgets(
            google_keys,
            count=1,
            exclude_names=blocked,
            fetch_multiplier=6,
        )
        if not gadgets:
            raise RuntimeError("No fresh trending gadget found (all blocked?)")
        gadget = gadgets[0]
        # Final hard check
        dup, matched = preg.is_duplicate(
            gadget["name"], channel_id=channel.get("id"), niche=channel.get("niche") or ""
        )
        if dup:
            raise RuntimeError(f"Trending returned duplicate {gadget['name']!r} ~ {matched!r}")
        ctx["gadget"] = gadget
        ctx["steps"].append({"step": "trending_topic", "ok": True, "name": gadget["name"]})
        logger.info("Fresh topic: %s (%s)", gadget["name"], gadget.get("why_trending"))

        UPLOAD_READY.mkdir(parents=True, exist_ok=True)
        work = UPLOAD_READY / "_work" / datetime.now().strftime("%Y%m%d_%H%M%S")
        work.mkdir(parents=True, exist_ok=True)

        notes = json.dumps(
            {
                "why": gadget.get("why_trending"),
                "hits": gadget.get("google_hits"),
                "query": gadget.get("search_query"),
                "source": gadget.get("source"),
                "blocklist_applied": blocked,
            },
            ensure_ascii=False,
        )

        result = None
        last_err = None
        for attempt in range(1, 4):
            try:
                logger.info("Generate short attempt %s for %s", attempt, gadget["name"])
                result = generate_video(
                    channel,
                    video_type="short",
                    topic=gadget["name"],
                    research_notes=notes,
                    work_dir=work / f"attempt_{attempt}",
                )
                dur = float(result.get("duration") or 0)
                if dur <= 0 or dur > 122:
                    raise RuntimeError(f"bad duration {dur}")
                if not Path(result["path"]).exists() or Path(result["path"]).stat().st_size < 20000:
                    raise RuntimeError("video too small")
                if not result.get("has_audio"):
                    raise RuntimeError("missing audio")
                break
            except Exception as exc:
                last_err = exc
                logger.warning("attempt failed: %s", exc)
                # If duplicate, pick another gadget
                if "Duplicate" in str(exc) or "non-duplicate" in str(exc):
                    more = find_trending_gadgets(
                        google_keys,
                        count=3,
                        exclude_names=blocked + [gadget["name"]],
                        fetch_multiplier=5,
                    )
                    if more:
                        gadget = more[0]
                        ctx["gadget"] = gadget
                        notes = json.dumps({"retry_topic": gadget}, ensure_ascii=False)
                        logger.info("Switched topic to %s", gadget["name"])
        if result is None:
            raise RuntimeError(f"Short generation failed: {last_err}")

        ctx["generation"] = {
            "topic": result.get("topic"),
            "title": result.get("title"),
            "duration": result.get("duration"),
            "director_provider": result.get("director_provider"),
            "path": result.get("path"),
            "job_id": result.get("job_id"),
        }
        ctx["steps"].append({"step": "generate_short", "ok": True, **ctx["generation"]})

        # Prove Google TTS was used: narration m4a files in workdir
        work_dir = Path(result["work_dir"])
        narr_files = list(work_dir.glob("narration_*.m4a")) + list(work_dir.glob("narration_*.wav"))
        ctx["tts_files"] = [str(p.name) for p in narr_files]
        if not narr_files:
            raise RuntimeError("No Google TTS narration files found in work dir")
        ctx["steps"].append({"step": "google_tts_verify", "ok": True, "count": len(narr_files)})

        thumb = work / "thumbnail.png"
        generate_thumbnail(
            result["title"],
            result.get("topic") or gadget["name"],
            thumb,
            pollinations_key=channel.get("pollinations_api") or "",
            logo_path=logo if logo.exists() else None,
        )
        if not thumb.exists():
            raise RuntimeError("thumbnail missing")
        ctx["steps"].append({"step": "thumbnail", "ok": True})

        pkg = export_upload_package(
            dest_root=UPLOAD_READY,
            channel_name=channel.get("youtube_name") or "গেজেট রিভিউ সোসাইটি",
            gadget=gadget,
            video_type="short",
            video_path=Path(result["path"]),
            title=result["title"],
            description=result["description"],
            tags=result.get("tags") or [],
            thumbnail_path=thumb,
            extra={
                "duration": result.get("duration"),
                "job_id": result.get("job_id"),
                "director_provider": result.get("director_provider"),
                "tts": "google_ai_studio",
                "topic": result.get("topic"),
                "duplicate_guard": True,
                "blocklist_size": len(blocked),
            },
        )
        ctx["package"] = str(pkg)
        ctx["steps"].append({"step": "export_package", "ok": True, "folder": str(pkg)})

        # Duplicate system self-test: same product must now be blocked
        dup_now, matched_now = preg.is_duplicate(
            result.get("topic") or gadget["name"],
            channel_id=channel.get("id"),
        )
        ctx["duplicate_self_test"] = {"is_duplicate": dup_now, "matched": matched_now}
        if not dup_now:
            raise RuntimeError("Product was not registered in duplicate store after generation")
        ctx["steps"].append({"step": "duplicate_self_test", "ok": True})

        ctx["ok"] = True
        ctx["finished_at"] = datetime.now().isoformat()
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("\n========== SHORT E2E SUCCESS ==========")
        print("Topic:", result.get("topic"))
        print("Title:", result.get("title"))
        print("Duration:", result.get("duration"), "s")
        print("Director:", result.get("director_provider"))
        print("TTS: Google AI Studio")
        print("Package:", pkg)
        print("Report:", REPORT)
        return 0
    except Exception as exc:
        ctx["ok"] = False
        ctx["fatal_error"] = str(exc)
        ctx["fatal_trace"] = traceback.format_exc()
        ctx["finished_at"] = datetime.now().isoformat()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        print("\n========== SHORT E2E FAILED ==========")
        print(exc)
        print("Report:", REPORT)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
