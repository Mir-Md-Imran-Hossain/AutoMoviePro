"""Custom pipeline — Stage 4: routed TTS → Audio/{EN,HI,...}/

Engine Allocation Matrix (tts_routing):
  - en / hi / ur → always Microsoft Edge-TTS (Jenny / Swara / Uzma) — zero Google cost
  - bn / ta / ml → Google AI Studio dual-key (PRIMARY→SECONDARY at 90%, 429 catch,
                   both dead → Edge Nabanita / Pallavi / Sobhana)
  - Continuous mode preferred: ONE synth call per language → split shots
  - Emotion softened to delivery-only (Gemini path only)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from pipeline.custom_pipeline.localization import (
    SUPPORTED_LANGUAGES,
    load_source_script,
    normalize_language_name,
)
from pipeline.custom_pipeline.package_layout import (
    CODE_TO_LANG_NAME,
    iso_code_for,
    lang_code_for,
    open_package,
)
from pipeline.custom_pipeline.tts_client import (
    concat_audio_files,
    get_last_tts_metadata,
    split_audio_by_word_ratios,
    synthesize_continuous_narration,
    synthesize_shot_audio,
)
from pipeline.lang_config import MASTER_VOICE_NAME, resolve_locked_voice, tts_contract
from pipeline.output_layout import write_json

logger = logging.getLogger(__name__)


def _reuse_agnes_native_for_english(
    *,
    paths,
    scenes: List[Dict[str, Any]],
    out_paths: List[Path],
    force: bool,
) -> Dict[str, Any]:
    """EN shots with Agnes native audio → copy, skip Google/Edge TTS for those shots.

    Returns:
      reused_indices, pending_indices, details
    """
    import shutil

    from pipeline.custom_pipeline.master_audio import find_native_audio

    reused: List[int] = []
    pending: List[int] = []
    details: List[Dict[str, Any]] = []
    for i, (sc, out) in enumerate(zip(scenes, out_paths)):
        n = int(sc["shot_number"])
        native = find_native_audio(paths.video_clips, n)
        if native and (force or not _audio_ok(out)):
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(native, out)
                if _audio_ok(out):
                    reused.append(i)
                    details.append(
                        {
                            "shot_number": n,
                            "source": "agnes_native",
                            "audio_path": str(out),
                            "from": str(native),
                        }
                    )
                    logger.info(
                        "EN TTS skip shot S%02d — reused Agnes native audio", n
                    )
                    continue
            except Exception as exc:
                logger.warning("EN native reuse failed S%02d: %s", n, exc)
        elif native and _audio_ok(out) and not force:
            reused.append(i)
            details.append(
                {
                    "shot_number": n,
                    "source": "agnes_native_existing",
                    "audio_path": str(out),
                }
            )
            continue
        pending.append(i)
    return {"reused": reused, "pending": pending, "details": details}


def resolve_voice_payload(
    package_root: Path,
    language: str,
    *,
    source: Optional[Union[str, Path, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    paths = open_package(package_root)
    code = lang_code_for(language)
    candidates = [
        paths.file_dir / f"localized_voice_{code}.json",
        *sorted(paths.file_dir.glob(f"Voice_*_{code}_*.json")),
        *sorted(paths.file_dir.glob(f"Voice_*_{code.lower()}_*.json")),
    ]
    if code == "BN":
        candidates.insert(0, paths.file_dir / "topic_script.json")
        candidates.extend(sorted(paths.file_dir.glob("Script_*.json")))

    for path in candidates:
        if path.is_file() and path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_source_path"] = str(path)
            return data

    if source is not None:
        data = load_source_script(source)
        data["_source_path"] = "inline"
        return data

    raise FileNotFoundError(
        f"No voice JSON for {language} ({code}) under {paths.file_dir}"
    )


def _scenes_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    scenes = payload.get("voice_scenes") or payload.get("script_scenes") or []
    out: List[Dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        text = str(sc.get("voiceover_script") or "").strip()
        if not text:
            continue
        try:
            n = int(sc.get("shot_number") or (i + 1))
        except (TypeError, ValueError):
            n = i + 1
        try:
            dur = float(sc.get("shot_duration_seconds") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        out.append(
            {
                "shot_number": n,
                "voiceover_script": text,
                "emotion_tag": str(sc.get("emotion_tag") or "").strip(),
                "shot_duration_seconds": dur,
            }
        )
    return out


def _script_fingerprint(scenes: Sequence[Dict[str, Any]]) -> str:
    import hashlib

    parts = [
        f"{int(sc.get('shot_number') or 0)}:{sc.get('voiceover_script') or ''}"
        for sc in scenes
    ]
    raw = "\n".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _audio_ok(path: Path, *, min_bytes: int = 1000) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def _resume_fingerprint_matches(audio_dir: Path, code: str, fp: str) -> bool:
    marker = audio_dir / f"tts_resume_{code}.json"
    if not marker.is_file():
        # Legacy artifacts without fingerprint — allow resume once, then stamp
        return True
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        return str(data.get("script_fingerprint") or "") == fp
    except Exception:
        return False


def _write_resume_marker(
    audio_dir: Path,
    code: str,
    *,
    fp: str,
    voice: str,
    mode: str,
) -> None:
    write_json(
        audio_dir / f"tts_resume_{code}.json",
        {
            "script_fingerprint": fp,
            "voice_name": voice,
            "mode": mode,
        },
    )


def _build_resume_summary(
    *,
    lang: str,
    code: str,
    iso: str,
    voice: str,
    scenes: Sequence[Dict[str, Any]],
    shot_paths: Sequence[Path],
    full_path: Path,
    audio_dir: Path,
    paths,
    reason: str,
) -> Dict[str, Any]:
    shot_results = []
    for sc, part in zip(scenes, shot_paths):
        shot_results.append(
            {
                "shot_number": int(sc["shot_number"]),
                "emotion_tag": sc.get("emotion_tag") or "",
                "delivery_mode": "resumed",
                "target_duration_seconds": sc.get("shot_duration_seconds") or 0,
                "audio_path": str(part),
                "voice_name": voice,
                "ok": True,
                "resumed": True,
            }
        )
    summary = {
        "ok": True,
        "resumed": True,
        "resume_reason": reason,
        "language": lang,
        "lang_code": code,
        "iso": iso,
        "mode": "resumed",
        "voice_name": voice,
        "shot_count": len(scenes),
        "success_count": len(shot_results),
        "audio_dir": str(audio_dir),
        "narration_full": str(full_path),
        "shots": shot_results,
        "errors": {},
        "script_fingerprint": _script_fingerprint(scenes),
    }
    write_json(audio_dir / "tts_manifest.json", summary)
    write_json(paths.file_dir / f"tts_manifest_{code}.json", summary)
    _write_resume_marker(
        audio_dir, code, fp=summary["script_fingerprint"], voice=voice, mode="resumed"
    )
    return summary


def synthesize_language_tts(
    package_root: Path | str,
    language: str,
    *,
    source: Optional[Union[str, Path, Dict[str, Any]]] = None,
    voice_name: str = "",
    keep_wav: bool = False,
    mode: str = "continuous",
    force: bool = False,
) -> Dict[str, Any]:
    """Synthesize all shots for one language → Audio/{CODE}/.

    mode:
      - continuous (default): ONE Gemini TTS call for the whole language, then
        split into S01/S02… by word-count ratios. Guarantees same speaker.
      - per_shot: legacy one-call-per-shot (identity-locked prompts; more drift risk).

    Resume (unless force):
      1) full + all shots present + fingerprint match → skip API
      2) full present, shots missing → re-split only (no API)
      3) all shots present, full missing → concat only (no API)
      4) per_shot: skip individual existing shots
    """
    import os

    pkg = Path(package_root)
    paths = open_package(pkg)
    lang = normalize_language_name(language)
    if lang.lower() in ("bangla", "bengali"):
        lang = "Bangla"
    code = lang_code_for(lang)
    iso = iso_code_for(lang)
    payload = resolve_voice_payload(pkg, lang, source=source)
    scenes = _scenes_from_payload(payload)
    if not scenes:
        raise ValueError(f"No voiceover scenes for TTS lang={lang}")

    audio_dir = paths.audio_lang(code)
    contract = tts_contract(iso)
    voice = resolve_locked_voice(
        voice_name or str(contract.get("voice_name") or MASTER_VOICE_NAME),
        language_hint=iso,
    )

    env_mode = (os.environ.get("AMP_TTS_MODE") or "").strip().lower()
    use_mode = (env_mode or mode or "continuous").strip().lower()
    if use_mode not in ("continuous", "per_shot"):
        use_mode = "continuous"

    env_force = str(os.environ.get("AMP_TTS_FORCE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    force = bool(force or env_force)
    fp = _script_fingerprint(scenes)

    shot_results: List[Dict[str, Any]] = []
    audio_parts: List[Path] = []
    errors: Dict[str, str] = {}
    concat: Optional[Path] = None

    out_paths = [audio_dir / f"S{int(sc['shot_number']):02d}_{code}.m4a" for sc in scenes]
    full_path = audio_dir / f"narration_full_{code}.m4a"
    texts = [str(sc["voiceover_script"]) for sc in scenes]
    tags = [str(sc.get("emotion_tag") or "") for sc in scenes]

    native_reuse: Dict[str, Any] = {"reused": [], "pending": list(range(len(scenes))), "details": []}
    if code == "EN":
        native_reuse = _reuse_agnes_native_for_english(
            paths=paths, scenes=scenes, out_paths=out_paths, force=force
        )
        # All Agnes-covered → concat only, zero TTS API cost
        if native_reuse["reused"] and not native_reuse["pending"]:
            concat = concat_audio_files(list(out_paths), full_path)
            _write_resume_marker(
                audio_dir, code, fp=fp, voice="agnes_native", mode="agnes_native"
            )
            summary = {
                "ok": True,
                "language": lang,
                "lang_code": code,
                "iso": iso,
                "voice": "agnes_native",
                "tts_mode": "agnes_native",
                "tts_engine": "AGNES_NATIVE",
                "shot_count": len(scenes),
                "success_count": len(scenes),
                "shots": native_reuse["details"],
                "full_narration": str(concat) if concat else str(full_path),
                "audio_dir": str(audio_dir),
                "script_fingerprint": fp,
                "native_reuse": native_reuse,
            }
            write_json(audio_dir / "tts_manifest.json", summary)
            return summary
        # Partial Agnes → synthesize remaining as per_shot only
        if native_reuse["reused"] and native_reuse["pending"]:
            use_mode = "per_shot"
            logger.info(
                "EN hybrid TTS: %s Agnes-native + %s to synthesize",
                len(native_reuse["reused"]),
                len(native_reuse["pending"]),
            )

    if not force and _resume_fingerprint_matches(audio_dir, code, fp):
        shots_ok = all(_audio_ok(p) for p in out_paths)
        full_ok = _audio_ok(full_path, min_bytes=2000)

        if full_ok and shots_ok:
            logger.info("TTS resume skip lang=%s (%s shots on disk)", lang, len(out_paths))
            return _build_resume_summary(
                lang=lang,
                code=code,
                iso=iso,
                voice=voice,
                scenes=scenes,
                shot_paths=out_paths,
                full_path=full_path,
                audio_dir=audio_dir,
                paths=paths,
                reason="full_and_shots",
            )

        if full_ok and not shots_ok:
            logger.info("TTS resume re-split lang=%s from existing narration_full", lang)
            try:
                from pipeline.custom_pipeline.audio_align import align_and_split_shots

                parts = align_and_split_shots(full_path, texts, out_paths)
            except Exception:
                parts = split_audio_by_word_ratios(full_path, texts, out_paths)
            if parts and all(_audio_ok(Path(p)) for p in parts):
                return _build_resume_summary(
                    lang=lang,
                    code=code,
                    iso=iso,
                    voice=voice,
                    scenes=scenes,
                    shot_paths=[Path(p) for p in parts],
                    full_path=full_path,
                    audio_dir=audio_dir,
                    paths=paths,
                    reason="resplit_from_full",
                )

        if shots_ok and not full_ok:
            logger.info("TTS resume concat lang=%s from existing shot files", lang)
            rebuilt = concat_audio_files(list(out_paths), full_path)
            if rebuilt and _audio_ok(Path(rebuilt), min_bytes=2000):
                return _build_resume_summary(
                    lang=lang,
                    code=code,
                    iso=iso,
                    voice=voice,
                    scenes=scenes,
                    shot_paths=out_paths,
                    full_path=Path(rebuilt),
                    audio_dir=audio_dir,
                    paths=paths,
                    reason="concat_from_shots",
                )

    if use_mode == "continuous":
        try:
            produced_full = synthesize_continuous_narration(
                texts,
                full_path,
                language=lang,
                language_code=iso,
                voice_name=voice,
                emotion_tags=tags,
            )
            try:
                from pipeline.custom_pipeline.audio_align import align_and_split_shots

                parts = align_and_split_shots(produced_full, texts, out_paths)
            except Exception:
                parts = split_audio_by_word_ratios(produced_full, texts, out_paths)
            if not keep_wav:
                for p in [produced_full.with_suffix(".wav"), *out_paths]:
                    w = Path(p).with_suffix(".wav")
                    if w.exists() and Path(p).suffix.lower() == ".m4a":
                        try:
                            w.unlink()
                        except Exception:
                            pass
            concat = Path(produced_full)
            audio_parts = [Path(p) for p in parts]
            for sc, part in zip(scenes, parts):
                shot_results.append(
                    {
                        "shot_number": int(sc["shot_number"]),
                        "emotion_tag": sc.get("emotion_tag") or "",
                        "delivery_mode": "locked_soft",
                        "target_duration_seconds": sc.get("shot_duration_seconds") or 0,
                        "audio_path": str(part),
                        "voice_name": voice,
                        "ok": True,
                    }
                )
            _write_resume_marker(audio_dir, code, fp=fp, voice=voice, mode="continuous")
        except Exception as exc:
            logger.exception("Continuous TTS failed lang=%s — falling back to per_shot", lang)
            errors["continuous"] = str(exc)
            use_mode = "per_shot"

    if use_mode == "per_shot" and not audio_parts:
        shot_results = []
        errors = {k: v for k, v in errors.items() if k != "continuous"} or {}
        for sc, out in zip(scenes, out_paths):
            n = int(sc["shot_number"])
            if not force and _audio_ok(out) and _resume_fingerprint_matches(audio_dir, code, fp):
                audio_parts.append(out)
                shot_results.append(
                    {
                        "shot_number": n,
                        "emotion_tag": sc.get("emotion_tag") or "",
                        "delivery_mode": "resumed",
                        "target_duration_seconds": sc.get("shot_duration_seconds") or 0,
                        "audio_path": str(out),
                        "voice_name": voice,
                        "ok": True,
                        "resumed": True,
                    }
                )
                continue
            try:
                produced = synthesize_shot_audio(
                    sc["voiceover_script"],
                    out,
                    language=lang,
                    language_code=iso,
                    emotion_tag=sc.get("emotion_tag") or "",
                    voice_name=voice,
                    target_duration_sec=float(sc.get("shot_duration_seconds") or 0),
                )
                if not keep_wav:
                    wav = produced.with_suffix(".wav")
                    if produced.suffix.lower() == ".m4a" and wav.exists():
                        try:
                            wav.unlink()
                        except Exception:
                            pass
                audio_parts.append(Path(produced))
                shot_results.append(
                    {
                        "shot_number": n,
                        "emotion_tag": sc.get("emotion_tag") or "",
                        "delivery_mode": "locked_soft",
                        "target_duration_seconds": sc.get("shot_duration_seconds") or 0,
                        "audio_path": str(produced),
                        "voice_name": voice,
                        "ok": True,
                    }
                )
            except Exception as exc:
                logger.exception("TTS failed lang=%s shot=%s", lang, n)
                errors[f"S{n:02d}"] = str(exc)
                shot_results.append(
                    {
                        "shot_number": n,
                        "emotion_tag": sc.get("emotion_tag") or "",
                        "ok": False,
                        "error": str(exc),
                    }
                )
        concat = concat_audio_files(audio_parts, full_path) if audio_parts else None
        if concat and not errors:
            _write_resume_marker(audio_dir, code, fp=fp, voice=voice, mode="per_shot")

    success_count = sum(1 for s in shot_results if s.get("ok"))
    all_shots_ok = success_count >= len(scenes) and len(scenes) > 0
    meta = get_last_tts_metadata(code)
    actual_engine = meta.get("engine") or ("GOOGLE_AI_STUDIO" if code in ("bn", "ta", "ml") else "EDGE_TTS")
    actual_voice = meta.get("voice") or voice
    manifest = {
        "ok": bool(all_shots_ok) and not any(k.startswith("S") for k in errors),
        "partial": (not all_shots_ok) and success_count > 0,
        "language": lang,
        "lang_code": code,
        "iso_code": iso,
        "engine": actual_engine,
        "voice_name": actual_voice,
        "requested_voice": voice,
        "model": meta.get("model") or "",
        "key_slot": meta.get("key_slot") or "",
        "tts_mode": use_mode if audio_parts else "failed",
        "voice_consistency": (
            "single_api_call_split"
            if use_mode == "continuous" and concat
            else "locked_prompt_per_shot"
        ),
        "tts_contract": {
            "english_name": contract.get("english_name"),
            "register": contract.get("register"),
            "pace_hint": contract.get("pace_hint"),
        },
        "source_voice_json": payload.get("_source_path"),
        "audio_dir": str(audio_dir),
        "narration_full": str(concat) if concat else None,
        "shots": shot_results,
        "errors": errors,
        "shot_count": len(scenes),
        "success_count": success_count,
        "script_fingerprint": fp,
        "resumed": False,
    }
    write_json(audio_dir / "tts_manifest.json", manifest)
    write_json(paths.file_dir / f"tts_manifest_{code}.json", manifest)

    logger.info(
        "TTS lang=%s (%s) mode=%s ok=%s shots=%s/%s",
        lang,
        code,
        manifest.get("tts_mode"),
        manifest["ok"],
        manifest["success_count"],
        manifest["shot_count"],
    )
    return manifest

def synthesize_package_tts(
    package_root: Path | str,
    *,
    languages: Optional[Sequence[str]] = None,
    include_bangla: bool = True,
    voice_name: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """TTS for each language — one unique Google key per language."""
    pkg = Path(package_root)
    langs: List[str] = []
    for lang in languages or list(SUPPORTED_LANGUAGES):
        name = normalize_language_name(lang)
        if name.lower() in ("bangla", "bengali"):
            name = "Bangla"
        if name not in langs:
            langs.append(name)
    if include_bangla and "Bangla" not in langs:
        langs.insert(0, "Bangla")

    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for name in langs:
        try:
            results[name] = synthesize_language_tts(
                pkg, name, voice_name=voice_name, force=force
            )
        except Exception as exc:
            logger.exception("TTS failed for %s", name)
            errors[name] = str(exc)

    # Honest ok: every requested language succeeded with all shots
    all_ok = True
    for name in langs:
        item = results.get(name) or {}
        if name in errors or not item.get("ok"):
            all_ok = False
            break
        if int(item.get("success_count") or 0) < int(item.get("shot_count") or 0):
            all_ok = False
            break

    return {
        "ok": all_ok and not errors,
        "partial": (not all_ok) and bool(results),
        "results": results,
        "errors": errors,
        "languages": langs,
        "package_root": str(pkg),
        "lang_folders": {n: lang_code_for(n) for n in langs},
        "expected_audio_codes": list(CODE_TO_LANG_NAME.keys()),
    }


run_tts = synthesize_language_tts
