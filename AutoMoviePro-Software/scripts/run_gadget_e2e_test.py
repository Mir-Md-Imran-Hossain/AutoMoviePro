#!/usr/bin/env python
"""
E2E test: Gadget Review Society — trending gadgets → short + long upload-ready packages.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("e2e")

REF_ENV = Path(r"e:\All Project\AutoMovieProSAAS\AutoMoviePro\.env")
UPLOAD_READY = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"
REPORT = ROOT / "output" / "E2E_TEST_REPORT.json"


def load_keys_from_ref() -> dict:
    keys = {}
    if not REF_ENV.exists():
        logger.warning("Reference .env missing: %s", REF_ENV)
        return keys
    for line in REF_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def ensure_ffmpeg() -> str:
    from pipeline.compose import ffmpeg_bin, ffprobe_bin
    import subprocess

    ff = ffmpeg_bin()
    fp = ffprobe_bin()
    try:
        subprocess.run([ff, "-version"], check=True, capture_output=True)
        subprocess.run([fp, "-version"], check=True, capture_output=True)
        logger.info("FFmpeg OK: %s", ff)
        return ff
    except Exception as exc:
        raise RuntimeError(f"FFmpeg not ready: {ff} ({exc})") from exc


def step(name: str):
    def deco(fn):
        def wrapped(ctx):
            logger.info("=== STEP: %s ===", name)
            try:
                result = fn(ctx)
                ctx["steps"].append({"step": name, "ok": True})
                return result
            except Exception as exc:
                logger.error("STEP FAILED %s: %s", name, exc)
                ctx["steps"].append(
                    {
                        "step": name,
                        "ok": False,
                        "error": str(exc),
                        "trace": traceback.format_exc(),
                    }
                )
                # attempt self-heal hooks
                raise
        return wrapped
    return deco


@step("init_db_and_keys")
def init_db_and_keys(ctx):
    from app import db as store

    store.init_db()
    ref = load_keys_from_ref()
    google_keys = [ref.get(f"GOOGLE_API_KEY_{i}", "") for i in range(1, 4)]
    google_keys = [k for k in google_keys if k]
    agnes_keys = [ref.get(f"AGNES_API_KEY_{i}", "") for i in range(1, 7)]
    agnes_keys = [k for k in agnes_keys if k]
    ctx["keys"] = {
        "google": google_keys,
        "agnes": agnes_keys,
        "pexels": ref.get("PEXELS_API_KEY_1", ""),
        "pollinations": ref.get("POLLINATIONS_API_KEY_1", ""),
    }
    if not google_keys:
        raise RuntimeError("No Google API keys found in reference .env")
    return ctx["keys"]


@step("ensure_ffmpeg")
def step_ffmpeg(ctx):
    ctx["ffmpeg"] = ensure_ffmpeg()
    return ctx["ffmpeg"]


@step("create_channel_assets")
def create_channel_assets(ctx):
    from pipeline.media_assets import generate_intro_video, generate_logo_pollinations

    ASSETS.mkdir(parents=True, exist_ok=True)
    logo_path = ASSETS / "logo.png"
    intro_path = ASSETS / "intro.mp4"

    logo_prompt = (
        "Gadget Review Society logo, modern teal and amber, circuit and play-button motif, "
        "minimal flat brand mark, square app icon"
    )
    try:
        generate_logo_pollinations(
            logo_prompt,
            logo_path,
            api_key=ctx["keys"]["pollinations"],
        )
    except Exception as exc:
        logger.warning("Pollinations logo failed (%s) — PIL fallback", exc)
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGBA", (1024, 1024), (11, 18, 21, 255))
        d = ImageDraw.Draw(img)
        d.ellipse([120, 120, 904, 904], fill=(46, 196, 182, 255))
        d.polygon([(420, 340), (420, 684), (720, 512)], fill=(11, 18, 21, 255))
        d.text((280, 920), "GRS", fill=(244, 162, 97, 255))
        img.save(logo_path)

    intro = generate_intro_video(
        "Cinematic intro for Gadget Review Society tech YouTube channel, "
        "futuristic gadgets, neon accents, logo reveal energy",
        intro_path,
        agnes_keys=ctx["keys"]["agnes"][:2],
        pollinations_key=ctx["keys"]["pollinations"],
        duration_sec=4.0,
        size="1280x720",
        ffmpeg_bin=ctx["ffmpeg"],
    )
    ctx["logo_path"] = str(logo_path)
    ctx["intro_path"] = intro["path"]
    ctx["intro_provider"] = intro.get("provider")
    return {"logo": ctx["logo_path"], "intro": ctx["intro_path"], "intro_provider": ctx["intro_provider"]}


@step("setup_fake_channel")
def setup_fake_channel(ctx):
    from app import db as store

    payload = {
        "youtube_name": "গেজেট রিভিউ সোসাইটি",
        "facebook_name": "গেজেট রিভিউ সোসাইটি",
        "niche": "Gadget Review",
        "video_special": "Bangla tech review tone, honest pros/cons, trending gadgets only",
        "long_upload_time": "18:00",
        "short_upload_time": "12:00",
        "example_script": "আজকের গ্যাজেট... প্রোস... কনস... কাদের জন্য বেস্ট...",
        "generation_special": "Focus on specs that matter to BD buyers: price, battery, camera, value",
        "title_desc_special": "SEO titles with gadget name + 2026 + review; description with timestamps",
        "logo_path": ctx["logo_path"],
        "intro_path": ctx["intro_path"],
        "google_api_1": ctx["keys"]["google"][0],
        "google_api_2": ctx["keys"]["google"][1] if len(ctx["keys"]["google"]) > 1 else ctx["keys"]["google"][0],
        "agnes_api": ctx["keys"]["agnes"][0] if ctx["keys"]["agnes"] else "",
        "pexels_api": ctx["keys"]["pexels"],
        "youtube_session": "",
        "facebook_session": "",
        "enabled": 1,
    }
    cid = store.upsert_channel(payload)
    channel = store.get_channel(cid)
    ctx["channel"] = channel
    ctx["channel_id"] = cid
    return {"channel_id": cid, "name": channel.get("youtube_name")}


@step("find_trending_gadgets")
def find_trending(ctx):
    from pipeline.trending_search import find_trending_gadgets

    gadgets = find_trending_gadgets(ctx["keys"]["google"], count=2)
    if len(gadgets) < 2:
        raise RuntimeError("Could not resolve 2 trending gadgets")
    ctx["gadgets"] = gadgets
    logger.info("Trending gadgets: %s", [g["name"] for g in gadgets])
    return gadgets


@step("generate_short_and_long")
def generate_videos(ctx):
    from pipeline.media_assets import generate_thumbnail
    from pipeline.package_export import export_upload_package
    from pipeline.video_pipeline import generate_video

    UPLOAD_READY.mkdir(parents=True, exist_ok=True)
    packages = []
    # One short for gadget[0], one long for gadget[1] — user asked two videos (short+long)
    # covering the two trending gadgets.
    plan = [
        ("short", ctx["gadgets"][0]),
        ("long", ctx["gadgets"][1]),
    ]
    channel = ctx["channel"]

    for video_type, gadget in plan:
        notes = json.dumps(
            {
                "why": gadget.get("why_trending"),
                "hits": gadget.get("google_hits"),
                "query": gadget.get("search_query"),
                "source": gadget.get("source"),
            },
            ensure_ascii=False,
        )
        work = UPLOAD_READY / "_work" / f"{video_type}_{gadget['name'][:40]}".replace(" ", "_")
        work.mkdir(parents=True, exist_ok=True)

        result = None
        last_err = None
        for attempt in range(1, 4):
            try:
                logger.info("Generating %s for %s (attempt %s)", video_type, gadget["name"], attempt)
                result = generate_video(
                    channel,
                    video_type=video_type,
                    topic=gadget["name"],
                    research_notes=notes,
                    work_dir=work / f"attempt_{attempt}",
                )
                # validate duration caps
                dur = float(result.get("duration") or 0)
                cap = 120 if video_type == "short" else 300
                if dur <= 0:
                    raise RuntimeError("duration probe failed / empty video")
                if dur > cap + 2:
                    raise RuntimeError(f"duration {dur} exceeds cap {cap}")
                if not Path(result["path"]).exists() or Path(result["path"]).stat().st_size < 10000:
                    raise RuntimeError("output video too small")
                break
            except Exception as exc:
                last_err = exc
                logger.warning("generate retry: %s", exc)
        if result is None:
            raise RuntimeError(f"Failed to generate {video_type}: {last_err}")

        thumb = work / "thumbnail.png"
        generate_thumbnail(
            result["title"],
            gadget["name"],
            thumb,
            pollinations_key=ctx["keys"]["pollinations"],
            logo_path=Path(ctx["logo_path"]),
        )
        pkg = export_upload_package(
            dest_root=UPLOAD_READY,
            channel_name=channel.get("youtube_name") or "গেজেট রিভিউ সোসাইটি",
            gadget=gadget,
            video_type=video_type,
            video_path=Path(result["path"]),
            title=result["title"],
            description=result["description"],
            tags=result.get("tags") or [],
            thumbnail_path=thumb if thumb.exists() else None,
            extra={
                "duration": result.get("duration"),
                "job_id": result.get("job_id"),
                "intro_provider": ctx.get("intro_provider"),
            },
        )
        packages.append(
            {
                "type": video_type,
                "gadget": gadget["name"],
                "folder": str(pkg),
                "title": result["title"],
                "duration": result.get("duration"),
            }
        )
        logger.info("Package ready: %s", pkg)

    ctx["packages"] = packages
    return packages


def main() -> int:
    ctx = {"steps": [], "started_at": datetime.now().isoformat()}
    try:
        init_db_and_keys(ctx)
        step_ffmpeg(ctx)
        create_channel_assets(ctx)
        setup_fake_channel(ctx)
        find_trending(ctx)
        generate_videos(ctx)
        ctx["ok"] = True
        ctx["finished_at"] = datetime.now().isoformat()
        ctx["upload_ready_root"] = str(UPLOAD_READY)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("\n========== E2E SUCCESS ==========")
        print("Upload-ready folder:", UPLOAD_READY)
        for p in ctx.get("packages") or []:
            print(f" - [{p['type']}] {p['gadget']}: {p['folder']} ({p.get('duration')}s)")
            print(f"   title: {p['title']}")
        print("Report:", REPORT)
        return 0
    except Exception as exc:
        ctx["ok"] = False
        ctx["fatal_error"] = str(exc)
        ctx["fatal_trace"] = traceback.format_exc()
        ctx["finished_at"] = datetime.now().isoformat()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("\n========== E2E FAILED ==========")
        print(exc)
        print("Partial report:", REPORT)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
