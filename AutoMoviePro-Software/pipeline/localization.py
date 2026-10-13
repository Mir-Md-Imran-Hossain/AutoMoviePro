"""
Localization orchestrator (AutoMoviePro-inspired, simplified for desktop).

Flow:
  1) Master = English picture + English audio (already composed)
  2) Culturally LOCALIZE English narration → target language
     (native emotion, tone, culture, faith-aware dignity — NOT literal MT)
  3) TTS in target language
  4) Remux: SAME video frames + new audio + burned subtitles
  5) Write SRT beside each language master

Does NOT re-call Agnes. Picture stays the English master visual.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.dialogue_sync import DIALOGUE_TAIL_PAD_SEC, pad_av_tail
from pipeline.lang_config import (
    LANG_DISPLAY,
    MASTER_VOICE_NAME,
    SOURCE_LANG,
    TARGET_LANG_CODES,
    folder_for_lang,
    localize_targets,
    locked_voice_chain,
    tts_contract,
)
from pipeline.tts_google import synthesize_narration

logger = logging.getLogger(__name__)


def assert_master_localized_voice_identity(
    *,
    language: str,
    voice_name: str = "",
) -> dict[str, Any]:
    """RCP-06D: localized TTS must keep the same VoiceIdentity contract as master."""
    from pipeline.production_consistency import (
        resolve_canonical_voice_identity,
        voice_identity_preserved,
    )

    profile = (voice_name or MASTER_VOICE_NAME).strip() or MASTER_VOICE_NAME
    master = resolve_canonical_voice_identity(
        language=SOURCE_LANG,
        voice_profile=profile,
        multilingual_consistent=True,
    )
    localized = resolve_canonical_voice_identity(
        language=language or SOURCE_LANG,
        voice_profile=profile,
        voice_identity_id=master.voice_identity_id,
        speaker_id=master.speaker_id,
        multilingual_consistent=True,
    )
    check = voice_identity_preserved(master, localized, language_changed=True)
    if not check.get("ok"):
        raise RuntimeError("VOICE_IDENTITY_CONTINUITY_BLOCKED:localized_mismatch")
    if check.get("provider_verified") or str(check.get("confidence") or "").upper() == "PROVIDER_VERIFIED":
        raise RuntimeError("VOICE_IDENTITY_HONESTY:preserved_must_not_be_provider_verified")
    return check


def localization_packages_complete(
    manifest: Optional[Dict[str, Any]],
    languages: Optional[List[str]],
) -> tuple[bool, List[str]]:
    """
    True iff every non-EN channel language has an ok package entry.
    Used by generate_video before ready_to_upload (H4 DEF-H4-001).
    Also rejects packages whose narration.txt is English-as-localized.
    """
    targets = [
        str(c).lower().strip()[:2]
        for c in (languages or [])
        if str(c or "").lower().strip()[:2] and str(c).lower().strip()[:2] != SOURCE_LANG
    ]
    targets = list(dict.fromkeys(targets))
    if not targets:
        return True, []
    lang_map = (manifest or {}).get("languages") or {}
    failed: List[str] = []
    en_src = ""
    en_entry = lang_map.get(SOURCE_LANG) if isinstance(lang_map.get(SOURCE_LANG), dict) else {}
    try:
        en_vid = (en_entry or {}).get("video")
        en_narr = Path(str(en_vid)).parent / "narration.txt" if en_vid else None
        if en_narr and en_narr.is_file():
            en_src = en_narr.read_text(encoding="utf-8").strip()
    except Exception:
        en_src = ""
    for code in targets:
        entry = lang_map.get(code)
        if not isinstance(entry, dict) or not entry.get("ok"):
            failed.append(code)
            continue
        video = entry.get("video")
        if video and not Path(str(video)).is_file():
            failed.append(code)
            continue
        narr_path = entry.get("narration") or entry.get("narration_txt")
        if not narr_path and video:
            narr_path = str(Path(str(video)).parent / "narration.txt")
        if not narr_path or not Path(str(narr_path)).is_file():
            # scene_local concat may omit narration.txt — require video only then
            continue
        try:
            from pipeline.localization_consistency.drift import detect_english_as_localized

            loc_txt = Path(str(narr_path)).read_text(encoding="utf-8").strip()
            if en_src:
                bad = detect_english_as_localized(en_src, loc_txt, code)
                if bad:
                    failed.append(code)
            else:
                # Without EN source, still reject Latin-dominant Indic/Arabic packages
                bad = detect_english_as_localized(
                    "The James Webb Space Telescope floats in deep space with golden mirrors.",
                    loc_txt,
                    code,
                )
                if bad == "english_as_localized:latin_dominant":
                    failed.append(code)
        except Exception:
            pass
    return (len(failed) == 0), failed


def dedupe_language_codes(languages: Optional[List[str]], *, exclude_source: bool = True) -> List[str]:
    """Preserve order; drop blanks/duplicates (H3 DEF-H3-003)."""
    out: List[str] = []
    seen: set[str] = set()
    for raw in languages or []:
        code = str(raw or "").lower().strip()
        if not code or code in seen:
            continue
        if exclude_source and code == SOURCE_LANG:
            continue
        seen.add(code)
        out.append(code)
    return out


def _translate_cache_path(work_dir: Path, src: str, tgt: str, text: str) -> Path:
    import hashlib

    # v2 = cultural localization prompts (not literal MT) — busts old translation caches
    h = hashlib.sha1(
        f"v2-cultural|{src}|{tgt}|{(text or '').strip()}".encode("utf-8")
    ).hexdigest()[:24]
    d = Path(work_dir) / "TRANSLATE_CACHE"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.txt"


def _live_loc(message: str, **extra: Any) -> None:
    try:
        from pipeline.live_activity import log as live_log

        live_log("localize", message, **extra)
    except Exception:
        pass


def fit_narration_for_agnes(
    text: str,
    *,
    google_api_keys: Optional[List[str]] = None,
    target_seconds: float = 8.5,
    max_seconds: float = 9.0,
) -> str:
    """
    Keep spoken English narration inside Agnes' reliable window (7–10s, spoken ≤9s).
    If too long, condense with Gemini while preserving meaning.
    """
    from pipeline.dialogue_sync import AGNES_MIN_SECONDS, estimate_spoken_seconds

    text = (text or "").strip()
    if not text:
        return text
    est = estimate_spoken_seconds(text, lang="en")
    if est <= max_seconds:
        # Soft pad short scripts aren't expanded — Agnes duration_hint handles floor
        return text

    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    from pipeline.prompt_engineering import condense_instruction

    instruction = condense_instruction(
        text=text, target_seconds=int(target_seconds), max_seconds=int(max_seconds)
    )
    try:
        from pipeline.llm_router import chat_text

        hit = chat_text(instruction, google_api_keys=keys, purpose="translate")
        out = (hit.get("text") or "").strip()
        out = re.sub(r'^["“]|["”]$', "", out).strip()
        if len(out) >= 20:
            new_est = estimate_spoken_seconds(out, lang="en")
            logger.info(
                "Condensed narration %.1fs→%.1fs via %s",
                est,
                new_est,
                hit.get("provider"),
            )
            return out
    except Exception as exc:
        logger.warning("condense via router failed: %s", str(exc)[:140])

    words = text.split()
    keep = max(10, int(target_seconds * 2.4))
    return " ".join(words[:keep])


def _clean_translation_output(out: str, *, source_text: str) -> str:
    """Strip model chatter (meta notes, second languages) — keep primary narration."""
    out = (out or "").strip()
    out = re.sub(r'^["“]|["”]$', "", out).strip()
    if not out:
        return ""
    # Drop lines that look like meta commentary / other-script explanations
    lines = []
    for ln in out.splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if any(
            x in low
            for x in (
                "here is",
                "here's",
                "translation:",
                "translated",
                "as an ai",
                "以下",
                "根据你的",
                "发帖",
            )
        ):
            continue
        # Skip pure CJK explanation blocks
        cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
        if cjk >= max(4, len(s) // 3):
            continue
        lines.append(s)
    if lines:
        out = " ".join(lines) if len(lines) <= 3 else lines[0]
    # If still hugely longer than source with mixed scripts, take first sentence
    if len(out) > max(80, len(source_text) * 4):
        out = re.split(r"(?<=[।.!?\n])\s+", out)[0].strip()
    return out.strip()


def translate_text(
    text: str,
    *,
    target_lang: str,
    source_lang: str = SOURCE_LANG,
    google_api_keys: Optional[List[str]] = None,
    domain_hint: str = "documentary narration",
    openrouter_keys: Optional[List[str]] = None,
    huggingface_keys: Optional[List[str]] = None,
    work_dir: Optional[Path] = None,
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    speaker_id: str = "",
    skip_preflight: bool = False,
    localized_validation: bool = True,
) -> str:
    """Translate via OpenRouter → HuggingFace → Google (burn-proof chain).

    AMP-004 Phase-06: deterministic preflight BEFORE provider; optional drift check after.
    """
    text = (text or "").strip()
    if not text:
        return ""
    tgt = (target_lang or "").lower().strip()
    src = (source_lang or SOURCE_LANG).lower().strip()
    if tgt == src:
        return text

    # H3: reuse prior translation for same source+locale under work_dir
    if work_dir is not None:
        cache_p = _translate_cache_path(Path(work_dir), src, tgt, text)
        if cache_p.exists():
            cached = ""
            try:
                cached = cache_p.read_text(encoding="utf-8").strip()
            except Exception:
                cached = ""
            if len(cached) >= max(8, len(text) // 8):
                reject_cache = False
                if localized_validation:
                    from pipeline.localization_consistency.drift import detect_english_as_localized

                    bad = detect_english_as_localized(text, cached, tgt)
                    if bad:
                        reject_cache = True
                        try:
                            cache_p.unlink(missing_ok=True)
                        except Exception:
                            pass
                if not reject_cache:
                    try:
                        from pipeline.idempotency.metrics import UsageEvent, record_usage_event

                        record_usage_event(
                            Path(work_dir),
                            UsageEvent(
                                operation="translate",
                                provider="cache",
                                cache_hit=True,
                                call_count=0,
                                detail=f"{src}->{tgt}",
                            ),
                        )
                        from pipeline.idempotency.store import IdempotencyStore

                        IdempotencyStore(Path(work_dir) / "idempotency").increment_metric(
                            "translate_cache_hit"
                        )
                    except Exception:
                        pass
                    if localized_validation:
                        from pipeline.localization_consistency.production import (
                            apply_production_localization,
                        )

                        apply_production_localization(
                            Path(work_dir),
                            job_id=job_id or Path(work_dir).name,
                            scene_id=scene_id or "0",
                            dialogue_id=dialogue_id or "dlg",
                            source_text=text,
                            source_language=src,
                            target_language=tgt,
                            localized_text=cached,
                            segment_id=segment_id,
                            revision_id=revision_id,
                            speaker_id=speaker_id,
                            block_on_critical=True,
                        )
                    return cached

    # Cost protection — reject invalid requests before provider
    if not skip_preflight:
        from pipeline.localization_consistency.preflight import preflight_localization_request

        preflight_localization_request(
            source_text=text,
            source_language=src,
            target_language=tgt,
            job_id=job_id or (Path(work_dir).name if work_dir else ""),
            scene_id=scene_id,
            dialogue_id=dialogue_id,
            segment_id=segment_id,
            revision_id=revision_id,
            speaker_id=speaker_id,
            block=True,
        )

    keys = [k.strip() for k in (google_api_keys or []) if (k or "").strip()]
    display = LANG_DISPLAY.get(tgt, tgt)
    from pipeline.lang_config import localization_culture_brief
    from pipeline.prompt_engineering import system_for_purpose, translate_instruction

    instruction = translate_instruction(
        text=text,
        src_display=LANG_DISPLAY.get(src, src),
        tgt_display=display,
        domain_hint=domain_hint,
        target_lang=tgt,
        culture_brief=localization_culture_brief(tgt),
    )
    system_msg = system_for_purpose("translate")

    from pipeline.llm_router import chat_text, mark_google_pool_exhausted, prefer_openrouter

    try:
        hit = chat_text(
            instruction,
            purpose="translate",
            system=system_msg,
            google_api_keys=keys,
            openrouter_keys=openrouter_keys,
            huggingface_keys=huggingface_keys,
            json_mode=False,
            prefer_or=True if prefer_openrouter() else False,
        )
        out = _clean_translation_output(hit.get("text") or "", source_text=text)
        if len(out) >= max(8, len(text) // 8):
            logger.info("translate %s→%s via %s", src, tgt, hit.get("provider"))
            if work_dir is not None:
                try:
                    from pipeline.idempotency.metrics import UsageEvent, record_usage_event
                    from pipeline.idempotency.store import IdempotencyStore

                    IdempotencyStore(Path(work_dir) / "idempotency").increment_metric(
                        "translate_cache_miss"
                    )
                    record_usage_event(
                        Path(work_dir),
                        UsageEvent(
                            operation="translate",
                            provider=str(hit.get("provider") or ""),
                            cache_hit=False,
                            call_count=1,
                            detail=f"{src}->{tgt}",
                        ),
                    )
                    _translate_cache_path(Path(work_dir), src, tgt, text).write_text(
                        out, encoding="utf-8"
                    )
                except Exception:
                    pass
                try:
                    from pipeline.localization_consistency.production import apply_production_localization

                    apply_production_localization(
                        Path(work_dir),
                        job_id=job_id or Path(work_dir).name,
                        scene_id=scene_id or "0",
                        dialogue_id=dialogue_id or "dlg",
                        source_text=text,
                        source_language=src,
                        target_language=tgt,
                        localized_text=out if localized_validation else "",
                        segment_id=segment_id,
                        revision_id=revision_id,
                        speaker_id=speaker_id,
                        block_on_critical=localized_validation,
                    )
                except Exception as loc_exc:
                    logger.warning("localization contract post-check: %s", loc_exc)
                    raise
            return out
        raise RuntimeError(f"short translation: {out[:40]!r}")
    except Exception as exc:
        # Re-raise localization preflight/drift as-is
        from pipeline.localization_consistency.preflight import LocalizationPreflightError

        if isinstance(exc, LocalizationPreflightError):
            raise
        err = str(exc)
        # First chat_text already walked the full translate chain — never double-burn.
        if "chat_text failed" in err:
            if "limit: 0" in err or "free_tier" in err or "google_pool_exhausted" in err:
                mark_google_pool_exhausted("translate")
            raise
        if "limit: 0" in err or "free_tier" in err or "google_pool_exhausted" in err:
            mark_google_pool_exhausted("translate")
        # Legacy single-provider failures only: one retry without Google keys
        if not keys:
            raise
        try:
            hit = chat_text(
                instruction,
                purpose="translate",
                system=system_msg,
                google_api_keys=[],
                openrouter_keys=openrouter_keys,
                huggingface_keys=huggingface_keys,
                prefer_or=True,
            )
            out = _clean_translation_output(hit.get("text") or "", source_text=text)
            if out:
                logger.info("translate %s→%s via %s-retry", src, tgt, hit.get("provider"))
                if localized_validation:
                    from pipeline.localization_consistency.drift import detect_english_as_localized

                    bad = detect_english_as_localized(text, out, tgt)
                    if bad:
                        raise RuntimeError(f"translation_rejected:{bad}")
                    if work_dir is not None:
                        from pipeline.localization_consistency.production import (
                            apply_production_localization,
                        )

                        apply_production_localization(
                            Path(work_dir),
                            job_id=job_id or Path(work_dir).name,
                            scene_id=scene_id or "0",
                            dialogue_id=dialogue_id or "dlg",
                            source_text=text,
                            source_language=src,
                            target_language=tgt,
                            localized_text=out,
                            segment_id=segment_id,
                            revision_id=revision_id,
                            speaker_id=speaker_id,
                            block_on_critical=True,
                        )
                return out
        except Exception as exc2:
            raise RuntimeError(f"Translation failed {src}→{tgt}: {exc2}") from exc2
        raise RuntimeError(f"Translation failed {src}→{tgt}: {exc}") from exc


def remux_replace_audio(
    *,
    video_src: Path,
    audio_src: Path,
    dest: Path,
    subtitle_text: str = "",
    lang_code: str = "en",
    size: str = "",
    image_fallback_work: Optional[Path] = None,
    pollinations_key: str = "",
    google_api_keys: Optional[List[str]] = None,
    narration_for_extend: str = "",
    work_dir: Optional[Path] = None,
    scene_id: str = "0",
    dialogue_id: str = "",
    subtitle_file: Optional[Path] = None,
) -> Path:
    """
    Keep the same picture; replace audio; optionally burn a short subtitle.

    Fit policy:
      - Agnes masters: mild setpts ≤18% else atempo audio (no stream_loop).
      - Image-fallback masters: if TTS longer → generate NEW same-seed Ken Burns
        beats (never stretch/tpad clone).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    v_dur = max(0.5, ffprobe_duration(video_src))
    a_dur = max(0.5, ffprobe_duration(audio_src))

    # Detect image-fallback workspace
    fb_work = Path(image_fallback_work) if image_fallback_work else None
    if fb_work is None:
        # master often lives in clip dir; beats under _fallback_i2v
        cand = video_src.parent / "_fallback_i2v"
        if cand.exists():
            fb_work = video_src.parent
        elif (video_src.parent.parent / "_fallback_i2v").exists():
            fb_work = video_src.parent.parent

    MAX_VISUAL_STRETCH = 1.18
    MIN_VISUAL_STRETCH = 0.85
    ratio = a_dur / v_dur if v_dur > 0 else 1.0

    # IMAGE FALLBACK RULE: long TTS → new same-seed images (not stretch)
    if fb_work is not None and ratio > MAX_VISUAL_STRETCH:
        try:
            from pipeline.fallback_image_video import extend_image_master_for_audio

            logger.info(
                "Localize lang=%s: image-extend (audio %.2fs / video %.2fs) same-seed beats",
                lang_code,
                a_dur,
                v_dur,
            )
            extended = dest.parent / f"_img_ext_{lang_code}_{dest.stem}.mp4"
            extend_image_master_for_audio(
                work=fb_work,
                master_video=video_src,
                audio_path=audio_src,
                out_path=extended,
                size=size or "1080x1920",
                narration=narration_for_extend or subtitle_text,
                pollinations_key=pollinations_key,
                google_api_keys=list(google_api_keys or []),
            )
            if extended.exists() and extended.stat().st_size > 8000:
                # Optional subtitle burn on extended
                if subtitle_text:
                    return remux_replace_audio(
                        video_src=extended,
                        audio_src=audio_src,
                        dest=dest,
                        subtitle_text=subtitle_text,
                        subtitle_file=subtitle_file,
                        lang_code=lang_code,
                        size=size,
                        image_fallback_work=None,  # already extended
                        narration_for_extend="",
                        work_dir=work_dir,
                        scene_id=scene_id,
                        dialogue_id=dialogue_id,
                    )
                import shutil

                shutil.copy2(extended, dest)
                return dest
        except Exception as exc:
            logger.warning("image-extend failed (%s) — falling back to setpts/atempo", str(exc)[:160])

    audio_for_mux = audio_src
    tmp_audio: Optional[Path] = None
    picture_src = video_src
    # Trim Agnes trailing black only — length match is setpts/atempo below (no freeze)
    try:
        from pipeline.video_extend import trailing_black_info, trim_to_content_end

        info = trailing_black_info(video_src)
        if info.get("has_trailing_black") and float(info.get("black_duration_sec") or 0) >= 0.25:
            trimmed = dest.parent / f"_loc_noblack_{lang_code}_{dest.stem}.mp4"
            trim_to_content_end(video_src, trimmed)
            if trimmed.exists() and trimmed.stat().st_size > 2000:
                picture_src = trimmed
                v_dur = max(0.5, ffprobe_duration(picture_src))
                ratio = a_dur / v_dur if v_dur > 0 else 1.0
    except Exception as exc:
        logger.warning("localize black trim failed: %s", exc)
        picture_src = video_src

    if ratio > MAX_VISUAL_STRETCH:
        # Speed audio down to fit mild stretch window (dialogue finishes with picture)
        target_a = v_dur * MAX_VISUAL_STRETCH
        atempo = max(0.5, min(2.0, a_dur / max(0.2, target_a)))
        tmp_audio = dest.parent / f"_atempo_{lang_code}_{dest.stem}.m4a"
        # chain atempo filters if outside 0.5–2.0 (already clamped)
        cmd_a = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(audio_src),
            "-filter:a",
            f"atempo={atempo:.4f}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(tmp_audio),
        ]
        r_a = subprocess.run(cmd_a, capture_output=True, text=True)
        if r_a.returncode == 0 and tmp_audio.exists() and tmp_audio.stat().st_size > 500:
            audio_for_mux = tmp_audio
            a_dur = max(0.5, ffprobe_duration(audio_for_mux))
            ratio = a_dur / v_dur
            logger.info(
                "Localize atempo=%.3f (audio %.2fs → %.2fs) lang=%s to avoid freeze-stretch",
                atempo,
                ffprobe_duration(audio_src),
                a_dur,
                lang_code,
            )
        else:
            logger.warning("atempo failed; falling back to capped setpts for %s", lang_code)

    pts_factor = max(MIN_VISUAL_STRETCH, min(MAX_VISUAL_STRETCH, ratio if ratio > 0 else 1.0))
    # Exact match target after audio fit
    out_dur = max(a_dur, v_dur * pts_factor * 0.98)

    vf_parts: List[str] = [f"setpts={pts_factor:.6f}*PTS"]
    if size and "x" in size:
        w, h = size.split("x")
        vf_parts.append(
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        )
    # fps BEFORE setpts can fight timestamps; keep fps after but don't extend with freeze mid-speech
    vf_parts.append("fps=25")
    vf_parts.append("format=yuv420p")

    if subtitle_text or subtitle_file is not None:
        # Prefer caller-provided SRT (canonical localize writes subtitles.srt first).
        # Idempotent write_srt may reuse that path — never assume dest.with_suffix('.srt') exists.
        srt_path: Optional[Path] = None
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if subtitle_file is not None and Path(subtitle_file).is_file() and Path(subtitle_file).stat().st_size > 8:
                srt_path = Path(subtitle_file)
            else:
                candidate = dest.with_suffix(".srt")
                dlg = dialogue_id or f"remux-{lang_code}"
                written = write_srt(
                    subtitle_text,
                    Path(audio_for_mux),
                    candidate,
                    work_dir=work_dir,
                    job_id=(work_dir.name if work_dir else dest.parent.name),
                    scene_id=str(scene_id),
                    dialogue_id=dlg,
                    language=lang_code,
                )
                srt_path = Path(written) if written else candidate
            if srt_path is None or not srt_path.is_file() or srt_path.stat().st_size < 8:
                raise FileNotFoundError(f"subtitle_asset_missing:{srt_path}")
            from pipeline.subtitle_burn import apply_subtitles_to_vf

            vf_string = apply_subtitles_to_vf(
                vf_parts,
                Path(srt_path),
                size=size or "1080x1920",
                lang=lang_code,
            )
        except Exception as srt_exc:
            logger.warning("subtitle burn-in path failed (%s) — drawtext fallback", str(srt_exc)[:160])
            from pipeline.scene_builder import resolve_fontfile_for_lang
            from pipeline.subtitle_burn import drawtext_fallback_filter

            font = resolve_fontfile_for_lang(lang_code)
            if (subtitle_text or "").strip():
                vf_parts.append(
                    drawtext_fallback_filter(
                        subtitle_text or "",
                        size=size or "1080x1920",
                        lang=lang_code,
                        fontfile=font or "",
                    )
                )
            vf_string = ",".join(vf_parts)
    else:
        vf_string = ",".join(vf_parts)

    logger.info(
        "Localize remux setpts=%.4f (video %.2fs, audio %.2fs, out~%.2fs) lang=%s — no stream_loop",
        pts_factor,
        v_dur,
        a_dur,
        out_dur,
        lang_code,
    )

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(picture_src),
        "-i",
        str(audio_for_mux),
        "-t",
        f"{a_dur:.3f}",
        "-vf",
        vf_string,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
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
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if tmp_audio and tmp_audio.exists():
        try:
            tmp_audio.unlink()
        except OSError:
            pass
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 2000:
        raise RuntimeError(f"remux failed: {(r.stderr or r.stdout)[-400:]}")
    # Hold ≥1s AFTER dialogue ends (silence + freeze) — never during speech.
    return pad_av_tail(dest, dest, DIALOGUE_TAIL_PAD_SEC)


