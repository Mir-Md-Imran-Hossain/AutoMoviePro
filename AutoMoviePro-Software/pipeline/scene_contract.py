"""SceneContract v0 — claim → observable evidence → shot → prompt preflight.

No provider API call should proceed if preflight FAILS.
UNKNOWN is never treated as PASS for visual readiness.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9\u0980-\u09FF]{3,}", (text or "").lower())


def build_scene_contract(
    scene: Dict[str, Any],
    *,
    scene_id: int,
    topic: str = "",
) -> Dict[str, Any]:
    narr = str(scene.get("narration") or scene.get("dialogue") or "").strip()
    element = str(scene.get("element") or "beat").strip()
    claim_id = str(scene.get("claim_id") or f"C{scene_id:02d}")
    # Primary claim = first sentence of narration (one claim per scene rule)
    primary = re.split(r"(?<=[.!?])\s+", narr, maxsplit=1)[0].strip() if narr else ""
    kws = scene.get("keyword_triggers") or scene.get("keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    must_show = list(scene.get("must_show") or kws or [])
    if topic and topic not in must_show and element in ("intro", "outro"):
        must_show = [topic] + must_show
    must_not = list(scene.get("must_not_show") or [])
    # History safety: block modern gadgets unless element is gadget-ish
    if element.lower() not in {
        "design",
        "display",
        "camera",
        "processor",
        "battery",
        "sound",
        "price",
        "software",
    }:
        for g in ("smartphone", "iphone", "earbuds", "unboxing table", "modern phone"):
            if g not in must_not:
                must_not.append(g)

    vp = str(scene.get("visual_prompt") or scene.get("exact_ai_video_prompt") or "")
    vq = str(scene.get("visual_query") or "")
    shot = scene.get("shot") if isinstance(scene.get("shot"), dict) else {}
    subject = str(shot.get("subject") or topic or element)
    action = str(shot.get("action") or "continuous camera drift revealing evidence")
    environment = str(shot.get("environment") or "documentary location matching claim")
    camera = str(shot.get("camera") or "slow push-in, stable documentary")
    lighting = str(shot.get("lighting") or "natural cinematic grade")
    composition = str(shot.get("composition") or "subject-centered, readable silhouette")

    return {
        "scene_id": scene_id,
        "claim_id": claim_id,
        "element": element,
        "dialogue": narr,
        "primary_claim": primary,
        "visual_evidence": {
            "must_show": must_show[:8],
            "should_show": list(scene.get("should_show") or [])[:6],
            "must_not_show": must_not[:10],
        },
        "shot": {
            "subject": subject,
            "action": action,
            "environment": environment,
            "camera": camera,
            "lighting": lighting,
            "composition": composition,
        },
        "audio": dict(scene.get("audio") or {}),
        "subtitle": dict(scene.get("subtitle") or {}),
        "continuity": dict(scene.get("continuity") or {"seed_hint": f"{topic}:{element}:{scene_id}"}),
        "prompt_fields": {
            "visual_prompt": vp,
            "visual_query": vq,
        },
        "version": "v0",
    }


def compile_prompt_from_contract(contract: Dict[str, Any]) -> str:
    shot = contract.get("shot") or {}
    ev = contract.get("visual_evidence") or {}
    must = ", ".join(ev.get("must_show") or []) or "claim-relevant evidence"
    must_not = ", ".join(ev.get("must_not_show") or []) or "none"
    parts = [
        f"SUBJECT: {shot.get('subject')}",
        f"ACTION: {shot.get('action')}",
        f"ENVIRONMENT: {shot.get('environment')}",
        f"CAMERA: {shot.get('camera')}",
        f"LIGHTING: {shot.get('lighting')}",
        f"COMPOSITION: {shot.get('composition')}",
        f"MUST_SHOW: {must}",
        f"MUST_NOT: {must_not}",
        f"CONTINUITY: {(contract.get('continuity') or {}).get('seed_hint')}",
        f"CLAIM: {contract.get('primary_claim')}",
    ]
    existing = str((contract.get("prompt_fields") or {}).get("visual_prompt") or "").strip()
    compiled = " | ".join(parts)
    if existing and len(existing) > 40:
        return f"{existing}\n\nCONTRACT: {compiled}"
    return compiled


def preflight_scene_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Return PASS / FAIL / UNKNOWN — never soft-PASS on missing fields."""
    issues: List[str] = []
    shot = contract.get("shot") or {}
    for key in ("subject", "action", "environment", "camera", "lighting", "composition"):
        if not str(shot.get(key) or "").strip():
            issues.append(f"missing_shot_{key}")
    if not str(contract.get("primary_claim") or "").strip():
        issues.append("missing_primary_claim")
    if not str(contract.get("dialogue") or "").strip():
        issues.append("missing_dialogue")
    must = (contract.get("visual_evidence") or {}).get("must_show") or []
    if not must:
        issues.append("missing_must_show")

    prompt = str((contract.get("prompt_fields") or {}).get("visual_prompt") or "")
    compiled_ok = all(
        str(shot.get(k) or "").strip()
        for k in ("subject", "action", "environment")
    )
    # If prompt empty but shot fields present → still PASS after compile
    if not prompt and not compiled_ok:
        issues.append("missing_visual_prompt")

    # Claim represented? loose token overlap claim vs subject+must_show
    claim_toks = set(_tokens(str(contract.get("primary_claim") or "")))
    evidence_blob = " ".join(
        [
            str(shot.get("subject") or ""),
            " ".join(must),
            prompt,
        ]
    )
    ev_toks = set(_tokens(evidence_blob))
    if claim_toks and len(claim_toks & ev_toks) == 0 and len(claim_toks) >= 4:
        # Not enough overlap — UNKNOWN not PASS
        return {
            "passed": False,
            "verdict": "UNKNOWN",
            "issues": issues + ["claim_evidence_unverified"],
            "allow_api": False,
        }

    if issues:
        return {
            "passed": False,
            "verdict": "FAIL",
            "issues": issues,
            "allow_api": False,
        }
    return {
        "passed": True,
        "verdict": "PASS",
        "issues": [],
        "allow_api": True,
    }


def attach_contracts_to_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate plan scenes with scene_contract + hardened visual_prompt."""
    topic = str(plan.get("topic") or "")
    scenes = list(plan.get("scenes") or [])
    out = []
    reports = []
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        contract = build_scene_contract(row, scene_id=i, topic=topic)
        compiled = compile_prompt_from_contract(contract)
        contract["prompt_fields"]["visual_prompt"] = compiled
        pf = preflight_scene_contract(contract)
        row["scene_contract"] = contract
        row["visual_prompt"] = compiled
        if not row.get("exact_ai_video_prompt"):
            row["exact_ai_video_prompt"] = compiled
        row["contract_preflight"] = pf
        out.append(row)
        reports.append({"scene_id": i, **pf})
    plan = dict(plan)
    plan["scenes"] = out
    plan["scene_contract_report"] = {
        "passed": all(r.get("verdict") == "PASS" for r in reports),
        "scenes": reports,
    }
    return plan


def plan_allows_generation(plan: Dict[str, Any]) -> bool:
    rep = plan.get("scene_contract_report") or {}
    if not rep:
        return False
    # Fail-closed: any FAIL/UNKNOWN blocks
    for s in rep.get("scenes") or []:
        if s.get("verdict") != "PASS":
            return False
    return bool(rep.get("passed"))
