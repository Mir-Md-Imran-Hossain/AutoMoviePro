"""Stage 5b — Per-language shot fit (setpts) + subtitle burn + final assemble."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.compose import ffmpeg_bin, ffprobe_duration
from pipeline.custom_pipeline.package_layout import (
    LANG_AUDIO_CODES,
    CODE_TO_LANG_NAME,
    iso_code_for,
    lang_code_for,
    open_package,
)
from pipeline.output_layout import write_json
from pipeline.subtitle_burn import (
    apply_subtitles_to_vf,
    ass_force_style,
    burn_subtitles_filter,
    font_size_for_canvas,
    margin_v_for_canvas,
    parse_canvas,
    preferred_font,
    wrap_cue_text,
)

logger = logging.getLogger(__name__)


def _format_ass_retention_text(text: str) -> str:
    """Converts HTML/markdown retention tags or auto-highlights focal words for ASS rendering."""
    if not text:
        return ""
    import re
    # If already formatted with <b><font color="...">...</font></b>
    if "<font" in text or "<b>" in text:
        # Convert font color to ASS BGR format (e.g. #FFD700 -> &H00D7FF&)
        def _replace_font(m):
            word = m.group(1)
            return rf"{{\b1\c&H00D7FF&}}{word}{{\b0\c&H00FFFFFF&}}"
        text = re.sub(r'<b><font[^>]*>(.*?)</font></b>', _replace_font, text)
        text = re.sub(r'<b>(.*?)</b>', lambda m: rf"{{\b1\c&H00D7FF&}}{m.group(1)}{{\b0\c&H00FFFFFF&}}", text)
        return text

    # Auto-highlight key retention terms
    trigger_words = {
        "আলোড়ন", "রহস্য", "গোপন", "অবিশ্বাস্য", "স্তব্ধ", "চরম", "বিস্ময়কর",
        "সত্য", "ভয়ানক", "আবিষ্কার", "বাস্তবতা", "shocking", "mystery", "secret",
        "baffled", "unbelievable", "truth", "breakthrough", "critical"
    }
    words = text.split()
    for i, w in enumerate(words):
        clean = re.sub(r'[^\w]', '', w).lower()
        if clean in trigger_words or (len(clean) >= 6 and i == 0):
            # Wrap in bold and gold accent color (&H00D7FF&)
            prefix = "" if w[0].isalnum() else w[0]
            suffix = "" if w[-1].isalnum() else w[-1]
            core = w.strip(".,!?:;\"'()[]{}")
            words[i] = f"{prefix}{{\\b1\\c&H00D7FF&}}{core}{{\\b0\\c&H00FFFFFF&}}{suffix}"
            break
    return " ".join(words)


def _write_simple_ass(
    cues: List[Dict[str, Any]],
    ass_path: Path,
    *,
    size: str = "1080x1920",
    lang: str = "en",
) -> Path:
    w, h = parse_canvas(size)
    is_short = (h > w)
    fs = font_size_for_canvas(w, h, is_short=is_short)
    mv = margin_v_for_canvas(h, is_short=is_short)
    font = preferred_font(lang)

    if is_short:
        # High-impact short-form styling: Bold yellow / crisp white, thick outline (4.2), platform safe margins
        style_line = (
            f"Style: Default,{font},{fs},&H0000FFFF,&H000000FF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,4.2,2.0,2,60,80,{mv},1"
        )
    else:
        # Long-form widescreen styling: Bold white, dark outline (3.2), clean documentary margins
        style_line = (
            f"Style: Default,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,3.2,1.5,2,48,48,{mv},1"
        )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\n"
        f"PlayResY: {h}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def _ts(sec: float) -> str:
        sec = max(0.0, float(sec))
        h0 = int(sec // 3600)
        m0 = int((sec % 3600) // 60)
        s0 = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h0}:{m0:02d}:{s0:02d}.{cs:02d}"

    events = []
    max_c_len = 22 if is_short else 42
    for cue in cues:
        raw = str(cue.get("text") or "")
        highlighted = _format_ass_retention_text(raw)
        text = wrap_cue_text(highlighted, max_chars_per_line=max_c_len)
        text = text.replace("\n", r"\N")
        events.append(
            f"Dialogue: 0,{_ts(cue.get('start') or 0)},{_ts(cue.get('end') or 1)},Default,,0,0,0,,{text}"
        )
    ass_path = Path(ass_path)
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _run(cmd: List[str]) -> None:
    r = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "ffmpeg failed")
        # FFmpeg prints a long banner first — keep the useful tail
        tail = err[-900:] if len(err) > 900 else err
        raise RuntimeError(tail)


def _canvas(aspect: str) -> str:
    if str(aspect).strip() in ("16:9", "landscape"):
        return "1920x1080"
    return "1080x1920"


def _load_voice_scenes(paths, code: str) -> List[Dict[str, Any]]:
    file_dir = paths.file_dir
    candidates = [
        file_dir / f"localized_voice_{code}.json",
        *sorted(file_dir.glob(f"Voice_*_{code}_*.json")),
    ]
    if code == "BN":
        candidates.insert(0, file_dir / "topic_script.json")
        candidates.extend(sorted(file_dir.glob("Script_*.json")))
    for p in candidates:
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        scenes = data.get("voice_scenes") or data.get("script_scenes") or []
        return [s for s in scenes if isinstance(s, dict)]
    return []


def _subtitle_for_shot(scenes: List[Dict[str, Any]], shot_number: int) -> str:
    for sc in scenes:
        try:
            n = int(sc.get("shot_number") or 0)
        except (TypeError, ValueError):
            continue
        if n == shot_number:
            return str(sc.get("subtitle_text") or sc.get("voiceover_script") or "").strip()
    return ""


def _audio_for_shot(paths, code: str, shot_number: int) -> Optional[Path]:
    audio_dir = paths.audio_lang(code)
    for name in (f"S{shot_number:02d}_{code}.m4a", f"S{shot_number:02d}_{code}.wav"):
        p = audio_dir / name
        if p.is_file():
            return p
    return None


def _phrase_cues(
    subtitle_text: str,
    audio_sec: float,
    lead_in: float = 0.0,
    is_short: bool = True,
) -> List[Dict[str, Any]]:
    """Split narration into phrase-level ASS cues synchronized with speech cadence across the shot duration."""
    text = " ".join(str(subtitle_text or "").split()).strip()
    if not text:
        return []
    import re

    # 1. Split on natural clause / sentence punctuation (preserve punctuation attached to word)
    raw_clauses = [p.strip() for p in re.split(r"(?<=[।.!?,;:\u2014\u2013\-])\s+", text) if p.strip()]
    if not raw_clauses:
        raw_clauses = [text]

    # Bounds for speech-synchronized chunking:
    # Short form (9:16 vertical): 2 to 4 words per cue (~0.8s - 1.6s) for rapid mobile readability
    # Long form (16:9 horizontal): 3 to 6 words per cue (~1.5s - 2.8s) for widescreen cinematic pacing
    max_words = 4 if is_short else 6

    parts: List[str] = []
    for clause in raw_clauses:
        words = clause.split()
        if len(words) <= max_words:
            parts.append(clause)
        else:
            # Intelligently distribute words into balanced sub-phrases
            n = len(words)
            k = (n + max_words - 1) // max_words
            chunk_size = n // k
            remainder = n % k
            idx = 0
            for i in range(k):
                take = chunk_size + (1 if i < remainder else 0)
                parts.append(" ".join(words[idx : idx + take]))
                idx += take

    offset = max(0.0, float(lead_in))
    total_end = audio_sec + offset
    if not parts:
        return [{"start": round(offset, 3), "end": round(max(offset + 0.4, total_end - 0.02), 3), "text": text}]

    # 2. Timing calculation weighted by word length and punctuation pauses
    # Words with more syllables/characters take more time to pronounce.
    # Punctuation pauses (। . ! ?) take an extra ~0.15s - 0.25s pause in natural speech.
    def _chunk_weight(chunk: str) -> float:
        w_list = chunk.split()
        char_weight = sum(max(2, len(w)) for w in w_list)
        last_char = chunk[-1] if chunk else ""
        pause_bonus = 3.5 if last_char in "।.!?" else (1.8 if last_char in ",;:—-" else 0.0)
        return float(char_weight + pause_bonus)

    weights = [_chunk_weight(p) for p in parts]
    total_w = float(sum(weights)) or 1.0

    cues: List[Dict[str, Any]] = []
    t = offset
    for i, (part, w) in enumerate(zip(parts, weights)):
        # Proportional duration from available audio_sec
        dur = max(0.35, audio_sec * (w / total_w))
        if i == len(parts) - 1:
            end = round(max(t + 0.25, total_end - 0.02), 3)
        else:
            end = round(min(total_end - 0.02, t + dur), 3)
        cues.append({"start": round(t, 3), "end": end, "text": part})
        t = end

    return cues


def fit_shot_for_language(
    *,
    master_video: Path,
    audio_path: Path,
    subtitle_text: str,
    out_path: Path,
    lang_code: str,
    aspect: str = "9:16",
    shot_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Fit master clip to language audio: stretch/slow or pad, mux audio, burn subtitle.

    Strategy:
      - If shot 1: add 250ms lead-in padding to avoid player/decoder truncation of the first words
      - If audio ≈ video duration → mild setpts
      - If audio shorter → speed up (setpts < 1) within 0.70–1.0
      - If audio longer → slow down up to 1.35×, then tpad clone for remainder
        (avoids extreme slow-mo looking broken)
    """
    if not master_video.is_file():
        raise FileNotFoundError(master_video)
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vdur = float(ffprobe_duration(master_video) or 0.0)
    adur = float(ffprobe_duration(audio_path) or 0.0)
    if adur <= 0.05:
        raise RuntimeError(f"bad audio duration audio={adur}")

    # Determine shot number for lead-in padding (shot 1 gets 250ms buffer)
    if shot_number is not None:
        shot_num = int(shot_number)
    else:
        try:
            shot_num = int("".join(c for c in master_video.stem if c.isdigit()) or 1)
        except Exception:
            shot_num = 1

    is_shot1 = (shot_num == 1)
    lead_in = 0.25 if is_shot1 else 0.0
    adur_total = adur + lead_in

    size = _canvas(aspect)
    w, h = parse_canvas(size)
    is_short = ("9:16" in str(aspect) or h > w)
    iso = iso_code_for(lang_code)

    import tempfile
    tmp_ass_dir = Path(tempfile.mkdtemp(prefix="amp_ass_"))
    ass_path = tmp_ass_dir / f"shot_{iso}.ass"

    is_still = master_video.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp') or vdur <= 0.05
    if is_still:
        # Still Image: Apply smooth dynamic Ken Burns (zoom-in / slow-pan / subtle-parallax)
        # Never leave any static frame!
        from pipeline.rendering_integrity.filtergraph import build_cinematic_motion_filter

        presets = ["dynamic_zoom_in", "slow_pan", "subtle_parallax"]
        preset = presets[(shot_num - 1) % len(presets)]

        motion_vf = build_cinematic_motion_filter(w=w, h=h, duration=adur_total, preset=preset)
        cues = _phrase_cues(subtitle_text, adur, lead_in=lead_in, is_short=is_short) if subtitle_text else []
        if cues:
            vf = apply_subtitles_to_vf([motion_vf], cues, size=size, lang=iso, is_short=is_short)
        else:
            vf = motion_vf
        pts = 1.0
        pad_sec = 0.0
    else:
        ratio = adur_total / vdur
        pad_sec = 0.0
        if ratio <= 1.35:
            pts = max(0.70, min(1.35, ratio))
        else:
            pts = 1.35
            pad_sec = max(0.0, adur_total - (vdur * pts))

        vf_parts = [f"setpts={pts:.6f}*PTS"]
        if pad_sec > 0.05:
            vf_parts.append(f"tpad=stop_mode=clone:stop_duration={pad_sec:.3f}")
        cues = _phrase_cues(subtitle_text, adur, lead_in=lead_in, is_short=is_short) if subtitle_text else []
        vf_parts.extend(["fps=25", "format=yuv420p"])
        if cues:
            vf = apply_subtitles_to_vf(vf_parts, cues, size=size, lang=iso, is_short=is_short)
        else:
            vf = ",".join(vf_parts)

    ff = ffmpeg_bin()
    # CRITICAL: map video from master + audio ONLY from TTS input.
    # Without -map, Agnes English audio on input 0 bleeds under Bangla/etc.
    af_filter = (
        f"adelay=250:all=1,atrim=0:{adur_total:.3f},asetpts=PTS-STARTPTS"
        if is_shot1
        else f"atrim=0:{adur:.3f},asetpts=PTS-STARTPTS"
    )
    cmd = [
        ff,
        "-y",
        "-i",
        str(master_video),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        vf,
        "-af",
        af_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        f"{adur_total:.3f}",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    try:
        _run(cmd)
    finally:
        import shutil

        shutil.rmtree(tmp_ass_dir, ignore_errors=True)

    return {
        "ok": out_path.is_file() and out_path.stat().st_size > 5000,
        "path": str(out_path),
        "pts_factor": pts,
        "pad_sec": round(pad_sec, 3),
        "video_in_sec": vdur,
        "audio_sec": adur,
        "lead_in_sec": lead_in,
        "total_sec": round(adur_total, 3),
        "subtitle": bool(subtitle_text),
        "subtitle_cues": len(cues),
    }


def compose_language_shots(
    package_root: Path | str,
    language: str,
    *,
    aspect: str = "9:16",
) -> Dict[str, Any]:
    """Build per-language fitted+subtitled shot clips under Video/Video Clips/{CODE}/."""
    pkg = Path(package_root)
    paths = open_package(pkg)
    code = lang_code_for(language)
    voice_scenes = _load_voice_scenes(paths, code)
    master_dir = paths.video_clips
    lang_clip_dir = master_dir / code
    lang_clip_dir.mkdir(parents=True, exist_ok=True)

    # Discover masters
    masters = sorted(master_dir.glob("S*.mp4"))
    masters = [p for p in masters if p.parent == master_dir]
    results: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}

    for master in masters:
        # S01.mp4
        stem = master.stem  # S01
        try:
            n = int(stem.lstrip("S").split("_")[0])
        except ValueError:
            continue
        audio = _audio_for_shot(paths, code, n)
        if not audio:
            errors[stem] = "missing audio"
            continue
        sub = _subtitle_for_shot(voice_scenes, n)
        out = lang_clip_dir / f"{stem}_{code}.mp4"
        if out.is_file() and out.stat().st_size > 5000:
            logger.info("Compose skip existing %s", out.name)
            results.append(
                {
                    "shot": stem,
                    "ok": True,
                    "path": str(out),
                    "resumed": True,
                    "subtitle": bool(sub),
                }
            )
            continue
        try:
            info = fit_shot_for_language(
                master_video=master,
                audio_path=audio,
                subtitle_text=sub,
                out_path=out,
                lang_code=code,
                aspect=aspect,
                shot_number=n,
            )
            results.append({"shot": stem, **info})
            if not info.get("ok"):
                errors[stem] = "ffmpeg output missing"
        except Exception as exc:
            logger.exception("compose shot %s lang=%s", stem, code)
            errors[stem] = str(exc)
            results.append({"shot": stem, "ok": False, "error": str(exc)})

    summary = {
        "ok": not errors,
        "language": CODE_TO_LANG_NAME.get(code, language),
        "lang_code": code,
        "clip_dir": str(lang_clip_dir),
        "shots": results,
        "errors": errors,
        "success_count": sum(1 for r in results if r.get("ok")),
    }
    write_json(paths.file_dir / f"compose_manifest_{code}.json", summary)
    return summary


