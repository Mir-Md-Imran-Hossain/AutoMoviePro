"""
Autonomous AV self-repair agent (history-trained).

Consults pipeline.agent_playbook for fault→repair recipes learned from the
Chernobyl training corrections. Prefers local ffmpeg + TTS over Gemini/Agnes
so API spend stays low.

Does NOT depend on Gemini critic quota. For every dialogue clip it:
  1) Diagnoses cutoff / hold / pace / last-word / black-tail / end-freeze
  2) Repairs with mux_fit_av_setpts (slow/fast motion) and/or paced TTS
  3) Re-gates until pass or max steps
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.av_quality_gates import (
    HARD_QUALITY_GATES,
    detect_black_tail,
    detect_burned_master_subs,
    detect_dialogue_cutoff,
    detect_end_freeze,
    detect_english_master_narration,
    detect_last_word_integrity,
    detect_speech_pace,
    detect_tail_hold,
    detect_visual_anchor_lock,
    detect_voice_sidecar_lock,
)
from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.dialogue_sync import DIALOGUE_TAIL_PAD_SEC, estimate_spoken_seconds, pad_av_tail

logger = logging.getLogger(__name__)

MAX_REPAIR_STEPS = 3

# Ensure history lessons are loaded into training rules (idempotent)
try:
    from pipeline.agent_playbook import sync_history_rules_to_training

    sync_history_rules_to_training()
except Exception:
    pass


def diagnose_clip(
    media: Path,
    *,
    narration: str,
    lang: str = "en",
    prompt: str = "",
    product_name: str = "",
    keywords: Optional[List[str]] = None,
    work: Optional[Path] = None,
    idx: int = 0,
) -> Dict[str, Any]:
    """Run all deterministic dialogue + language/visual/voice gates."""
    media = Path(media)
    gates = [
        detect_dialogue_cutoff(media, narration_text=narration, lang=lang),
        detect_tail_hold(media),
        detect_speech_pace(media, narration_text=narration, lang=lang),
        detect_last_word_integrity(media, narration_text=narration),
        detect_black_tail(media),
        detect_end_freeze(media),
        detect_english_master_narration(narration, lang=lang),
        detect_visual_anchor_lock(
            prompt=prompt,
            product_name=product_name,
            keywords=keywords,
            narration=narration,
        ),
        detect_voice_sidecar_lock(work, idx=idx),
        detect_burned_master_subs(work, idx=idx, lang=lang),
    ]
    issues: List[str] = []
    critical: List[str] = []
    for g in gates:
        if g.get("passed", True):
            continue
        issues.extend(g.get("issues") or [])
        critical.extend(g.get("critical_issues") or [])
    hard = sorted(set(critical) & HARD_QUALITY_GATES)
    try:
        from pipeline.agent_playbook import repair_hint_for_hits

        hint = repair_hint_for_hits(hard)
    except Exception:
        hint = ""
    visual_hard = set(hard) & {
        "wrong_subject",
        "unrelated_broll",
        "talking_head",
        "visual_anchors_missing",
    }
    return {
        "passed": not hard and all(g.get("passed", True) for g in gates),
        "issues": issues,
        "critical_issues": sorted(set(critical)),
        "hard_hits": hard,
        "repair_hint": hint,
        "gates": gates,
        "needs_tts_replace": bool(
            set(hard)
            & {
                "dialogue_cutoff",
                "speech_pace_too_fast",
                "speech_pace_too_slow",
                "last_word_incomplete",
                "master_not_english",
                "voice_drift",
            }
        ),
        "needs_language_repair": "master_not_english" in hard,
        "needs_visual_regen": bool(visual_hard),
        "needs_tail_pad": bool(
            set(hard) & {"missing_tail_hold", "duration_too_short"}
        ),
        "needs_black_trim": bool(
            set(hard) & {"black_tail_freeze", "end_frame_freeze"}
        ),
        "needs_burnin_strip": "burned_master_subs" in hard,
        "audio_passed": not (
            set(hard)
            & {
                "dialogue_cutoff",
                "speech_pace_too_fast",
                "speech_pace_too_slow",
                "last_word_incomplete",
                "missing_tail_hold",
                "black_tail_freeze",
                "end_frame_freeze",
            }
        ),
    }


def _strip_master_burnin(media: Path, dest: Path) -> Optional[Path]:
    """Re-encode without drawtext so localization can reuse clean frames."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=25,format=yuv420p"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(media),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 800:
        logger.warning("strip burn-in failed: %s", (r.stderr or "")[-180:])
        return None
    try:
        Path(str(dest) + ".vf.txt").write_text(vf, encoding="utf-8")
    except Exception:
        pass
    return dest