def write_srt(
    text: str,
    audio_path: Path,
    srt_path: Path,
    *,
    work_dir: Optional[Path] = None,
    job_id: str = "",
    scene_id: str = "0",
    dialogue_id: str = "d01",
    language: str = "en",
    segment_id: str = "",
    scene_duration_sec: float = 0.0,
    is_short: bool = False,
) -> Path:
    """Write timed SRT cues covering full audio (split into short readable lines)."""
    if work_dir is not None:
        from pipeline.idempotency.subtitle_bridge import idempotent_write_srt

        return idempotent_write_srt(
            text,
            audio_path,
            srt_path,
            work_dir=Path(work_dir),
            job_id=job_id or Path(work_dir).name,
            scene_id=str(scene_id),
            dialogue_id=dialogue_id,
            language=language,
            segment_id=segment_id,
            scene_duration_sec=scene_duration_sec,
        )

    dur = max(1.0, ffprobe_duration(audio_path))
    body = re.sub(r"\s+", " ", (text or "").strip()) or " "
    # PART-5H: shape RTL scripts before cue split when libs available
    lang_l = str(language or "en").lower()[:2]
    if lang_l in ("ur", "ar", "fa", "he"):
        try:
            from pipeline.localization_consistency.rtl_font import shape_rtl_text

            shaped = shape_rtl_text(body, lang_l)
            if shaped.get("shaped") and shaped.get("text"):
                body = str(shaped["text"])
        except Exception:
            pass
    # Short cues (≤6 words for long, 1-3 words for shorts) + ≤2 wrapped lines
    from pipeline.subtitle_burn import chunk_words_for_cues

    chunks = chunk_words_for_cues(
        body,
        words_per_chunk=2 if is_short else 6,
        max_chars_per_line=24 if is_short else (28 if lang_l != "en" else 36),
        is_short=is_short,
    )
    if not chunks:
        chunks = [body]

    n = len(chunks)
    lines = []
    for i, chunk in enumerate(chunks):
        start = dur * (i / n)
        end = dur * ((i + 1) / n)
        lines.append(f"{i + 1}")
        lines.append(f"{_srt_ts(start)} --> {_srt_ts(end)}")
        lines.append(chunk)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def _srt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def localize_scene_clip(
    *,
    scene_video: Path,
    english_narration: str,
    scene_idx: int,
    work: Path,
    google_api_keys: List[str],
    languages: List[str],
    size: str = "1080x1920",
    pollinations_key: str = "",
) -> Dict[str, Any]:
    """
    Immediately after an English scene is ready: for every channel language,
    translate → TTS → burn THAT language's timed subtitle into THAT scene only.

    Layout: work/SCENE_LOCAL/{idx:02d}/{lang}/video.mp4 (+ srt + narration)
    Prevents subtitle/audio from one scene bleeding into another at final mux.
    """
    from pipeline.tts_reuse import reuse_or_synthesize_tts

    en_text = (english_narration or "").strip()
    if not en_text or not scene_video.exists():
        return {"ok": False, "reason": "missing_scene_or_text"}
    targets = [c.lower().strip()[:2] for c in (languages or []) if c]
    targets = [c for c in targets if c and c != SOURCE_LANG]
    if not targets:
        return {"ok": True, "languages": {}, "skipped": "en_only"}

    root = work / "SCENE_LOCAL" / f"{int(scene_idx):02d}"
    root.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Any] = {"ok": True, "languages": {}, "scene_idx": scene_idx}
    _live_loc(
        f"Scene {scene_idx + 1}: localize {len(targets)} langs (burn-in)",
        scene=scene_idx + 1,
        force_new=True,
    )

    for code in targets:
        lang_dir = root / code
        lang_dir.mkdir(parents=True, exist_ok=True)
        try:
            local_text = translate_text(
                en_text,
                target_lang=code,
                source_lang="en",
                google_api_keys=google_api_keys,
                work_dir=work,
                job_id=work.name,
                scene_id=str(scene_idx),
                dialogue_id=f"loc-{int(scene_idx):02d}-{code}",
                localized_validation=True,
            )
            (lang_dir / "narration.txt").write_text(local_text, encoding="utf-8")
            assert_master_localized_voice_identity(language=code, voice_name=MASTER_VOICE_NAME)
            audio_path = reuse_or_synthesize_tts(
                local_text,
                lang_dir / "narration.m4a",
                language_hint=code,
                google_api_keys=google_api_keys,
                voice_name=MASTER_VOICE_NAME,
                work_dir=work,
                job_id=work.name,
                scene_id=int(scene_idx),
                dialogue_id=f"loc-{int(scene_idx):02d}-{code}",
            )
            is_vertical = False
            if size and "x" in size:
                try:
                    w_s, h_s = size.split("x", 1)
                    is_vertical = int(h_s) > int(w_s)
                except Exception:
                    pass
            srt_written = write_srt(
                local_text,
                audio_path,
                lang_dir / "subtitles.srt",
                work_dir=work,
                job_id=work.name,
                scene_id=str(scene_idx),
                dialogue_id=f"loc-{int(scene_idx):02d}-{code}",
                language=code,
                is_short=is_vertical,
            )
            video_out = lang_dir / "video.mp4"
            remux_replace_audio(
                video_src=scene_video,
                audio_src=audio_path,
                dest=video_out,
                subtitle_text=local_text,
                subtitle_file=srt_written,
                lang_code=code,
                size=size,
                pollinations_key=pollinations_key,
                google_api_keys=google_api_keys,
                narration_for_extend=local_text,
                work_dir=work,
                scene_id=str(scene_idx),
                dialogue_id=f"loc-{int(scene_idx):02d}-{code}",
            )
            results["languages"][code] = {
                "ok": video_out.exists(),
                "video": str(video_out),
                "srt": str(lang_dir / "subtitles.srt"),
                "audio": str(audio_path),
            }
            _live_loc(f"Scene {scene_idx + 1}/{code}: burned", dest=str(video_out))
        except Exception as exc:
            logger.warning("localize_scene_clip %s/%s failed: %s", scene_idx, code, exc)
            results["languages"][code] = {"ok": False, "error": str(exc)[:200]}
            results["ok"] = False

    (root / "manifest.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results


def try_compose_from_scene_local(
    *,
    work: Path,
    scene_indexes: List[int],
    lang_code: str,
    dest: Path,
    size: str = "1080x1920",
) -> Optional[Path]:
    """If per-scene localized packs exist for lang, concat them (subtitle-safe)."""
    clips: List[Path] = []
    for idx in scene_indexes:
        p = work / "SCENE_LOCAL" / f"{int(idx):02d}" / lang_code / "video.mp4"
        if not p.exists() or p.stat().st_size < 2000:
            return None
        clips.append(p)
    if not clips:
        return None
    try:
        from pipeline.scene_builder import concat_av_clips

        dest.parent.mkdir(parents=True, exist_ok=True)
        return concat_av_clips(clips, dest, size)
    except Exception as exc:
        logger.warning("scene-local concat failed for %s: %s", lang_code, exc)
        return None


def localize_master_clip(
    *,
    master_video: Path,
    english_narration: str,
    out_dir: Path,
    google_api_keys: List[str],
    slug: str = "clip",
    size: str = "1080x1920",
    languages: Optional[List[str]] = None,
    translations: Optional[Dict[str, str]] = None,
    english_audio: Optional[Path] = None,
    image_fallback_work: Optional[Path] = None,
    pollinations_key: str = "",
    work_for_scene_local: Optional[Path] = None,
    scene_indexes: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Produce language folders under out_dir.
    Prefer concatenating per-scene SCENE_LOCAL packs when complete.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    en_text = (english_narration or "").strip()
    if not en_text:
        raise RuntimeError("english_narration required")
    if not master_video.exists():
        raise RuntimeError(f"master video missing: {master_video}")

    if work_for_scene_local and scene_indexes:
        packed: Dict[str, Any] = {
            "slug": slug,
            "source_lang": SOURCE_LANG,
            "languages": {},
            "method": "scene_local_concat",
        }
        targets = dedupe_language_codes(languages or list(TARGET_LANG_CODES))
        all_ok = True
        for code in targets:
            folder = out_dir / folder_for_lang(code)
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / "video.mp4"
            built = try_compose_from_scene_local(
                work=work_for_scene_local,
                scene_indexes=scene_indexes,
                lang_code=code,
                dest=dest,
                size=size,
            )
            if built and built.exists():
                # Assemble narration/srt provenance beside the composed video
                narr_parts: List[str] = []
                for idx in scene_indexes:
                    np = work_for_scene_local / "SCENE_LOCAL" / f"{int(idx):02d}" / code / "narration.txt"
                    if np.is_file():
                        narr_parts.append(np.read_text(encoding="utf-8").strip())
                narr_path = folder / "narration.txt"
                if narr_parts:
                    narr_path.write_text(" ".join(narr_parts), encoding="utf-8")
                # Prefer first scene audio as package marker; full mux already embeds audio
                aud = work_for_scene_local / "SCENE_LOCAL" / f"{int(scene_indexes[0]):02d}" / code / "narration.m4a"
                packed["languages"][code] = {
                    "ok": True,
                    "video": str(built),
                    "narration": str(narr_path) if narr_path.is_file() else "",
                    "audio": str(aud) if aud.is_file() else "",
                    "via": "scene_local",
                }
                _live_loc(f"Language {code}: composed from scene packs", dest=str(built))
            else:
                all_ok = False
                break
        if all_ok and packed["languages"]:
            en_dir = out_dir / folder_for_lang(SOURCE_LANG)
            en_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(master_video, en_dir / "video.mp4")
            packed["languages"][SOURCE_LANG] = {
                "ok": True,
                "video": str(en_dir / "video.mp4"),
            }
            (out_dir / "LOCALIZE_METHOD.json").write_text(
                json.dumps(packed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return packed

    return _localize_master_clip_body(
        master_video=master_video,
        english_narration=en_text,
        out_dir=out_dir,
        google_api_keys=google_api_keys,
        slug=slug,
        size=size,
        languages=languages,
        translations=translations,
        english_audio=english_audio,
        image_fallback_work=image_fallback_work,
        pollinations_key=pollinations_key,
    )


def _localize_master_clip_body(
    *,
    master_video: Path,
    english_narration: str,
    out_dir: Path,
    google_api_keys: List[str],
    slug: str = "clip",
    size: str = "1080x1920",
    languages: Optional[List[str]] = None,
    translations: Optional[Dict[str, str]] = None,
    english_audio: Optional[Path] = None,
    image_fallback_work: Optional[Path] = None,
    pollinations_key: str = "",
) -> Dict[str, Any]:
    """
    Produce language folders under out_dir:
      English/  (copy/link master)
      Bangla/, Hindi/, ... with video.mp4 + narration.* + subtitles.srt + meta.json

    When image_fallback_work is set (or _fallback_i2v exists), long localized TTS
    grows the picture with same-seed Ken Burns beats instead of setpts stretch.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    en_text = (english_narration or "").strip()
    if not en_text:
        raise RuntimeError("english_narration required")
    if not master_video.exists():
        raise RuntimeError(f"master video missing: {master_video}")

    langs = dedupe_language_codes(languages or list(TARGET_LANG_CODES), exclude_source=False)
    # Keep EN package for packaging, then process unique non-source targets
    target_langs = [c for c in langs if c != SOURCE_LANG]
    results: Dict[str, Any] = {"slug": slug, "source_lang": SOURCE_LANG, "languages": {}}
    work = Path(master_video).resolve().parent
    _live_loc(
        f"Localize start — {len(target_langs)} languages from English master",
        dest=str(out_dir),
        force_new=True,
    )

    fb_work = Path(image_fallback_work) if image_fallback_work else None
    if fb_work is None and (master_video.parent / "_fallback_i2v").exists():
        fb_work = master_video.parent
    image_mode = fb_work is not None

    # Ensure English package — reuse audio when provided
    en_dir = out_dir / folder_for_lang("en")
    en_dir.mkdir(parents=True, exist_ok=True)
    en_video = en_dir / "video.mp4"
    if str(master_video.resolve()) != str(en_video.resolve()):
        import shutil

        shutil.copy2(master_video, en_video)
    (en_dir / "narration.txt").write_text(en_text, encoding="utf-8")
    en_audio = en_dir / "narration.m4a"
    if english_audio and Path(english_audio).exists():
        import shutil

        shutil.copy2(english_audio, en_audio)
    else:
        from pipeline.tts_reuse import reuse_or_synthesize_tts

        en_audio = reuse_or_synthesize_tts(
            en_text,
            en_dir / "narration.m4a",
            language_hint="en",
            google_api_keys=google_api_keys,
            extra_candidates=[
                master_video.parent / "narration_en_tts.m4a",
                master_video.parent / "scene_00_agent_tts_raw.m4a",
            ],
            work_dir=master_video.parent,
            job_id=master_video.parent.name,
            scene_id=0,
            dialogue_id=f"master-en-{slug}",
        )
    # English final package should include the 1s post-dialogue hold (once).
    from pipeline.av_quality_gates import (
        detect_av_length_match,
        detect_dialogue_cutoff,
        detect_subtitle_coverage,
        detect_tail_hold,
    )
    from pipeline.dialogue_sync import DIALOGUE_TAIL_PAD_SEC, pad_av_tail

    en_final = en_dir / "video.mp4"
    cutoff = detect_dialogue_cutoff(en_video, narration_text=en_text, lang="en")
    # If end still has speech energy, pad would hide cutoff — still pad for package
    # but mark gate fail so callers can regenerate master.
    if float(cutoff.get("end_rms") or 1.0) >= 0.008 or not detect_tail_hold(en_video).get("passed", True):
        pad_av_tail(en_video, en_final, DIALOGUE_TAIL_PAD_SEC)
    elif str(en_video.resolve()) != str(en_final.resolve()):
        import shutil

        shutil.copy2(en_video, en_final)
    write_srt(
        en_text,
        en_audio,
        en_dir / "subtitles.srt",
        work_dir=master_video.parent,
        job_id=master_video.parent.name,
        scene_id="0",
        dialogue_id=f"master-en-{slug}",
        language="en",
    )
    en_gates = [
        cutoff,
        detect_tail_hold(en_final),
        detect_av_length_match(en_final),  # compare embedded A/V after pad
        detect_subtitle_coverage(en_dir / "subtitles.srt", en_audio),
    ]
    en_ok = all(g.get("passed", True) for g in en_gates)
    if not en_ok:
        # Do NOT soft-ship English masters with dialogue_cutoff / other critical fails
        logger.error(
            "English localize package failed gates: %s",
            [g.get("issues") for g in en_gates if not g.get("passed", True)],
        )
    (en_dir / "meta.json").write_text(
        json.dumps(
            {
                "lang": "en",
                "role": "source_master",
                "video": en_final.name,
                "audio": Path(en_audio).name,
                "quality_gates": en_gates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    results["languages"]["en"] = {
        "ok": bool(en_ok),
        "video": str(en_final),
        "audio": str(en_audio),
        "quality_gates": en_gates,
    }
    for code in target_langs:
        code = code.lower().strip()
        if code == "en":
            continue
        # Free-tier friendly pause between language TTS (mission sets 300–600s)
        try:
            import os
            import time as _time

            pause = float(os.environ.get("AMP_TTS_LANG_PAUSE_SEC", "0") or 0)
            if pause > 0:
                logger.info(
                    "TTS lang pause %.0fs before %s (AMP_TTS_LANG_PAUSE_SEC)",
                    pause,
                    code,
                )
                _time.sleep(pause)
        except Exception:
            pass
        lang_dir = out_dir / folder_for_lang(code)
        lang_dir.mkdir(parents=True, exist_ok=True)
        try:
            _live_loc(f"Language {code}: translate EN → {code}", dest=str(lang_dir), force_new=True)
            # Translate
            if translations and code in translations and translations[code].strip():
                local_text = translations[code].strip()
                from pipeline.localization_consistency.drift import detect_english_as_localized

                bad = detect_english_as_localized(en_text, local_text, code)
                if bad:
                    raise RuntimeError(f"localization_rejected:{bad}")
            else:
                local_text = translate_text(
                    en_text,
                    target_lang=code,
                    source_lang="en",
                    google_api_keys=google_api_keys,
                    work_dir=work,
                    job_id=work.name if work else "",
                    scene_id="master",
                    dialogue_id=f"master-{code}",
                    localized_validation=True,
                )
            (lang_dir / "narration.txt").write_text(local_text, encoding="utf-8")
            _live_loc(
                f"Language {code}: translation received ({len(local_text)} chars) → narration.txt",
                response=local_text[:180],
                dest=str(lang_dir / "narration.txt"),
                force_new=True,
            )

            # TTS — reuse existing lang audio when text matches; else Edge/Google
            from pipeline.tts_reuse import reuse_or_synthesize_tts

            contract = tts_contract(code)
            voices = locked_voice_chain(code)
            audio_path = None
            last_tts_err = None
            try:
                _live_loc(f"Language {code}: TTS synthesize / reuse", dest=str(lang_dir / "narration.m4a"))
                assert_master_localized_voice_identity(language=code, voice_name=MASTER_VOICE_NAME)
                audio_path = reuse_or_synthesize_tts(
                    local_text,
                    lang_dir / "narration.m4a",
                    language_hint=code,
                    google_api_keys=google_api_keys,
                    voice_name=MASTER_VOICE_NAME,
                    extra_candidates=[lang_dir / "narration.mp3"],
                    work_dir=out_dir.parent,
                    job_id=out_dir.parent.name,
                    scene_id=0,
                    dialogue_id=f"master-{slug}-{code}",
                )
            except Exception as exc:
                last_tts_err = exc
                logger.warning("TTS reuse/synth %s failed: %s", code, str(exc)[:120])
                for voice in voices:
                    try:
                        audio_path = synthesize_narration(
                            local_text,
                            lang_dir / "narration",
                            google_api_keys=google_api_keys,
                            voice_name=str(voice),
                            language_hint=code,
                            idempotency_work_dir=out_dir.parent,
                            idempotency_job_id=out_dir.parent.name,
                            idempotency_scene_id=0,
                            idempotency_dialogue_id=f"master-{slug}-{code}",
                        )
                        break
                    except Exception as exc2:
                        last_tts_err = exc2
            if audio_path is None:
                raise RuntimeError(f"TTS failed for {code}: {last_tts_err}")

            # Issue-2 gate: if TTS much longer than picture, condense + re-TTS once
            from pipeline.av_quality_gates import (
                detect_av_length_match,
                detect_localization_text,
                detect_localize_ratio,
                detect_subtitle_coverage,
                detect_tail_hold,
            )

            text_gate = detect_localization_text(
                lang_code=code, narration=local_text, english_narration=en_text
            )
            if not text_gate.get("passed", True):
                # One repair: force re-translate
                local_text = translate_text(
                    en_text,
                    target_lang=code,
                    source_lang="en",
                    google_api_keys=google_api_keys,
                    work_dir=work,
                    job_id=work.name if work else "",
                    scene_id="master",
                    dialogue_id=f"master-{code}",
                    localized_validation=True,
                )
                (lang_dir / "narration.txt").write_text(local_text, encoding="utf-8")
                text_gate = detect_localization_text(
                    lang_code=code, narration=local_text, english_narration=en_text
                )

            ratio_gate = detect_localize_ratio(master_video, audio_path, max_stretch=1.18)
            # Image mode: keep long TTS — remux will same-seed extend (do NOT condense/re-TTS)
            if (not image_mode) and (not ratio_gate.get("passed", True)):
                v_sec = max(1.0, ffprobe_duration(master_video))
                local_text = fit_narration_for_agnes(
                    local_text,
                    google_api_keys=google_api_keys,
                    target_seconds=max(5.0, v_sec * 0.92),
                    max_seconds=max(6.0, v_sec * 1.05),
                )
                (lang_dir / "narration.txt").write_text(local_text, encoding="utf-8")
                assert_master_localized_voice_identity(language=code, voice_name=MASTER_VOICE_NAME)
                audio_path = reuse_or_synthesize_tts(
                    local_text,
                    lang_dir / "narration.m4a",
                    language_hint=code,
                    google_api_keys=google_api_keys,
                    voice_name=MASTER_VOICE_NAME,
                    work_dir=out_dir.parent,
                    job_id=out_dir.parent.name,
                    scene_id=0,
                    dialogue_id=f"master-{slug}-{code}-recondense",
                )
                ratio_gate = detect_localize_ratio(master_video, audio_path, max_stretch=1.18)
                text_gate = detect_localization_text(
                    lang_code=code, narration=local_text, english_narration=en_text
                )
            elif image_mode and not ratio_gate.get("passed", True):
                logger.info(
                    "Localize %s image-mode: TTS longer — will same-seed extend (no condense)",
                    code,
                )

            write_srt_path = write_srt(
                local_text,
                audio_path,
                lang_dir / "subtitles.srt",
                work_dir=out_dir.parent,
                job_id=out_dir.parent.name,
                scene_id="0",
                dialogue_id=f"master-{slug}-{code}",
                language=code,
            )
            video_out = lang_dir / "video.mp4"
            remux_replace_audio(
                video_src=master_video,
                audio_src=audio_path,
                dest=video_out,
                subtitle_text=local_text,
                subtitle_file=write_srt_path,
                lang_code=code,
                size=size,
                image_fallback_work=fb_work,
                pollinations_key=pollinations_key,
                google_api_keys=google_api_keys,
                narration_for_extend=local_text,
                work_dir=out_dir.parent,
                scene_id="0",
                dialogue_id=f"master-{slug}-{code}",
            )
            hold_gate = detect_tail_hold(video_out)
            if not hold_gate.get("passed", True):
                pad_av_tail(video_out, video_out, DIALOGUE_TAIL_PAD_SEC)
                hold_gate = detect_tail_hold(video_out)
            sub_gate = detect_subtitle_coverage(lang_dir / "subtitles.srt", audio_path)
            av_gate = detect_av_length_match(video_out)
            gates = [text_gate, ratio_gate, hold_gate, sub_gate, av_gate]
            (lang_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "lang": code,
                        "role": "localized",
                        "localized_from": "en",
                        "video": video_out.name,
                        "audio": Path(audio_path).name,
                        "picture_source": "english_master_visual",
                        "quality_gates": gates,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            ok = all(g.get("passed", True) for g in gates)
            results["languages"][code] = {
                "ok": ok,
                "video": str(video_out),
                "audio": str(audio_path),
                "chars": len(local_text),
                "quality_gates": gates,
            }
            if ok:
                logger.info("Localized %s → %s OK", slug, code)
                _live_loc(f"Language {code}: package OK → {video_out.name}", dest=str(video_out), force_new=True)
            else:
                logger.warning(
                    "Localized %s → %s with gate warnings: %s",
                    slug,
                    code,
                    [g.get("issues") for g in gates if not g.get("passed", True)],
                )
                _live_loc(
                    f"Language {code}: package with gate warnings → {video_out.name}",
                    dest=str(video_out),
                    level="warn",
                    force_new=True,
                )
        except Exception as exc:
            logger.error("Localization failed %s/%s: %s", slug, code, exc)
            _live_loc(f"Language {code}: FAILED — {exc}", level="error", force_new=True)
            results["languages"][code] = {"ok": False, "error": str(exc)}

    (out_dir / "LOCALIZE_MANIFEST.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _live_loc("Localize manifest written", dest=str(out_dir / "LOCALIZE_MANIFEST.json"), force_new=True)
    # Asset-decoupled archive (audio / silent video / metadata → optional Drive)
    try:
        import os

        from app.config import amp_skip_active

        if not amp_skip_active("AMP_SKIP_ASSET_ARCHIVE"):
            from pipeline.asset_archive import archive_localized_tree

            archived = archive_localized_tree(
                out_dir,
                base_id=str(slug or out_dir.name),
                channel_id=0,
                niche="",
                upload_drive=os.environ.get("AMP_DRIVE_UPLOAD", "1").strip() != "0",
            )
            results["asset_archive"] = [
                {"asset_id": a.get("asset_id"), "ok": a.get("ok"), "migration_ready": a.get("migration_ready")}
                for a in archived
            ]
    except Exception as exc:
        logger.warning("asset archive after localize skipped: %s", exc)
    return results
