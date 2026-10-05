"""Script / director-plan structural validation (BUILD-04C)."""
from __future__ import annotations

import json
from typing import Any, Optional

from domain.adapters import script_from_plan
from domain.script import Script


def validate_director_plan(plan: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(plan, dict):
        return False, "plan_not_dict"
    title = str(plan.get("title") or plan.get("topic") or "").strip()
    if not title:
        return False, "missing_title"
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return False, "missing_scenes"
    seen_elements: set[str] = set()
    dialogue_ids: set[str] = set()
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            return False, f"scene_{i}_not_dict"
        narr = str(sc.get("narration") or sc.get("dialogue") or "").strip()
        if not narr:
            return False, f"scene_{i}_missing_narration"
        element = str(sc.get("element") or f"beat-{i}").strip().lower()
        dlg_id = str(sc.get("dialogue_id") or sc.get("scene_id") or f"{element}-{i}")
        if dlg_id in dialogue_ids:
            return False, f"duplicate_dialogue_id:{dlg_id}"
        dialogue_ids.add(dlg_id)
        seen_elements.add(element)
    return True, "ok"


def validate_script_contract(script: Script) -> tuple[bool, str]:
    try:
        if not (script.title or "").strip():
            return False, "empty_title"
        if not script.sections:
            return False, "no_sections"
        dlg_ids: set[str] = set()
        for sec in script.sections:
            if not sec.dialogues:
                return False, f"section_{sec.section_key}_missing_dialogue"
            for dlg in sec.dialogues:
                key = dlg.scene_id or dlg.id
                if key in dlg_ids:
                    return False, f"duplicate_dialogue_id:{key}"
                dlg_ids.add(key)
                if not (dlg.text or "").strip():
                    return False, "empty_dialogue_text"
        return True, "ok"
    except Exception as exc:
        return False, f"contract_error:{exc}"


def validate_plan_and_script(plan: dict[str, Any], *, topic_id: Optional[str] = None) -> tuple[bool, str]:
    ok, reason = validate_director_plan(plan)
    if not ok:
        return ok, reason
    try:
        script = script_from_plan(plan, topic_id=topic_id)
        return validate_script_contract(script)
    except Exception as exc:
        return False, f"script_build_failed:{exc}"


def validate_script_json_text(text: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    if not (text or "").strip():
        return False, "empty_response", None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False, "malformed_json", None
    if not isinstance(data, dict):
        return False, "not_object", None
    ok, reason = validate_director_plan(data)
    return ok, reason, data if ok else None
