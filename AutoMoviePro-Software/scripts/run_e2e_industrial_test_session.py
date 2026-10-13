"""E2E Industrial Test Session Runner for AutoMovie Pro
Executes:
1. Short Video Pipeline (with all 6 languages and localized thumbnails)
2. Long Video Pipeline (with all 6 languages and localized thumbnails)
Logs execution into Output/industrial_test_session/session.log
and writes summary to Output/industrial_test_session/session_summary.json.
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

SESSION_DIR = ROOT / "Output" / "industrial_test_session"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = SESSION_DIR / "session.log"

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w")
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger("IndustrialTestSession")
ALL_LANGUAGES = ["English", "Hindi", "Tamil", "Malayalam", "Urdu"]


def progress_tracker(pct: float, msg: str) -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    line = f"[{now_str}] [{pct:3.0f}%] {msg}"
    print(line, flush=True)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from pipeline.custom_pipeline.runner import run_short_pipeline, run_long_pipeline
    from pipeline.custom_pipeline.pipeline_preflight import run_pipeline_preflight, raise_if_preflight_blocked

    logger.info("=" * 70)
    logger.info("STARTING E2E INDUSTRIAL TEST SESSION (SHORT & LONG PIPELINE)")
    logger.info("=" * 70)

    # 1. Preflight
    logger.info("[SESSION] Running preflight check...")
    preflight = run_pipeline_preflight(
        languages=ALL_LANGUAGES,
        include_bangla_tts=True,
        allow_degraded=True,
    )
    raise_if_preflight_blocked(preflight)
    logger.info("[SESSION] Preflight passed successfully.")

    session_summary = {
        "start_time": datetime.now().isoformat(),
        "short": {},
        "long": {},
        "ok": False,
    }

    # 2. Short Video Pipeline
    logger.info("=" * 70)
    logger.info("PHASE 1: SHORT VIDEO PIPELINE EXECUTION")
    logger.info("=" * 70)
    t0_short = time.time()
    try:
        short_res = run_short_pipeline(
            niche="Robotics & Modern Automation (রোবোটিক্স ও অটোমেশন)",
            audience="সাধারণ দর্শক ও প্রযুক্তিপ্রেমী",
            languages=ALL_LANGUAGES,
            include_bangla_tts=True,
            skip_thumbnail=False,
            progress_cb=progress_tracker,
        )
        elapsed_short = round(time.time() - t0_short, 1)
        session_summary["short"] = {
            "ok": bool(short_res.get("ok")),
            "shippable": bool(short_res.get("shippable")),
            "package_root": short_res.get("package_root"),
            "elapsed_sec": elapsed_short,
            "error": None,
        }
        logger.info("Phase 1 Short Pipeline Finished in %ss, Shippable=%s", elapsed_short, short_res.get("shippable"))
    except Exception as exc:
        elapsed_short = round(time.time() - t0_short, 1)
        logger.exception("Phase 1 Short Pipeline Failed: %s", exc)
        session_summary["short"] = {
            "ok": False,
            "shippable": False,
            "package_root": None,
            "elapsed_sec": elapsed_short,
            "error": str(exc),
        }

    # 3. Long Video Pipeline
    logger.info("=" * 70)
    logger.info("PHASE 2: LONG VIDEO PIPELINE EXECUTION")
    logger.info("=" * 70)
    t0_long = time.time()
    try:
        long_res = run_long_pipeline(
            niche="Deep Space & Astrophysics (মহাকাশ ও জ্যোতির্বিজ্ঞান)",
            audience="বিজ্ঞান ও মহাকাশ অনুসন্ধিৎসু দর্শক",
            languages=ALL_LANGUAGES,
            include_bangla_tts=True,
            skip_thumbnail=False,
            progress_cb=progress_tracker,
        )
        elapsed_long = round(time.time() - t0_long, 1)
        session_summary["long"] = {
            "ok": bool(long_res.get("ok")),
            "shippable": bool(long_res.get("shippable")),
            "package_root": long_res.get("package_root"),
            "elapsed_sec": elapsed_long,
            "error": None,
        }
        logger.info("Phase 2 Long Pipeline Finished in %ss, Shippable=%s", elapsed_long, long_res.get("shippable"))
    except Exception as exc:
        elapsed_long = round(time.time() - t0_long, 1)
        logger.exception("Phase 2 Long Pipeline Failed: %s", exc)
        session_summary["long"] = {
            "ok": False,
            "shippable": False,
            "package_root": None,
            "elapsed_sec": elapsed_long,
            "error": str(exc),
        }

    session_summary["end_time"] = datetime.now().isoformat()
    session_summary["ok"] = bool(session_summary["short"].get("ok")) and bool(session_summary["long"].get("ok"))

    summary_file = SESSION_DIR / "session_summary.json"
    summary_file.write_text(json.dumps(session_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("=" * 70)
    logger.info("SESSION COMPLETE. Summary written to %s", summary_file)
    logger.info("=" * 70)

    return 0 if session_summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
