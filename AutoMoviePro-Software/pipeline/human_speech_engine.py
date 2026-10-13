"""Human Speech Engine — Story → Human Speech → Performance (protocol §25–31)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pipeline.robot_detector import robot_score


def story_writer(topic: str, fact_claims: Optional[List[str]] = None) -> Dict[str, Any]:
    claims = [c for c in (fact_claims or []) if str(c).strip()]
    hook = f"What if everything you knew about {topic} was only half the dig?"
    context = f"Researchers still argue over how {topic} fit into power, belief, and daily survival."
    conflict = "One trench note refuses to fit the old timeline."
    evidence = claims[0] if claims else f"Tool marks and dated layers keep forcing harder questions about {topic}."
    reveal = claims[1] if len(claims) > 1 else "The pattern only appears when you line the finds against the sky."
    payoff = "That single alignment changes what the ruins are allowed to mean."
    ending = "The map is still unfinished — and the next cut may rewrite it again."
    return {
        "stage": "story_writer",
        "hook": hook,
        "context": context,
        "conflict": conflict,
        "evidence": evidence,
        "reveal": reveal,
        "payoff": payoff,
        "ending": ending,
    }


def human_speech_editor(story: Dict[str, Any]) -> Dict[str, Any]:
    """Convert plan beats into spoken prose with variation."""
    order = ["hook", "context", "conflict", "evidence", "reveal", "payoff", "ending"]
    lines: List[str] = []
    for key in order:
        raw = str(story.get(key) or "").strip()
        if not raw:
            continue
        # Contractions / shorter cuts
        t = raw.replace("What if everything you knew", "What if everything you'd heard")
        t = t.replace("Researchers still argue", "Researchers still fight")
        t = re.sub(r"\s+", " ", t).strip()
        if not t.endswith((".", "?", "!")):
            t += "."
        lines.append(t)
    audit = robot_score(lines)
    return {
        "stage": "human_speech_editor",
        "lines": lines,
        "robot_audit": audit,
        "passed": bool(audit.get("passed")),
    }


def performance_editor(
    lines: List[str],
    *,
    drama_level: float = 1.0,
) -> Dict[str, Any]:
    """Attach fine-tuned pause/emphasis/breath and speech drama metadata for TTS pacing."""
    beats: List[Dict[str, Any]] = []
    dramatic_cues = {"secret", "truth", "refuses", "changes", "pattern", "forbidden", "why", "shock", "never", "only"}

    for i, line in enumerate(lines):
        words = line.split()
        emphasis = []
        for w in words:
            if w[:1].isupper() and len(w) > 3:
                emphasis.append(w.strip(".,!?"))

        # Detect dramatic tension
        lower_line = line.lower()
        is_question = "?" in line
        has_cue = any(c in lower_line for c in dramatic_cues)
        is_closing_hook = i == len(lines) - 1 or i in (0, 2)

        # Fine-tune speech drama and pause controls
        if is_question or (has_cue and is_closing_hook):
            drama_mode = "dramatic_cadence"
            pause_after = 0.45 * drama_level
            speed = 0.92
        elif is_closing_hook:
            drama_mode = "revelation_pause"
            pause_after = 0.38 * drama_level
            speed = 0.95
        else:
            drama_mode = "narrative_flow"
            pause_after = 0.20
            speed = 1.0

        pause_before = 0.20 if (has_cue and i > 0) else (0.15 if i > 0 else 0.0)

        beats.append(
            {
                "index": i,
                "text": line,
                "pause_before_sec": round(pause_before, 2),
                "pause_after_sec": round(pause_after, 2),
                "emphasis": emphasis[:3],
                "speed": round(speed, 2),
                "breath_point": i % 2 == 1,
                "drama_mode": drama_mode,
                "drama_intensity": round(0.85 if is_closing_hook else 0.60, 2),
            }
        )
    return {"stage": "performance_editor", "beats": beats}


def run_human_speech_pipeline(
    topic: str,
    *,
    fact_claims: Optional[List[str]] = None,
) -> Dict[str, Any]:
    story = story_writer(topic, fact_claims)
    human = human_speech_editor(story)
    perf = performance_editor(list(human.get("lines") or []))
    return {
        "topic": topic,
        "story": story,
        "human": human,
        "performance": perf,
        "passed": bool(human.get("passed")),
        "version": "v1",
    }


def attach_speech_to_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    plan = dict(plan or {})
    topic = str(plan.get("topic") or "")
    claims = []
    for s in plan.get("scenes") or []:
        if isinstance(s, dict) and s.get("narration"):
            claims.append(str(s.get("narration")))
    pipe = run_human_speech_pipeline(topic, fact_claims=claims[:4])
    plan["human_speech_engine"] = {
        "passed": pipe.get("passed"),
        "robot_audit": (pipe.get("human") or {}).get("robot_audit"),
        "performance_beats": len((pipe.get("performance") or {}).get("beats") or []),
    }
    # Optional: annotate first scenes with performance metadata
    beats = (pipe.get("performance") or {}).get("beats") or []
    scenes = []
    for i, sc in enumerate(plan.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        if i < len(beats):
            row["performance"] = {
                "pause_after_sec": beats[i].get("pause_after_sec"),
                "emphasis": beats[i].get("emphasis"),
                "speed": beats[i].get("speed"),
            }
        scenes.append(row)
    plan["scenes"] = scenes
    return plan
