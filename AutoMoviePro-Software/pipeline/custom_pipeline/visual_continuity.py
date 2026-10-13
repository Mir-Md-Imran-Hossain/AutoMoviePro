"""Package-level visual continuity: seed lock, multi-beat stills, AV stock queries.

Goals
-----
1) IMAGE shots may use 2–3 stills (not one boring frame) — same seed + character lock,
   each beat tightly matched to dialogue + previous frame.
2) VIDEO shots keep the same package seed / character reference for clip-to-clip match.
3) Media mode can force images_only | video_only | prefer_stock_video to avoid
   jarring Agnes-vs-Pollinations quality gaps.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pipeline.custom_pipeline.media_prompts import narration_to_visual_cues


def resolve_media_visual_mode() -> str:
    """auto | images_only | video_only | prefer_stock_video"""
    raw = (os.environ.get("AMP_MEDIA_VISUAL_MODE") or "auto").strip().lower()
    if raw in ("images_only", "image_only", "stills"):
        return "images_only"
    if raw in ("video_only", "agnes_only", "ai_video_only"):
        return "video_only"
    if raw in ("prefer_stock_video", "stock_video", "stock_first"):
        return "prefer_stock_video"
    return "auto"


def package_seed(package_root: str | os.PathLike, *, explicit: Optional[int] = None) -> int:
    """Stable 31-bit seed for the whole package (character + still continuity)."""
    env = (os.environ.get("AMP_PACKAGE_SEED") or "").strip()
    if explicit is not None:
        return int(explicit) & 0x7FFFFFFF
    if env.isdigit():
        return int(env) & 0x7FFFFFFF
    digest = hashlib.sha256(str(package_root).encode("utf-8", errors="replace")).hexdigest()
    return int(digest[:8], 16) & 0x7FFFFFFF


def shot_seed(package_seed_val: int, shot_number: int, *, frame_index: int = 0) -> int:
    """Same package seed family; tiny frame offset keeps providers from cloning 1:1."""
    # Keep family identity: base seed dominates; frame nudges for variation without drift
    return int(package_seed_val + shot_number * 17 + frame_index) & 0x7FFFFFFF


def frames_for_duration(duration: float, *, forced: Optional[int] = None) -> int:
    """How many stills for one IMAGE shot (2–3). Longer VO → more frames."""
    env = (os.environ.get("AMP_IMAGE_FRAMES_PER_SHOT") or "").strip()
    if forced is not None:
        return max(1, min(3, int(forced)))
    if env.isdigit():
        return max(1, min(3, int(env)))
    dur = float(duration or 6.0)
    if dur >= 8.0:
        return 3
    if dur >= 4.5:
        return 2
    return 1


def split_narration_beats(narration: str, n_frames: int) -> List[str]:
    """Split VO into N dialogue-aligned beats for multi-still prompts."""
    text = " ".join(str(narration or "").split()).strip()
    if n_frames <= 1:
        return [text] if text else [""]
    if not text:
        return [""] * n_frames

    parts = [p.strip() for p in re.split(r"(?<=[।.!?,;:])\s+", text) if p.strip()]
    if len(parts) < n_frames:
        words = text.split()
        if len(words) >= n_frames:
            chunk = max(1, len(words) // n_frames)
            parts = []
            for i in range(n_frames):
                start = i * chunk
                end = len(words) if i == n_frames - 1 else min(len(words), (i + 1) * chunk)
                parts.append(" ".join(words[start:end]))
        else:
            parts = (parts + [text] * n_frames)[:n_frames]

    # Merge/split to exact n_frames
    if len(parts) > n_frames:
        # fold extras into last buckets
        out = parts[: n_frames - 1]
        out.append(" ".join(parts[n_frames - 1 :]))
        parts = out
    while len(parts) < n_frames:
        parts.append(parts[-1] if parts else text)
    return parts[:n_frames]


def beat_visual_prompt(
    *,
    base_scene: Dict[str, Any],
    beat_text: str,
    frame_index: int,
    total_frames: int,
    package_seed_val: int,
    prev_beat: str = "",
    art_style: str = "",
) -> str:
    """Continuity-locked prompt for one still inside a multi-image shot."""
    from pipeline.custom_pipeline.media_prompts import build_detailed_media_prompt, resolve_scene_subject
    from pipeline.custom_pipeline.visual_subject_policy import (
        SUBJECT_BROLL,
        SUBJECT_PRODUCT_UI,
        character_allowed,
        is_non_presenter_topic,
        is_product_or_tool_niche,
    )

    scene = dict(base_scene)
    subject = resolve_scene_subject(scene, narration_text=beat_text)
    prefer_ui = not character_allowed(subject)
    cues = narration_to_visual_cues(beat_text, max_cues=10, prefer_ui=prefer_ui)
    if subject == SUBJECT_BROLL:
        continuity = (
            f"FRAME {frame_index + 1}/{total_frames} of the SAME continuous scene. "
            f"SEED LOCK {package_seed_val}: consistent environment, bright 5600K high-key lighting, clean white-balanced grade — "
            f"STRICTLY NO human face, NO female face, NO female robot face, NO gynoid, NO mannequin face, NO doll face, "
            f"NO robot face close-up, NO talking head portrait. Only camera angle / mechanical action changes slightly."
        )
    elif prefer_ui:
        continuity = (
            f"FRAME {frame_index + 1}/{total_frames} of the SAME continuous UI shot. "
            f"SEED LOCK {package_seed_val}: identical UI chrome, environment, color grade — NO human face, NO portrait. "
            f"Only camera angle / panel focus may change slightly to match THIS dialogue beat."
        )
    else:
        continuity = (
            f"FRAME {frame_index + 1}/{total_frames} of the SAME continuous shot. "
            f"SEED LOCK {package_seed_val}: identical appearance, wardrobe, room, color grade. "
            f"Only camera angle / prop focus may change slightly to match THIS dialogue beat."
        )
    if prev_beat and not re.search(r"[^\x00-\x7F]", prev_beat):
        continuity += f" Continues visually from previous beat ({prev_beat[:80]})."
    if cues:
        continuity += f" MUST SHOW for this beat: {cues}."

    # Inject beat as narration; keep visual_prompt but annotate continuity first
    vp = str(scene.get("visual_prompt") or "")
    scene["visual_prompt"] = f"{continuity} {vp}".strip()
    scene["visual_subject"] = subject
    return build_detailed_media_prompt(
        scene,
        aspect_ratio=str(
            (scene.get("aspect_ratio") or "9:16")
        ),
        art_style=art_style or "Cinematic Hyper-realistic",
        for_video=False,
        narration_text=beat_text,
    )


def av_matched_stock_query(narration: str, scene: Optional[Dict[str, Any]] = None) -> str:
    """Stock video/image search string tightly tied to spoken beat (not generic studio)."""
    from pipeline.custom_pipeline.media_prompts import narration_to_visual_cues, resolve_scene_subject
    from pipeline.custom_pipeline.visual_subject_policy import (
        character_allowed,
        is_non_presenter_topic,
        is_product_or_tool_niche,
        strip_face_language,
    )

    sc = scene or {}
    subject = resolve_scene_subject(sc, narration_text=narration)
    prefer_ui = not character_allowed(subject)
    cues = narration_to_visual_cues(narration, max_cues=8, prefer_ui=prefer_ui)
    topic_str = str(sc.get("topic") or sc.get("package_topic") or "")
    niche_str = str(sc.get("niche") or sc.get("package_niche") or "")

    bits: List[str] = []
    if cues:
        bits.append(cues.replace(",", " "))

    if is_non_presenter_topic(niche_str, topic_str):
        # Extract meaningful topic words (e.g. humanoid robot factory automation)
        t_words = [w for w in re.findall(r"[A-Za-z0-9]+", topic_str) if len(w) > 2]
        if t_words:
            bits.extend(t_words[:4])
        else:
            bits.extend(["technology", "futuristic", "cinematic"])
    elif is_product_or_tool_niche(niche_str, topic_str):
        p_name = niche_str or "software"
        bits.extend([p_name, "laptop", "screen", "settings", "interface"])

    if scene:
        for k in (
            "source_camera_angle",
            "camera_angle",
            "source_background",
            "background",
        ):
            v = str(scene.get(k) or "").strip()
            if v:
                bits.append(v[:60])
    text = " ".join(bits)
    if prefer_ui:
        text = strip_face_language(text)
        text = re.sub(
            r"(?i)\b(?:young|man|woman|male|female|portrait|face|hoodie|person|people|presenter|host)\b",
            " ",
            text,
        )
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 2][:10]
    if not words:
        if is_non_presenter_topic(niche_str, topic_str):
            words = ["humanoid", "robot", "automation", "technology"]
        elif prefer_ui:
            words = ["software", "screen", "technology", "interface"]
        else:
            words = ["cinematic", "technology", "closeup"]
    return " ".join(words)


def apply_visual_mode_to_render_type(render_type: str, mode: str) -> str:
    """Rewrite IMAGE/VIDEO according to AMP_MEDIA_VISUAL_MODE."""
    rt = (render_type or "IMAGE").upper()
    if mode == "images_only":
        return "IMAGE"
    if mode == "video_only":
        return "VIDEO"
    if mode == "prefer_stock_video" and rt == "IMAGE":
        return "STOCK_VIDEO"
    return rt


def seed_lock_prompt_suffix(seed: int, *, character_ref_name: str = "") -> str:
    bits = [f"SEED LOCK {seed}: keep identical identity, wardrobe, set, color grade"]
    if character_ref_name:
        bits.append(f"match character_reference {character_ref_name} exactly")
    return ". ".join(bits)
