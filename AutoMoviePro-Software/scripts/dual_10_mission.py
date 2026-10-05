"""
Dual 10-clip mission (fresh outputs):

  A) Agnes ACTIVE  → 10 clips × 6 languages
  B) Agnes FALLBACK (image→video) → 10 clips × 6 languages

Between clips: cooldown (Agnes/API).
Between localization languages: AMP_TTS_LANG_PAUSE_SEC (default 300 = 5 min).

After each clip: human + agent dual analysis; teach agent on gaps.

Usage:
  venv\\Scripts\\python.exe scripts\\dual_10_mission.py
  venv\\Scripts\\python.exe scripts\\dual_10_mission.py --mode both --clips 1-10
  venv\\Scripts\\python.exe scripts\\dual_10_mission.py --mode agnes --wipe
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AGNES_OUT = ROOT / "output" / "Agnes_10_SixLang"
IMG_OUT = ROOT / "output" / "ImageFallback_10_SixLang"
LEGACY_WIPE = [
    ROOT / "output" / "ImageFallback_TrainCompare",
    ROOT / "output" / "Chernobyl_30_TrainCompare",
    ROOT / "output" / "_motion_smoke",
    AGNES_OUT,
    IMG_OUT,
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("dual10")


def _wipe() -> None:
    for d in LEGACY_WIPE:
        if d.exists():
            logger.info("Wiping %s", d)
            shutil.rmtree(d, ignore_errors=True)
    AGNES_OUT.mkdir(parents=True, exist_ok=True)
    IMG_OUT.mkdir(parents=True, exist_ok=True)
    (AGNES_OUT / "COMPARE").mkdir(parents=True, exist_ok=True)
    (IMG_OUT / "COMPARE").mkdir(parents=True, exist_ok=True)


def _parse_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            ids.extend(range(int(a), int(b) + 1))
        elif part:
            ids.append(int(part))
    return ids


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_md(path: Path, title: str, rows: List[Dict[str, Any]]) -> None:
    lines = [f"# {title}", f"Updated: {datetime.now().isoformat()}", ""]
    for r in rows:
        lines.append(
            f"- clip={r.get('clip')} passed={r.get('human_passed')}/{r.get('agent_passed')} "
            f"adequate={r.get('agent_adequate')} rules={len(r.get('rules') or [])} "
            f"final={r.get('final')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_agnes_batch(ids: List[int], *, clip_pause: float, lang_pause: float) -> List[Dict[str, Any]]:
    os.environ["AMP_TTS_LANG_PAUSE_SEC"] = str(int(lang_pause))
    # Point Chernobyl OUT at Agnes_10 folder by patching module OUT
    import scripts.chernobyl_30_train as ch

    ch.OUT = AGNES_OUT
    ch.COMPARE = AGNES_OUT / "COMPARE"
    ch.COMPARE.mkdir(parents=True, exist_ok=True)
    ch.CASES_PATH = AGNES_OUT / "cases_30.json"
    ch.PROGRESS_PATH = AGNES_OUT / "progress.json"
    ch.RESULTS_PATH = AGNES_OUT / "results.jsonl"
    ch.REPORT_PATH = AGNES_OUT / "TRAINING_REPORT.md"
    ch.LOCK_PATH = AGNES_OUT / "agnes10.lock"

    from pipeline.api_keys import load_api_bundle
    from app import db as store

    cases = {int(c["id"]): c for c in ch._cases()}
    chans = store.list_channels()
    if not chans:
        raise RuntimeError("no_channel")
    ch_row = chans[0]
    bundle = load_api_bundle(channel=ch_row)
    keys = list(bundle.get("google_keys") or [])
    agnes_keys = list(bundle.get("agnes_keys") or [])
    if not agnes_keys:
        raise RuntimeError("agnes_keys_missing")
    rows: List[Dict[str, Any]] = []
    for i, cid in enumerate(ids):
        case = cases.get(cid)
        if not case:
            logger.error("unknown clip %s", cid)
            continue
        logger.info("===== AGNES clip %s (%s/%s) =====", cid, i + 1, len(ids))
        try:
            row = ch.run_one(
                case,
                ch_row,
                keys,
                agnes_keys=agnes_keys,
                pollinations_key=str(bundle.get("pollinations_key") or ""),
                pexels_key=str(bundle.get("pexels_key") or ""),
            )
            row["mode"] = "agnes"
            row["clip"] = cid
            # Dual analyze master
            final = Path(row.get("final") or "")
            narr = (AGNES_OUT / f"clip_{cid:02d}" / "narration_en.txt").read_text(encoding="utf-8").strip() if (AGNES_OUT / f"clip_{cid:02d}" / "narration_en.txt").exists() else ""
            dual = _dual_analyze(final, narr, cid, mode="agnes")
            row.update(dual)
            _append_jsonl(AGNES_OUT / "dual_results.jsonl", row)
            rows.append(row)
            logger.info(
                "AGNES clip %s human=%s agent=%s adequate=%s",
                cid,
                dual.get("human_passed"),
                dual.get("agent_passed"),
                dual.get("agent_adequate"),
            )
        except Exception as exc:
            logger.exception("AGNES clip %s failed: %s", cid, exc)
            rows.append({"clip": cid, "mode": "agnes", "error": str(exc)[:300], "human_passed": False})
        if i < len(ids) - 1 and clip_pause > 0:
            logger.info("Cooldown clip pause %.0fs…", clip_pause)
            time.sleep(clip_pause)
    _write_md(AGNES_OUT / "DUAL_ANALYSIS_REPORT.md", "Agnes 10 × 6-lang", rows)
    return rows


def run_image_batch(ids: List[int], *, clip_pause: float, lang_pause: float) -> List[Dict[str, Any]]:
    os.environ["AMP_TTS_LANG_PAUSE_SEC"] = str(int(lang_pause))
    os.environ.setdefault("AMP_PREFER_EDGE_TTS", "0")  # use Google TTS key map for langs
    os.environ.setdefault("AMP_FORCE_PRECHECK", "0")
    os.environ.setdefault("IMAGE_PROVIDER_PRIORITY", "pollinations,freetheai,google")

    import scripts.image_fallback_train as im

    im.OUT = IMG_OUT
    im.COMPARE = IMG_OUT / "COMPARE"
    im.COMPARE.mkdir(parents=True, exist_ok=True)
    im.RESULTS = IMG_OUT / "results.jsonl"
    im.REPORT = IMG_OUT / "DUAL_ANALYSIS_REPORT.md"

    from pipeline.api_keys import load_api_bundle
    from pipeline.av_sync_critic import apply_training_rule

    apply_training_rule(
        "IMAGE FALLBACK motion: Ken Burns must move for the entire beat — never freeze still photos.",
        source="dual10_motion",
    )
    cases = {int(c["id"]): c for c in __import__("scripts.chernobyl_30_train", fromlist=["_cases"])._cases()}
    bundle = load_api_bundle()
    keys = list(bundle.get("google_keys") or [])
    pollinations_key = str(bundle.get("pollinations_key") or "")
    rows: List[Dict[str, Any]] = []
    for i, cid in enumerate(ids):
        case = cases.get(cid)
        if not case:
            continue
        logger.info("===== IMAGE-FALLBACK clip %s (%s/%s) =====", cid, i + 1, len(ids))
        try:
            dual = im.run_one(
                case,
                keys,
                pollinations_key,
                localize=True,
                resume=False,
            )
            dual["mode"] = "image_fallback"
            dual["clip"] = cid
            _append_jsonl(IMG_OUT / "dual_results.jsonl", dual)
            rows.append(dual)
            logger.info(
                "IMAGE clip %s human=%s agent=%s adequate=%s",
                cid,
                dual.get("human_passed"),
                dual.get("agent_passed"),
                dual.get("agent_adequate"),
            )
        except Exception as exc:
            logger.exception("IMAGE clip %s failed: %s", cid, exc)
            rows.append({"clip": cid, "mode": "image_fallback", "error": str(exc)[:300], "human_passed": False})
        if i < len(ids) - 1 and clip_pause > 0:
            logger.info("Between clip pause %.0fs…", clip_pause)
            time.sleep(clip_pause)
    _write_md(IMG_OUT / "DUAL_ANALYSIS_REPORT.md", "Image-fallback 10 × 6-lang", rows)
    return rows


def _dual_analyze(final: Path, narration: str, cid: int, *, mode: str) -> Dict[str, Any]:
    from pipeline.av_self_repair_agent import diagnose_clip
    from pipeline.av_sync_critic import apply_training_rule

    out: Dict[str, Any] = {
        "human_passed": False,
        "agent_passed": False,
        "agent_adequate": True,
        "rules": [],
        "final": str(final) if final else "",
    }
    if not final or not Path(final).exists():
        out["human_issues"] = ["missing_final"]
        apply_training_rule(
            f"{mode} clip {cid}: missing final deliverable scene_*.mp4 after pipeline — hard fail.",
            source=f"dual10_{mode}_{cid}",
        )
        out["rules"].append("missing_final")
        return out

    diag = diagnose_clip(Path(final), narration=narration or "", lang="en")
    hard = list(diag.get("hard_hits") or [])
    out["agent_passed"] = bool(diag.get("passed"))
    out["agent_hard"] = hard
    out["human_passed"] = not hard and Path(final).stat().st_size > 8000
    out["human_issues"] = [f"gate:{h}" for h in hard]

    # Agent missed something human catches via file naming
    if Path(final).name.startswith("agnes_") and "i2v" in Path(final).name:
        out["human_passed"] = False
        out["human_issues"].append("raw_i2v_as_final")
        if "raw_i2v" not in " ".join(hard):
            out["agent_adequate"] = False
            rule = (
                "Deliverable must be scene_XX_*.mp4 after agent repair, never raw agnes_*_i2v_*.mp4."
            )
            apply_training_rule(rule, source=f"dual10_{mode}_{cid}_teach")
            out["rules"].append(rule)

    if hard and diag.get("passed"):
        out["agent_adequate"] = False
        rule = (
            "Never mark PASS while diagnose_clip still reports HARD_QUALITY_GATES; "
            "re-run diagnose after each repair."
        )
        apply_training_rule(rule, source=f"dual10_{mode}_{cid}_false_pass")
        out["rules"].append(rule)

    # Localization completeness check
    loc = Path(final).parent / "LOCALIZED"
    if loc.exists():
        from pipeline.lang_config import TARGET_LANG_CODES, folder_for_lang

        missing = []
        for code in TARGET_LANG_CODES:
            vid = loc / folder_for_lang(code) / "video.mp4"
            if not vid.exists() or vid.stat().st_size < 8000:
                missing.append(code)
        out["localize_missing"] = missing
        if missing:
            out["human_issues"].append("localize_incomplete:" + ",".join(missing))
            if not hard:
                # agent may not check localize — teach
                apply_training_rule(
                    "After localize_master_clip, verify all 6 language folders have video.mp4 "
                    f"(>=8KB). Missing on clip {cid}: {', '.join(missing)}.",
                    source=f"dual10_{mode}_{cid}_loc",
                )
                out["rules"].append("localize_incomplete")
                out["agent_adequate"] = False
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("both", "agnes", "image"), default="both")
    ap.add_argument("--clips", default="1-10")
    ap.add_argument("--wipe", action="store_true", default=True)
    ap.add_argument("--no-wipe", action="store_true")
    ap.add_argument("--clip-pause", type=float, default=90.0, help="Seconds between clips")
    ap.add_argument(
        "--lang-pause",
        type=float,
        default=300.0,
        help="Seconds between localization language TTS (default 5 min)",
    )
    args = ap.parse_args()
    ids = _parse_ids(args.clips)
    if not args.no_wipe:
        _wipe()
    else:
        AGNES_OUT.mkdir(parents=True, exist_ok=True)
        IMG_OUT.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Dual-10 mission mode=%s clips=%s clip_pause=%.0fs lang_pause=%.0fs",
        args.mode,
        ids,
        args.clip_pause,
        args.lang_pause,
    )
    all_rows: List[Dict[str, Any]] = []
    if args.mode in ("both", "agnes"):
        all_rows.extend(run_agnes_batch(ids, clip_pause=args.clip_pause, lang_pause=args.lang_pause))
    if args.mode in ("both", "image"):
        all_rows.extend(run_image_batch(ids, clip_pause=args.clip_pause, lang_pause=args.lang_pause))

    summary = ROOT / "output" / "DUAL_10_MISSION_SUMMARY.md"
    _write_md(summary, "Dual 10 mission summary (Agnes + Image fallback)", all_rows)
    logger.info("DONE — summary %s", summary)
    ok = sum(1 for r in all_rows if r.get("human_passed"))
    logger.info("Passed %s / %s", ok, len(all_rows))
    return 0 if ok == len(all_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
