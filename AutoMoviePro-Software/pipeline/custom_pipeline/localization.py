"""Custom pipeline — Stage 2: Voice + subtitle + SEO localization ONLY.

Visuals (visual_prompt / character_details / lighting / camera_angle / sfx / bgm)
live ONLY in Shared/topic_script.json (+ Shared/visual_render_plan.json).
Every language reuses the same visuals; only voice & subtitles change.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from pipeline.custom_pipeline.google_localize_client import google_localize_chat
from pipeline.custom_pipeline.prompts import (
    DEFAULT_AUDIENCE_CULTURE,
    SYSTEM_LOCALIZE_JSON,
    build_localization_prompt,
)
from pipeline.custom_pipeline.topic_research import parse_grok_json, pick_primary_title
from pipeline.lang_config import LANG_FOLDERS
from pipeline.output_layout import (
    CURATED_OUTPUT_ROOT,
    build_video_identity,
    ensure_package_dirs,
    write_json,
)

logger = logging.getLogger(__name__)

LOCALIZED_FILENAME = "localized_voice.json"
# Back-compat alias filename still written
LEGACY_LOCALIZED_FILENAME = "localized_script.json"

VISUAL_FIELDS_FORBIDDEN = (
    "camera_angle",
    "lighting",
    "character_details",
    "visual_prompt",
    "sfx",
    "bgm_style",
)

SUPPORTED_LANGUAGES = ("English", "Hindi", "Tamil", "Malayalam", "Urdu")

LANG_CODE_BY_NAME = {
    "english": "en",
    "hindi": "hi",
    "urdu": "ur",
    "tamil": "ta",
    "malayalam": "ml",
    "bangla": "bn",
    "bengali": "bn",
}


def normalize_language_name(language: str) -> str:
    raw = (language or "").strip()
    if not raw:
        return "English"
    lower = raw.lower()
    for name in SUPPORTED_LANGUAGES:
        if name.lower() == lower:
            return name
    mapping = {
        "en": "English",
        "hi": "Hindi",
        "ur": "Urdu",
        "ta": "Tamil",
        "ml": "Malayalam",
    }
    if lower in mapping:
        return mapping[lower]
    return raw.title()


def language_folder_code(language: str) -> str:
    name = normalize_language_name(language)
    return LANG_CODE_BY_NAME.get(name.lower(), "en")


def load_source_script(source: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(source, dict):
        return dict(source)
    if isinstance(source, Path) or (
        isinstance(source, str) and Path(source).is_file()
    ):
        return json.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(source, str):
        text = source.strip()
        if text.startswith("{"):
            return parse_grok_json(text)
        path = Path(text)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError("source must be a dict, JSON string, or path to topic_script.json")


def extract_voice_input(source: Dict[str, Any]) -> Dict[str, Any]:
    """Strip visuals before sending to the localization model."""
    seo = dict(source.get("seo_metadata") or {})
    scenes = source.get("script_scenes") or source.get("voice_scenes") or []
    voice_scenes: List[Dict[str, Any]] = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        voice_scenes.append(
            {
                "shot_number": sc.get("shot_number"),
                "shot_duration_seconds": sc.get("shot_duration_seconds"),
                "voiceover_script": sc.get("voiceover_script") or "",
                "emotion_tag": sc.get("emotion_tag") or "",
            }
        )
    return {
        "seo_metadata": {
            "selected_topic": seo.get("selected_topic"),
            "suggested_titles": seo.get("suggested_titles") or [],
            "seo_keywords": seo.get("seo_keywords") or [],
            "video_type": seo.get("video_type"),
            "target_duration_seconds": seo.get("target_duration_seconds"),
        },
        "voice_scenes": voice_scenes,
    }


def build_voice_only_payload(
    localized: Dict[str, Any],
    source: Dict[str, Any],
    *,
    target_language: str,
) -> Dict[str, Any]:
    """Keep only voice/SEO fields; never persist visual fields per language."""
    src_seo = dict(source.get("seo_metadata") or {})
    loc_seo = dict(localized.get("seo_metadata") or {})
    seo = {
        "selected_topic": loc_seo.get("selected_topic") or src_seo.get("selected_topic"),
        "suggested_titles": loc_seo.get("suggested_titles") or src_seo.get("suggested_titles") or [],
        "seo_keywords": loc_seo.get("seo_keywords") or src_seo.get("seo_keywords") or [],
        "video_type": src_seo.get("video_type") or loc_seo.get("video_type"),
        "target_duration_seconds": src_seo.get("target_duration_seconds")
        or loc_seo.get("target_duration_seconds"),
    }

    src_scenes = list(source.get("script_scenes") or source.get("voice_scenes") or [])
    loc_scenes = list(
        localized.get("voice_scenes")
        or localized.get("script_scenes")
        or []
    )
    by_num: Dict[int, Dict[str, Any]] = {}
    for sc in loc_scenes:
        if isinstance(sc, dict):
            try:
                by_num[int(sc.get("shot_number") or 0)] = sc
            except (TypeError, ValueError):
                pass

    voice_scenes: List[Dict[str, Any]] = []
    for i, src in enumerate(src_scenes):
        if not isinstance(src, dict):
            continue
        try:
            n = int(src.get("shot_number") or (i + 1))
        except (TypeError, ValueError):
            n = i + 1
        loc = by_num.get(n) or (
            loc_scenes[i] if i < len(loc_scenes) and isinstance(loc_scenes[i], dict) else {}
        )
        vo = str(loc.get("voiceover_script") or src.get("voiceover_script") or "").strip()
        emotion = str(loc.get("emotion_tag") or src.get("emotion_tag") or "").strip()
        subtitle = str(loc.get("subtitle_text") or vo).strip()
        try:
            dur = int(src.get("shot_duration_seconds") or loc.get("shot_duration_seconds") or 6)
        except (TypeError, ValueError):
            dur = 6
        voice_scenes.append(
            {
                "shot_number": n,
                "shot_duration_seconds": dur,
                "voiceover_script": vo,
                "emotion_tag": emotion,
                "subtitle_text": subtitle,
            }
        )

    return {
        "target_language": target_language,
        "visuals_shared": True,
        "visual_source": "Shared/topic_script.json",
        "render_plan_source": "Shared/visual_render_plan.json",
        "note": "Visuals/SFX/BGM are shared once; only voice + subtitles + SEO are language-specific.",
        "seo_metadata": seo,
        "voice_scenes": voice_scenes,
    }


# Back-compat name used by older tests
def merge_locked_visuals(
    localized: Dict[str, Any],
    source: Dict[str, Any],
    *,
    target_language: str,
) -> Dict[str, Any]:
    return build_voice_only_payload(localized, source, target_language=target_language)


def save_localized_script(
    payload: Dict[str, Any],
    *,
    language: str,
    package_root: Optional[Path] = None,
    video_type: str = "short",
    primary_title: Optional[str] = None,
    output_root: Optional[Path] = None,
    source_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save voice-only JSON under Output/.../File/Voice_NNN_EN_(Title).json."""
    from pipeline.custom_pipeline.package_layout import (
        create_package,
        lang_code_for,
        open_package,
        titled_json_name,
        write_file_json,
    )

    lang_name = normalize_language_name(language)
    code = lang_code_for(lang_name)

    if package_root:
        paths = open_package(package_root)
        title = primary_title or paths.title
    else:
        title = (
            primary_title
            or pick_primary_title(source_payload or {})
            or "Untitled"
        )
        paths = create_package(
            title=title, video_type=video_type, output_root=output_root
        )

    voice_name = titled_json_name("Voice", paths.number, title, lang=code)
    out_path = write_file_json(paths, voice_name, payload)
    # Stable alias
    write_file_json(paths, f"localized_voice_{code}.json", payload)

    return {
        "ok": True,
        "language": lang_name,
        "lang_code": code,
        "lang_folder": code,
        "json_path": str(out_path),
        "shared_path": str(paths.file_dir / f"localized_voice_{code}.json"),
        "package_root": str(paths.root),
    }


