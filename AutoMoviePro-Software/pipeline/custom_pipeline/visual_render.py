"""Custom pipeline — Stage 3: Visual render decision (IMAGE vs VIDEO).

One Grok call analyzes each shot and returns:
  - render_type: IMAGE | VIDEO
  - visual_prompt (image or video engine ready)
  - motion_directives (ffmpeg for IMAGE, camera/action for VIDEO)

Saves to Output/.../Shared/visual_render_plan.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from pipeline.custom_pipeline.grok_client import grok_chat
from pipeline.custom_pipeline.localization import load_source_script
from pipeline.custom_pipeline.prompts import (
    SYSTEM_VISUAL_RENDER_JSON,
    build_visual_render_prompt,
)
from pipeline.custom_pipeline.topic_research import parse_grok_json, pick_primary_title
from pipeline.output_layout import (
    CURATED_OUTPUT_ROOT,
    build_video_identity,
    ensure_package_dirs,
    write_json,
)

logger = logging.getLogger(__name__)

OUTPUT_FILENAME = "visual_render_plan.json"

DEFAULT_IMAGE_FFMPEG_LANDSCAPE = (
    # Built dynamically via motion_presets; kept for import back-compat only
    "zoompan=z='min(zoom+0.00045,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=150:s=1920x1080:fps=25"
)
DEFAULT_IMAGE_FFMPEG_PORTRAIT = (
    "zoompan=z='min(zoom+0.00045,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=150:s=1080x1920:fps=25"
)
# Back-compat alias (prefer default_image_ffmpeg())
DEFAULT_IMAGE_FFMPEG = DEFAULT_IMAGE_FFMPEG_PORTRAIT


def default_image_ffmpeg(aspect_ratio: str = "9:16") -> str:
    from pipeline.custom_pipeline.media_providers import canvas_for_aspect
    from pipeline.custom_pipeline.motion_presets import build_smooth_kenburns_filter

    w, h = canvas_for_aspect(aspect_ratio)
    return build_smooth_kenburns_filter(w=w, h=h, duration=6.0, preset="slow_zoom_in")


def aspect_ratio_for_video_type(video_type: str) -> str:
    raw = str(video_type or "").strip().lower()
    if raw in ("short", "shorts", "reel", "reels", "9:16", "portrait"):
        return "9:16"
    return "16:9"


def infer_video_type_from_script(source: Dict[str, Any]) -> str:
    seo = source.get("seo_metadata") if isinstance(source.get("seo_metadata"), dict) else {}
    vt = str(seo.get("video_type") or "").lower()
    if "short" in vt:
        return "short"
    return "long"


def _source_scenes(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    scenes = source.get("script_scenes") or source.get("render_scenes") or []
    return [s for s in scenes if isinstance(s, dict)]


def normalize_render_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in ("VIDEO", "VID", "AI_VIDEO", "CLIP"):
        return "VIDEO"
    if raw in ("STOCK_VIDEO", "STOCK", "BROLL", "B-ROLL"):
        return "STOCK_VIDEO"
    return "IMAGE"


def normalize_render_payload(
    payload: Dict[str, Any],
    source: Dict[str, Any],
    *,
    aspect_ratio: str,
) -> Dict[str, Any]:
    """Align shot numbers/durations with source; normalize IMAGE/VIDEO shapes."""
    src_scenes = _source_scenes(source)
    raw_scenes = list(payload.get("render_scenes") or [])
    meta = dict(payload.get("production_metadata") or {})
    topic = str(
        source.get("topic")
        or (source.get("seo_metadata") or {}).get("selected_topic")
        or meta.get("topic")
        or ""
    ).strip()
    niche = str(
        source.get("niche")
        or meta.get("niche")
        or ""
    ).strip()
    meta["topic"] = topic
    meta["niche"] = niche
    meta["aspect_ratio"] = aspect_ratio or meta.get("aspect_ratio") or "16:9"
    meta["total_shots"] = len(src_scenes) if src_scenes else len(raw_scenes)
    if not meta.get("art_style"):
        meta["art_style"] = "Cinematic Hyper-realistic"

    from pipeline.custom_pipeline.visual_subject_policy import is_non_presenter_topic
    non_presenter_topic = is_non_presenter_topic(niche, topic)

    by_num: Dict[int, Dict[str, Any]] = {}
    for sc in raw_scenes:
        if not isinstance(sc, dict):
            continue
        try:
            n = int(sc.get("shot_number") or 0)
        except (TypeError, ValueError):
            n = 0
        if n:
            by_num[n] = sc

    merged: List[Dict[str, Any]] = []
    for i, src in enumerate(src_scenes or [{}] * max(len(raw_scenes), 0)):
        try:
            shot_no = int(src.get("shot_number") or (i + 1))
        except (TypeError, ValueError):
            shot_no = i + 1
        loc = by_num.get(shot_no) or (
            raw_scenes[i] if i < len(raw_scenes) and isinstance(raw_scenes[i], dict) else {}
        )
        rtype = normalize_render_type(loc.get("render_type"))
        visual_subject = (
            loc.get("visual_subject")
            or src.get("visual_subject")
            or loc.get("source_visual_subject")
            or src.get("source_visual_subject")
        )
        # Non-presenter documentary, or any middle shots: strictly B-roll, zero human presenter faces
        if (non_presenter_topic or shot_no > 1) and str(visual_subject or "").strip().lower() in ("presenter", "person", "character"):
            visual_subject = "broll"
            char_details = "none"
        elif non_presenter_topic:
            char_details = "none"
        else:
            char_details = src.get("character_details")

        # Industrial: never plan STOCK for brand/product UI — stock cannot show real chrome
        try:
            from pipeline.custom_pipeline.av_match_gate import stock_forbidden_for_shot

            if rtype == "STOCK_VIDEO" and stock_forbidden_for_shot(
                visual_subject=str(visual_subject or ""),
                narration=str(src.get("voiceover_script") or loc.get("source_voiceover_script") or ""),
            ):
                logger.info(
                    "Plan-time STOCK→IMAGE rewrite shot=%s subject=%s (brand/product UI)",
                    shot_no,
                    visual_subject,
                )
                rtype = "IMAGE"
        except Exception:
            pass
        try:
            dur = float(src.get("shot_duration_seconds") or loc.get("shot_duration_seconds") or 6)
        except (TypeError, ValueError):
            dur = 6.0
        dur_i = max(5, min(9, int(round(dur))))

        motion = dict(loc.get("motion_directives") or {})
        if rtype == "IMAGE":
            from pipeline.custom_pipeline.motion_presets import motion_directive_for_shot
            from pipeline.custom_pipeline.media_providers import canvas_for_aspect
            from pipeline.custom_pipeline.visual_continuity import frames_for_duration

            cw, ch = canvas_for_aspect(aspect_ratio)
            preferred = str(
                motion.get("animation_type") or motion.get("motion_preset") or ""
            )
            rebuilt = motion_directive_for_shot(
                shot_no,
                duration=float(dur_i),
                w=cw,
                h=ch,
                preferred_label=preferred,
            )
            motion["ffmpeg_filter"] = rebuilt["ffmpeg_filter"]
            motion["animation_type"] = rebuilt["animation_type"]
            motion["motion_preset"] = rebuilt["motion_preset"]
            motion["image_frame_count"] = frames_for_duration(float(dur_i))
            motion.pop("camera_movement", None)
            motion.pop("character_action", None)
        elif rtype == "STOCK_VIDEO":
            motion.setdefault("camera_movement", "Natural documentary b-roll")
            motion.setdefault("character_action", "Match spoken beat props")
            motion.pop("ffmpeg_filter", None)
        else:
            motion.setdefault("camera_movement", "Subtle cinematic move")
            motion.setdefault("character_action", "Natural subject motion")
            motion.pop("ffmpeg_filter", None)

        loc_prompt = str(loc.get("visual_prompt") or "").strip()
        src_prompt = str(src.get("visual_prompt") or "").strip()
        generic_markers = (
            "topic subject", "subject in action", "matching the spoken voiceover",
            "intricate mechanical or subject", "visual prompt",
        )
        is_generic_loc = any(m in loc_prompt.lower() for m in generic_markers)
        if (not loc_prompt) or is_generic_loc or (len(loc_prompt.split()) < 35 and len(src_prompt.split()) >= len(loc_prompt.split())):
            prompt = src_prompt or loc_prompt
        else:
            prompt = loc_prompt or src_prompt
        frame_count = int(
            loc.get("image_frame_count") or motion.get("image_frame_count") or 0
        )
        merged.append(
            {
                "shot_number": shot_no,
                "shot_duration_seconds": dur_i,
                "render_type": rtype,
                "visual_prompt": prompt,
                "visual_subject": visual_subject,
                "motion_directives": motion,
                "image_frame_count": frame_count or None,
                "topic": topic,
                "niche": niche,
                "source_camera_angle": src.get("camera_angle"),
                "source_lighting": src.get("lighting"),
                "source_character_details": char_details,
                "source_voiceover_script": src.get("voiceover_script"),
                "source_emotion_tag": src.get("emotion_tag"),
                "source_visual_subject": visual_subject,
                "source_background": src.get("background")
                or src.get("environment")
                or src.get("setting"),
            }
        )

    if not merged and raw_scenes:
        for i, loc in enumerate(raw_scenes):
            if not isinstance(loc, dict):
                continue
            rtype = normalize_render_type(loc.get("render_type"))
            motion = dict(loc.get("motion_directives") or {})
            merged.append(
                {
                    "shot_number": int(loc.get("shot_number") or (i + 1)),
                    "shot_duration_seconds": int(loc.get("shot_duration_seconds") or 6),
                    "render_type": rtype,
                    "visual_prompt": str(loc.get("visual_prompt") or ""),
                    "motion_directives": motion,
                }
            )

    meta["total_shots"] = len(merged)
    meta["image_shots"] = sum(1 for s in merged if s["render_type"] == "IMAGE")
    meta["video_shots"] = sum(1 for s in merged if s["render_type"] == "VIDEO")
    meta["stock_video_shots"] = sum(1 for s in merged if s["render_type"] == "STOCK_VIDEO")

    return {
        "production_metadata": meta,
        "render_scenes": merged,
    }


def _resolve_package_root(
    source: Union[str, Path, Dict[str, Any]],
    package_root: Optional[Path],
) -> Optional[Path]:
    if package_root:
        return Path(package_root)
    if isinstance(source, (str, Path)) and Path(source).is_file():
        p = Path(source).resolve()
        if p.parent.name in ("Shared", "File"):
            return p.parent.parent
        if p.parent.name == "Script":
            return p.parent.parent.parent
    return None


def save_visual_render_plan(
    payload: Dict[str, Any],
    *,
    package_root: Optional[Path] = None,
    video_type: str = "short",
    primary_title: Optional[str] = None,
    output_root: Optional[Path] = None,
    source_payload: Optional[Dict[str, Any]] = None,
    audit_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save under Output/.../File/Visual_NNN_(Title).json and visual_plan_audit.json."""
    from pipeline.custom_pipeline.package_layout import (
        create_package,
        open_package,
        titled_json_name,
        write_file_json,
    )

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

    visual_name = titled_json_name("Visual", paths.number, title)
    out_path = write_file_json(paths, visual_name, payload)
    write_file_json(paths, OUTPUT_FILENAME, payload)

    if audit_report:
        write_file_json(paths, "visual_plan_audit.json", audit_report)

    return {
        "ok": True,
        "json_path": str(out_path),
        "meta_path": str(paths.file_dir / OUTPUT_FILENAME),
        "audit_path": str(paths.file_dir / "visual_plan_audit.json") if audit_report else None,
        "package_root": str(paths.root),
        "folder_name": paths.folder_name,
        "image_shots": (payload.get("production_metadata") or {}).get("image_shots"),
        "video_shots": (payload.get("production_metadata") or {}).get("video_shots"),
    }


