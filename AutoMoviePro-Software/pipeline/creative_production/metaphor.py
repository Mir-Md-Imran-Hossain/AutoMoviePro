"""Figurative / metaphor visualization policy (AMP-004 Phase-07)."""
from __future__ import annotations

import re
from typing import Any

METAPHOR_PATTERNS = (
    (r"heart of the (city|nation|system)", "figurative_core", "do_not_show_anatomical_heart"),
    (r"camera powerhouse", "figurative_capability", "do_not_show_power_station_or_transform"),
    (r"war on (misinformation|cancer|drugs)", "figurative_conflict", "do_not_show_literal_warfare"),
    (r"exploding growth", "figurative_increase", "do_not_show_explosion"),
    (r"tsunami of", "figurative_volume", "do_not_show_literal_tsunami"),
    (r"flood of", "figurative_volume", "do_not_show_literal_flood"),
    (r"the phone is a camera", "metonymy_feature", "show_phone_with_camera_module_not_replacement"),
)


def detect_figurative_language(text: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    raw = text or ""
    for pat, meaning, policy in METAPHOR_PATTERNS:
        if re.search(pat, raw, re.I):
            hits.append(
                {
                    "span": pat,
                    "literal_meaning": "not visual-literal",
                    "figurative_meaning": meaning,
                    "visualization_policy": policy,
                }
            )
    return hits


def validate_metaphor_visualization(narration: str, visual_text: str = "") -> dict[str, Any]:
    hits = detect_figurative_language(narration)
    issues: list[str] = []
    vis = (visual_text or "").lower()
    for h in hits:
        pol = h["visualization_policy"]
        if "anatomical_heart" in pol and re.search(r"\b(heart organ|bloody heart|anatomical heart)\b", vis):
            issues.append("metaphor_literalized:heart")
        if "power_station" in pol and re.search(r"\b(power plant|explosion|morph)\b", vis):
            issues.append("metaphor_literalized:powerhouse")
        if "warfare" in pol and re.search(r"\b(soldiers|battlefield|guns|explosion)\b", vis):
            issues.append("metaphor_literalized:war")
        if "explosion" in pol and re.search(r"\b(explosion|blast|fireball)\b", vis):
            issues.append("metaphor_literalized:exploding_growth")
        if "tsunami" in pol and "tsunami" in vis:
            issues.append("metaphor_literalized:tsunami")
        if "flood" in pol and re.search(r"\bflood(?:ed|ing)?\b", vis):
            issues.append("metaphor_literalized:flood")
        if "not_replacement" in pol and re.search(r"\b(becomes a camera|transforms into)\b", vis):
            issues.append("metaphor_literalized:phone_is_camera")
    return {
        "status": "BLOCK" if issues else "PASS",
        "issues": issues,
        "hits": hits,
        "policy": "literal_unless_explicit",
        "method": "DETERMINISTIC",
    }


def figurative_negative_constraints(hits: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    for h in hits:
        out.append(f"DO NOT visually literalize: {h.get('figurative_meaning')}")
        out.append(str(h.get("visualization_policy") or ""))
    if hits:
        out.append("DO NOT perform multiple incompatible actions simultaneously")
        out.append("DO NOT add objects not required by the scene")
    return [x for x in out if x]
