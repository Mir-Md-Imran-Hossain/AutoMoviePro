#!/usr/bin/env python
"""Regenerate short+long upload packages with audio + dialogue-matched footage."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("regen")

REF_ENV = Path(r"e:\All Project\AutoMovieProSAAS\AutoMoviePro\.env")
OUT = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v2"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"


def load_ref():
    keys = {}
    for line in REF_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def main() -> int:
    from app import db as store
    from pipeline.package_export import export_upload_package
    from pipeline.media_assets import generate_thumbnail
    from pipeline.video_pipeline import generate_video
    from pipeline.compose import ffprobe_bin
    import subprocess

    store.init_db()
    ref = load_ref()
    google = [ref.get(f"GOOGLE_API_KEY_{i}", "") for i in range(1, 6)]
    google = [g for g in google if g]

    channel = {
        "id": 1,
        "youtube_name": "গেজেট রিভিউ সোসাইটি",
        "facebook_name": "গেজেট রিভিউ সোসাইটি",
        "niche": "Gadget Review",
        "logo_path": str(ASSETS / "logo.png") if (ASSETS / "logo.png").exists() else "",
        "intro_path": str(ASSETS / "intro.mp4") if (ASSETS / "intro.mp4").exists() else "",
        "google_api_1": google[0] if google else "",
        "google_api_2": google[1] if len(google) > 1 else (google[0] if google else ""),
        "agnes_api": ref.get("AGNES_API_KEY_1", ""),
        "pexels_api": ref.get("PEXELS_API_KEY_1", ""),
        "pollinations_api": ref.get("POLLINATIONS_API_KEY_1", ""),
        "openrouter_api": ref.get("OPENROUTER_API_KEY_1", ""),
    }

    gadgets = [
        ("short", "Nothing Phone (3)", "trending android phone review camera display battery"),
        ("long", "Samsung Galaxy Buds 4", "trending earbuds review sound fit battery case"),
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    packages = []

    for vtype, topic, notes in gadgets:
        logger.info("=== Building %s :: %s ===", vtype, topic)
        work = OUT / "_work" / f"{vtype}_{topic.replace(' ', '_')}"
        result = generate_video(
            channel,
            video_type=vtype,
            topic=topic,
            research_notes=notes,
            work_dir=work,
        )
        # validate audio
        raw = subprocess.check_output(
            [ffprobe_bin(), "-v", "quiet", "-print_format", "json", "-show_streams", result["path"]]
        )
        streams = json.loads(raw).get("streams") or []
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_video = any(s.get("codec_type") == "video" for s in streams)
        if not has_audio or not has_video:
            raise RuntimeError(f"{vtype} missing streams audio={has_audio} video={has_video}")

        thumb = work / "thumbnail.jpg"
        generate_thumbnail(
            result["title"],
            topic,
            thumb,
            pollinations_key=channel["pollinations_api"],
            logo_path=Path(channel["logo_path"]) if channel["logo_path"] else None,
        )
        pkg = export_upload_package(
            dest_root=OUT,
            channel_name=channel["youtube_name"],
            gadget={"name": topic, "source": "regen_v2"},
            video_type=vtype,
            video_path=Path(result["path"]),
            title=result["title"],
            description=result["description"],
            tags=result.get("tags") or [],
            thumbnail_path=thumb if thumb.exists() else None,
            extra={
                "duration": result.get("duration"),
                "has_audio": True,
                "topic": result.get("topic"),
                "director_provider": result.get("director_provider"),
                "plan_file": str(work / "director_plan.json"),
            },
        )
        # copy director plan into package
        plan_src = work / "director_plan.json"
        if plan_src.exists():
            (pkg / "director_plan.json").write_text(plan_src.read_text(encoding="utf-8"), encoding="utf-8")

        packages.append(
            {
                "type": vtype,
                "topic": topic,
                "folder": str(pkg),
                "title": result["title"],
                "duration": result.get("duration"),
                "has_audio": True,
            }
        )
        logger.info("Package OK: %s (%.1fs)", pkg, result.get("duration") or 0)

    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "fixes": [
            "Added Google Gemini TTS + edge-tts fallback (was video-only / silent)",
            "Niche director plans dialogue beats with element-matched visual queries",
            "Each dialogue drives footage (camera/display/processor/battery/sound/...)",
            "Forced A/V re-encode concat to prevent long-video freeze",
            "Final validation requires audio+video streams",
        ],
        "packages": packages,
        "output_root": str(OUT),
    }
    (OUT / "REGEN_REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception("regen failed")
        print("FAILED:", exc)
        raise SystemExit(1)
