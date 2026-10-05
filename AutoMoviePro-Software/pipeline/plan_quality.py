"""Apply FactPack barrier + robot detector to a director plan (post-process)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def enforce_plan_quality(plan: Dict[str, Any], fact_pack: Dict[str, Any] | None = None) -> Dict[str, Any]:
    from pipeline.fact_pack import build_fact_pack, claim_allowed
    from pipeline.robot_detector import evaluate_plan_speech

    plan = dict(plan or {})
    topic = str(plan.get("topic") or "")
    pack = fact_pack or build_fact_pack(topic, notes=str(plan.get("research_notes") or ""))
    scenes: List[Dict[str, Any]] = []
    unknown_claims = 0
    for sc in plan.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        narr = str(row.get("narration") or "")
        gate = claim_allowed(narr, pack, min_overlap=0.15)
        row["fact_gate"] = gate
        if gate.get("verdict") == "UNKNOWN":
            unknown_claims += 1
            # Soft: tag unknown; do not rewrite historical documentary freely here
            row["fact_unknown"] = True
        scenes.append(row)
    plan["scenes"] = scenes
    plan["fact_pack"] = {"topic": pack.get("topic"), "claim_count": len(pack.get("claims") or [])}
    speech = evaluate_plan_speech(plan)
    plan["speech_audit"] = speech
    plan["quality_enforcement"] = {
        "unknown_claims": unknown_claims,
        "speech_passed": bool(speech.get("passed")),
        "speech_score": speech.get("score"),
    }
    return plan