def localize_script(
    source: Union[str, Path, Dict[str, Any]],
    *,
    target_language: str,
    audience_culture: Optional[str] = None,
    api_keys: Optional[Sequence[str]] = None,
    package_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
    video_type: Optional[str] = None,
    temperature: float = 0.55,
    save: bool = True,
) -> Dict[str, Any]:
    """Localize voice + subtitles + SEO only (shared visuals unchanged)."""
    src = load_source_script(source)
    lang = normalize_language_name(target_language)
    culture = (audience_culture or "").strip() or DEFAULT_AUDIENCE_CULTURE.get(
        lang, "General audience"
    )
    voice_in = extract_voice_input(src)
    prompt = build_localization_prompt(
        target_language=lang,
        audience_culture=culture,
        source_json=json.dumps(voice_in, ensure_ascii=False, indent=2),
    )
    raw = google_localize_chat(
        prompt,
        system=SYSTEM_LOCALIZE_JSON,
        language=lang,
        api_keys=api_keys,
        temperature=temperature,
    )
    parsed = parse_grok_json(raw)
    payload = build_voice_only_payload(parsed, src, target_language=lang)

    seo = src.get("seo_metadata") or {}
    kind = video_type or (
        "short"
        if str(seo.get("video_type") or "").lower() in ("shorts", "short")
        else "long"
    )

    result: Dict[str, Any] = {
        "ok": True,
        "target_language": lang,
        "audience_culture": culture,
        "payload": payload,
        "raw_text": raw,
        "prompt": prompt,
    }
    if save:
        result["save"] = save_localized_script(
            payload,
            language=lang,
            package_root=package_root,
            video_type=kind,
            primary_title=pick_primary_title(src),
            output_root=output_root,
            source_payload=src,
        )
        logger.info("Localized voice %s → %s", lang, result["save"].get("json_path"))
    return result


