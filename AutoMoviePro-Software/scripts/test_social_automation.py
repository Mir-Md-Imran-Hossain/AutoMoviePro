"""
Social automation contract tests — analyze → assert → re-assert (multi-round).

Run:
  venv\\Scripts\\python.exe scripts\\test_social_automation.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.pc_load import is_pc_idle, should_run_background_generate  # noqa: E402
from publishers.comment_reply_agent import draft_comment_reply  # noqa: E402
from publishers.upload_meta import (  # noqa: E402
    build_facebook_caption,
    find_thumbnail,
    match_upload_window,
    normalize_job_meta,
    parse_tags,
    youtube_video_id,
)

failed = 0
passed = 0


def expect(cond: bool, msg: str) -> None:
    global failed, passed
    if cond:
        passed += 1
        print(f"OK  {msg}")
    else:
        failed += 1
        print(f"FAIL {msg}")


def round_meta() -> None:
    print("\n=== Round A1: meta parse ===")
    tags = parse_tags("Pixel 9a, review, 2026, #Android")
    expect(tags[:3] == ["Pixel 9a", "review", "2026"], "comma tags parsed")
    expect("Android" in tags, "hash stripped from tags")
    expect(parse_tags(["a", "a", "b"]) == ["a", "b"], "dedupe tags")
    expect(parse_tags(json.dumps(["x", "y"])) == ["x", "y"], "json list tags")

    print("\n=== Round A2: package thumbnail discovery ===")
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        vid = work / "final.mp4"
        vid.write_bytes(b"00")
        thumb = work / "thumbnail.jpg"
        thumb.write_bytes(b"JPEG")
        pkg = work / "UPLOAD_PACKAGE" / "short_demo"
        pkg.mkdir(parents=True)
        (pkg / "thumbnail.jpg").write_bytes(b"JPEG2")
        job = {"local_path": str(vid), "title": "T", "description": "D", "tags": tags}
        meta = normalize_job_meta(job)
        expect(meta["title"] == "T", "title normalized")
        expect(find_thumbnail(job) is not None, "thumbnail found beside video")
        expect(Path(meta["thumbnail"]).name.startswith("thumbnail"), "meta thumbnail path")

    print("\n=== Round A3: facebook caption + youtube id ===")
    cap = build_facebook_caption("Hello Phone", "Great battery", ["Pixel 9a", "review"])
    expect("Hello Phone" in cap and "#Pixel9a" in cap.replace(" ", ""), "FB caption has title+hashtag")
    expect(youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ", "watch?v= id")
    expect(youtube_video_id("https://youtu.be/ABCDEFG1234") == "ABCDEFG1234", "youtu.be id")
    expect(youtube_video_id("dry-run://youtube/x") is None, "dry-run skipped")


def round_timer_idle() -> None:
    print("\n=== Round B1: upload window ===")
    expect(match_upload_window("12:00", "12:00", 1), "exact minute match")
    expect(match_upload_window("12:01", "12:00", 1), "plus-one minute window")
    expect(match_upload_window("11:59", "12:00", 1), "minus-one minute window")
    expect(not match_upload_window("12:05", "12:00", 1), "outside window rejected")

    print("\n=== Round B2: idle gate (force CPU) ===")
    import os

    os.environ["AMP_FORCE_CPU_PERCENT"] = "20"
    os.environ["AMP_IDLE_CPU_MAX"] = "45"
    expect(is_pc_idle() is True, "low CPU = idle")
    d = should_run_background_generate(has_pending_job=False)
    expect(d.get("ok") is True, "idle allows pregenerate")
    d2 = should_run_background_generate(has_pending_job=True)
    expect(d2.get("ok") is False and d2.get("reason") == "pending_job_exists", "pending blocks pregen")

    print("\n=== Round B3: busy pause ===")
    os.environ["AMP_FORCE_CPU_PERCENT"] = "90"
    expect(is_pc_idle() is False, "high CPU = busy")
    d3 = should_run_background_generate(has_pending_job=False)
    expect(d3.get("ok") is False and d3.get("reason") == "pc_busy", "busy pauses generation")
    os.environ.pop("AMP_FORCE_CPU_PERCENT", None)


def round_comment_agent() -> None:
    print("\n=== Round C1: local reply draft ===")
    r = draft_comment_reply(
        video_title="Pixel 9a Review",
        comment_text="What's the price?",
        channel_name="GadgetLab",
    )
    expect(len(r) >= 10, "reply non-empty")
    expect("Pixel" in r or "description" in r.lower() or "Thanks" in r, "reply references context")

    print("\n=== Round C2: empty comment ===")
    expect(draft_comment_reply(video_title="X", comment_text="") == "", "empty comment → empty reply")

    print("\n=== Round C3: youtube helpers import ===")
    from publishers import youtube_uploader, facebook_uploader, comment_reply_agent

    expect(hasattr(youtube_uploader, "fill_youtube_studio_details"), "YT fill helper exported")
    expect(hasattr(facebook_uploader, "upload_facebook"), "FB uploader present")
    expect(hasattr(comment_reply_agent, "run_comment_reply_pass"), "comment pass entry")


def round_scheduler_wiring() -> None:
    print("\n=== Round D1: scheduler methods ===")
    from app.scheduler_service import SchedulerService

    s = SchedulerService()
    expect(hasattr(s, "idle_pregenerate_job"), "idle pregenerate job")
    expect(hasattr(s, "timed_upload_job"), "timed upload job")
    expect(hasattr(s, "comment_reply_job"), "comment reply job")
    expect(hasattr(s, "generation_and_upload_job"), "legacy alias kept")


def main() -> int:
    round_meta()
    round_timer_idle()
    round_comment_agent()
    round_scheduler_wiring()
    # Re-run critical rounds (2nd analysis cycle)
    print("\n=== Re-analysis cycle ===")
    round_meta()
    round_timer_idle()
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
