"""Live E2E after prompt re-engineering: topic → visual → localize → TTS → media → finals.

Niche chosen to exercise visual_subject / product_ui (ChatGPT settings) policy.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "Output" / "_live4_prompt_e2e.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(LOG, encoding="utf-8"),
    ],
)
logger = logging.getLogger("live4")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from pipeline.custom_pipeline import run_short_pipeline, session_key_report

    print("=== LIVE4 PROMPT-E2E: short pipeline topic→final ===", flush=True)
    print(f"log={LOG}", flush=True)
    t0 = time.time()

    result = run_short_pipeline(
        niche="AI Tech / ChatGPT Productivity Hacks",
        audience="স্টুডেন্ট ও ফ্রিল্যান্সার",
        include_bangla_tts=True,
        # full pipeline — do not skip stages
        skip_localize=False,
        skip_visual=False,
        skip_tts=False,
        skip_media=False,
    )

    elapsed = time.time() - t0
    pkg = Path(result.get("package_root") or "")
    summary = {
        "ok": result.get("ok"),
        "shippable": result.get("shippable"),
        "partial": result.get("partial"),
        "package_root": str(pkg),
        "elapsed_sec": round(elapsed, 1),
        "session_keys": result.get("session_keys") or session_key_report(),
        "stage_errors": {
            "localize": (result.get("stage2_localize") or {}).get("errors"),
            "tts": (result.get("stage4_tts") or {}).get("errors"),
            "media": (result.get("stage5_media") or {}).get("errors")
            if isinstance(result.get("stage5_media"), dict)
            else None,
        },
    }

    # Final video presence
    finals = {}
    if pkg.is_dir():
        fv = pkg / "Video" / "Final Video"
        if fv.is_dir():
            for lang_dir in sorted(fv.iterdir()):
                if not lang_dir.is_dir():
                    continue
                vids = list(lang_dir.glob("final_*.mp4"))
                finals[lang_dir.name] = [
                    {"name": v.name, "bytes": v.stat().st_size} for v in vids if v.stat().st_size > 10000
                ]
    summary["finals"] = finals

    # visual_subject sampling from topic script
    script_path = pkg / "File" / "topic_script.json" if pkg.is_dir() else None
    subjects = []
    if script_path and script_path.is_file():
        data = json.loads(script_path.read_text(encoding="utf-8"))
        for sc in data.get("script_scenes") or []:
            subjects.append(
                {
                    "shot": sc.get("shot_number"),
                    "visual_subject": sc.get("visual_subject"),
                    "char": (sc.get("character_details") or "")[:60],
                    "vo": (sc.get("voiceover_script") or "")[:80],
                }
            )
    summary["visual_subjects"] = subjects

    out_json = ROOT / "Output" / "_live4_prompt_e2e_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"SUMMARY_JSON={out_json}", flush=True)

    ship = bool(result.get("shippable") or result.get("ok"))
    has_bn = bool(finals.get("BN"))
    return 0 if ship and has_bn else 1


if __name__ == "__main__":
    raise SystemExit(main())
