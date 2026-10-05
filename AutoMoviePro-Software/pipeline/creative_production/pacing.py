"""Dialogue pacing representation — scene-bound, not one global timing model."""
from __future__ import annotations

import re
from typing import Any


def dialogue_pacing_plan(text: str, *, emotion: str = "", duration_target_sec: float | None = None) -> dict[str, Any]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]
    pauses: list[dict[str, Any]] = []
    pos = 0
    for i, s in enumerate(sentences):
        words = s.split()
        pos += len(words)
        kind = "beat"
        if i == len(sentences) - 1:
            kind = "close"
        elif "?" in s:
            kind = "question"
        elif emotion.lower() in ("urgent", "warning", "serious") and i == 0:
            kind = "emphasis"
        pauses.append({"after_sentence": i, "kind": kind, "approx_words": len(words)})
    wps = 2.4
    est = (len((text or "").split()) / wps) if text else 0.0
    return {
        "sentence_count": len(sentences),
        "pause_intent": pauses,
        "estimated_sec": round(est, 2),
        "duration_target_sec": duration_target_sec,
        "emotion": emotion,
        "method": "HEURISTIC",
    }


def validate_dialogue_visual_sync(
    *,
    narration: str,
    visual_intent: str,
    primary_action: str = "",
) -> dict[str, Any]:
    issues: list[str] = []
    n = (narration or "").lower()
    v = f"{visual_intent} {primary_action}".lower()
    pairs = (
        ("opens the door", ("eat", "eating", "food")),
        ("sits on a chair", ("floor", "ground")),
        ("sits on the floor", ("chair",)),
        ("camera has improved", ("transforms", "becomes a camera", "giant camera")),
    )
    for said, bad_vis in pairs:
        if said in n and any(b in v for b in bad_vis):
            issues.append(f"dialogue_visual_mismatch:{said}")
    return {"status": "BLOCK" if issues else "PASS", "issues": issues, "method": "DETERMINISTIC"}
