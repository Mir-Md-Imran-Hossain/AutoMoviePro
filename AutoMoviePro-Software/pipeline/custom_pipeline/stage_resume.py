"""Skip-if-exists helpers for topic / visual / localize stages.

Validates artifact shape so corrupt/empty JSON never silently burns or skips wrongly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("resume read failed %s: %s", path.name, exc)
        return None
    if not isinstance(data, dict) or not data:
        return None
    return data


def _topic_payload_ok(payload: Dict[str, Any]) -> bool:
    scenes = payload.get("script_scenes") or payload.get("voice_scenes") or []
    if not isinstance(scenes, list) or len(scenes) < 1:
        return False
    # At least one scene with dialogue
    for sc in scenes:
        if isinstance(sc, dict) and str(sc.get("voiceover_script") or "").strip():
            return True
    return False


def _visual_payload_ok(payload: Dict[str, Any]) -> bool:
    scenes = payload.get("render_scenes") or []
    if not isinstance(scenes, list) or len(scenes) < 1:
        return False
    return any(isinstance(sc, dict) and sc.get("render_type") for sc in scenes)


def _voice_payload_ok(payload: Dict[str, Any]) -> bool:
    scenes = payload.get("voice_scenes") or payload.get("script_scenes") or []
    if not isinstance(scenes, list) or len(scenes) < 1:
        return False
    return any(
        isinstance(sc, dict) and str(sc.get("voiceover_script") or "").strip() for sc in scenes
    )


def existing_topic_package(package_root: Path) -> Optional[Dict[str, Any]]:
    from pipeline.custom_pipeline.package_layout import open_package

    if not package_root or not Path(package_root).is_dir():
        return None
    paths = open_package(package_root)
    candidates = [paths.file_dir / "topic_script.json", *sorted(paths.file_dir.glob("Script_*.json"))]
    for p in candidates:
        if not p.is_file():
            continue
        payload = _read_json(p)
        if not payload or not _topic_payload_ok(payload):
            logger.warning("topic resume rejected (invalid/empty): %s", p.name)
            continue
        return {
            "ok": True,
            "resumed": True,
            "payload": payload,
            "save": {"json_path": str(p), "package_root": str(package_root)},
        }
    return None


def existing_visual_plan(package_root: Path) -> Optional[Dict[str, Any]]:
    from pipeline.custom_pipeline.package_layout import open_package

    paths = open_package(package_root)
    for p in [paths.file_dir / "visual_render_plan.json", *sorted(paths.file_dir.glob("Visual_*.json"))]:
        if not p.is_file():
            continue
        payload = _read_json(p)
        if not payload or not _visual_payload_ok(payload):
            logger.warning("visual resume rejected (invalid/empty): %s", p.name)
            continue
        meta = payload.get("production_metadata") or {}
        return {
            "ok": True,
            "resumed": True,
            "payload": payload,
            "save": {
                "json_path": str(p),
                "package_root": str(package_root),
                "image_shots": meta.get("image_shots"),
                "video_shots": meta.get("video_shots"),
            },
        }
    return None


def existing_localize_lang(package_root: Path, lang_code: str) -> Optional[Dict[str, Any]]:
    from pipeline.custom_pipeline.package_layout import open_package

    paths = open_package(package_root)
    code = str(lang_code or "").upper()
    candidates = [
        paths.file_dir / f"localized_voice_{code}.json",
        *sorted(paths.file_dir.glob(f"Voice_*_{code}_*.json")),
    ]
    for p in candidates:
        if not p.is_file():
            continue
        payload = _read_json(p)
        if not payload or not _voice_payload_ok(payload):
            logger.warning("localize resume rejected (invalid/empty): %s", p.name)
            continue
        return {
            "ok": True,
            "resumed": True,
            "payload": payload,
            "save": {"json_path": str(p)},
            "json_path": str(p),
        }
    return None
