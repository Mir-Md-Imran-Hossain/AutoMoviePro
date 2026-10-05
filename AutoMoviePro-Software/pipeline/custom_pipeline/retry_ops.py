"""Retry one shot / one language without full pipeline rerun."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.custom_pipeline.media_compose import assemble_final_video, compose_language_shots
from pipeline.custom_pipeline.media_generate import generate_shared_media
from pipeline.custom_pipeline.package_layout import lang_code_for, open_package
from pipeline.custom_pipeline.tts_synthesize import synthesize_language_tts
from pipeline.output_layout import write_json

logger = logging.getLogger(__name__)


def retry_media_shot(
    package_root: Path | str,
    shot_number: int,
    *,
    languages: Optional[Sequence[str]] = None,
    force: bool = True,
) -> Dict[str, Any]:
    """Clear one shot from media state and regenerate + recompose affected langs."""
    pkg = Path(package_root)
    paths = open_package(pkg)
    key = f"S{int(shot_number):02d}"
    state_path = paths.file_dir / "media_generation_state.json"
    if state_path.is_file():
        st = json.loads(state_path.read_text(encoding="utf-8"))
        shots = dict(st.get("shots") or {})
        shots.pop(key, None)
        st["shots"] = shots
        write_json(state_path, st)
    for p in (
        paths.video_clips / f"{key}.mp4",
        paths.image / f"{key}.png",
        paths.video_clips / f"{key}.still.png",
    ):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    # Regenerate all shared (resume skips others)
    shared = generate_shared_media(pkg, force=False)
    # Recompose languages
    langs = list(languages) if languages else []
    if not langs:
        for code_dir in paths.audio.iterdir() if paths.audio.is_dir() else []:
            if code_dir.is_dir() and any(code_dir.glob("S*.m4a")):
                from pipeline.custom_pipeline.package_layout import CODE_TO_LANG_NAME

                langs.append(CODE_TO_LANG_NAME.get(code_dir.name, code_dir.name))
    composed = {}
    finals = {}
    for lang in langs:
        code = lang_code_for(lang)
        # delete lang clip for this shot so compose regenerates it
        clip = paths.video_clips / code / f"{key}_{code}.mp4"
        if clip.exists():
            try:
                clip.unlink()
            except Exception:
                pass
        composed[lang] = compose_language_shots(pkg, lang)
        finals[lang] = assemble_final_video(pkg, lang)

    report = {
        "ok": bool(shared.get("ok")) and all(
            isinstance(finals.get(lang), dict) and finals[lang].get("ok") for lang in langs
        )
        if langs
        else bool(shared.get("ok")),
        "shippable": False,  # single-shot retry is never full-package shippable alone
        "partial": True,
        "shot": key,
        "shared": shared,
        "composed": composed,
        "finals": finals,
    }
    write_json(paths.file_dir / f"retry_shot_{key}_manifest.json", report)
    return report


def retry_language(
    package_root: Path | str,
    language: str,
    *,
    force_tts: bool = True,
) -> Dict[str, Any]:
    """Re-run TTS + compose + final for one language."""
    pkg = Path(package_root)
    paths = open_package(pkg)
    code = lang_code_for(language)
    if force_tts:
        for p in (paths.audio_lang(code)).glob("S*.m4a"):
            try:
                p.unlink()
            except Exception:
                pass
        full = paths.audio_lang(code) / f"narration_full_{code}.m4a"
        if full.exists():
            try:
                full.unlink()
            except Exception:
                pass
    tts = synthesize_language_tts(pkg, language, force=force_tts)
    # wipe lang clips
    clip_dir = paths.video_clips / code
    if clip_dir.is_dir():
        for p in clip_dir.glob(f"S*_{code}.mp4"):
            try:
                p.unlink()
            except Exception:
                pass
    composed = compose_language_shots(pkg, language)
    final = assemble_final_video(pkg, language)
    report = {"ok": bool(tts.get("ok") and composed.get("ok") and final.get("ok")), "tts": tts, "compose": composed, "final": final}
    write_json(paths.file_dir / f"retry_lang_{code}_manifest.json", report)
    return report