def assemble_final_video(
    package_root: Path | str,
    language: str,
) -> Dict[str, Any]:
    """Concat language shot clips → Video/Final Video/{CODE}/final_{CODE}.mp4"""
    pkg = Path(package_root)
    paths = open_package(pkg)
    code = lang_code_for(language)
    clip_dir = paths.video_clips / code
    finals = paths.final_video_lang(code)
    clips = sorted(clip_dir.glob(f"S*_{code}.mp4")) if clip_dir.is_dir() else []
    if not clips:
        return {"ok": False, "error": f"no clips in {clip_dir}", "lang_code": code}

    # Detect canvas from first clip / plan
    aspect = "9:16"
    plan_path = paths.file_dir / "visual_render_plan.json"
    if plan_path.is_file():
        try:
            meta = json.loads(plan_path.read_text(encoding="utf-8")).get("production_metadata") or {}
            aspect = str(meta.get("aspect_ratio") or aspect)
        except Exception:
            pass
    size = _canvas(aspect)
    w, h = (1080, 1920) if "1080x1920" in size else (1920, 1080)

    out = finals / f"final_{code}.mp4"
    ff = ffmpeg_bin()
    import shutil
    import tempfile

    # Normalize every clip to identical video/audio params in an ASCII temp dir,
    # then concat demuxer (copy). This survives emoji paths + Agnes/KenBurns mismatch.
    tmp = Path(tempfile.mkdtemp(prefix=f"amp_concat_{code}_"))
    try:
        mapped: List[Path] = []
        for i, c in enumerate(clips):
            dest = tmp / f"s{i:02d}.mp4"
            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,format=yuv420p"
            )
            norm_cmd = [
                ff, "-y", "-i", str(c),
                "-vf", vf,
                "-af", "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(dest),
            ]
            _run(norm_cmd)
            mapped.append(dest)
        if len(mapped) == 1:
            shutil.copy2(mapped[0], out)
        else:
            list_file = tmp / "list.txt"
            list_file.write_text(
                "\n".join(f"file '{m.as_posix()}'" for m in mapped) + "\n",
                encoding="ascii",
                errors="strict",
            )
            concat_cmd = [
                ff, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", "-movflags", "+faststart", str(out),
            ]
            try:
                _run(concat_cmd)
            except RuntimeError:
                # Last resort: re-encode concat
                concat_cmd = [
                    ff, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out),
                ]
                _run(concat_cmd)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = out.is_file() and out.stat().st_size > 10000
    summary = {
        "ok": ok,
        "lang_code": code,
        "path": str(out) if ok else None,
        "shot_count": len(clips),
        "duration_sec": ffprobe_duration(out) if ok else 0,
    }
    write_json(paths.file_dir / f"final_manifest_{code}.json", summary)
    logger.info("Final video %s ok=%s → %s", code, ok, out)
    return summary


