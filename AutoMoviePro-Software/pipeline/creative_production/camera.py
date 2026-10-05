"""Shot purpose and camera continuity (AMP-004 Phase-07).

Extends ShotPlan; does not replace ContinuityTracker camera_language.
"""
from __future__ import annotations

from typing import Any, Optional

ALLOWED_SHOTS = {
    "close-up",
    "medium",
    "wide",
    "over-the-shoulder",
    "top-down",
    "establishing",
}

UNMOTIVATED_MOTIONS = {"spin", "flash", "glitch", "shake", "whip-pan", "random-zoom"}


def validate_shot_purpose(
    *,
    shot_type: str,
    shot_purpose: str,
    narrative_role: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    st = (shot_type or "").strip().lower()
    purpose = (shot_purpose or "").strip()
    if st and st not in ALLOWED_SHOTS:
        issues.append(f"unknown_shot_type:{st}")
    if st and not purpose:
        issues.append("shot_missing_purpose")
    if not st and not purpose:
        issues.append("shot_unspecified")
    status = "BLOCK" if any("missing_purpose" in i or i == "shot_unspecified" for i in issues) else (
        "WARN" if issues else "PASS"
    )
    # unknown type is WARN not BLOCK — allow documented aliases
    return {
        "status": status,
        "issues": issues,
        "shot_type": st,
        "shot_purpose": purpose,
        "narrative_role": narrative_role,
        "method": "DETERMINISTIC",
    }


def validate_camera_continuity(
    shots: list[dict[str, str]],
) -> dict[str, Any]:
    """Detect unmotivated identical or chaotic camera changes. Not random jitter."""
    issues: list[str] = []
    types = [(s.get("shot_type") or s.get("camera") or "").lower() for s in shots]
    motions = [(s.get("camera_motion") or "").lower() for s in shots]
    if len(types) >= 3 and len(set(t for t in types if t)) == 1:
        issues.append("robotic_same_camera_every_scene")
    for i, m in enumerate(motions):
        for bad in UNMOTIVATED_MOTIONS:
            if bad in m:
                purpose = str(shots[i].get("shot_purpose") or "")
                if not purpose or purpose in ("none", "random"):
                    issues.append(f"unmotivated_camera_motion:{bad}")
    # Rapid style oscillation
    if len(types) >= 4:
        flips = sum(1 for a, b in zip(types, types[1:]) if a and b and a != b)
        if flips >= len(types) - 1 and len(set(types)) >= 4:
            issues.append("rapid_unmotivated_shot_style_changes")
    status = "BLOCK" if any(i.startswith("unmotivated_") for i in issues) else (
        "WARN" if issues else "PASS"
    )
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def controlled_variation_for_role(narrative_role: str, *, prior_shot: str = "") -> dict[str, str]:
    """Purpose-based variation — not RNG. Continuity-safe defaults."""
    from pipeline.creative_production.contract import ROLE_SHOT_DEFAULTS

    role = (narrative_role or "evidence").lower()
    shot, purpose = ROLE_SHOT_DEFAULTS.get(role, ("medium", "serve_scene_purpose"))
    if prior_shot and prior_shot == shot and role not in ("hook", "close"):
        # slight controlled shift, still purposeful
        shot = "medium" if shot == "close-up" else shot
    return {"shot_type": shot, "shot_purpose": purpose, "camera_motion": "stable"}