def _atempo_filter(rate: float) -> str:
    """Build ffmpeg atempo chain (each stage must be within 0.5–2.0)."""
    rate = max(0.5, min(2.0, float(rate)))
    parts: List[str] = []
    r = rate
    # Split extreme rates into stacked atempo filters
    while r > 2.0 + 1e-6:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5 - 1e-6:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.5f}")
    return ",".join(parts)


def _normalize_audio_pace(
    audio_src: Path,
    dest: Path,
    *,
    narration: str,
    lang: str = "en",
) -> Path:
    """
    Pitch-preserving speed adjust so speech lands near estimate_spoken_seconds.
    Faster than target → slow down (atempo < 1); slower → speed up.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    a_dur = max(0.35, ffprobe_duration(audio_src))
    target = max(1.0, estimate_spoken_seconds(narration, lang=lang))
    # Keep a small slack so we do not over-correct natural pauses
    if a_dur <= 0.35:
        import shutil

        shutil.copy2(audio_src, dest)
        return dest
    rate = a_dur / target
    # Only retune outside ~10% band
    if 0.90 <= rate <= 1.10:
        import shutil

        shutil.copy2(audio_src, dest)
        return dest
    # Stronger slow-down for badly short TTS (needed for last_word speech_too_short)
    rate = max(0.55, min(1.30, rate))
    af = _atempo_filter(rate)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(audio_src),
        "-af",
        af,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        logger.warning("atempo pace normalize failed: %s", (r.stderr or "")[-180:])
        import shutil

        shutil.copy2(audio_src, dest)
    else:
        logger.info(
            "Pace-normalized audio %.2fs → target~%.2fs (rate=%.3f)",
            a_dur,
            target,
            rate,
        )
    return dest


def _mux_picture_with_audio(
    *,
    video_src: Path,
    audio_src: Path,
    dest: Path,
    work: Path,
    idx: int,
    tag: str,
) -> Optional[Path]:
    """
    Keep picture, replace audio, match lengths with setpts slow/fast (motion
    continues). Trim Agnes black first. Never freeze-pad for length matching.
    """
    if not video_src.exists() or not audio_src.exists():
        return None
    try:
        from pipeline.video_extend import mux_fit_av_setpts

        return mux_fit_av_setpts(
            video_src=video_src,
            audio_src=audio_src,
            dest=dest,
            work=work,
            stem=f"scene_{idx:02d}_{tag}",
            post_silence_sec=DIALOGUE_TAIL_PAD_SEC,
        )
    except Exception as exc:
        logger.warning("mux_fit_av_setpts failed: %s", exc)
        return None


def repair_with_complete_paced_tts(
    *,
    video_src: Path,
    dest: Path,
    narration: str,
    google_api_keys: List[str],
    work: Path,
    idx: int,
    lang: str = "en",
) -> Optional[Path]:
    """Generate clear TTS, normalize pace/pitch character, pad video to fit."""
    import os

    text = (narration or "").strip()
    if not text or not video_src.exists():
        return None
    if (lang or "en").lower()[:2] == "en":
        try:
            from pipeline.master_lang import ensure_english_text, looks_like_english_master

            if not looks_like_english_master(text):
                text, meta = ensure_english_text(
                    text,
                    google_api_keys=google_api_keys,
                    field="narration",
                )
                logger.info("Agent TTS refused non-English; repaired via=%s", meta.get("via"))
            if not looks_like_english_master(text):
                logger.warning("Agent TTS skipped — narration still not English master")
                return None
        except Exception as exc:
            logger.warning("Agent TTS English lock failed: %s", exc)
            return None
    try:
        raw_tts = work / f"scene_{idx:02d}_agent_tts_raw.m4a"
        reused = False
        try:
            from pipeline.tts_reuse import find_reusable_tts

            hit = find_reusable_tts(
                raw_tts,
                text,
                extra_candidates=[
                    work / "narration_en_tts.m4a",
                    work / f"scene_{idx:02d}_narration_tts.m4a",
                    work / f"narration_{idx:02d}.m4a",
                ],
                lang=lang,
                voice_name="Charon",
            )
            if hit is not None:
                import shutil

                shutil.copy2(hit, raw_tts)
                reused = True
                try:
                    from pipeline.tts_reuse import write_tts_sidecar

                    write_tts_sidecar(raw_tts, text, voice_name="Charon")
                except Exception:
                    pass
                logger.info("Agent TTS reuse fingerprint+voice %s", hit.name)
        except Exception:
            reused = False
        if not reused and (not raw_tts.exists() or raw_tts.stat().st_size < 800):
            prefer_edge = os.environ.get("AMP_PREFER_EDGE_TTS", "").strip().lower() in {
                "1",
                "true",
                "yes",
            } or not google_api_keys
            if prefer_edge:
                from pipeline.edge_tts_fallback import synthesize_edge_tts

                synthesize_edge_tts(text, raw_tts, language_hint=lang)
            else:
                from pipeline.tts_google import synthesize_narration

                synthesize_narration(
                    text,
                    raw_tts,
                    google_api_keys=google_api_keys,
                    language_hint=lang,
                    target_duration_sec=estimate_spoken_seconds(text, lang=lang),
                )
        if not raw_tts.exists() or raw_tts.stat().st_size < 800:
            return None
        paced = work / f"scene_{idx:02d}_agent_tts_paced.m4a"
        _normalize_audio_pace(raw_tts, paced, narration=text, lang=lang)
        fixed = _mux_picture_with_audio(
            video_src=video_src,
            audio_src=paced if paced.exists() else raw_tts,
            dest=dest,
            work=work,
            idx=idx,
            tag="agent_tts",
        )
        return fixed
    except Exception as exc:
        logger.warning("agent TTS repair failed: %s", exc)
        return None


def repair_with_audio_retime(
    *,
    video_src: Path,
    audio_or_video: Path,
    dest: Path,
    narration: str,
    work: Path,
    idx: int,
    lang: str = "en",
) -> Optional[Path]:
    """
    Offline repair (no TTS API): extract speech, pitch-preserving atempo toward
    documentary pace, extend picture with tpad so dialogue + 1s hold fit.
    """
    try:
        raw_a = work / f"scene_{idx:02d}_agent_retime_src.m4a"
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(audio_or_video),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(raw_a),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not raw_a.exists():
            return None
        paced = work / f"scene_{idx:02d}_agent_retime_paced.m4a"
        _normalize_audio_pace(raw_a, paced, narration=narration, lang=lang)
        return _mux_picture_with_audio(
            video_src=video_src,
            audio_src=paced if paced.exists() else raw_a,
            dest=dest,
            work=work,
            idx=idx,
            tag="agent_retime",
        )
    except Exception as exc:
        logger.warning("offline audio retime repair failed: %s", exc)
        return None


def run_av_self_repair_agent(
    *,
    media: Path,
    video_src: Optional[Path],
    dest: Path,
    narration: str,
    google_api_keys: Optional[List[str]],
    work: Path,
    idx: int,
    lang: str = "en",
    force_tts_clarity: bool = False,
    prompt: str = "",
    product_name: str = "",
    keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Diagnose → repair loop. Returns report with final path + whether passed.

    force_tts_clarity: when True (recommended for Agnes native audio), always
    replace speech with paced Charon TTS so closing words like 'crime' are clear
    and pitch matches the rest of the documentary.

    Audio pass is NEVER a visual pass: if prompt/product anchors are missing,
    passed stays False so scene_builder regenerates picture.
    """
    work = Path(work)
    media = Path(media)
    dest = Path(dest)
    keys = [k for k in (google_api_keys or []) if (k or "").strip()]
    picture = Path(video_src) if video_src and Path(video_src).exists() else media
    report: Dict[str, Any] = {
        "agent": "av_self_repair",
        "steps": [],
        "passed": False,
        "final": str(dest),
    }

    def _d(path: Path) -> Dict[str, Any]:
        return diagnose_clip(
            path,
            narration=narration,
            lang=lang,
            prompt=prompt,
            product_name=product_name,
            keywords=keywords,
            work=work,
            idx=idx,
        )

    current = media
    if not current.exists():
        report["error"] = "missing_media"
        return report

    if (lang or "en").lower()[:2] == "en":
        try:
            from pipeline.master_lang import ensure_english_text, looks_like_english_master

            if not looks_like_english_master(narration):
                narration, meta = ensure_english_text(
                    narration,
                    google_api_keys=keys,
                    field="narration",
                    topic=product_name,
                )
                report["language_repair"] = meta
                force_tts_clarity = True
                logger.warning("Agent repaired non-English master narration via=%s", meta.get("via"))
        except Exception as exc:
            logger.warning("Agent language repair skipped: %s", exc)

    diagnosis = _d(current)
    report["initial"] = {
        "passed": diagnosis["passed"],
        "hard_hits": diagnosis["hard_hits"],
        "issues": diagnosis["issues"][:12],
    }
    report["audio_passed"] = bool(diagnosis.get("audio_passed"))
    report["needs_visual_regen"] = bool(diagnosis.get("needs_visual_regen"))

    # Never TTS English-hint on leftover Bangla — language repair already ran.
    if diagnosis.get("needs_language_repair"):
        force_tts_clarity = False
        logger.warning("Agent holding TTS — master_not_english still set after language repair")

    # Picture is wrong: audio-only remux cannot fix pixels. Skip TTS unless audio is also broken.
    visual_only = bool(diagnosis.get("needs_visual_regen")) and bool(
        diagnosis.get("audio_passed")
    ) and not diagnosis.get("needs_language_repair") and not diagnosis.get("needs_tts_replace") and not diagnosis.get("needs_burnin_strip")
    if visual_only:
        import shutil

        if current.resolve() != dest.resolve():
            shutil.copy2(current, dest)
        report["passed"] = False
        report["action"] = "visual_regen_required"
        report["final_hard_hits"] = diagnosis.get("hard_hits") or []
        _write_report(work, idx, report)
        return report

    need_work = (not diagnosis["passed"]) or force_tts_clarity
    if not need_work:
        import shutil

        if current.resolve() != dest.resolve():
            shutil.copy2(current, dest)
        report["passed"] = True
        report["action"] = "already_ok"
        report["audio_passed"] = True
        report["needs_visual_regen"] = False
        _write_report(work, idx, report)
        return report

    for step in range(1, MAX_REPAIR_STEPS + 1):
        step_info: Dict[str, Any] = {"step": step}
        d = _d(current)
        step_info["before"] = d["hard_hits"]
        if d.get("needs_language_repair"):
            step_info["repair"] = "blocked_non_english_tts"
            report["steps"].append(step_info)
            break

        did = False
        if d.get("needs_burnin_strip"):
            out_s = work / f"scene_{idx:02d}_agent_noburn_s{step}.mp4"
            stripped = _strip_master_burnin(current, out_s)
            if stripped and stripped.exists():
                current = stripped
                did = True
                step_info["repair"] = "strip_master_drawtext"
                for p in work.glob(f"scene_{idx:02d}*.vf.txt"):
                    try:
                        blob = p.read_text(encoding="utf-8", errors="ignore")
                        if "drawtext" in blob.lower():
                            p.write_text(
                                blob.split("drawtext")[0].rstrip(" ,"),
                                encoding="utf-8",
                            )
                    except Exception:
                        pass
        # Black-tail only: replace black with last content frame (no TTS needed)
        if d.get("needs_black_trim") and not (
            force_tts_clarity or d.get("needs_tts_replace")
        ):
            from pipeline.video_extend import repair_black_tail_with_setpts

            out_b = work / f"scene_{idx:02d}_agent_blackfix_s{step}.mp4"
            extra = DIALOGUE_TAIL_PAD_SEC if d.get("needs_tail_pad") else 0.0
            repair_black_tail_with_setpts(current, out_b, extra_silence_sec=extra)
            if out_b.exists():
                current = out_b
                did = True
                step_info["repair"] = "black_trim_plus_setpts_motion"

        if (not did) and keys and (
            force_tts_clarity
            or d.get("needs_tts_replace")
            or "missing_tail_hold" in d.get("hard_hits", [])
            or d.get("needs_black_trim")
        ):
            out = work / f"scene_{idx:02d}_agent_repair_s{step}.mp4"
            fixed = repair_with_complete_paced_tts(
                video_src=picture,
                dest=out,
                narration=narration,
                google_api_keys=keys,
                work=work,
                idx=idx,
                lang=lang,
            )
            if fixed and fixed.exists():
                current = fixed
                did = True
                step_info["repair"] = "tts_replace_plus_setpts_fit"
                force_tts_clarity = False  # only force once
            else:
                step_info["repair_failed"] = "tts"
                # Offline fallback: retime existing audio + pad video
                out2 = work / f"scene_{idx:02d}_agent_retime_s{step}.mp4"
                fixed2 = repair_with_audio_retime(
                    video_src=picture,
                    audio_or_video=current,
                    dest=out2,
                    narration=narration,
                    work=work,
                    idx=idx,
                    lang=lang,
                )
                if fixed2 and fixed2.exists():
                    current = fixed2
                    did = True
                    step_info["repair"] = "offline_atempo_plus_setpts_fit"
                    force_tts_clarity = False
        elif (not did) and (d.get("needs_tts_replace") or force_tts_clarity or d.get("needs_black_trim")):
            out2 = work / f"scene_{idx:02d}_agent_retime_s{step}.mp4"
            fixed2 = repair_with_audio_retime(
                video_src=picture,
                audio_or_video=current,
                dest=out2,
                narration=narration,
                work=work,
                idx=idx,
                lang=lang,
            )
            if fixed2 and fixed2.exists():
                current = fixed2
                did = True
                step_info["repair"] = "offline_atempo_plus_setpts_fit"
                force_tts_clarity = False
            else:
                # Last resort: black trim + setpts motion (no freeze)
                from pipeline.video_extend import repair_black_tail_with_setpts

                out_b = work / f"scene_{idx:02d}_agent_blackfix_s{step}.mp4"
                repair_black_tail_with_setpts(
                    current, out_b, extra_silence_sec=DIALOGUE_TAIL_PAD_SEC
                )
                if out_b.exists():
                    current = out_b
                    did = True
                    step_info["repair"] = "black_trim_plus_setpts_motion"
                else:
                    step_info["repair_failed"] = "offline_retime"
        elif (not did) and d.get("needs_tail_pad"):
            pad_av_tail(current, dest, DIALOGUE_TAIL_PAD_SEC)
            current = dest
            did = True
            step_info["repair"] = "tail_pad_only"

        if not did:
            step_info["repair"] = "none_available"
            report["steps"].append(step_info)
            break

        after = _d(current)
        step_info["after"] = after["hard_hits"]
        step_info["passed"] = after["passed"]
        report["steps"].append(step_info)
        if after["passed"]:
            break

    import shutil

    if current.exists():
        # Ensure scene meets Agnes min window (pace repair alone often lands ~6.0s)
        try:
            from pipeline.dialogue_sync import AGNES_MIN_SECONDS

            dur_now = float(ffprobe_duration(current) or 0.0)
            if dur_now > 0.5 and dur_now < AGNES_MIN_SECONDS - 0.05:
                need = AGNES_MIN_SECONDS - dur_now + 0.2
                pad_dest = work / f"scene_{idx:02d}_agent_minpad.mp4"
                pad_av_tail(current, pad_dest, need)
                if pad_dest.exists() and pad_dest.stat().st_size > 8000:
                    current = pad_dest
                    report.setdefault("steps", []).append(
                        {
                            "repair": "min_duration_pad",
                            "from_sec": round(dur_now, 3),
                            "pad_sec": round(need, 3),
                            "to_sec": round(float(ffprobe_duration(current) or 0.0), 3),
                        }
                    )
        except Exception as exc:
            logger.warning("min duration pad failed scene %s: %s", idx, exc)
        if current.resolve() != dest.resolve():
            shutil.copy2(current, dest)
        # Always ensure unpadded+final markers for localization
        unpadded = work / f"scene_{idx:02d}_agent_unpadded.mp4"
        try:
            shutil.copy2(dest, unpadded)
        except Exception:
            pass
        marker = work / f"scene_{idx:02d}_master_for_localize.txt"
        marker.write_text(str(dest.resolve()), encoding="utf-8")

    final_d = _d(dest) if dest.exists() else diagnosis
    report["passed"] = bool(final_d.get("passed")) and not final_d.get("needs_visual_regen")
    report["audio_passed"] = bool(final_d.get("audio_passed"))
    report["needs_visual_regen"] = bool(final_d.get("needs_visual_regen"))
    report["final_hard_hits"] = final_d.get("hard_hits") or []
    report["final"] = str(dest)
    _write_report(work, idx, report)
    logger.info(
        "AV self-repair scene %s passed=%s hits=%s steps=%s",
        idx,
        report["passed"],
        report.get("final_hard_hits"),
        len(report["steps"]),
    )
    return report

def _write_report(work: Path, idx: int, report: Dict[str, Any]) -> None:
    path = work / f"scene_{idx:02d}_AGENT_REPAIR.json"
    try:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
