#!/usr/bin/env python
"""Regenerate only the long Buds review with longer narrations."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REF = Path(r"e:\All Project\AutoMovieProSAAS\AutoMoviePro\.env")
OUT = ROOT / "output" / "UPLOAD_READY_GadgetReviewSociety_v2"
ASSETS = ROOT / "assets" / "channels" / "gadget_review_society"


def load_ref() -> dict:
    keys: dict = {}
    for line in REF.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def main() -> int:
    from app import db as store
    from pipeline.compose import ffprobe_bin
    from pipeline.media_assets import generate_thumbnail
    from pipeline.package_export import export_upload_package
    from pipeline.video_pipeline import generate_video

    store.init_db()
    ref = load_ref()
    google = [ref.get(f"GOOGLE_API_KEY_{i}", "") for i in range(1, 6)]
    google = [g for g in google if g]
    channel = {
        "id": 1,
        "youtube_name": "গেজেট রিভিউ সোসাইটি",
        "niche": "Gadget Review",
        "logo_path": str(ASSETS / "logo.png") if (ASSETS / "logo.png").exists() else "",
        "intro_path": str(ASSETS / "intro.mp4") if (ASSETS / "intro.mp4").exists() else "",
        "google_api_1": google[0],
        "google_api_2": google[1] if len(google) > 1 else google[0],
        "pexels_api": ref.get("PEXELS_API_KEY_1", ""),
        "pollinations_api": ref.get("POLLINATIONS_API_KEY_1", ""),
        "openrouter_api": ref.get("OPENROUTER_API_KEY_1", ""),
        "agnes_api": ref.get("AGNES_API_KEY_1", ""),
    }
    topic = "Samsung Galaxy Buds 4"
    work = OUT / "_work" / "long_Samsung_Galaxy_Buds_4_longform"
    result = generate_video(
        channel,
        video_type="long",
        topic=topic,
        research_notes="earbuds long review",
        work_dir=work,
    )
    raw = subprocess.check_output(
        [ffprobe_bin(), "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", result["path"]]
    )
    data = json.loads(raw)
    print("duration", data["format"]["duration"])
    print("streams", [(s["codec_type"], s["codec_name"]) for s in data["streams"]])
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
        gadget={"name": topic, "source": "long_regen"},
        video_type="long",
        video_path=Path(result["path"]),
        title=result["title"],
        description=result["description"],
        tags=result.get("tags") or [],
        thumbnail_path=thumb if thumb.exists() else None,
        extra={"duration": result.get("duration"), "has_audio": True},
    )
    plan = work / "director_plan.json"
    if plan.exists():
        (pkg / "director_plan.json").write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
    print("PACKAGE", pkg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
