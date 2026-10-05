"""TextPlan layout / overflow / safe-area / effects (AMP-004 Phase-06)."""
from __future__ import annotations

from typing import Any

from pipeline.localization_consistency.contract import TEXT_TYPES, TextElement, TextPlan


ALLOWED_EFFECTS = frozenset({"none", "fade", "slide", "scale", "highlight"})


def validate_text_effect(effect: str, *, purpose: str = "") -> list[str]:
    issues: list[str] = []
    e = (effect or "none").lower()
    if e not in ALLOWED_EFFECTS:
        issues.append(f"invalid_text_effect:{effect}")
    if e != "none" and purpose.upper() == "WATERMARK":
        issues.append("purposeless_watermark_animation")
    # random/noise effects banned
    if e in ("shake", "glitch", "spin", "random"):
        issues.append("non_purposeful_text_effect")
    return issues


def validate_text_overflow(
    element: TextElement,
    *,
    frame_w: int = 1920,
    frame_h: int = 1080,
    safe_margin_pct: float = 0.05,
    max_chars_per_line: int = 42,
) -> list[str]:
    issues: list[str] = []
    if element.max_width_pct > 1.0 or element.max_width_pct <= 0:
        issues.append("invalid_max_width")
    if element.max_height_pct > 0.5:
        issues.append("text_height_overflow_risk")
    content = element.content or ""
    purpose = (element.purpose or "").upper()
    if purpose == "SUBTITLE":
        # Full narration is cue-split at burn/write_srt time. Gate per wrapped line,
        # not the entire dialogue blob as one on-screen card.
        cpl = max(12, int(max_chars_per_line or 42))
        line = ""
        lines: list[str] = []
        for w in content.split():
            trial = (line + " " + w).strip()
            if len(trial) > cpl and line:
                lines.append(line)
                line = w
            else:
                line = trial
        if line:
            lines.append(line)
        # Hard overflow only if a single unsplittable token/line exceeds cpl*1.35
        if any(len(ln) > int(cpl * 1.35) for ln in (lines or [content])):
            issues.append("text_overflow")
    else:
        max_chars = int((frame_w * element.max_width_pct) / 18)
        if len(content) > max_chars * max(1, content.count("\n") + 1) and len(content) > 80:
            issues.append("text_overflow")
    if not element.safe_area:
        issues.append("safe_area_violation")
    # margin violation if position is edge without safe
    if element.position in ("top_left_unsafe", "bottom_edge"):
        issues.append("safe_area_violation")
    _ = (safe_margin_pct, frame_h)  # reserved for geometry solvers
    return issues


def validate_subtitle_text_collision(
    subtitle_region: str = "bottom",
    text_position: str = "bottom_center",
    *,
    overlay_purpose: str = "",
) -> list[str]:
    issues: list[str] = []
    # A SUBTITLE element is the subtitle track itself — not an overlay colliding with it.
    if (overlay_purpose or "").upper() == "SUBTITLE":
        return issues
    if subtitle_region == "bottom" and text_position in ("bottom_center", "bottom", "lower_third"):
        # lower_third + subtitle both bottom → collision risk unless prioritized
        issues.append("subtitle_text_collision")
    return issues


def validate_text_plan(plan: TextPlan, *, max_chars_per_line: int = 42) -> dict[str, Any]:
    issues: list[str] = []
    for el in plan.elements:
        if el.purpose.upper() not in TEXT_TYPES:
            issues.append(f"invalid_text_purpose:{el.purpose}")
        issues.extend(validate_text_effect(el.effect, purpose=el.purpose))
        issues.extend(validate_text_overflow(el, max_chars_per_line=max_chars_per_line))
        if el.purpose.upper() != "SUBTITLE":
            issues.extend(
                validate_subtitle_text_collision(
                    text_position=el.position, overlay_purpose=el.purpose
                )
            )
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC", "effect_policy": plan.effect_policy}


def validate_visual_text_consistency(
    *,
    visual_objects: list[str],
    text_content: str,
) -> list[str]:
    """SceneIntent-compatible text vs visual contradiction heuristics."""
    issues: list[str] = []
    objs = " ".join(visual_objects or []).lower()
    text = (text_content or "").lower()
    if "smartphone" in objs or "iphone" in objs or "phone" in objs:
        if re_search_cinema_camera(text) and "phone" not in text and "smartphone" not in text:
            issues.append("visual_text_contradiction:phone_vs_cinema_camera")
    if "historical" in objs or "ancient" in objs:
        if "iphone" in text or "smartphone" in text:
            issues.append("visual_text_contradiction:historical_vs_modern_device")
    return issues


def re_search_cinema_camera(text: str) -> bool:
    import re

    return bool(re.search(r"\b(cinema\s+camera|broadcast\s+camera|professional\s+cinema)\b", text))
