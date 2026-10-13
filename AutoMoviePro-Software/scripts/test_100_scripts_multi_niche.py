#!/usr/bin/env python3
"""Multi-Niche Scriptwriting Stress Test & Quality Audit Suite.

Generates and audits scripts across diverse niches (Tech, Science, Space, History,
Finance, Crime, Biology, Wildlife, Psychology, Energy, Megaprojects) to verify:
1. Viral psychological 3-second hook (zero boring openings).
2. Simplification with everyday visual metaphors (zero dry datasheet dumps).
3. Conversational flow & storytelling bridges (zero robotic bullet lists).
4. Mid-roll retention hooks & intelligent audience questions.
5. Factual substance combined with engaging presentation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("USE_GEMINI_RESEARCH", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("multi_niche_test")

from pipeline.custom_pipeline.script_quality_gate import evaluate_script_quality
from pipeline.custom_pipeline.topic_research import run_topic_research

NICHES = [
    "Robotics & Modern Automation (রোবোটিক্স ও অটোমেশন)",
    "Artificial Intelligence & Future Tech (কৃত্রিম বুদ্ধিমত্তা)",
    "Deep Space & Astrophysics (মহাকাশ ও জ্যোতির্বিজ্ঞান)",
    "Deep Ocean Exploration & Marine Mysteries (গভীর সমুদ্র ও রহস্য)",
    "History & Lost Civilizations (ইতিহাস ও প্রাচীন রহস্য)",
    "Unsolved Mysteries & Forensics (রহস্য ও অপরাধ তদন্ত)",
    "Finance, Money & Business Strategy (ব্যবসা ও অর্থশাস্ত্র)",
    "Human Brain, Biology & Medicine (মানবদেহ ও মস্তিষ্ক বিজ্ঞান)",
    "Extreme Wildlife & Animal Superpowers (বন্যপ্রাণী ও প্রকৃতি)",
    "Psychology & Human Behavior (মানব মনস্তত্ত্ব ও আচরণ)",
    "Future Green Energy & Physics (ভবিষ্যতের পরিবেশবান্ধব শক্তি)",
    "Extreme Engineering & Megaprojects (মেগাপ্রজেক্ট ও স্থাপত্য)",
]


def run_script_audit(
    *,
    iterations: int = 10,
    video_type: str = "short",
    output_dir: Path | None = None,
) -> Dict[str, Any]:
    out_dir = output_dir or (ROOT / "Output" / "multi_niche_script_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    results_file = out_dir / "audit_report.json"

    print("=" * 80)
    print(f"🚀 STARTING MULTI-NICHE SCRIPTWRITING AUDIT: {iterations} ITERATIONS")
    print(f"Target Video Type: {video_type.upper()}")
    print(f"Niches Covered: {len(NICHES)} diverse categories")
    print("=" * 80)

    records: List[Dict[str, Any]] = []
    passed_count = 0
    failed_count = 0

    for idx in range(1, iterations + 1):
        niche = NICHES[(idx - 1) % len(NICHES)]
        print(f"\n[{idx}/{iterations}] Generating Script for Niche: '{niche}'...")
        t0 = time.time()

        try:
            res = run_topic_research(
                niche=niche,
                video_type=video_type,
                save=False,
                max_dedupe_retries=3,
            )
            elapsed = round(time.time() - t0, 2)
            payload = res.get("payload") or {}
            meta = payload.get("seo_metadata") or {}
            topic = meta.get("selected_topic") or "Unknown Topic"
            scenes = payload.get("script_scenes") or []
            q = res.get("script_quality") or evaluate_script_quality(payload, video_type=video_type)

            score = q.get("score", 0.0)
            is_ok = q.get("ok", False)
            issues = q.get("issues", [])
            breakdown = q.get("breakdown", {})

            hook_vo = scenes[0].get("voiceover_script", "") if scenes else ""
            total_words = q.get("evaluations", {}).get("density", {}).get("total_words", 0)

            rec = {
                "iteration": idx,
                "niche": niche,
                "topic": topic,
                "score": score,
                "ok": is_ok,
                "elapsed_seconds": elapsed,
                "total_words": total_words,
                "breakdown": breakdown,
                "issues": issues,
                "hook_voiceover": hook_vo,
                "scenes_count": len(scenes),
                "suggested_titles": meta.get("suggested_titles", []),
                "first_three_scenes": [
                    {
                        "shot": s.get("shot_number"),
                        "dur": s.get("shot_duration_seconds"),
                        "vo": s.get("voiceover_script"),
                    }
                    for s in scenes[:3]
                ],
            }
            records.append(rec)

            if is_ok:
                passed_count += 1
                status_icon = "✅ PASSED"
            else:
                failed_count += 1
                status_icon = "❌ FAILED"

            print(f"   Status: {status_icon} | Score: {score:.3f} | Words: {total_words} | Time: {elapsed}s")
            print(f"   Topic: {topic}")
            print(f"   Hook: \"{hook_vo[:85]}...\"")
            if issues:
                print(f"   Issues: {issues}")

        except Exception as e:
            failed_count += 1
            print(f"   ❌ ERROR: {e}")
            records.append({
                "iteration": idx,
                "niche": niche,
                "error": str(e),
                "ok": False,
                "score": 0.0,
            })

        # Save incremental report
        summary = {
            "total_tested": idx,
            "passed": passed_count,
            "failed": failed_count,
            "success_rate": f"{(passed_count / idx) * 100:.1f}%",
            "records": records,
        }
        results_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("🏁 MULTI-NICHE AUDIT FINISHED!")
    print(f"Total: {iterations} | Passed: {passed_count} | Failed: {failed_count} | Success Rate: {(passed_count / max(1, iterations)) * 100:.1f}%")
    print(f"Full Report: {results_file}")
    print("=" * 80)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Niche Script Audit")
    parser.add_argument("--count", type=int, default=12, help="Number of script iterations to run")
    parser.add_argument("--type", type=str, default="short", choices=["short", "long"], help="Video type")
    args = parser.parse_args()

    run_script_audit(iterations=args.count, video_type=args.type)
