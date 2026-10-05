"""VFX + transition governance for render boundary. Reuses creative_production policy."""
from __future__ import annotations

from typing import Any

from pipeline.creative_production.transitions import validate_transition
from pipeline.rendering_integrity.contract import (
    ALLOWED_TRANSITION_TYPES,
    NOISE_TRANSITIONS,
    VFX_PURPOSES,
    TransitionDirective,
    VfxDirective,
)


def validate_vfx_directives(
    directives: list[VfxDirective] | list[dict[str, Any]],
    *,
    scene_bounds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    bounds = scene_bounds or {}
    for raw in directives or []:
        v = raw if isinstance(raw, VfxDirective) else VfxDirective(**{k: raw[k] for k in (
            "vfx_id", "scene_id", "purpose", "start_time", "end_time", "target", "intensity", "blend_mode", "provenance", "approval_status"
        ) if k in raw})
        if not (v.vfx_id or "").strip():
            issues.append("vfx_missing_id")
        if not (v.scene_id or "").strip():
            issues.append(f"vfx_missing_scene:{v.vfx_id}")
        purpose = (v.purpose or "").strip().lower()
        if not purpose or purpose == "none" and (v.intensity or 0) > 0:
            issues.append(f"vfx_without_purpose:{v.vfx_id}")
        elif purpose not in VFX_PURPOSES:
            issues.append(f"vfx_invalid_purpose:{v.vfx_id}:{purpose}")
        if float(v.end_time) < float(v.start_time):
            issues.append(f"vfx_negative_span:{v.vfx_id}")
        if float(v.end_time) == float(v.start_time) and purpose not in ("none",):
            issues.append(f"vfx_zero_duration:{v.vfx_id}")
        if v.approval_status not in ("approved", "draft", ""):
            issues.append(f"vfx_unapproved:{v.vfx_id}")
        # Noise effects without storytelling purpose
        if purpose in ("", "none") and any(x in (v.target or "").lower() for x in NOISE_TRANSITIONS):
            issues.append(f"unmotivated_vfx:{v.vfx_id}")
        if v.scene_id in bounds:
            s0, s1 = bounds[v.scene_id]
            if v.start_time < s0 - 1e-3 or v.end_time > s1 + 1e-3:
                issues.append(f"vfx_outside_scene_bounds:{v.vfx_id}")
        # Excessive intensity
        if float(v.intensity) > 1.0 or float(v.intensity) < 0:
            issues.append(f"vfx_intensity_out_of_range:{v.vfx_id}")
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def validate_transition_directives(
    directives: list[TransitionDirective] | list[dict[str, Any]],
    *,
    scene_interval: dict[str, float] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    intervals = scene_interval or {}
    for raw in directives or []:
        t = raw if isinstance(raw, TransitionDirective) else TransitionDirective(
            source_scene=str(raw.get("source_scene") or ""),
            destination_scene=str(raw.get("destination_scene") or ""),
            type=str(raw.get("type") or "cut"),
            duration=float(raw.get("duration") or 0),
            reason=str(raw.get("reason") or ""),
            timing=float(raw.get("timing") or 0),
        )
        tr = validate_transition(t.type, scene_purpose=t.reason)
        issues.extend(tr.get("issues") or [])
        if (t.type or "").lower() in NOISE_TRANSITIONS and not (t.reason or "").strip():
            issues.append(f"transition_missing_reason:{t.source_scene}->{t.destination_scene}")
        if float(t.duration) < 0:
            issues.append("transition_negative_duration")
        # Transition longer than available interval at boundary
        key = f"{t.source_scene}->{t.destination_scene}"
        avail = intervals.get(key) or intervals.get(t.source_scene)
        if avail is not None and float(t.duration) > float(avail) + 1e-6:
            issues.append(f"transition_longer_than_interval:{key}")
        if (t.type or "cut").lower() not in ALLOWED_TRANSITION_TYPES | NOISE_TRANSITIONS:
            issues.append(f"unknown_transition_type:{t.type}")
    # Excessive frequency: noise transitions more than half of cuts
    noise_n = sum(1 for d in directives or [] if str(getattr(d, "type", None) or (d.get("type") if isinstance(d, dict) else "")).lower() in NOISE_TRANSITIONS)
    if noise_n >= 3 and noise_n > max(1, len(directives or []) // 2):
        issues.append("excessive_transition_frequency")
    status = "BLOCK" if any(
        i.startswith("unmotivated_") or i.startswith("transition_longer") or i.startswith("transition_negative")
        for i in issues
    ) else ("WARN" if issues else "PASS")
    if any(i.startswith("transition_longer") or i.startswith("unmotivated_") for i in issues):
        status = "BLOCK"
    return {"status": status, "issues": list(dict.fromkeys(issues)), "method": "DETERMINISTIC"}