def plan_visual_renders(
    source: Union[str, Path, Dict[str, Any]],
    *,
    video_type: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    art_style: str = "Cinematic Hyper-realistic",
    api_keys: Optional[Sequence[str]] = None,
    package_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
    temperature: float = 0.5,
    save: bool = True,
) -> Dict[str, Any]:
    """Grok: decide IMAGE vs VIDEO per shot and generate prompts + motion directives.
    
    Includes Stage A Holistic Cross-Check Gate to verify dialogue-visual consistency
    and eliminate literal brand/tangent errors before saving.
    """
    src = load_source_script(source)
    kind = (video_type or infer_video_type_from_script(src)).strip().lower()
    if kind not in ("short", "long"):
        kind = infer_video_type_from_script(src)
    ar = (aspect_ratio or aspect_ratio_for_video_type(kind)).strip()

    prompt = build_visual_render_prompt(
        source_json=json.dumps(src, ensure_ascii=False, indent=2),
        aspect_ratio=ar,
        art_style=art_style,
    )
    raw = grok_chat(
        prompt,
        system=SYSTEM_VISUAL_RENDER_JSON,
        api_keys=api_keys,
        json_mode=True,
        temperature=temperature,
    )
    parsed = parse_grok_json(raw)
    payload = normalize_render_payload(parsed, src, aspect_ratio=ar)

    # ── Stage A: Post-Plan Holistic Cross-Check & Verification Gate ──
    from pipeline.custom_pipeline.visual_intelligence import cross_check_visual_plan
    payload, audit_report = cross_check_visual_plan(payload, src)

    pkg = _resolve_package_root(source, package_root)
    result: Dict[str, Any] = {
        "ok": True,
        "payload": payload,
        "audit_report": audit_report,
        "raw_text": raw,
        "prompt": prompt,
        "video_type": kind,
        "aspect_ratio": ar,
    }
    if save:
        result["save"] = save_visual_render_plan(
            payload,
            package_root=pkg,
            video_type=kind,
            primary_title=pick_primary_title(src),
            output_root=output_root,
            source_payload=src,
            audit_report=audit_report,
        )
        logger.info(
            "Visual render plan saved → %s (IMAGE=%s VIDEO=%s, Mismatches Fixed=%s)",
            result["save"].get("json_path"),
            result["save"].get("image_shots"),
            result["save"].get("video_shots"),
            audit_report.get("total_mismatches_fixed", 0),
        )
    return result


run_visual_render_plan = plan_visual_renders
