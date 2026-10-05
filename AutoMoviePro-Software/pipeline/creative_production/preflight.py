"""Deterministic creative preflight BEFORE expensive provider calls."""
from __future__ import annotations

from typing import Any, Optional

from pipeline.creative_production.action_entity import (
    parse_action_atoms,
    validate_action_atomicity,
    validate_entity_attribute_ownership,
    validate_physical_plausibility_heuristic,
)
from pipeline.creative_production.camera import validate_shot_purpose
from pipeline.creative_production.contract import CreativeProductionPlan, ScenePurpose
from pipeline.creative_production.metaphor import validate_metaphor_visualization
from pipeline.creative_production.pacing import validate_dialogue_visual_sync
from pipeline.creative_production.script_quality import classify_hook, validate_script_structure
from pipeline.creative_production.transitions import validate_transition


class CreativePreflightError(RuntimeError):
    def __init__(self, message: str, *, issues: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


def preflight_script_generation_request(
    spec: Any,
    *,
    block: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []
    job_id = str(getattr(spec, "job_id", "") or "")
    topic = str(getattr(spec, "topic", "") or "")
    language = str(getattr(spec, "language", "") or "en")
    niche = str(getattr(spec, "niche", "") or "")
    if not job_id.strip():
        issues.append("missing_job_id")
    if not topic.strip():
        issues.append("missing_topic")
    if not language.strip():
        issues.append("missing_language")
    if language.strip().lower() in ("xx", "invalid", "und"):
        issues.append("invalid_language")
    if not niche.strip():
        issues.append("missing_niche")
    status = "BLOCK" if issues else "PASS"
    if block and status == "BLOCK":
        raise CreativePreflightError("creative_script_preflight_blocked", issues=issues)
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def preflight_scene_purpose(purpose: ScenePurpose | dict[str, Any], *, block: bool = True) -> dict[str, Any]:
    if isinstance(purpose, ScenePurpose):
        data = purpose.to_dict()
    else:
        data = dict(purpose or {})
    issues: list[str] = []
    if not str(data.get("scene_id") or "").strip():
        issues.append("missing_scene_id")
    if not str(data.get("purpose") or "").strip():
        issues.append("scene_without_purpose")
    if not str(data.get("narrative_role") or "").strip():
        issues.append("missing_narrative_role")
    status = "BLOCK" if issues else "PASS"
    if block and status == "BLOCK":
        raise CreativePreflightError("scene_purpose_preflight_blocked", issues=issues)
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def preflight_creative_generation(
    *,
    plan: Optional[dict[str, Any]] = None,
    cpp: Optional[CreativeProductionPlan] = None,
    scenes: Optional[list[dict[str, Any]]] = None,
    block: bool = True,
) -> dict[str, Any]:
    src = dict(plan or {})
    rows = list(scenes if scenes is not None else (src.get("scenes") or []))
    issues: list[str] = []
    struct = validate_script_structure(src, scenes=rows)
    issues.extend(struct.get("issues") or [])
    if cpp:
        if not cpp.scenes:
            issues.append("creative_plan_has_no_scene_purpose")
        for sp in cpp.scenes:
            r = preflight_scene_purpose(sp, block=False)
            issues.extend(r.get("issues") or [])
        if cpp.hook:
            hk = classify_hook(cpp.hook.text, topic=cpp.topic)
            issues.extend(hk.get("issues") or [])
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        narr = str(row.get("narration") or "")
        vis = str(row.get("visual_intent") or row.get("visual_prompt") or "")
        atoms = parse_action_atoms(narr)
        # mark simultaneous if caller said so
        if row.get("simultaneous_actions"):
            for a in atoms:
                a.relation = "simultaneous"
        issues.extend(validate_action_atomicity(atoms).get("issues") or [])
        issues.extend(
            validate_entity_attribute_ownership(narration=narr, visual_text=vis).get("issues") or []
        )
        issues.extend(validate_metaphor_visualization(narr, vis).get("issues") or [])
        issues.extend(
            validate_dialogue_visual_sync(
                narration=narr, visual_intent=vis, primary_action=str(row.get("primary_action") or "")
            ).get("issues")
            or []
        )
        shot = validate_shot_purpose(
            shot_type=str(row.get("shot_type") or (cpp.scenes[i].shot_type if cpp and i < len(cpp.scenes) else "")),
            shot_purpose=str(row.get("shot_purpose") or (cpp.scenes[i].shot_purpose if cpp and i < len(cpp.scenes) else "")),
            narrative_role=str(row.get("narrative_role") or ""),
        )
        if shot.get("status") == "BLOCK":
            issues.extend(shot.get("issues") or [])
        tr = validate_transition(str(row.get("transition_intent") or "cut"), scene_purpose=str(row.get("purpose") or ""))
        if tr.get("status") == "BLOCK":
            issues.extend(tr.get("issues") or [])
        phys = validate_physical_plausibility_heuristic(atoms=atoms, posture=str(row.get("posture") or ""), location=str(row.get("location") or ""))
        if phys.get("status") == "BLOCK":
            issues.extend(phys.get("issues") or [])
    blocking = [
        i
        for i in issues
        if i
        in (
            "no_scenes",
            "missing_topic",
            "scene_without_purpose",
            "missing_scene_id",
            "weak_generic_hook",
            "clickbait_hook",
            "unsupported_hook_claim",
            "empty_or_too_short_scene",
            "smartphone_transforms_into_camera",
            "incompatible_transform_with_hold_or_describe",
            "incompatible_simultaneous_sit_stand",
            "unexplained_transformation",
            "clickbait_title",
        )
        or i.startswith("dialogue_visual_mismatch")
        or i.startswith("metaphor_literalized")
        or i.startswith("unmotivated_transition")
        or i.startswith("repetition_")
        or i.startswith("camera_module")
        or i.startswith("incompatible_simultaneous")
        or i.startswith("shot_missing")
        or i.startswith("shot_unspecified")
        or i.startswith("attribute_literalized")
    ]
    # Filter filler WARN out of BLOCK
    warn_only = {i for i in issues if i.startswith("filler_") or i.startswith("excessive_")}
    hard = [i for i in issues if i not in warn_only]
    status = "BLOCK" if blocking or any(
        x in hard
        for x in (
            "no_scenes",
            "missing_topic",
            "scene_without_purpose",
        )
    ) else ("WARN" if issues else "PASS")
    if blocking:
        status = "BLOCK"
    if block and status == "BLOCK":
        raise CreativePreflightError("creative_generation_preflight_blocked", issues=list(dict.fromkeys(issues)))
    return {
        "status": status,
        "issues": list(dict.fromkeys(issues)),
        "structure": struct,
        "method": "DETERMINISTIC",
        "provider_allowed": status != "BLOCK",
    }
