"""Purposeful transitions — simple cuts preferred. Deep VFX is PHASE-09."""
from __future__ import annotations

from typing import Any

ALLOWED_TRANSITIONS = {"cut", "dissolve", "fade", "none"}
NOISE_TRANSITIONS = {"zoom", "flash", "spin", "glitch", "wipe", "shake"}


def validate_transition(transition_intent: str, *, scene_purpose: str = "") -> dict[str, Any]:
    t = (transition_intent or "cut").strip().lower() or "cut"
    issues: list[str] = []
    if t in NOISE_TRANSITIONS:
        if not scene_purpose or scene_purpose in ("none", "random", ""):
            issues.append(f"unmotivated_transition:{t}")
        elif "glitch" in scene_purpose or t in (scene_purpose or ""):
            pass  # explicit purpose
        else:
            issues.append(f"unmotivated_transition:{t}")
    elif t not in ALLOWED_TRANSITIONS:
        issues.append(f"unknown_transition:{t}")
    status = "BLOCK" if any(i.startswith("unmotivated_") for i in issues) else (
        "WARN" if issues else "PASS"
    )
    return {"status": status, "issues": issues, "transition": t, "method": "DETERMINISTIC"}


def validate_music_emotion(*, music_mood: str, scene_emotion: str) -> dict[str, Any]:
    mood = (music_mood or "").lower()
    emo = (scene_emotion or "").lower()
    issues: list[str] = []
    tragic = any(x in emo for x in ("tragic", "sad", "grief", "mourning", "solemn"))
    calm = any(x in emo for x in ("calm", "neutral", "explanatory", "informative"))
    if tragic and any(x in mood for x in ("happy", "upbeat", "party", "comic")):
        issues.append("music_emotional_mismatch")
    if calm and any(x in mood for x in ("high-energy", "drop", "battle", "trap")):
        issues.append("music_energy_mismatch")
    return {"status": "BLOCK" if issues else "PASS", "issues": issues, "method": "DETERMINISTIC"}


def validate_sfx_purpose(sfx_events: list[dict[str, Any]], *, narration: str = "") -> dict[str, Any]:
    issues: list[str] = []
    for ev in sfx_events or []:
        if not isinstance(ev, dict):
            continue
        purpose = str(ev.get("purpose") or ev.get("reason") or "").strip()
        name = str(ev.get("name") or ev.get("id") or "")
        if not purpose:
            issues.append(f"sfx_without_purpose:{name}")
    return {"status": "BLOCK" if issues else "PASS", "issues": issues, "method": "DETERMINISTIC"}
