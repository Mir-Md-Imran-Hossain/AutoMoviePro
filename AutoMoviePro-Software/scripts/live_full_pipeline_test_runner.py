"""
Live Comprehensive E2E Video Pipeline Test Runner
Executes:
  1) SHORT Video Pipeline across all 6 languages (BN, EN, HI, UR, TA, ML)
  2) LONG Video Pipeline across all 6 languages (BN, EN, HI, UR, TA, ML)
Monitors every stage in real-time, validates artifacts, catches errors and ensures shippability.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("LiveE2ERunner")

ALL_LANGUAGES = ["English", "Hindi", "Tamil", "Malayalam", "Urdu"]


def progress_tracker(pct: float, msg: str) -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    bar_len = 25
    filled = int(bar_len * (pct / 100.0))
    bar = "=" * filled + "-" * (bar_len - filled)
    print(f"[{now_str}] [{bar}] {pct:3.0f}% -> {msg}", flush=True)


def verify_pipeline_artifacts(pkg: Path, kind: str) -> dict:
    results = {"package": str(pkg), "kind": kind, "checks": [], "all_ok": True}
    
    def _chk(name: str, passed: bool, detail: str = ""):
        results["checks"].append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            results["all_ok"] = False
        mark = "✓ PASS" if passed else "✗ FAIL"
        print(f"    [{mark}] {name} {detail}")

    print(f"\n--- Verifying Artifacts for {kind.upper()} ({pkg.name}) ---")
    _chk("Package Directory Exists", pkg.is_dir(), str(pkg))
    _chk("Audio Directory Exists", (pkg / "Audio").is_dir())
    _chk("File Directory Exists", (pkg / "File").is_dir())
    _chk("Image Directory Exists", (pkg / "Image").is_dir())
    _chk("Video Directory Exists", (pkg / "Video").is_dir())
    _chk("Final Video Directory Exists", (pkg / "Video" / "Final Video").is_dir())

    # Check File JSONs
    file_dir = pkg / "File"
    if file_dir.is_dir():
        jsons = [p.name for p in file_dir.glob("*.json")]
        _chk("Script JSON Present", any(n.startswith("Script_") or n == "topic_script.json" for n in jsons))
        _chk("Visual Plan JSON Present", any(n.startswith("Visual_") or n == "visual_render_plan.json" for n in jsons))
        for code in ("EN", "HI", "TL", "ML", "UR"):
            _chk(f"Localized Script JSON ({code})", any(f"_{code}_" in n or f"_{code}." in n for n in jsons))

    # Check Audio across all 6 languages
    audio_dir = pkg / "Audio"
    for lang, code in [
        ("Bangla", "BN"),
        ("English", "EN"),
        ("Hindi", "HI"),
        ("Tamil", "TL"),
        ("Malayalam", "ML"),
        ("Urdu", "UR"),
    ]:
        lang_audio = audio_dir / code
        shots = list(lang_audio.glob("S*.m4a")) if lang_audio.is_dir() else []
        full = list(lang_audio.glob("narration_full_*.m4a")) if lang_audio.is_dir() else []
        _chk(f"Audio Narrations ({lang} / {code})", len(shots) >= 1 or len(full) >= 1, f"({len(shots)} shots, {len(full)} full)")

    # Check Final Assembled Videos
    final_video_dir = pkg / "Video" / "Final Video"
    if final_video_dir.is_dir():
        for lang, code in [
            ("Bangla", "BN"),
            ("English", "EN"),
            ("Hindi", "HI"),
            ("Tamil", "TL"),
            ("Malayalam", "ML"),
            ("Urdu", "UR"),
        ]:
            vf = final_video_dir / code
            vids = list(vf.glob("*.mp4")) if vf.is_dir() else []
            if not vids:
                # check root final video dir as fallback
                vids = list(final_video_dir.glob(f"*{code}*.mp4"))
            _chk(f"Final Video MP4 ({lang} / {code})", len(vids) >= 1, f"{vids[0].name} ({vids[0].stat().st_size} bytes)" if vids else "None")

    return results


def run_live_test():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from pipeline.custom_pipeline.runner import run_short_pipeline, run_long_pipeline
    from pipeline.custom_pipeline.pipeline_preflight import run_pipeline_preflight, raise_if_preflight_blocked

    print("\n" + "=" * 70)
    print(" AUTOMOVIE PRO - FULL PIPELINE LIVE TEST RUN (SHORT & LONG)")
    print(" All Languages: Bangla, English, Hindi, Tamil, Malayalam, Urdu")
    print("=" * 70 + "\n")

    # Step 0: Preflight check
    print("[PREFLIGHT] Validating API slots and dedicated keys...")
    preflight = run_pipeline_preflight(
        languages=ALL_LANGUAGES,
        include_bangla_tts=True,
        allow_degraded=True,
    )
    raise_if_preflight_blocked(preflight)
    print("✓ Preflight passed without blockers.\n")

    overall_results = {}

    # =========================================================================
    # PART 1: LIVE SHORT VIDEO PIPELINE RUN
    # =========================================================================
    print(">>> [PART 1/2] STARTING SHORT VIDEO PIPELINE LIVE RUN")
    start_short = time.time()
    try:
        short_res = run_short_pipeline(
            niche="AI Technology & Future Robots",
            audience="সাধারণ দর্শক ও প্রযুক্তিপ্রেমী",
            languages=ALL_LANGUAGES,
            include_bangla_tts=True,
            progress_cb=progress_tracker,
        )
        short_pkg = Path(short_res.get("package_root") or "")
        short_ver = verify_pipeline_artifacts(short_pkg, "short")
        overall_results["short"] = {
            "ok": short_res.get("ok"),
            "package": str(short_pkg),
            "elapsed_sec": round(time.time() - start_short, 1),
            "verification": short_ver,
        }
        print(f"\n✓ Short Video Pipeline Completed in {overall_results['short']['elapsed_sec']}s")
    except Exception as exc:
        logger.exception("Short video pipeline run encountered an error: %s", exc)
        overall_results["short"] = {"ok": False, "error": str(exc)}
        print(f"\n✗ Short Video Pipeline Failed: {exc}")

    # =========================================================================
    # PART 2: LIVE LONG VIDEO PIPELINE RUN
    # =========================================================================
    print("\n" + "=" * 70)
    print(">>> [PART 2/2] STARTING LONG VIDEO PIPELINE LIVE RUN")
    print("=" * 70)
    start_long = time.time()
    try:
        long_res = run_long_pipeline(
            niche="Mysteries of the Universe & Deep Space",
            audience="বিজ্ঞান ও মহাকাশ অনুসন্ধিৎসু দর্শক",
            languages=ALL_LANGUAGES,
            include_bangla_tts=True,
            progress_cb=progress_tracker,
        )
        long_pkg = Path(long_res.get("package_root") or "")
        long_ver = verify_pipeline_artifacts(long_pkg, "long")
        overall_results["long"] = {
            "ok": long_res.get("ok"),
            "package": str(long_pkg),
            "elapsed_sec": round(time.time() - start_long, 1),
            "verification": long_ver,
        }
        print(f"\n✓ Long Video Pipeline Completed in {overall_results['long']['elapsed_sec']}s")
    except Exception as exc:
        logger.exception("Long video pipeline run encountered an error: %s", exc)
        overall_results["long"] = {"ok": False, "error": str(exc)}
        print(f"\n✗ Long Video Pipeline Failed: {exc}")

    # =========================================================================
    # SUMMARY REPORT
    # =========================================================================
    print("\n" + "=" * 70)
    print(" FINAL LIVE PIPELINE TEST SUMMARY REPORT")
    print("=" * 70)
    print(json.dumps(overall_results, ensure_ascii=False, indent=2, default=str))

    report_path = ROOT / "output" / "LIVE_PIPELINE_TEST_SUMMARY.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(overall_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

    short_ok = bool(overall_results.get("short", {}).get("ok"))
    long_ok = bool(overall_results.get("long", {}).get("ok"))
    return 0 if (short_ok and long_ok) else 1


if __name__ == "__main__":
    sys.exit(run_live_test())
