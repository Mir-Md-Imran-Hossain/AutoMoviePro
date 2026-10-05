"""Robot / essay-like speech detector for Human Speech Engine."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

GENERIC_OPENERS = (
    "in today's video",
    "hey guys",
    "welcome back",
    "without further ado",
    "in this video we will",
    "let's dive in",
)
GENERIC_ENDS = (
    "like and subscribe",
    "thanks for watching",
    "see you in the next",
    "hit the bell",
)
BUZZ = (
    "revolutionary",
    "game-changer",
    "game changer",
    "unlock",
    "seamless",
    "cutting-edge",
    "leverage",
    "synergy",
    "delve",
)


def robot_score(texts: Sequence[str]) -> Dict[str, Any]:
    lines = [str(t or "").strip() for t in texts if str(t or "").strip()]
    issues: List[str] = []
    if not lines:
        return {"score": 1.0, "verdict": "FAIL", "issues": ["empty"], "passed": False}

    blob = " ".join(lines).lower()
    for g in GENERIC_OPENERS:
        if blob.startswith(g) or f". {g}" in blob:
            issues.append(f"generic_opener:{g}")
    for g in GENERIC_ENDS:
        if g in blob:
            issues.append(f"generic_ending:{g}")

    buzz_hits = sum(1 for b in BUZZ if b in blob)
    if buzz_hits >= 2:
        issues.append(f"buzzword_density:{buzz_hits}")

    # Repetitive transitions
    transitions = re.findall(r"\b(moreover|furthermore|additionally|in conclusion)\b", blob)
    if len(transitions) >= 2:
        issues.append("repeated_transition")

    # Sentence length symmetry (too uniform)
    lengths = [len(l.split()) for l in lines]
    if len(lengths) >= 4:
        avg = sum(lengths) / len(lengths)
        var = sum((x - avg) ** 2 for x in lengths) / len(lengths)
        if var < 2.5 and avg > 12:
            issues.append("overly_symmetrical_sentences")

    # Low specificity: few digits / proper-ish tokens
    specifics = len(re.findall(r"\d|[A-Z][a-z]{3,}", " ".join(lines)))
    if specifics < 2 and len(blob.split()) > 40:
        issues.append("low_specificity")

    # Score 0 = human, 1 = robot
    score = min(1.0, 0.15 * len(set(issues)) + 0.08 * buzz_hits)
    passed = score < 0.45 and "generic_opener" not in str(issues)
    # soften: any generic opener fails
    if any(i.startswith("generic_opener") for i in issues):
        passed = False
        score = max(score, 0.6)
    return {
        "score": round(score, 3),
        "verdict": "PASS" if passed else "FAIL",
        "passed": passed,
        "issues": issues,
        "prompt_version": "human_speech_editor:v1",
    }


def evaluate_plan_speech(plan: Dict[str, Any]) -> Dict[str, Any]:
    narrs = [
        str(s.get("narration") or "")
        for s in (plan.get("scenes") or [])
        if isinstance(s, dict)
    ]
    return robot_score(narrs)
