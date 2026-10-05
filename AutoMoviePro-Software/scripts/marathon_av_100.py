"""
100-clip AV-sync marathon:
  per clip: TTS → prompt precheck → Agnes → post critic → meta-audit → train rules
Resumable. Progress: output/marathon_100/progress.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output" / "marathon_100"
OUT.mkdir(parents=True, exist_ok=True)
LOCK_PATH = OUT / "marathon.lock"


def _acquire_lock() -> None:
    """Single-instance lock so parallel marathons cannot race Agnes/Google quotas."""
    if LOCK_PATH.exists():
        try:
            old = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            pid = int(old.get("pid") or 0)
        except Exception:
            pid = 0
        alive = False
        if pid:
            try:
                import os

                os.kill(pid, 0)
                alive = True
            except Exception:
                alive = False
        if alive:
            raise SystemExit(f"Another marathon is running (pid={pid}). Stop it first.")
    LOCK_PATH.write_text(
        json.dumps({"pid": __import__("os").getpid(), "ts": datetime.now().isoformat()}),
        encoding="utf-8",
    )


def _release_lock() -> None:
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUT / "marathon.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("marathon100")

from app import db as store
from pipeline.av_sync_critic import apply_training_rule, meta_audit_critique
from pipeline.scene_builder import build_dialogue_clip
from pipeline.tts_google import synthesize_narration

CASES_PATH = OUT / "cases_100.json"
PROGRESS_PATH = OUT / "progress.json"
RESULTS_PATH = OUT / "results.jsonl"


def _seed_cases() -> List[Dict[str, Any]]:
    """100 diverse dialogue beats across niches."""
    gadgets = [
        ("OnePlus 13", "intro", "আজকের রিভিউতে আছে OnePlus 13 — কেন এটা এখন এত আলোচনায়।",
         ["OnePlus 13", "hero", "unboxing"], "Cinematic hero shot of OnePlus 13 on dark desk, rim light, slow push-in"),
        ("OnePlus 13", "design", "ডিজাইন ও বিল্ড হাতে নিলেই বোঝা যায়—ফিনিশ আর গ্রিপ কেমন।",
         ["chassis", "finish", "macro"], "Macro orbit around OnePlus 13 chassis, premium materials, studio light"),
        ("OnePlus 13", "display", "ডিসপ্লেতে উজ্জ্বলতা আর স্ক্রল স্মুথনেস কন্টেন্ট দেখার অভিজ্ঞতা বদলে দেয়।",
         ["display", "screen", "scroll", "brightness"], "Close-up OnePlus 13 AMOLED screen ON with colorful scrolling UI, bright"),
        ("OnePlus 13", "camera", "ক্যামেরা মডিউল ম্যাক্রোতে দেখলে লেন্সের রিং ও সেন্সর বোঝা যায়।",
         ["camera", "lens", "macro"], "Macro cinematic of OnePlus 13 triple camera module, rim light"),
        ("OnePlus 13", "battery", "ব্যাটারি আর ফাস্ট চার্জিং রোজকার আরাম নির্ধারণ করে।",
         ["charging", "cable", "battery"], "OnePlus 13 plugged in charging on night desk, cable glow"),
        ("Google Pixel 9a", "intro", "Pixel 9a নিয়ে আজকের সংক্ষিপ্ত রিভিউ—ক্যামেরা আর ক্লিন অ্যান্ড্রয়েড ফোকাস।",
         ["Pixel 9a", "hero", "product"], "Hero product shot of Google Pixel 9a, soft studio light"),
        ("Google Pixel 9a", "camera", "পিক্সেলের ক্যামেরা ডেলাইট শটে ন্যাচারাল কালার দেয়।",
         ["camera", "sample", "lens"], "Pixel 9a camera lens macro with soft daylight sample metaphor"),
        ("Google Pixel 9a", "software", "ক্লিন সফটওয়্যার ও AI ফিচারই অনেকের কেনার কারণ।",
         ["UI", "settings", "software"], "Pixel 9a screen showing clean Android settings UI, fingers optional out of focus"),
        ("Sony WF-1000XM5", "sound", "সাউন্ড ও ANC অভিজ্ঞতাই আসল গেমচেঞ্জার—মিউজিক পরিষ্কার থাকা চাই।",
         ["earbuds", "ANC", "sound"], "Cinematic close-up Sony WF-1000XM5 earbuds with subtle audio-wave atmosphere"),
        ("Sony WF-1000XM5", "case", "কেস ডিজাইন ও পোর্টেবিলিটি পকেটে নিয়ে চলার সুবিধা দেয়।",
         ["case", "open", "earbuds"], "Sony WF-1000XM5 charging case opening cinematic macro"),
        ("Apple Watch Series 11", "software", "স্মার্টওয়াচ UI ও হেলথ ট্র্যাকিং রোজকার ব্যবহার নির্ধারণ করে।",
         ["watch", "UI", "wrist"], "Apple Watch glowing UI on wrist cinematic shallow DOF"),
        ("DJI Osmo Pocket 3", "camera", "পকেট ক্যামেরায় স্টেবিলাইজড শট ভ্লগিংকে সহজ করে।",
         ["gimbal", "camera", "pocket"], "DJI Osmo Pocket 3 gimbal camera close-up, smooth motion"),
    ]
    science = [
        ("nuclear resilience", "hook", "পারমাণবিক বিস্ফোরণও যার কিছুই করতে পারে না—এই বস্তুর রহস্য কী?",
         ["nuclear", "fire", "shell"], "Macro white egg-like shell under intense teal-orange blowtorch flame, dark background"),
        ("nuclear resilience", "metaphor", "আগুনের শিখায়ও এটি গলে না—পৃষ্ঠে শুধু আলো নাচে।",
         ["flame", "heat", "invulnerable"], "Extreme macro of textured shell resisting turquoise flame, sparks flying"),
        ("chemical reaction", "reveal", "ল্যাবে সবুজ ধোঁয়ার স্তম্ভ উঠলেই বোঝা যায় বিক্রিয়া শুরু।",
         ["teal smoke", "lab", "reaction"], "Teal chemical plume rising from metal tray in dark lab, orange side flames"),
        ("molecular structure", "reveal", "অণুর গঠন কাচের প্লেটে সবুজ আলোয় জ্বলজ্বল করে।",
         ["molecule", "glass", "green glow"], "Glowing green molecular structure on transparent glass plate in teal-graded lab"),
        ("locked secret", "mystery", "তালাবদ্ধ বইয়ে লুকানো সত্য কেউ খুলতে পারেনি।",
         ["locked book", "padlock", "secret"], "Weathered leather book with metal padlock, dark teal laboratory bokeh"),
    ]
    mystery = [
        ("sealed vault", "hook", "শতাব্দী ধরে বন্ধ ভল্ট—ভেতরে কী আছে কেউ জানে না।",
         ["vault", "seal", "fog"], "Ancient sealed metal vault door in fog, dramatic side light, teal grade"),
        ("vanishing light", "metaphor", "আলো হঠাৎ নিভে গেলে অন্ধকারে শুধু একটা ছায়া থাকে।",
         ["light", "shadow", "dark"], "Single candle flame extinguishing into darkness, cinematic smoke"),
        ("hidden map", "reveal", "পুরনো মানচিত্রে লাল দাগই পথ দেখায়।",
         ["map", "red mark", "parchment"], "Macro aged parchment map with red ink route, desaturated film look"),
    ]
    islamic = [
        ("light of guidance", "hook", "আলোর রশ্মি যখন অন্ধকার কাটে—সেই দৃশ্যই প্রশান্তি আনে।",
         ["light rays", "serenity", "warm gold"], "Warm golden light rays through architectural arches, faceless serene atmosphere"),
        ("open pages", "metaphor", "খোলা পাতার টেক্সচারে জ্ঞানের ছোঁয়া অনুভব হয়।",
         ["open book", "pages", "texture"], "Macro of open book pages with soft golden ambient light, faceless"),
        ("mosque exterior", "outro", "মসজিদের গম্বুজ দূরে নরম আলোয় দাঁড়িয়ে।",
         ["dome", "architecture", "dusk"], "Distant mosque dome exterior at dusk warm light, respectful wide shot no faces"),
    ]
    history = [
        ("ancient relic", "hook", "ধুলামাখা ধাতব নিদর্শন ইতিহাসের সাক্ষী।",
         ["relic", "metal", "dust"], "Macro ancient metal relic with dust particles, desaturated documentary grade"),
        ("ruins silhouette", "metaphor", "ধ্বংসাবশেষের ছায়ায় অতীত ফিসফিস করে।",
         ["ruins", "silhouette", "sunset"], "Silhouette of stone ruins at sunset, filmic desaturated grade"),
        ("battle map", "reveal", "যুদ্ধের মানচিত্রে তীরচিহ্নই কৌশল বলে।",
         ["battle map", "arrows", "strategy"], "Close-up historical battle map with ink arrows, textured period light"),
    ]

    bank: List[Dict[str, Any]] = []
    pools = [
        ("Gadget Review", gadgets),
        ("Science Facts", science),
        ("Mystery Stories", mystery),
        ("Islamic Reminder", islamic),
        ("History Channel", history),
    ]
    # Expand to 100 by rotating variants
    i = 0
    while len(bank) < 100:
        for niche, rows in pools:
            for topic, element, narr, kws, prompt in rows:
                i += 1
                # slight prompt/narration variants for diversity
                variant = (len(bank) // max(1, sum(len(r) for _, r in pools))) + 1
                bank.append(
                    {
                        "id": len(bank) + 1,
                        "niche": niche,
                        "topic": topic,
                        "element": element,
                        "narration": narr if variant == 1 else narr + " এক নজরে দেখুন।",
                        "keyword_triggers": kws,
                        "exact_ai_video_prompt": (
                            prompt
                            if variant == 1
                            else prompt + ", vertical 9:16, intentional camera motion, sharp focus"
                        ),
                        "visual_query": f"{topic} {element}",
                        "visual_prompt": prompt,
                    }
                )
                if len(bank) >= 100:
                    break
            if len(bank) >= 100:
                break
    return bank[:100]


def _load_progress() -> Dict[str, Any]:
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "completed_ids": [],
        "passed": 0,
        "failed": 0,
        "agent_errors": 0,
        "last_id": 0,
    }


def _save_progress(p: Dict[str, Any]) -> None:
    p["updated_at"] = datetime.now().isoformat(timespec="seconds")
    PROGRESS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_result(row: Dict[str, Any]) -> None:
    with RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_one(case: Dict[str, Any], channel: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    cid = int(case["id"])
    work = OUT / f"clip_{cid:03d}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

    audio_base = work / "narration"
    audio = None
    for ext in (".m4a", ".wav", ".mp3"):
        cand = audio_base.with_suffix(ext)
        if cand.exists() and cand.stat().st_size > 1000:
            audio = cand
            break
    if audio is None:
        audio = synthesize_narration(
            case["narration"],
            audio_base,
            google_api_keys=keys,
            voice_name="",
            language_hint="en",
        )

    final = work / f"scene_00_{case['element']}.mp4"
    if not (final.exists() and final.stat().st_size > 20000):
        build_dialogue_clip(
            work=work,
            idx=0,
            narration_audio=audio,
            visual_query=case.get("visual_query") or case["topic"],
            visual_prompt=case.get("visual_prompt") or case["exact_ai_video_prompt"],
            element=case["element"],
            size="1080x1920",
            product_name=case["topic"] if "Gadget" in case["niche"] else case["topic"],
            agnes_api=channel.get("agnes_api") or "",
            google_api_keys=keys,
            subtitle_text=case["narration"],
            keyword_triggers=case.get("keyword_triggers") or [],
            exact_ai_video_prompt=case.get("exact_ai_video_prompt") or "",
            niche=case["niche"],
            max_av_retries=3,
            require_agnes=True,
        )

    # Load latest critique
    critiques = sorted(work.glob("scene_00_critique_attempt*.json"))
    critique: Dict[str, Any] = {}
    if critiques:
        critique = json.loads(critiques[-1].read_text(encoding="utf-8"))

    precheck = {}
    pre_path = work / "scene_00_precheck.json"
    if pre_path.exists():
        precheck = json.loads(pre_path.read_text(encoding="utf-8"))

    meta = {}
    outage = bool((critique.get("raw") or {}).get("fallback")) or (
        work / "scene_00_CRITIC_OUTAGE.txt"
    ).exists()
    # Meta-audit: always on fail; sample every 10th on pass (quota save)
    need_meta = final.exists() and critique and (
        not critique.get("passed") or cid % 10 == 0
    )
    if need_meta and not outage:
        meta = meta_audit_critique(
            video_path=final,
            narration_bn=case["narration"],
            agent_critique=critique,
            keyword_triggers=case.get("keyword_triggers") or [],
            google_api_keys=keys,
        )
        (work / "meta_audit.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if meta.get("error_type") == "false_pass":
            apply_training_rule(
                meta.get("training_rule")
                or f"Do not pass clips for {case['element']} when keywords {case.get('keyword_triggers')} are missing.",
                source=f"marathon_clip_{cid}",
            )
    elif outage:
        meta = {
            "agent_was_correct": None,
            "error_type": "quota_deferred",
            "explanation": "critic API quota — clip saved, re-critique later",
        }

    passed = bool(critique.get("passed")) and meta.get("error_type") not in {
        "false_pass",
        "missed_critical",
    }
    quota_deferred = outage and final.exists()
    if quota_deferred:
        passed = False
    row = {
        "id": cid,
        "niche": case["niche"],
        "element": case["element"],
        "topic": case["topic"],
        "agent_score": critique.get("match_score"),
        "agent_passed": critique.get("passed"),
        "precheck_score": precheck.get("prompt_score"),
        "precheck_passed": precheck.get("passed"),
        "meta_correct": meta.get("agent_was_correct"),
        "meta_error": meta.get("error_type"),
        "final_passed": passed,
        "quota_deferred": quota_deferred,
        "attempts": len(critiques),
        "clip": str(final) if final.exists() else "",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    (work / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _acquire_lock()
    try:
        return _main_inner()
    finally:
        _release_lock()


def _main_inner() -> int:
    if not CASES_PATH.exists():
        cases = _seed_cases()
        CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    channels = store.list_channels()
    if not channels:
        logger.error("No channel configured")
        return 2
    ch = channels[0]
    keys = [k for k in [ch.get("google_api_1") or "", ch.get("google_api_2") or ""] if k.strip()]
    if not keys:
        logger.error("No Google API keys")
        return 2
    if not (ch.get("agnes_api") or "").strip():
        logger.error("No Agnes API key")
        return 2

    from pipeline.av_sync_critic import TRAINING_RULES_PATH, load_training_rules

    if TRAINING_RULES_PATH.exists():
        try:
            parsed = json.loads(TRAINING_RULES_PATH.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                TRAINING_RULES_PATH.write_text(
                    json.dumps({"rules": parsed, "updated_by": "seed"}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
    logger.info("Training rules loaded: %s", len(load_training_rules()))

    progress = _load_progress()
    done = set(progress.get("completed_ids") or [])

    logger.info("Marathon start: %s/%s done", len(done), len(cases))
    for case in cases:
        cid = int(case["id"])
        if cid in done:
            continue
        logger.info("===== CLIP %s/%s %s / %s =====", cid, len(cases), case["niche"], case["element"])
        try:
            row = run_one(case, ch, keys)
            _append_result(row)
            if row.get("quota_deferred"):
                logger.warning(
                    "CLIP %s quota-deferred — not marking complete (will retry)",
                    cid,
                )
                progress["last_id"] = cid
                _save_progress(progress)
                time.sleep(90)
                continue
            done.add(cid)
            progress["completed_ids"] = sorted(done)
            progress["last_id"] = cid
            if row.get("final_passed"):
                progress["passed"] = int(progress.get("passed") or 0) + 1
            else:
                progress["failed"] = int(progress.get("failed") or 0) + 1
            if row.get("meta_correct") is False:
                progress["agent_errors"] = int(progress.get("agent_errors") or 0) + 1
            _save_progress(progress)
            logger.info(
                "CLIP %s result: agent=%s meta=%s final=%s",
                cid,
                row.get("agent_score"),
                row.get("meta_error"),
                row.get("final_passed"),
            )
            # Quota-friendly pacing between clips (Agnes also paces ~32s)
            time.sleep(45)
        except Exception as exc:
            logger.error("CLIP %s FAILED: %s\n%s", cid, exc, traceback.format_exc()[-800:])
            err_row = {
                "id": cid,
                "error": str(exc),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            _append_result(err_row)
            progress["failed"] = int(progress.get("failed") or 0) + 1
            progress["last_id"] = cid
            # still mark completed to avoid infinite retry on hard API death? No — allow resume retry
            # Only skip permanent after 3 hard fails tracked in work dir
            work = OUT / f"clip_{cid:03d}"
            fails = work / "_hard_fails.txt"
            n = 1
            if fails.exists():
                try:
                    n = int(fails.read_text(encoding="utf-8").strip() or "0") + 1
                except Exception:
                    n = 1
            work.mkdir(parents=True, exist_ok=True)
            fails.write_text(str(n), encoding="utf-8")
            if n >= 3:
                done.add(cid)
                progress["completed_ids"] = sorted(done)
                logger.warning("CLIP %s skipped after %s hard fails", cid, n)
            _save_progress(progress)
            # backoff on quota
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                time.sleep(30)
            else:
                time.sleep(5)

    logger.info(
        "Marathon finished: passed=%s failed=%s agent_errors=%s",
        progress.get("passed"),
        progress.get("failed"),
        progress.get("agent_errors"),
    )
    summary = {
        "passed": progress.get("passed"),
        "failed": progress.get("failed"),
        "agent_errors": progress.get("agent_errors"),
        "completed": len(progress.get("completed_ids") or []),
        "total": len(cases),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
