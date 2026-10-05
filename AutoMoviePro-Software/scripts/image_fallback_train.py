"""
Image→Video fallback training mission (Agnes forced down).

Simulates Agnes failure, builds each clip via image pipeline (Pollinations/Goblin/…)
+ Ken Burns + TTS, then dual-analyzes with the AV self-repair agent.

Output: AutoMoviePro-Software/output/ImageFallback_TrainCompare/

Usage:
  venv\\Scripts\\python.exe scripts\\image_fallback_train.py --clips 1,2,3,4,5
  venv\\Scripts\\python.exe scripts\\image_fallback_train.py --clip 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output" / "ImageFallback_TrainCompare"
OUT.mkdir(parents=True, exist_ok=True)
COMPARE = OUT / "COMPARE_SIDE_BY_SIDE"
COMPARE.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "results.jsonl"
REPORT = OUT / "DUAL_ANALYSIS_REPORT.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUT / "image_fallback_train.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("img_fallback_train")

# Reuse Chernobyl case bank
from scripts.chernobyl_30_train import _cases, _ensure_english_narration  # noqa: E402

from pipeline.api_keys import load_api_bundle  # noqa: E402
from pipeline.av_self_repair_agent import diagnose_clip, run_av_self_repair_agent  # noqa: E402
from pipeline.av_sync_critic import apply_training_rule  # noqa: E402
from pipeline.compose import ffmpeg_bin, ffprobe_duration  # noqa: E402
from pipeline.dialogue_sync import (  # noqa: E402
    AGNES_AUDIO_CHUNK_MAX,
    AGNES_TARGET_SECONDS,
    estimate_spoken_seconds,
)
from pipeline.localization import fit_narration_for_agnes  # noqa: E402
from pipeline.scene_builder import build_dialogue_clip  # noqa: E402


def _sync_playbook() -> None:
    try:
        from pipeline.agent_playbook import sync_history_rules_to_training

        n = sync_history_rules_to_training(source="image_fallback_train")
        logger.info("Playbook sync: %s new rules", n)
    except Exception as exc:
        logger.warning("playbook sync: %s", exc)


def _make_tts(text: str, dest: Path, keys: List[str]) -> Path:
    """Reuse existing TTS when text matches; synthesize only if missing/stale."""
    from pipeline.tts_reuse import reuse_or_synthesize_tts

    return reuse_or_synthesize_tts(
        text,
        dest,
        language_hint="en",
        google_api_keys=keys,
        extra_candidates=[
            dest.parent / "narration_en_tts.m4a",
            dest.parent / "narration_en_tts.mp3",
            dest.parent / "scene_00_agent_tts_raw.m4a",
        ],
    )


def _localization_complete(work: Path) -> bool:
    loc = work / "LOCALIZED"
    if not loc.exists():
        return False
    from pipeline.lang_config import TARGET_LANG_CODES, folder_for_lang

    for code in TARGET_LANG_CODES:
        vid = loc / folder_for_lang(code) / "video.mp4"
        if not vid.exists() or vid.stat().st_size < 8000:
            return False
    return True


def _find_final(work: Path, element: str) -> Optional[Path]:
    for name in (
        f"scene_00_{element}.mp4",
        "scene_00_hook.mp4",
        "scene_00_reveal.mp4",
        "scene_00_metaphor.mp4",
        "scene_00_outro.mp4",
    ):
        p = work / name
        if p.exists() and p.stat().st_size > 8000:
            return p
    cands = [
        p
        for p in work.glob("scene_00_*.mp4")
        if "agent" not in p.name
        and "unpadded" not in p.name
        and "_a" not in p.name
        and "tts" not in p.name
        and "repair" not in p.name
    ]
    return cands[0] if cands else None


def _export_compare(cid: int, work: Path, final: Path, human: Dict[str, Any], gaps: Dict[str, Any]) -> None:
    dest = COMPARE / f"clip_{cid:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    if final.exists():
        shutil.copy2(final, dest / f"final_{final.name}")
    for img in sorted((work / "_fallback_i2v").glob("fb_beat_*.png"))[:6]:
        shutil.copy2(img, dest / img.name)
    for img in sorted(work.glob("fb_beat_*.png"))[:6]:
        shutil.copy2(img, dest / img.name)
    for name in (
        "dual_analysis.json",
        "narration_en.txt",
        "case.json",
    ):
        src = work / name
        if src.exists():
            shutil.copy2(src, dest / name)
    fb = work / "_fallback_i2v" / "fallback_result.json"
    if fb.exists():
        shutil.copy2(fb, dest / "fallback_result.json")
    for ar in sorted(work.glob("scene_*_AGENT_REPAIR.json"))[-1:]:
        try:
            shutil.copy2(ar, dest / ar.name)
        except Exception:
            pass
    loc = work / "LOCALIZED"
    if loc.exists():
        loc_dest = dest / "LOCALIZED"
        if loc_dest.exists():
            shutil.rmtree(loc_dest, ignore_errors=True)
        shutil.copytree(loc, loc_dest, dirs_exist_ok=True)
    (dest / "README.txt").write_text(
        f"clip={cid}\nhuman_passed={human.get('passed')}\n"
        f"agent_passed={human.get('agent_passed')}\n"
        f"gaps={json.dumps(gaps, ensure_ascii=False)}\n"
        f"open final_*.mp4 + LOCALIZED/*/video.mp4 to review\n",
        encoding="utf-8",
    )



def _human_probe(media: Path, narration: str) -> Dict[str, Any]:
    """Independent human/operator checklist (deterministic, no LLM)."""
    media = Path(media)
    issues: List[str] = []
    notes: List[str] = []
    if not media.exists() or media.stat().st_size < 8000:
        return {
            "passed": False,
            "issues": ["missing_or_tiny_deliverable"],
            "notes": ["Final mp4 missing — pipeline hard-fail"],
            "dur": 0.0,
        }
    dur = ffprobe_duration(media)
    est = estimate_spoken_seconds(narration, lang="en")
    try:
        from pipeline.compose import ffprobe_bin as _ffprobe_bin
    except Exception:
        _ffprobe_bin = None  # type: ignore
    try:
        probe = _ffprobe_bin() if _ffprobe_bin else "ffprobe"
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height", "-of", "json", str(media)],
            capture_output=True, text=True, timeout=30,
        )
        meta = json.loads(r.stdout or "{}")
        streams = meta.get("streams") or []
        has_a = any(s.get("codec_type") == "audio" for s in streams)
        has_v = any(s.get("codec_type") == "video" for s in streams)
        if not has_v:
            issues.append("no_video_stream")
        if not has_a:
            issues.append("no_audio_stream")
        else:
            notes.append("audio_stream_present")
    except Exception as exc:
        notes.append(f"ffprobe_soft_fail:{exc}")
    if dur < max(3.0, est * 0.55):
        issues.append("video_much_shorter_than_speech_estimate")
    if dur > est + 6.0:
        notes.append("video_longer_than_speech_est_ok_if_tail_hold")
    if media.name.startswith("agnes_") and "i2v" in media.name:
        issues.append("raw_i2v_named_as_final_should_be_scene_")
    if not media.name.startswith("scene_"):
        notes.append(f"deliverable_name={media.name}")
    beat_imgs = sorted(media.parent.glob("fb_beat_*.png"))
    if not beat_imgs:
        beat_imgs = sorted(media.parent.glob("_fallback_i2v/fb_beat_*.png"))
    if not beat_imgs:
        issues.append("no_fb_beat_images_in_work_dir")
    else:
        notes.append(f"beat_images={len(beat_imgs)}")
    fb = media.parent / "fallback_result.json"
    if not fb.exists():
        fb = media.parent / "_fallback_i2v" / "fallback_result.json"
    if fb.exists():
        try:
            fr = json.loads(fb.read_text(encoding="utf-8"))
            notes.append(f"fallback_provider={fr.get('provider')}")
            notes.append(f"fallback_beats={fr.get('beats')}")
            if not (fr.get("inspector") or {}).get("sync_ok", True):
                issues.append("fallback_inspector_sync_fail")
            beats = (fr.get("inspector") or {}).get("beats") or []
            kw_hits = 0
            for b in beats:
                pr = str((b or {}).get("prompt") or "").lower()
                if "required visual anchors" in pr or "pripyat" in pr or "chernobyl" in pr:
                    kw_hits += 1
            if beats and kw_hits == 0:
                issues.append("visual_prompts_missing_topic_anchors")
                notes.append("visual_relevance_weak")
        except Exception:
            pass
    else:
        issues.append("missing_fallback_result_json")
    agent_reports = sorted(media.parent.glob("scene_*_AGENT_REPAIR.json"))
    agent_passed = None
    agent_issues: List[str] = []
    if agent_reports:
        try:
            ar = json.loads(agent_reports[-1].read_text(encoding="utf-8"))
            agent_passed = bool(ar.get("passed"))
            agent_issues = list(ar.get("issues") or ar.get("critical_issues") or [])
            notes.append(f"agent_steps={ar.get('steps')}")
        except Exception:
            pass
    else:
        issues.append("missing_agent_repair_json")
    diag = diagnose_clip(media, narration=narration, lang="en")
    hard = list(diag.get("hard_hits") or [])
    if hard:
        issues.extend([f"gate:{h}" for h in hard])
    passed = not hard and "no_audio_stream" not in issues and "missing_or_tiny_deliverable" not in issues
    return {
        "passed": passed,
        "issues": sorted(set(issues)),
        "notes": notes,
        "dur": dur,
        "est_speech": est,
        "agent_passed": agent_passed,
        "agent_issues": agent_issues,
        "diag_hard": hard,
        "diag_issues": list(diag.get("issues") or []),
        "beat_images": [p.name for p in beat_imgs],
    }



def _gap_analysis(human: Dict[str, Any], agent_diag: Dict[str, Any]) -> Dict[str, Any]:
    """What did human catch that agent missed (or vice versa)?"""
    h_set = set(human.get("diag_hard") or []) | {
        i.replace("gate:", "") for i in (human.get("issues") or []) if i.startswith("gate:")
    }
    a_set = set(agent_diag.get("hard_hits") or [])
    human_only = sorted(h_set - a_set)
    agent_only = sorted(a_set - h_set)
    structural = [
        i
        for i in (human.get("issues") or [])
        if not i.startswith("gate:")
        and i
        not in {
            "missing_agent_repair_json",  # may exist under other name
        }
    ]
    new_rules: List[str] = []
    if "no_audio_stream" in (human.get("issues") or []) or "no_fb_beat_images_in_work_dir" in (
        human.get("issues") or []
    ):
        new_rules.append(
            "IMAGE FALLBACK: every master must have narration audio muxed AND at least one fb_beat_*.png; "
            "silent Ken Burns alone is a hard fail — agent must force TTS remux."
        )
    if human_only:
        new_rules.append(
            "IMAGE FALLBACK agent gap: missed hard gates "
            + ", ".join(human_only)
            + " — always re-run diagnose_clip after TTS/setpts repair before PASS."
        )
    if "fallback_inspector_sync_fail" in (human.get("issues") or []):
        new_rules.append(
            "IMAGE FALLBACK: if audio longer than picture, extend with SAME-seed Ken Burns beats "
            "(never tpad clone); then re-check sync before PASS."
        )
    if "raw_i2v_named_as_final_should_be_scene_" in (human.get("issues") or []):
        new_rules.append(
            "Deliverable must be scene_XX_*.mp4 after agent repair, never raw agnes_*_i2v_*.mp4."
        )
    if "visual_prompts_missing_topic_anchors" in (human.get("issues") or []):
        new_rules.append(
            "DIALOGUE<->IMAGE LOCK: every beat prompt must include REQUIRED visual anchors AND "
            "at least 2 spoken content words from that beat's narration; rewrite before image API."
        )
    return {
        "human_only_hard": human_only,
        "agent_only_hard": agent_only,
        "structural_issues": structural,
        "agent_caught_same": sorted(h_set & a_set),
        "new_training_rules": new_rules,
        "agent_adequate": not human_only
        and "no_audio_stream" not in (human.get("issues") or [])
        and not (
            human.get("agent_passed") is True and (human.get("diag_hard") or [])
        ),
    }


def _apply_gap_training(gaps: Dict[str, Any], clip_id: int) -> List[str]:
    applied = []
    for rule in gaps.get("new_training_rules") or []:
        apply_training_rule(rule, source=f"img_fb_clip_{clip_id}")
        applied.append(rule)
        logger.info("TRAIN rule clip %s: %s", clip_id, rule[:140])
    # Strengthen playbook if agent falsely passed
    if gaps.get("agent_adequate") is False:
        apply_training_rule(
            "Never mark IMAGE FALLBACK PASS while diagnose_clip still reports any HARD_QUALITY_GATES hit; "
            "re-run diagnose after each repair step.",
            source=f"img_fb_clip_{clip_id}_strict",
        )
        applied.append("strict_no_false_pass")
    return applied



def run_one(
    case: Dict[str, Any],
    keys: List[str],
    pollinations_key: str,
    *,
    localize: bool = False,
    resume: bool = True,
) -> Dict[str, Any]:
    cid = int(case["id"])
    work = OUT / f"clip_{cid:02d}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

    # Resume: skip full rebuild if final + (optional) localization already OK
    existing = _find_final(work, case["element"])
    if resume and existing and existing.exists():
        narr_file = work / "narration_en.txt"
        narration_en = narr_file.read_text(encoding="utf-8").strip() if narr_file.exists() else ""
        if narration_en and (not localize or _localization_complete(work)):
            logger.info("CLIP %s RESUME skip rebuild (final exists%s)", cid, " + localized" if localize else "")
            dual_path = work / "dual_analysis.json"
            if dual_path.exists():
                try:
                    return json.loads(dual_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

    narration_en_raw = _ensure_english_narration(case, work, keys)
    fitted_path = work / "narration_en.txt"
    if fitted_path.exists() and fitted_path.stat().st_size > 20 and resume:
        narration_en = fitted_path.read_text(encoding="utf-8").strip()
        logger.info("CLIP %s reuse fitted narration_en.txt", cid)
    else:
        narration_en = fit_narration_for_agnes(
            narration_en_raw,
            google_api_keys=keys,
            target_seconds=AGNES_TARGET_SECONDS,
            max_seconds=AGNES_AUDIO_CHUNK_MAX,
        )
        fitted_path.write_text(narration_en, encoding="utf-8")
    est = estimate_spoken_seconds(narration_en, lang="en")
    logger.info("CLIP %s fitted EN ~%.1fs: %s", cid, est, narration_en[:120])

    # TTS reuse — only synth when missing/stale
    tts_path = _make_tts(narration_en, work / "narration_en_tts.m4a", keys)
    logger.info("CLIP %s TTS ready: %s (%.1fs)", cid, tts_path.name, ffprobe_duration(tts_path))

    need_build = True
    if resume and existing and existing.exists() and existing.stat().st_mtime >= tts_path.stat().st_mtime:
        need_build = False
        final_path = existing
        logger.info("CLIP %s reuse existing final %s", cid, final_path.name)

    if need_build:
        final_path = build_dialogue_clip(
            work=work,
            idx=0,
            narration_audio=tts_path,
            visual_query=case.get("visual_query") or case["topic"],
            visual_prompt=case.get("visual_prompt") or case["exact_ai_video_prompt"],
            element=case["element"],
            size="1080x1920",
            product_name=case["topic"],
            agnes_api="",
            agnes_api_keys=[],
            google_api_keys=keys,
            subtitle_text=narration_en,
            keyword_triggers=case.get("keyword_triggers") or [],
            exact_ai_video_prompt=case["exact_ai_video_prompt"],
            niche=case["niche"],
            max_av_retries=1,
            require_agnes=True,
            allow_image_fallback=True,
            pexels_api="",
            pollinations_key=pollinations_key,
            prefer_agnes_native_audio=False,
        )

    # Agent diagnose + repair (reuse TTS inside agent)
    agent_diag = diagnose_clip(final_path, narration=narration_en, lang="en")
    if not agent_diag.get("passed") and final_path.exists():
        repair_dest = work / "scene_00_post_train_repair.mp4"
        report = run_av_self_repair_agent(
            media=final_path,
            video_src=final_path,
            dest=repair_dest,
            narration=narration_en,
            google_api_keys=keys,
            work=work,
            idx=0,
            force_tts_clarity=False,  # reuse narration_en_tts; only fix gates
        )
        if repair_dest.exists() and (report.get("passed") or report.get("steps")):
            shutil.copy2(repair_dest, final_path)
            agent_diag = diagnose_clip(final_path, narration=narration_en, lang="en")

    loc_result: Dict[str, Any] = {}
    if localize:
        from pipeline.localization import localize_master_clip

        localize_dir = work / "LOCALIZED"
        try:
            # Prefer extracted/agent audio
            audio = work / "narration_en_tts.m4a"
            loc_result = localize_master_clip(
                master_video=final_path,
                english_narration=narration_en,
                out_dir=localize_dir,
                google_api_keys=keys,
                slug=f"clip_{cid:02d}",
                size="1080x1920",
                english_audio=audio if audio.exists() else None,
                image_fallback_work=work,
                pollinations_key=pollinations_key,
            )
        except Exception as exc:
            logger.error("CLIP %s localization failed: %s", cid, exc)
            loc_result = {"ok": False, "error": str(exc)}
            apply_training_rule(
                f"IMAGE FALLBACK localize clip {cid} failed: {str(exc)[:140]} — "
                "reuse lang TTS when present; same-seed extend when TTS longer than picture.",
                source=f"img_fb_clip_{cid}_loc",
            )

    human = _human_probe(final_path, narration_en)
    if localize and not _localization_complete(work):
        human["issues"] = list(human.get("issues") or []) + ["localization_incomplete"]
        human["passed"] = False
    gaps = _gap_analysis(human, agent_diag)
    trained = _apply_gap_training(gaps, cid)

    dual = {
        "clip_id": cid,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": "agnes_forced_image_fallback",
        "final": str(final_path),
        "narration_en": narration_en,
        "human_analysis": human,
        "agent_diagnosis": agent_diag,
        "gap_analysis": gaps,
        "training_rules_applied": trained,
        "duration": ffprobe_duration(final_path) if final_path.exists() else 0,
        "localized": bool(localize),
        "localization": {
            code: bool((loc_result.get("languages") or {}).get(code, {}).get("ok"))
            for code in ("en", "bn", "hi", "ur", "ta", "ml")
        }
        if loc_result
        else {},
    }
    (work / "dual_analysis.json").write_text(
        json.dumps(dual, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _export_compare(cid, work, final_path, human, gaps)

    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dual, ensure_ascii=False) + "\n")

    logger.info(
        "CLIP %s DONE human_pass=%s agent_pass=%s gaps=%s dur=%.1fs loc=%s",
        cid,
        human.get("passed"),
        agent_diag.get("passed"),
        not gaps.get("agent_adequate"),
        dual["duration"],
        localize,
    )
    return dual


def _append_report(dual: Dict[str, Any]) -> None:
    cid = dual["clip_id"]
    h = dual["human_analysis"]
    g = dual["gap_analysis"]
    block = (
        f"\n## Clip {cid:02d}\n"
        f"- Final: `{dual.get('final')}`\n"
        f"- Duration: {dual.get('duration'):.1f}s\n"
        f"- Localized: {dual.get('localized')} → {dual.get('localization')}\n"
        f"- Human passed: **{h.get('passed')}** | Agent diagnose passed: **{dual['agent_diagnosis'].get('passed')}**\n"
        f"- Human issues: {h.get('issues')}\n"
        f"- Agent hard: {dual['agent_diagnosis'].get('hard_hits')}\n"
        f"- Gap human_only: {g.get('human_only_hard')} | agent_adequate: {g.get('agent_adequate')}\n"
        f"- Rules trained: {len(dual.get('training_rules_applied') or [])}\n"
        f"- Narration: {dual.get('narration_en', '')[:180]}…\n"
    )
    if not REPORT.exists():
        REPORT.write_text(
            "# Image Fallback Dual Analysis Report\n\n"
            f"Started {datetime.now().isoformat(timespec='seconds')}\n"
            f"Output root: `{OUT}`\n"
            f"Compare: `{COMPARE}`\n"
            "Rules: TTS reuse; image long-TTS → same-seed new beats; clips 1–17 full localize.\n",
            encoding="utf-8",
        )
    with REPORT.open("a", encoding="utf-8") as f:
        f.write(block)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--clips",
        default="1-30",
        help="Comma list or range like 1-30 (default all 30)",
    )
    ap.add_argument("--clip", type=int, default=0, help="Single clip id (overrides --clips)")
    ap.add_argument("--localize-through", type=int, default=17, help="Localize clips 1..N (default 17)")
    ap.add_argument("--no-resume", action="store_true", help="Force rebuild even if outputs exist")
    args = ap.parse_args()

    _sync_playbook()
    apply_training_rule(
        "TTS: reuse existing narration_*.m4a / lang TTS when text fingerprint matches; "
        "only synthesize when missing or stale — never spray free TTS APIs waiting.",
        source="img_fb_tts_reuse_policy",
    )
    apply_training_rule(
        "DIALOGUE<->IMAGE LOCK: each beat image prompt must include >=2 spoken content words "
        "from that beat plus REQUIRED visual anchors — rewrite before image API (no extra LLM).",
        source="img_fb_dialogue_image_lock",
    )
    apply_training_rule(
        "TTS key map: non-English languages use one dedicated Google API slot each; "
        "English rotates one key per synthesize call when English TTS is needed.",
        source="tts_lang_key_map_policy",
    )

    bundle = load_api_bundle()
    keys = list(bundle.get("google_keys") or [])
    pollinations_key = ""
    try:
        from app import db as store

        chans = store.list_channels() if hasattr(store, "list_channels") else []
        if chans:
            ch = chans[0] if isinstance(chans[0], dict) else {}
            pollinations_key = (ch.get("pollinations_api") or "").strip()
    except Exception:
        pass
    pollinations_key = pollinations_key or (bundle.get("pollinations_key") or "")

    cases = {int(c["id"]): c for c in _cases()}
    if args.clip:
        ids = [int(args.clip)]
    else:
        raw = str(args.clips).strip()
        ids = []
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                ids.extend(range(int(a), int(b) + 1))
            elif part:
                ids.append(int(part))

    resume = not args.no_resume
    loc_through = int(args.localize_through)
    logger.info(
        "=== Image fallback train clips=%s localize<=%s resume=%s out=%s ===",
        ids,
        loc_through,
        resume,
        OUT,
    )
    logger.info("Agnes FORCED EMPTY | TTS reuse ON | same-seed image extend ON")

    os.environ.setdefault("AMP_PREFER_EDGE_TTS", "1")
    os.environ.setdefault("GOBLIN_PRIMARY", "false")
    os.environ.setdefault("GOBLIN_ENABLED", "false")
    os.environ.setdefault("IMAGE_PROVIDER_PRIORITY", "pollinations,freetheai,google")
    os.environ.setdefault("AMP_FORCE_PRECHECK", "0")

    for cid in ids:
        case = cases.get(cid)
        if not case:
            logger.error("Unknown clip id %s", cid)
            continue
        try:
            dual = run_one(
                case,
                keys,
                str(pollinations_key or ""),
                localize=(cid <= loc_through),
                resume=resume,
            )
            _append_report(dual)
            print("\n" + "=" * 60)
            print(f"CLIP {cid} SUMMARY")
            print(
                json.dumps(
                    {
                        "final": dual.get("final"),
                        "human_passed": dual["human_analysis"].get("passed"),
                        "agent_passed": dual["agent_diagnosis"].get("passed"),
                        "human_issues": dual["human_analysis"].get("issues"),
                        "agent_hard": dual["agent_diagnosis"].get("hard_hits"),
                        "agent_adequate": dual["gap_analysis"].get("agent_adequate"),
                        "localized": dual.get("localization"),
                        "rules": dual.get("training_rules_applied"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            print("=" * 60 + "\n")
        except Exception as exc:
            logger.exception("CLIP %s FAILED: %s", cid, exc)
            err = {
                "clip_id": cid,
                "error": str(exc),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
            apply_training_rule(
                f"IMAGE FALLBACK train clip {cid} raised: {str(exc)[:160]} — "
                "ensure Pollinations image + reusable Edge-TTS before accept.",
                source=f"img_fb_clip_{cid}_exception",
            )



if __name__ == "__main__":
    main()
