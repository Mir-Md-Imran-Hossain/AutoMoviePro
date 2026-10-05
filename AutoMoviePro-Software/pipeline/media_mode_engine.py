"""Industrial Media Mode Engine — VIDEO (Agnes) primary, IMAGE only when justified.

Authority for deciding whether a dialogue beat should be:
  - VIDEO              → Agnes AI video clip (DEFAULT / PRIMARY)
  - IMAGE_WITH_MOTION  → still + Ken Burns / controlled motion (exception)
  - IMAGE              → pure still (rare; static-sufficient mood only)

Policy (fail-closed for production):
  1) Agnes VIDEO is the main priority for nearly every beat.
  2) IMAGE / IMAGE_WITH_MOTION only when the engine explicitly authorizes it
     (static mood plate, establishing texture, sacred/faceless still, etc.).
  3) Prefer-image-fallback MUST NOT silently convert the whole film to stills.
  4) VIDEO beats require Agnes; silent Ken-Burns downgrade is unauthorized
     unless AMP_ALLOW_IMAGE_FALLBACK=1 AND allow_image_fallback is true.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Sequence

from pipeline.visual_intelligence import (
    MODE_IMAGE,
    MODE_IMAGE_WITH_MOTION,
    MODE_VIDEO,
    SUPPORTED_VISUAL_MODES,
)

ENGINE_VERSION = "media_mode_engine_v1"

# Beats that may legitimately use stills (Ken Burns) instead of Agnes video.
_IMAGE_OK_ELEMENTS = frozenset(
    {
        "outro",
        "title",
        "endcard",
        "thumbnail",
        "quote",
        "inscription",
        "calligraphy",
        "map_static",
        "diagram",
        "document",
        "parchment",
    }
)

_MOTION_VERBS = (
    "run",
    "walk",
    "fly",
    "crash",
    "explode",
    "transform",
    "morph",
    "chase",
    "spin",
    "fall",
    "drive",
    "fight",
    "dance",
    "jump",
    "orbit",
    "launch",
    "deploy",
    "align",
    "rotate",
    "unfold",
    "travel",
    "approach",
    "descend",
    "ascend",
    "scan",
    "move",
    "push",
    "pan",
    "dolly",
)

_STATIC_MOOD_HINTS = (
    "inscription",
    "calligraphy",
    "parchment",
    "map",
    "diagram",
    "quote",
    "emblem",
    "seal",
    "still life",
    "portrait plate",
)


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def prefer_image_fallback_default() -> bool:
    """Production default: False (VIDEO-first). Override with AMP_PREFER_IMAGE_FALLBACK=1."""
    return _env_flag("AMP_PREFER_IMAGE_FALLBACK", "0")


def allow_image_fallback_default(channel: Optional[dict] = None) -> bool:
    """
    Channel may set allow_image_fallback.
    Production default False for VIDEO-first — emergency escape via AMP_ALLOW_IMAGE_FALLBACK=1.
    """
    if _env_flag("AMP_ALLOW_IMAGE_FALLBACK", "0"):
        return True
    if isinstance(channel, dict) and "allow_image_fallback" in channel:
        return bool(channel.get("allow_image_fallback"))
    return False


def require_agnes_for_mode(visual_mode: str, *, allow_image_fallback: bool = False) -> bool:
    mode = (visual_mode or MODE_VIDEO).strip().upper() or MODE_VIDEO
    if mode == MODE_VIDEO:
        return True
    # Image modes never require Agnes
    if mode in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION):
        return False
    return not allow_image_fallback


def decide_media_mode(
    *,
    primary_action: str = "",
    camera_motion: str = "",
    narration: str = "",
    element: str = "",
    requires_transformation: bool = False,
    static_sufficient: bool = False,
    controlled_motion_helps: bool = False,
    explicit_mode: str = "",
    prefer_image_fallback: bool = False,
    visual_change_candidate: bool = True,
    beat_index: int = 0,
    total_beats: int = 1,
) -> Dict[str, Any]:
    """
    Industrial decision with provenance.

    Returns:
      mode, reason, ok, image_authorized, agnes_required, engine_version
    """
    explicit = (explicit_mode or "").strip().upper()
    if explicit:
        if explicit not in SUPPORTED_VISUAL_MODES:
            return {
                "mode": MODE_VIDEO,
                "reason": f"unsupported_mode_forced_video:{explicit}",
                "ok": "true",
                "image_authorized": False,
                "agnes_required": True,
                "engine_version": ENGINE_VERSION,
            }
        return {
            "mode": explicit,
            "reason": f"explicit_mode:{explicit}",
            "ok": "true",
            "image_authorized": explicit in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION),
            "agnes_required": explicit == MODE_VIDEO,
            "engine_version": ENGINE_VERSION,
        }

    action = (primary_action or "").lower()
    motion = (camera_motion or "").lower()
    narr = (narration or "").lower()
    el = (element or "").lower().strip()
    blob = f"{action} {motion} {narr} {el}"

    # Hard VIDEO signals
    if requires_transformation or any(v in action for v in _MOTION_VERBS) or motion in (
        "tracking",
        "orbit",
        "dolly",
        "crane",
        "flythrough",
        "handheld",
    ):
        return {
            "mode": MODE_VIDEO,
            "reason": "meaningful_motion_or_transformation_required",
            "ok": "true",
            "image_authorized": False,
            "agnes_required": True,
            "engine_version": ENGINE_VERSION,
        }

    # Explicit static plate (rare) — only when engine can justify
    image_element = el in _IMAGE_OK_ELEMENTS or any(h in blob for h in _STATIC_MOOD_HINTS)
    # Last beat outro may be IMAGE_WITH_MOTION (Ken Burns end card), not forced Agnes
    is_closing = total_beats > 1 and beat_index >= max(0, total_beats - 1) and el in ("outro", "ending", "")

    if prefer_image_fallback:
        # Emergency / quota path: still prefer IMAGE_WITH_MOTION over pure IMAGE
        # so the cut has cinematic motion — NOT a silent whole-film still dump
        # unless static plate is clearly justified.
        if image_element or (static_sufficient and not visual_change_candidate):
            return {
                "mode": MODE_IMAGE_WITH_MOTION,
                "reason": "prefer_image_fallback_authorized_still_plate",
                "ok": "true",
                "image_authorized": True,
                "agnes_required": False,
                "engine_version": ENGINE_VERSION,
                "warning": "prefer_image_fallback_active",
            }
        # Even under prefer_image_fallback, default remaining beats to VIDEO if Agnes available path
        # — preference means "allow image", not "force image for all".
        return {
            "mode": MODE_VIDEO,
            "reason": "prefer_image_fallback_but_video_still_primary",
            "ok": "true",
            "image_authorized": False,
            "agnes_required": True,
            "engine_version": ENGINE_VERSION,
            "warning": "prefer_image_fallback_ignored_for_non_static_beat",
        }

    if image_element and static_sufficient and not visual_change_candidate:
        return {
            "mode": MODE_IMAGE_WITH_MOTION if (controlled_motion_helps or is_closing) else MODE_IMAGE,
            "reason": "static_mood_plate_authorized",
            "ok": "true",
            "image_authorized": True,
            "agnes_required": False,
            "engine_version": ENGINE_VERSION,
        }

    if controlled_motion_helps and static_sufficient and image_element:
        return {
            "mode": MODE_IMAGE_WITH_MOTION,
            "reason": "still_sufficient_controlled_motion_improves_engagement",
            "ok": "true",
            "image_authorized": True,
            "agnes_required": False,
            "engine_version": ENGINE_VERSION,
        }

    # DEFAULT: Agnes VIDEO (industrial primary)
    return {
        "mode": MODE_VIDEO,
        "reason": "default_video_primary_agnes",
        "ok": "true",
        "image_authorized": False,
        "agnes_required": True,
        "engine_version": ENGINE_VERSION,
    }


def authorize_image_path(
    *,
    visual_mode: str,
    image_authorized: bool = False,
    allow_image_fallback: bool = False,
    decision_reason: str = "",
) -> Dict[str, Any]:
    """Gate: may we serve Ken Burns / still instead of Agnes?"""
    mode = (visual_mode or "").strip().upper()
    if mode == MODE_VIDEO:
        if allow_image_fallback and _env_flag("AMP_ALLOW_IMAGE_FALLBACK", "0"):
            return {
                "allowed": True,
                "reason": "emergency_amp_allow_image_fallback",
                "downgrade": True,
            }
        return {
            "allowed": False,
            "reason": "video_beat_image_path_unauthorized",
            "downgrade": False,
        }
    if mode in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION):
        if image_authorized or decision_reason.startswith("explicit") or decision_reason.startswith("static"):
            return {"allowed": True, "reason": "engine_authorized_image_mode", "downgrade": False}
        if allow_image_fallback:
            return {"allowed": True, "reason": "image_mode_with_channel_fallback", "downgrade": False}
        return {"allowed": True, "reason": "image_mode_selected", "downgrade": False}
    return {"allowed": False, "reason": "unknown_mode", "downgrade": False}


def enforce_video_primary_on_plan(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    """Rewrite scene visual_mode to VIDEO unless already image-authorized."""
    plan = dict(plan or {})
    scenes = list(plan.get("scenes") or [])
    n = len(scenes)
    changed = 0
    out_scenes = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            out_scenes.append(sc)
            continue
        row = dict(sc)
        current = str(row.get("visual_mode") or "").strip().upper()
        decision = decide_media_mode(
            primary_action=str(row.get("element") or row.get("action") or ""),
            narration=str(row.get("narration") or ""),
            element=str(row.get("element") or ""),
            explicit_mode="" if current in ("", MODE_IMAGE, MODE_IMAGE_WITH_MOTION) else current,
            # Re-evaluate IMAGE* that came from prefer_image_fallback bias
            prefer_image_fallback=False,
            visual_change_candidate=True,
            static_sufficient=False,
            beat_index=i,
            total_beats=n,
        )
        # Keep explicit VIDEO; replace biased IMAGE/IMAGE_WITH_MOTION unless element authorizes stills
        if current == MODE_VIDEO:
            row["visual_mode"] = MODE_VIDEO
            row["media_mode_decision"] = {
                "mode": MODE_VIDEO,
                "reason": "preserved_video",
                "engine_version": ENGINE_VERSION,
            }
        elif current in (MODE_IMAGE, MODE_IMAGE_WITH_MOTION):
            el = str(row.get("element") or "").lower()
            if el in _IMAGE_OK_ELEMENTS:
                row["visual_mode"] = MODE_IMAGE_WITH_MOTION
                row["media_mode_decision"] = {
                    "mode": MODE_IMAGE_WITH_MOTION,
                    "reason": "element_authorized_still",
                    "image_authorized": True,
                    "engine_version": ENGINE_VERSION,
                }
            else:
                row["visual_mode"] = MODE_VIDEO
                row["media_mode_decision"] = decision
                changed += 1
        else:
            row["visual_mode"] = decision["mode"]
            row["media_mode_decision"] = decision
            if decision["mode"] == MODE_VIDEO:
                changed += 1
        out_scenes.append(row)
    plan["scenes"] = out_scenes
    meta = dict(plan.get("metadata") or {})
    meta["media_mode_engine"] = {
        "version": ENGINE_VERSION,
        "video_primary_enforced": True,
        "modes_rewritten_to_video": changed,
    }
    plan["metadata"] = meta
    return plan


def summarize_modes(plan: Dict[str, Any]) -> Dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    counts = {MODE_VIDEO: 0, MODE_IMAGE: 0, MODE_IMAGE_WITH_MOTION: 0, "OTHER": 0}
    for s in scenes:
        m = str(s.get("visual_mode") or "").upper()
        if m in counts:
            counts[m] += 1
        else:
            counts["OTHER"] += 1
    return {"scene_count": len(scenes), "counts": counts, "engine_version": ENGINE_VERSION}
