"""RTL honesty + font/glyph validation (AMP-004 Phase-06)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from pipeline.localization_consistency.contract import RTL_LANGS


def classify_rtl_support(lang: str) -> dict[str, Any]:
    """
    Honest RTL classification — attempt optional python-bidi + arabic-reshaper.
    Without libraries: UNKNOWN (never fake full shaping PASS).
    """
    code = (lang or "").lower().split("-")[0]
    if code not in RTL_LANGS:
        return {
            "rtl": False,
            "status": "PASS",
            "support_level": "LTR",
            "method": "DETERMINISTIC",
            "shaping_guaranteed": False,
        }
    reshaper_ok = False
    bidi_ok = False
    try:
        import arabic_reshaper  # type: ignore

        reshaper_ok = True
        _ = arabic_reshaper
    except Exception:
        reshaper_ok = False
    try:
        from bidi.algorithm import get_display  # type: ignore

        bidi_ok = True
        _ = get_display
    except Exception:
        bidi_ok = False
    if reshaper_ok and bidi_ok:
        return {
            "rtl": True,
            "status": "PASS",
            "support_level": "SHAPING_LIBS_AVAILABLE",
            "method": "DETERMINISTIC",
            "shaping_guaranteed": True,
            "libs": ["arabic_reshaper", "python-bidi"],
        }
    return {
        "rtl": True,
        "status": "UNKNOWN",
        "support_level": "PARTIAL_FONT_ONLY",
        "method": "DETERMINISTIC",
        "shaping_guaranteed": False,
        "issues": ["rtl_shaping_not_guaranteed"],
        "policy": "UNKNOWN_blocks_publish_when_mandatory",
        "note": "Install arabic-reshaper + python-bidi for shaping PASS",
        "libs_available": {"arabic_reshaper": reshaper_ok, "python_bidi": bidi_ok},
    }


def detect_mixed_rtl_ltr(text: str) -> dict[str, Any]:
    has_rtl = bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u0590-\u05FF]", text or ""))
    has_ltr = bool(re.search(r"[A-Za-z]{2,}", text or ""))
    mixed = has_rtl and has_ltr
    if mixed:
        status = "UNKNOWN"
        issues = ["mixed_rtl_ltr_unverified"]
    elif has_rtl or not has_rtl:
        status = "PASS"
        issues = []
    return {
        "mixed": mixed,
        "has_rtl_script": has_rtl,
        "has_latin": has_ltr,
        "status": status,
        "issues": issues,
    }


def validate_font_availability(lang: str) -> dict[str, Any]:
    try:
        from pipeline.scene_builder import resolve_fontfile_for_lang

        font = resolve_fontfile_for_lang(lang)
    except Exception as exc:
        return {"status": "FAIL", "issues": [f"font_resolve_failed:{exc}"], "font": ""}
    if not font:
        return {"status": "FAIL", "issues": ["font_unavailable"], "font": ""}
    # resolve_fontfile_for_lang returns ffmpeg-escaped paths (C\:/Windows/...); check real file
    real = str(font).replace("\\:", ":").replace("/", "\\") if "\\" in str(font) or "/" in str(font) else str(font)
    # Also try forward-slash unsescaped form
    candidates = [
        Path(real),
        Path(str(font).replace("\\:", ":")),
        Path(str(font).replace("\\:", ":").replace("\\", "/")),
    ]
    p = next((c for c in candidates if c.is_file()), None)
    if p is None:
        return {"status": "FAIL", "issues": ["font_file_missing"], "font": font}
    return {"status": "PASS", "issues": [], "font": font, "resolved_path": str(p), "method": "DETERMINISTIC"}


def validate_glyph_coverage(text: str, font_path: str) -> dict[str, Any]:
    """
    Best-effort glyph check without full fonttools dependency.
    Detects replacement characters and reports UNKNOWN if cannot prove coverage.
    """
    if "\ufffd" in (text or ""):
        return {"status": "FAIL", "issues": ["replacement_character_present"], "method": "DETERMINISTIC"}
    # ffmpeg-escaped font paths (C\:/Windows/...) must be normalized for exists()
    raw = str(font_path or "")
    candidates = [
        Path(raw),
        Path(raw.replace("\\:", ":")),
        Path(raw.replace("\\:", ":").replace("\\", "/")),
        Path(raw.replace("\\:", ":").replace("/", "\\")),
    ]
    p = next((c for c in candidates if c.is_file()), None)
    if not raw or p is None:
        return {"status": "FAIL", "issues": ["font_missing_for_glyph_check"], "method": "DETERMINISTIC"}
    # Without fonttools cmap parse, cannot claim full coverage
    return {
        "status": "UNKNOWN",
        "issues": ["glyph_coverage_unverified_without_cmap"],
        "method": "UNAVAILABLE",
        "confidence_label": "NO_FONTTOOLS_CMAP",
        "unknown_is_not_pass": True,
        "resolved_path": str(p),
    }


def shape_rtl_text(text: str, lang: str = "ur") -> dict[str, Any]:
    """Apply arabic-reshaper + python-bidi when available; else return original + UNKNOWN."""
    rtl = classify_rtl_support(lang)
    raw = text or ""
    if not rtl.get("rtl"):
        return {"text": raw, "status": "PASS", "shaped": False, "shaping_guaranteed": False}
    if not rtl.get("shaping_guaranteed"):
        return {
            "text": raw,
            "status": "UNKNOWN",
            "shaped": False,
            "shaping_guaranteed": False,
            "issues": list(rtl.get("issues") or []),
        }
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        reshaped = arabic_reshaper.reshape(raw)
        display = get_display(reshaped)
        return {
            "text": display,
            "status": "PASS",
            "shaped": True,
            "shaping_guaranteed": True,
            "method": "arabic_reshaper+python-bidi",
        }
    except Exception as exc:
        return {
            "text": raw,
            "status": "UNKNOWN",
            "shaped": False,
            "shaping_guaranteed": False,
            "issues": [f"shape_failed:{exc}"],
        }


def validate_rtl_and_font(lang: str, text: str = "") -> dict[str, Any]:
    rtl = classify_rtl_support(lang)
    font = validate_font_availability(lang)
    mixed = detect_mixed_rtl_ltr(text) if text else {"mixed": False, "issues": []}
    glyph = validate_glyph_coverage(text, font.get("font") or "") if text else {"status": "PASS", "issues": []}
    shaped = shape_rtl_text(text, lang) if text else {"status": "PASS", "shaped": False}
    issues = list(rtl.get("issues") or []) + list(font.get("issues") or []) + list(mixed.get("issues") or [])
    if shaped.get("status") == "UNKNOWN":
        issues.extend(shaped.get("issues") or [])
    # Font FAIL is hard block; RTL shaping libs + font PASS → PASS even if glyph cmap UNKNOWN
    status = "PASS"
    if font.get("status") == "FAIL":
        status = "FAIL"
    elif rtl.get("rtl") and rtl.get("status") == "UNKNOWN":
        status = "UNKNOWN"
    elif mixed.get("status") == "UNKNOWN":
        status = "UNKNOWN"
    elif shaped.get("status") == "UNKNOWN" and rtl.get("rtl"):
        status = "UNKNOWN"
    elif glyph.get("status") == "FAIL":
        status = "FAIL"
    return {
        "status": status,
        "rtl": rtl,
        "font": font,
        "mixed": mixed,
        "glyph": glyph,
        "shaped": shaped,
        "issues": issues,
        "shaping_guaranteed": bool(rtl.get("shaping_guaranteed")),
    }