def compose_and_assemble_all(
    package_root: Path | str,
    *,
    languages: Optional[List[str]] = None,
    aspect: str = "9:16",
    include_bangla: bool = True,
) -> Dict[str, Any]:
    pkg = Path(package_root)
    paths = open_package(pkg)
    # Detect aspect from plan if present
    plan_path = paths.file_dir / "visual_render_plan.json"
    if plan_path.is_file():
        try:
            meta = (json.loads(plan_path.read_text(encoding="utf-8")).get("production_metadata") or {})
            aspect = str(meta.get("aspect_ratio") or aspect)
        except Exception:
            pass

    if languages:
        langs = list(languages)
    else:
        langs = []
        for code in LANG_AUDIO_CODES:
            # only languages that have audio
            if any((paths.audio / code).glob("S*.m4a")):
                langs.append(CODE_TO_LANG_NAME.get(code, code))
        if include_bangla and "Bangla" not in langs and any((paths.audio / "BN").glob("S*.m4a")):
            langs.insert(0, "Bangla")

    composed: Dict[str, Any] = {}
    finals: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for lang in langs:
        try:
            composed[lang] = compose_language_shots(pkg, lang, aspect=aspect)
            if not composed[lang].get("ok"):
                errors[f"compose_{lang}"] = str(composed[lang].get("errors"))
            finals[lang] = assemble_final_video(pkg, lang)
            if not finals[lang].get("ok"):
                errors[f"final_{lang}"] = str(finals[lang].get("error"))
        except Exception as exc:
            logger.exception("compose/assemble failed %s", lang)
            errors[lang] = str(exc)

    summary = {
        "ok": False,  # filled below — never soft-ok on any()
        "languages": langs,
        "composed": composed,
        "finals": finals,
        "errors": errors,
        "package_root": str(pkg),
        "partial": False,
    }
    finals_ok = [l for l in langs if isinstance(finals.get(l), dict) and finals[l].get("ok")]
    from pipeline.custom_pipeline.honest_status import honest_completion

    status = honest_completion(success_count=len(finals_ok), expected_count=len(langs))
    summary["ok"] = status["ok"]
    summary["partial"] = status["partial"]
    summary["failed"] = status["failed"]
    summary["finals_ok"] = finals_ok
    summary["missing_languages"] = [l for l in langs if l not in finals_ok]
    write_json(paths.file_dir / "media_compose_manifest.json", summary)
    return summary