def localize_to_languages(
    source: Union[str, Path, Dict[str, Any]],
    *,
    languages: Optional[Sequence[str]] = None,
    audience_cultures: Optional[Dict[str, str]] = None,
    api_keys: Optional[Sequence[str]] = None,
    package_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
    video_type: Optional[str] = None,
    temperature: float = 0.55,
    save: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    from pipeline.custom_pipeline.package_layout import lang_code_for
    from pipeline.custom_pipeline.stage_resume import existing_localize_lang

    langs = list(languages) if languages else list(SUPPORTED_LANGUAGES)
    cultures = audience_cultures or {}
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    pkg = Path(package_root) if package_root else None
    if pkg is None and isinstance(source, (str, Path)) and Path(source).is_file():
        p = Path(source).resolve()
        if p.parent.name in ("Shared", "File"):
            pkg = p.parent.parent

    for lang in langs:
        name = normalize_language_name(lang)
        try:
            if pkg and not force:
                code = lang_code_for(name)
                resumed = existing_localize_lang(pkg, code)
                if resumed:
                    logger.info("Localize resume skip lang=%s", name)
                    results[name] = resumed
                    continue
            results[name] = localize_script(
                source,
                target_language=name,
                audience_culture=cultures.get(name) or cultures.get(lang),
                api_keys=api_keys,
                package_root=pkg,
                output_root=output_root,
                video_type=video_type,
                temperature=temperature,
                save=save,
            )
        except Exception as exc:
            logger.exception("Localization failed for %s", name)
            errors[name] = str(exc)

    return {
        "ok": not errors and len(results) >= len(langs),
        "partial": bool(errors) and bool(results),
        "results": results,
        "errors": errors,
        "languages": [normalize_language_name(l) for l in langs],
        "resumed_count": sum(1 for v in results.values() if isinstance(v, dict) and v.get("resumed")),
        "api_count": sum(
            1 for v in results.values() if isinstance(v, dict) and not v.get("resumed")
        ),
    }


run_localization = localize_script
