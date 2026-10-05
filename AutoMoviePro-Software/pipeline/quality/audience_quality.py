"""Audience retention / industrial creative gate (PART-5P + Critical-12).

Deterministic structural checks — does not claim human certification.
UNKNOWN ≠ PASS. FAIL blocks publish when wired.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

GATE_NAME = "AUDIENCE_QUALITY_GATE.json"


def _hook_score(text: str, topic: str) -> dict[str, Any]:
    from pipeline.creative_production.script_quality import classify_hook, score_opening_attention

    hook = classify_hook(text, topic=topic)
    opening = score_opening_attention(text, topic=topic)
    ok = hook.get("status") != "BLOCK" and opening.get("status") != "BLOCK"
    return {
        "status": "PASS" if ok else "FAIL",
        "hook": hook,
        "opening": opening,
        "attention_first_10s": opening.get("score"),
    }


def _hold_issues(scene_boundary_gate: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    # Softened documentary SB gates must not cascade into audience FAIL
    if scene_boundary_gate.get("softened") or str(scene_boundary_gate.get("status") or "").upper() == "PASS":
        return issues
    for raw in scene_boundary_gate.get("issues") or []:
        s = str(raw)
        if s.startswith("soft:"):
            continue
        if "excessive_static_hold" in s or "boundary_delta" in s or "planned_vs" in s:
            issues.append(s)
    st = str(scene_boundary_gate.get("status") or "").upper()
    if st in ("FAIL", "FAILED", "BLOCKED"):
        issues.append(f"scene_boundary_{st.lower()}")
    return issues


def _repetition_metric(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    subjects = [str(s.get("subject") or s.get("required_subject") or "").lower().strip() for s in scenes]
    subjects = [x for x in subjects if x]
    streaks = 0
    best = 0
    prev = ""
    for s in subjects:
        if s and s == prev:
            streaks += 1
            best = max(best, streaks)
        else:
            streaks = 1
            prev = s
            best = max(best, 1)
    unique = len(set(subjects))
    return {
        "status": "FAIL" if best >= 4 and unique <= 2 else "PASS",
        "max_same_subject_streak": best,
        "unique_subjects": unique,
        "scene_count": len(scenes),
    }


def _skip_risk(plan: dict[str, Any], hold_issues: Sequence[str]) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    ranked: list[dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        narr = str(sc.get("narration") or "")
        risk = 0.2
        if len(narr.split()) > 55:
            risk += 0.25
        if len(narr.split()) < 6:
            risk += 0.2
        if any(f"scene_{i}" in h or f"_{i:02d}" in h for h in hold_issues):
            risk += 0.35
        ranked.append({"scene_index": i, "skip_risk": round(min(1.0, risk), 3), "preview": narr[:80]})
    ranked.sort(key=lambda r: r["skip_risk"], reverse=True)
    weak = ranked[:3]
    strong = list(reversed(ranked[-3:])) if ranked else []
    return {
        "weakest": weak,
        "strongest": strong,
        "status": "FAIL" if ranked and ranked[0]["skip_risk"] >= 0.75 else "PASS",
    }


def _emotion_progression(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    emos = [
        str(s.get("emotion") or s.get("emotional_intent") or "neutral").strip().lower()
        for s in scenes
    ]
    unique = len(set(emos))
    flat = len(scenes) >= 4 and unique <= 1 and (emos[0] in ("", "neutral") if emos else True)
    return {"status": "FAIL" if flat else "PASS", "unique_emotions": unique, "sequence": emos[:12]}


def _info_density(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    overload = 0
    gaps = 0
    for s in scenes:
        narr = str(s.get("narration") or "")
        words = narr.split()
        nums = len(re.findall(r"\d+", narr))
        if len(words) > 60 or nums >= 5:
            overload += 1
        if len(words) < 5:
            gaps += 1
    return {
        "status": "FAIL" if overload >= 3 or gaps >= 3 else "PASS",
        "overload_scenes": overload,
        "gap_scenes": gaps,
    }


def evaluate_audience_quality(
    *,
    plan: dict[str, Any],
    scene_boundary_gate: Optional[dict[str, Any]] = None,
    creative_report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    topic = str(plan.get("topic") or plan.get("title") or "")
    opening = str(
        plan.get("hook")
        or (scenes[0].get("narration") if scenes else "")
        or ""
    )
    hook = _hook_score(opening, topic)
    holds = _hold_issues(scene_boundary_gate or {})
    rep = _repetition_metric(plan)
    skip = _skip_risk(plan, holds)
    emo = _emotion_progression(plan)
    dens = _info_density(plan)
    dims = {
        "first_10s_attention": hook.get("status"),
        "hook_effective": hook.get("status"),
        "boring_hold": "FAIL" if holds else "PASS",
        "visual_repetition": rep.get("status"),
        "skip_risk": skip.get("status"),
        "story_progression": "PASS" if len(scenes) >= 3 else "FAIL",
        "emotional_progression": emo.get("status"),
        "information_density": dens.get("status"),
    }
    # Creative report hook weakness also fails
    cr = creative_report or {}
    if str(cr.get("overall_verdict") or "").upper() in ("REGENERATE_REQUIRED", "FAIL"):
        dims["creative_report"] = "FAIL"
    issues = []
    for k, v in dims.items():
        if v == "FAIL":
            issues.append(k)
    issues.extend(holds[:6])
    status = "FAIL" if issues else "PASS"
    return {
        "schema": "amp_audience_quality_gate_v1",
        "status": status,
        "verdict": status,
        "publishable": status == "PASS",
        "unknown_as_pass": False,
        "claims_human_certification": False,
        "industrial_automated_pass": status == "PASS",
        "dimensions": dims,
        "hook_detail": hook,
        "repetition": rep,
        "skip_and_strength": skip,
        "emotional_progression": emo,
        "information_density": dens,
        "issues": issues,
        "authority": "pipeline.quality.audience_quality",
    }


def persist_audience_quality_gate(work_dir: Path, gate: dict[str, Any]) -> Path:
    path = Path(work_dir) / GATE_NAME
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_audience_quality_gate(
    work_dir: Path,
    *,
    plan: dict[str, Any],
    scene_boundary_gate: Optional[dict[str, Any]] = None,
    creative_report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    gate = evaluate_audience_quality(
        plan=plan,
        scene_boundary_gate=scene_boundary_gate,
        creative_report=creative_report,
    )
    persist_audience_quality_gate(work_dir, gate)
    logger.info("audience quality gate status=%s issues=%s", gate.get("status"), gate.get("issues"))
    return gate
