"""Text/subtitle integrity at render boundary — reuses Phase-06 authorities."""
from __future__ import annotations

from typing import Any, Optional


def validate_render_text(
    *,
    text: str,
    language: str = "en",
    font_path: str = "",
    max_chars_per_line: int = 42,
    safe_area: bool = True,
    overflow: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []
    if overflow:
        issues.append("subtitle_overflow")
    if not safe_area:
        issues.append("text_outside_safe_area")
    lines = (text or "").splitlines() or [text or ""]
    for line in lines:
        if len(line) > max_chars_per_line * 2:
            issues.append("text_line_excessive")
    # Glyph / font via P06 when available
    try:
        from pipeline.localization_consistency.rtl_font import (
            classify_rtl_support,
            validate_font_availability,
            validate_glyph_coverage,
        )

        rtl = classify_rtl_support(language)
        if rtl.get("status") == "UNKNOWN" and language.lower()[:2] in ("ar", "ur", "fa", "he"):
            issues.append("rtl_shaping_unknown")
        fa = validate_font_availability(language)
        if fa.get("status") == "FAIL":
            issues.extend(fa.get("issues") or ["font_unavailable"])
        if font_path:
            gc = validate_glyph_coverage(text, font_path)
            if gc.get("status") == "FAIL":
                issues.extend(gc.get("issues") or ["missing_glyph"])
            if gc.get("status") == "UNKNOWN":
                issues.append("glyph_coverage_unknown")
    except Exception:
        if any(ord(c) > 127 for c in (text or "")) and not font_path:
            issues.append("glyph_coverage_unknown")
    hard = [i for i in issues if i in ("subtitle_overflow", "text_outside_safe_area", "missing_glyph", "font_unavailable")]
    unknown = [i for i in issues if i.endswith("_unknown")]
    if hard:
        status = "BLOCK"
    elif unknown:
        status = "UNKNOWN"
    elif issues:
        status = "WARN"
    else:
        status = "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}
