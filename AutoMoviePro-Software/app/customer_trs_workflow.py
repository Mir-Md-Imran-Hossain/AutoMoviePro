"""C06-B — Customer Topic → Research → Script workflow (orchestration only).

Authorities (do not duplicate):
  BUILD-04G — discovery, research, duplicate, reserve
  BUILD-03 script runtime — via trs_facade.plan_script_for_trs
  domain.script.ScriptPlan — canonical script
  BUILD-04F — evaluate_script_quality
  C05-TRS — handoff target after APPROVED_SCRIPT (no media here)

C02/C04 ownership enforced by callers + login_id/channel_id scoping.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_DIR
from app.customer_job import sanitize_customer_error

TOPIC_SOURCES = ("MANUAL", "INTELLIGENCE", "RESERVED", "SUGGESTED")
TOPIC_STATUSES = ("NOT_STARTED", "READY", "RUNNING", "COMPLETED", "BLOCKED", "FAILED")
SCRIPT_APPROVAL = ("NOT_READY", "READY_FOR_REVIEW", "APPROVED", "REJECTED")
QUALITY_VERDICTS = ("PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_RUN")


def _now() -> str:
    return datetime.now().isoformat()


def _workflow_path(login_id: str, channel_id: int) -> Path:
    lid = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (login_id or "anon").strip())[:80] or "anon"
    return DATA_DIR / "customer_trs" / lid / f"ch{int(channel_id)}.json"


def _empty_state(login_id: str, channel_id: int) -> Dict[str, Any]:
    return {
        "schema_version": "C06-B.1",
        "owner_login_id": login_id,
        "channel_id": int(channel_id),
        "project_id": f"trs-ch{channel_id}",
        "updated_at": _now(),
        "topic": {
            "topic_id": None,
            "project_id": f"trs-ch{channel_id}",
            "owner_login_id": login_id,
            "topic_text": "",
            "topic_source": None,
            "topic_status": "NOT_STARTED",
            "selected_at": None,
            "created_at": None,
            "updated_at": None,
            "duplicate": None,
            "blocked_reason": None,
            "error_code": None,
        },
        "suggestions": [],
        "topic_history": [],
        "reserved": [],
        "research": {
            "research_status": "NOT_STARTED",
            "fact_count": 0,
            "evidence_count": 0,
            "source_count": 0,
            "confidence": None,
            "unresolved_items": [],
            "capability": {
                "provider_capability": "UNKNOWN",
                "external_live_research": "UNAVAILABLE",
                "is_external_live": False,
                "note": "LOCAL_FACTPACK must not be claimed as EXTERNAL_LIVE",
            },
            "fact_pack": None,
            "error_code": None,
            "error_summary": None,
        },
        "script": {
            "script_status": "NOT_STARTED",
            "script_plan": None,
            "preview": None,
            "scene_count": 0,
            "beat_count": 0,
            "dialogue_count": 0,
            "quality": {"status": "NOT_RUN", "issues": [], "actions": []},
            "approval": {"state": "NOT_READY", "publishes": False, "means_generated": False},
            "error_code": None,
            "error_summary": None,
        },
        "c05_handoff": {
            "ready": False,
            "status": "NOT_READY",
            "path": "ScriptPlan → C05-TRS → C05-S → C05-GA → C05-GP → C05-GX → C05-MR",
            "note": "APPROVED_SCRIPT only — does not generate media",
        },
        "revision": 0,
    }


def load_workflow(login_id: str, channel_id: int) -> Dict[str, Any]:
    path = _workflow_path(login_id, channel_id)
    if not path.is_file():
        return _empty_state(login_id, channel_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state(login_id, channel_id)
    if str(data.get("owner_login_id") or "") != str(login_id):
        # Fail closed — do not leak another customer's workflow
        return _empty_state(login_id, channel_id)
    if int(data.get("channel_id") or 0) != int(channel_id):
        return _empty_state(login_id, channel_id)
    return data


def save_workflow(state: Dict[str, Any]) -> Path:
    login_id = str(state.get("owner_login_id") or "")
    channel_id = int(state.get("channel_id") or 0)
    path = _workflow_path(login_id, channel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    state["revision"] = int(state.get("revision") or 0) + 1
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    return path


def assert_workflow_owner(state: Dict[str, Any], login_id: str, channel_id: int) -> Optional[Dict[str, Any]]:
    if str(state.get("owner_login_id") or "") != str(login_id):
        return {"ok": False, "error": "workflow_access_denied", "error_code": "ownership_violation"}
    if int(state.get("channel_id") or 0) != int(channel_id):
        return {"ok": False, "error": "workflow_channel_mismatch", "error_code": "ownership_violation"}
    return None


def _topic_id_for(text: str, source: str) -> str:
    h = hashlib.sha256(f"{source}|{text.strip().lower()}".encode("utf-8")).hexdigest()[:16]
    return f"topic-{h}"


def _append_topic_history(
    state: Dict[str, Any],
    *,
    text: str,
    topic_id: str = "",
    source: str = "",
    channel_id: int = 0,
    niche: str = "",
) -> None:
    now = _now()
    hist = list(state.get("topic_history") or [])
    hist = [
        h
        for h in hist
        if str((h.get("topic_text") if isinstance(h, dict) else h) or "").lower() != text.lower()
    ]
    hist.insert(0, {"topic_text": text, "topic_id": topic_id, "source": source, "at": now})
    state["topic_history"] = hist[:80]
    try:
        from pipeline.intelligence.topic_history import record_topic_use

        record_topic_use(
            int(channel_id),
            text,
            source=f"trs_{(source or 'selected').lower()}",
            niche=niche,
        )
    except Exception:
        pass


def check_topic_duplicate(
    topic_text: str,
    *,
    channel_id: int,
    niche: str = "",
    corpus: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Reuse BUILD-04G duplicate + product_registry — no UI algorithm."""
    from pipeline.intelligence.duplicate import analyze_duplicate
    from pipeline import product_registry as preg

    text = (topic_text or "").strip()
    corpus_list = list(corpus or [])
    # Merge historical / blocked product names for this channel
    try:
        blocked = list(preg.blocked_names(channel_id=int(channel_id), niche=niche or None) or [])
    except TypeError:
        try:
            blocked = list(preg.blocked_names() or [])
        except Exception:
            blocked = []
    except Exception:
        blocked = []
    merged = list(dict.fromkeys([*corpus_list, *blocked]))
    dup = analyze_duplicate(text, merged)
    verdict = getattr(dup.verdict, "value", str(dup.verdict))
    is_block = verdict in ("DUPLICATE", "UNKNOWN")
    prod_dup = False
    matched = None
    try:
        prod_dup, matched = preg.is_duplicate(text, channel_id=int(channel_id), niche=niche or "")
    except Exception:
        prod_dup = False
    if prod_dup:
        is_block = True
        verdict = "DUPLICATE"
    return {
        "verdict": verdict,
        "blocked": bool(is_block),
        "matched": matched or getattr(dup, "comparison_target", None),
        "detail": dup.to_dict() if hasattr(dup, "to_dict") else {"verdict": verdict},
        "authority": "BUILD-04G.duplicate + product_registry",
    }


def set_manual_topic(
    login_id: str,
    channel_id: int,
    topic_text: str,
    *,
    niche: str = "",
    corpus: Optional[Sequence[str]] = None,
    allow_duplicate: bool = False,
) -> Dict[str, Any]:
    text = sanitize_customer_error((topic_text or "").strip(), 240)
    if not text:
        return {"ok": False, "error": "topic_required", "error_code": "validation_failure"}
    from pipeline.intelligence.topic_quality import validate_topic_quality

    quality = validate_topic_quality(text, niche=niche)
    if not quality.get("ok"):
        return {
            "ok": False,
            "error": "topic_placeholder_or_generic",
            "error_code": str(quality.get("error_code") or "topic_placeholder_or_generic"),
            "quality": quality,
        }
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    if allow_duplicate:
        dup = {"blocked": False, "verdict": "ALLOWED_DUP", "matched": None, "cert_bypass": True}
    else:
        dup = check_topic_duplicate(text, channel_id=channel_id, niche=niche, corpus=corpus)
    now = _now()
    topic = state["topic"]
    topic.update(
        {
            "topic_id": _topic_id_for(text, "MANUAL"),
            "topic_text": text,
            "topic_source": "MANUAL",
            "selected_at": now,
            "created_at": topic.get("created_at") or now,
            "updated_at": now,
            "owner_login_id": login_id,
            "duplicate": dup,
        }
    )
    if dup.get("blocked"):
        topic["topic_status"] = "BLOCKED"
        topic["blocked_reason"] = f"Duplicate/conflict: {dup.get('matched') or dup.get('verdict')}"
        topic["error_code"] = "topic_duplicate"
        state["topic"] = topic
        # Reset downstream
        state["research"]["research_status"] = "NOT_STARTED"
        state["script"]["script_status"] = "NOT_STARTED"
        state["script"]["approval"] = {"state": "NOT_READY", "publishes": False, "means_generated": False}
        state["c05_handoff"]["ready"] = False
        save_workflow(state)
        return {"ok": False, "error": "topic_duplicate", "error_code": "topic_duplicate", "topic": topic, "workflow": project_trs_workflow(state)}
    topic["topic_status"] = "COMPLETED"
    topic["blocked_reason"] = None
    topic["error_code"] = None
    state["topic"] = topic
    _append_topic_history(
        state,
        text=text,
        topic_id=str(topic.get("topic_id") or ""),
        source="MANUAL",
        channel_id=channel_id,
        niche=niche,
    )
    state["research"]["research_status"] = "READY"
    state["script"]["script_status"] = "NOT_STARTED"
    state["script"]["approval"] = {"state": "NOT_READY", "publishes": False, "means_generated": False}
    state["c05_handoff"]["ready"] = False
    save_workflow(state)
    return {"ok": True, "topic": topic, "workflow": project_trs_workflow(state)}


def suggest_topics(
    login_id: str,
    channel: Dict[str, Any],
    *,
    video_type: str = "short",
    count: int = 6,
) -> Dict[str, Any]:
    """BUILD-04G discovery only — local suggestions, not external trending."""
    from pipeline.intelligence.contracts import ContentFormat
    from pipeline.intelligence.discovery import discover_topic_candidates
    from pipeline.intelligence.scoring import channel_profile_from_row
    from pipeline.intelligence.reserve_queue import load_reserve, purge_low_quality_reserve
    from pipeline.intelligence.topic_history import load_channel_topic_history

    channel_id = int(channel.get("id") or 0)
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    profile = channel_profile_from_row(channel)
    fmt = ContentFormat.SHORT if video_type == "short" else ContentFormat.LONG
    lang = str(channel.get("lang_code") or profile.language or "en")
    niche = str(channel.get("niche") or profile.niche or "")
    try:
        purge_low_quality_reserve(None, fmt, channel_id=channel_id, language=lang, niche=niche)
    except Exception:
        pass
    reserved_rows = load_reserve(None, fmt, channel_id=channel_id, language=lang)
    reserved_titles = [str(r.get("title") or r.get("canonical_topic") or "") for r in reserved_rows]
    historical = load_channel_topic_history(
        channel_id,
        niche=niche,
        channel={**channel, "owner_login_id": login_id},
    )
    # Include current workflow topic + suggestion history so UI doesn't re-offer the same set
    cur = str((state.get("topic") or {}).get("topic_text") or "")
    if cur:
        historical = list(dict.fromkeys([cur, *historical]))
    for prev in list(state.get("topic_history") or [])[:40]:
        if isinstance(prev, dict):
            historical.append(str(prev.get("topic_text") or prev.get("topic") or ""))
        else:
            historical.append(str(prev))
    historical = list(dict.fromkeys([h for h in historical if h]))

    candidates = discover_topic_candidates(
        profile,
        fmt=fmt,
        count=max(count, 8),
        historical=historical,
        reserved=reserved_titles,
        blocked=historical,
    )
    suggestions = []
    for c in candidates[:count]:
        suggestions.append(
            {
                "topic_id": c.topic_id,
                "topic_text": c.title or c.canonical_topic,
                "canonical_topic": c.canonical_topic,
                "source": "SUGGESTED",
                "authority": "BUILD-04G.discovery",
                "external_api": False,
            }
        )
    state["suggestions"] = suggestions
    state["reserved"] = [
        {
            "topic_id": str(r.get("topic_id") or ""),
            "topic_text": str(r.get("title") or r.get("canonical_topic") or ""),
            "source": "RESERVED",
            "authority": "BUILD-04G.reserve_queue",
        }
        for r in reserved_rows[:12]
        if (r.get("title") or r.get("canonical_topic"))
    ]
    save_workflow(state)
    return {
        "ok": True,
        "suggestions": suggestions,
        "reserved": state["reserved"],
        "historical_count": len(historical),
        "note": "Suggestions are local BUILD-04G discovery with anti-repeat history — not external live web research",
        "workflow": project_trs_workflow(state),
    }


def select_topic(
    login_id: str,
    channel: Dict[str, Any],
    *,
    topic_id: str = "",
    topic_text: str = "",
    source: str = "SUGGESTED",
    niche: str = "",
) -> Dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    src = (source or "SUGGESTED").upper()
    if src not in TOPIC_SOURCES:
        return {"ok": False, "error": "invalid_topic_source", "error_code": "validation_failure"}
    text = (topic_text or "").strip()
    tid = (topic_id or "").strip()
    if tid and not text:
        pool = list(state.get("suggestions") or []) + list(state.get("reserved") or [])
        for item in pool:
            if str(item.get("topic_id")) == tid:
                text = str(item.get("topic_text") or "")
                src = str(item.get("source") or src).upper()
                break
    if not text:
        return {"ok": False, "error": "topic_not_found", "error_code": "validation_failure"}
    from pipeline.intelligence.topic_quality import validate_topic_quality

    quality = validate_topic_quality(text, niche=niche or channel.get("niche") or "")
    if not quality.get("ok"):
        return {
            "ok": False,
            "error": "topic_placeholder_or_generic",
            "error_code": str(quality.get("error_code") or "topic_placeholder_or_generic"),
            "quality": quality,
        }
    # Reserved ownership: only from this channel's reserve list
    if src == "RESERVED":
        allowed = {str(r.get("topic_text") or "") for r in (state.get("reserved") or [])}
        if text not in allowed and tid not in {str(r.get("topic_id") or "") for r in (state.get("reserved") or [])}:
            return {
                "ok": False,
                "error": "reservation_not_owned",
                "error_code": "ownership_violation",
                "message": "Cannot claim another channel/customer reserved topic",
            }
    dup = check_topic_duplicate(text, channel_id=channel_id, niche=niche or channel.get("niche") or "")
    now = _now()
    topic = state["topic"]
    topic.update(
        {
            "topic_id": tid or _topic_id_for(text, src),
            "topic_text": text,
            "topic_source": src if src != "INTELLIGENCE" else "SUGGESTED",
            "selected_at": now,
            "created_at": topic.get("created_at") or now,
            "updated_at": now,
            "owner_login_id": login_id,
            "duplicate": dup,
        }
    )
    if dup.get("blocked"):
        topic["topic_status"] = "BLOCKED"
        topic["blocked_reason"] = f"Duplicate/conflict: {dup.get('matched') or dup.get('verdict')}"
        topic["error_code"] = "topic_duplicate"
        state["topic"] = topic
        state["c05_handoff"]["ready"] = False
        save_workflow(state)
        return {"ok": False, "error": "topic_duplicate", "error_code": "topic_duplicate", "topic": topic, "workflow": project_trs_workflow(state)}
    topic["topic_status"] = "COMPLETED"
    topic["blocked_reason"] = None
    topic["error_code"] = None
    state["topic"] = topic
    _append_topic_history(
        state,
        text=text,
        topic_id=str(topic.get("topic_id") or ""),
        source=src,
        channel_id=channel_id,
        niche=str(niche or channel.get("niche") or ""),
    )
    state["research"]["research_status"] = "READY"
    state["script"]["script_status"] = "NOT_STARTED"
    state["script"]["approval"] = {"state": "NOT_READY", "publishes": False, "means_generated": False}
    state["c05_handoff"]["ready"] = False
    save_workflow(state)
    return {"ok": True, "topic": topic, "workflow": project_trs_workflow(state)}


def run_research(
    login_id: str,
    channel: Dict[str, Any],
    *,
    use_mock: bool = False,
    work_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """BUILD-04G research runtime — honest capability labeling."""
    from pipeline.intelligence.contracts import ResearchRequest
    from pipeline.intelligence.research_runtime import execute_research_request
    from pipeline.intelligence.research_provider import classify_research_capability
    from pipeline.intelligence.factpack_gate import validate_fact_pack

    channel_id = int(channel.get("id") or 0)
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    topic = state.get("topic") or {}
    if topic.get("topic_status") != "COMPLETED" or not topic.get("topic_text"):
        return {
            "ok": False,
            "error": "topic_required",
            "error_code": "missing_prerequisite",
            "message": "Select a non-blocked topic before research",
        }
    state["research"]["research_status"] = "RUNNING"
    save_workflow(state)

    work = Path(work_dir) if work_dir else (DATA_DIR / "customer_trs" / "_research" / login_id / f"ch{channel_id}")
    work.mkdir(parents=True, exist_ok=True)
    req = ResearchRequest(
        topic_id=str(topic.get("topic_id") or "topic"),
        canonical_topic=str(topic.get("topic_text")),
        query=str(topic.get("topic_text")),
        language=str(channel.get("lang_code") or "en"),
    )
    try:
        rr = execute_research_request(
            work,
            req,
            job_id=f"c06b-{channel_id}-{topic.get('topic_id')}",
            use_mock=use_mock,
        )
    except Exception as exc:
        state["research"].update(
            {
                "research_status": "FAILED",
                "error_code": "research_failure",
                "error_summary": sanitize_customer_error(str(exc)),
            }
        )
        save_workflow(state)
        return {"ok": False, "error": "research_failure", "error_code": "research_failure", "workflow": project_trs_workflow(state)}

    cap = classify_research_capability(rr.research if isinstance(rr.research, dict) else {})
    gate = validate_fact_pack(rr.fact_pack) if rr.fact_pack else {"verdict": "RESEARCH_REQUIRED"}
    claims = (rr.fact_pack or {}).get("claims") or []
    sources = set()
    for c in claims:
        if isinstance(c, dict):
            for s in c.get("sources") or c.get("source_refs") or []:
                sources.add(str(s))
    external = "UNAVAILABLE"
    if cap.get("is_external_live"):
        external = "AVAILABLE"
    elif cap.get("provider_capability") == "LOCAL_FACTPACK":
        external = "UNAVAILABLE"
    else:
        external = "UNKNOWN"

    success = bool(rr.success) and str(gate.get("verdict") or "") == "PASS"
    state["research"] = {
        "research_status": "COMPLETED" if success else "FAILED",
        "fact_count": len(claims),
        "evidence_count": len(claims),
        "source_count": len(sources),
        "confidence": None,  # do not invent
        "unresolved_items": list(gate.get("issues") or gate.get("reasons") or [])[:20],
        "capability": {
            "provider_capability": cap.get("provider_capability"),
            "provider_mode": cap.get("provider_mode"),
            "external_live_research": external,
            "is_external_live": bool(cap.get("is_external_live")),
            "external_api": bool(cap.get("external_api")),
            "note": cap.get("note") or "LOCAL_FACTPACK ≠ EXTERNAL_LIVE",
        },
        "fact_pack": rr.fact_pack,
        "gate": gate,
        "fingerprint": getattr(rr, "fingerprint", None),
        "action": getattr(rr, "action", None),
        "error_code": None if success else "research_gate_failed",
        "error_summary": None if success else sanitize_customer_error(str(gate.get("reason") or gate.get("verdict") or "research_failed")),
        # Explicit honesty flag for UI
        "live_research_complete": False if not cap.get("is_external_live") else True,
    }
    if success:
        state["script"]["script_status"] = "READY"
    else:
        state["script"]["script_status"] = "NOT_STARTED"
    state["c05_handoff"]["ready"] = False
    save_workflow(state)
    return {"ok": success, "research": state["research"], "workflow": project_trs_workflow(state)}


def _script_plan_to_preview(plan: Dict[str, Any]) -> Dict[str, Any]:
    beats = plan.get("beats") or []
    entities: List[str] = []
    locations: List[str] = []
    relationships: List[str] = []
    dialogue_ids: List[str] = []
    beat_ids: List[str] = []
    scene_ids: List[str] = []
    for i, b in enumerate(beats):
        if not isinstance(b, dict):
            continue
        beat_ids.append(str(b.get("beat_id") or f"beat-{i}"))
        dialogue_ids.append(str((b.get("metadata") or {}).get("dialogue_id") or b.get("beat_id") or f"dlg-{i}"))
        scene_ids.append(str((b.get("metadata") or {}).get("scene_id") or f"scene-{i:02d}"))
        for e in b.get("entity_refs") or []:
            entities.append(str(e))
        if b.get("location_ref"):
            locations.append(str(b.get("location_ref")))
        # relationship hints from action_intent / visual_implication (preserve text, don't invent graph)
        for field in ("action_intent", "visual_implication", "narration"):
            val = str(b.get(field) or "")
            for token in ("beside", "inside", "with", "near", "holding"):
                if token in val.lower():
                    relationships.append(f"{token}:{val[:80]}")
    return {
        "topic": plan.get("topic"),
        "hook": plan.get("hook"),
        "beat_count": len(beats),
        "dialogue_count": len(dialogue_ids),
        "scene_count": len(set(scene_ids)) if scene_ids else len(beats),
        "entities": list(dict.fromkeys(entities)),
        "locations": list(dict.fromkeys(locations)),
        "relationships": list(dict.fromkeys(relationships))[:20],
        "dialogue_ids": dialogue_ids,
        "beat_ids": beat_ids,
        "scene_ids": scene_ids,
        "beats_summary": [
            {
                "beat_id": b.get("beat_id"),
                "narration": (b.get("narration") or "")[:160],
                "speaker": b.get("speaker"),
                "emotion": b.get("emotion"),
                "entity_refs": b.get("entity_refs") or [],
                "location_ref": b.get("location_ref") or "",
                "estimated_duration_sec": b.get("estimated_duration_sec"),
            }
            for b in beats
            if isinstance(b, dict)
        ][:40],
    }


def _normalize_quality_status(raw: Any) -> str:
    if raw is None or raw == "":
        return "NOT_RUN"
    s = str(raw).strip().upper()
    if s in QUALITY_VERDICTS:
        return s
    if s in ("PASSED", "OK", "TRUE"):
        return "PASS"
    if s in ("FAILED", "FALSE"):
        return "FAIL"
    if "UNKNOWN" in s:
        return "UNKNOWN"
    if "BLOCK" in s:
        return "BLOCKED"
    if "PASS" in s:
        return "PASS"
    if "FAIL" in s:
        return "FAIL"
    return "UNKNOWN"


def generate_script(
    login_id: str,
    channel: Dict[str, Any],
    *,
    video_type: str = "short",
    max_seconds: Optional[int] = None,
    use_mock: bool = False,
    work_dir: Optional[Path] = None,
    tone: str = "",
    audience: str = "",
    instructions: str = "",
) -> Dict[str, Any]:
    """Existing script authority via plan_script_for_trs + ScriptPlan normalize."""
    from pipeline.trs_facade import (
        plan_script_for_trs,
        normalize_niche_plan_to_script_plan,
        script_plan_to_dialogue_segments,
    )
    from pipeline.quality.evaluators import evaluate_script_quality
    from pipeline.creative_production.script_quality import (
        enforce_dialogue_window_on_plan,
        validate_script_plan_preflight,
    )
    from domain.script import ScriptPlan
    from pipeline.duration_budget import resolve_duration_contract

    # RCP-06B: script packing uses target_seconds from unified contract (not a divergent hardcode)
    _vt = "long" if str(video_type).lower() == "long" else "short"
    if max_seconds is None:
        _contract = resolve_duration_contract(_vt)
    else:
        _contract = resolve_duration_contract(_vt, target_seconds=int(max_seconds))
    max_seconds = int(_contract["target_seconds"])
    channel_id = int(channel.get("id") or 0)
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    topic = state.get("topic") or {}
    research = state.get("research") or {}
    if topic.get("topic_status") != "COMPLETED":
        return {"ok": False, "error": "topic_required", "error_code": "missing_prerequisite"}
    if research.get("research_status") != "COMPLETED":
        return {"ok": False, "error": "research_required", "error_code": "missing_prerequisite"}

    state["script"]["script_status"] = "RUNNING"
    save_workflow(state)

    work = Path(work_dir) if work_dir else (DATA_DIR / "customer_trs" / "_scripts" / login_id / f"ch{channel_id}")
    work.mkdir(parents=True, exist_ok=True)
    notes = str((research.get("fact_pack") or {}).get("summary") or "")
    if tone or audience or instructions:
        notes = (notes + f"\ntone={tone}; audience={audience}; instructions={instructions}").strip()

    try:
        result = plan_script_for_trs(
            work,
            job_id=f"c06b-script-{channel_id}-{topic.get('topic_id')}",
            niche=str(channel.get("niche") or "general"),
            channel_name=str(channel.get("youtube_name") or channel.get("niche") or "channel"),
            topic=str(topic.get("topic_text")),
            video_type=video_type,
            max_seconds=max_seconds,
            research_notes=notes,
            use_mock=use_mock,
            niche_id=channel.get("niche_id"),
        )
        # plan_script_for_trs returns niche plan dict (or may raise)
        plan_payload = result if isinstance(result, dict) else {}
        if plan_payload.get("plan") and isinstance(plan_payload.get("plan"), dict):
            plan_payload = plan_payload["plan"]
        plan_payload.setdefault("topic", topic.get("topic_text"))
        fmt = "SHORT" if video_type == "short" else "LONG"
        script_plan = normalize_niche_plan_to_script_plan(
            plan_payload,
            topic_id=str(topic.get("topic_id") or ""),
            fmt=fmt,
            language=str(channel.get("lang_code") or "en"),
            fact_pack=research.get("fact_pack"),
            target_duration_sec=float(max_seconds),
        )
        if isinstance(script_plan, ScriptPlan):
            plan_dict = script_plan.model_dump()
        else:
            plan_dict = dict(script_plan)
        # Preserve dialogue_id on beats for C05
        for i, b in enumerate(plan_dict.get("beats") or []):
            meta = dict(b.get("metadata") or {})
            meta.setdefault("dialogue_id", b.get("beat_id") or f"dlg-{i}")
            meta.setdefault("scene_id", f"scene-{i:02d}")
            b["metadata"] = meta
        # Live marathon: enforce 7–9s spoken window + dialogue bridges before gates
        plan_dict = enforce_dialogue_window_on_plan(plan_dict)
        # Also normalize niche-style scenes payload used by BUILD-04F
        if plan_payload.get("scenes"):
            plan_payload = enforce_dialogue_window_on_plan(plan_payload)
        # Attach retention roles/open-loops so preflight does not block approval
        try:
            from pipeline.retention_architecture import attach_retention_to_plan

            plan_dict = attach_retention_to_plan(plan_dict)
            if plan_payload.get("scenes"):
                plan_payload = attach_retention_to_plan(plan_payload)
        except Exception:
            pass
        # BUILD-04F quality on niche-style plan + TRS preflight on ScriptPlan
        cq = evaluate_script_quality(
            subject_id=f"ch{channel_id}",
            plan=plan_payload if plan_payload.get("scenes") else {
                "topic": plan_dict.get("topic"),
                "scenes": [{"narration": b.get("narration") or ""} for b in (plan_dict.get("beats") or [])],
            },
            fact_pack=research.get("fact_pack"),
        )
        preflight = validate_script_plan_preflight(plan_dict)
        cq_verdict = getattr(getattr(cq, "verdict", None), "value", None) or getattr(cq, "verdict", None) or "UNKNOWN"
        q_status = _normalize_quality_status(cq_verdict)
        if isinstance(preflight, dict) and preflight.get("ok") is False:
            if q_status == "PASS":
                q_status = "FAIL"
        issues = []
        actions = []
        if hasattr(cq, "issues"):
            for iss in (cq.issues or [])[:20]:
                issues.append(sanitize_customer_error(getattr(iss, "description", None) or str(iss), 160))
                act = getattr(iss, "action", None)
                if act:
                    actions.append(str(act))
        preview = _script_plan_to_preview(plan_dict)
        state["script"] = {
            "script_status": "COMPLETED",
            "script_plan": plan_dict,
            "preview": preview,
            "scene_count": preview["scene_count"],
            "beat_count": preview["beat_count"],
            "dialogue_count": preview["dialogue_count"],
            "quality": {
                "status": q_status,
                "issues": issues,
                "actions": actions,
                "preflight": preflight if isinstance(preflight, dict) else {"ok": bool(preflight)},
                "authority": "BUILD-04F.evaluate_script_quality + TRS preflight",
            },
            "approval": {
                "state": "READY_FOR_REVIEW" if q_status in ("PASS", "UNKNOWN") else "NOT_READY",
                "publishes": False,
                "means_generated": False,
            },
            "error_code": None if q_status != "FAIL" else "script_quality_fail",
            "error_summary": None if q_status != "FAIL" else "Script quality failed — repair via existing actions",
            "script_action": "reuse" if (work / "director_plan.json").is_file() else "execute",
        }
        # Dialogue segments projection for C05 readiness (no media)
        try:
            segs = script_plan_to_dialogue_segments(ScriptPlan.model_validate(plan_dict))
            state["script"]["dialogue_segments_count"] = len(segs or [])
        except Exception:
            state["script"]["dialogue_segments_count"] = preview["dialogue_count"]
        state["c05_handoff"]["ready"] = False
        state["c05_handoff"]["status"] = "SCRIPT_READY_FOR_APPROVAL"
        save_workflow(state)
        return {"ok": True, "script": state["script"], "workflow": project_trs_workflow(state)}
    except Exception as exc:
        state["script"].update(
            {
                "script_status": "FAILED",
                "error_code": "script_generation_failure",
                "error_summary": sanitize_customer_error(str(exc)),
                "approval": {"state": "NOT_READY", "publishes": False, "means_generated": False},
            }
        )
        state["c05_handoff"]["ready"] = False
        save_workflow(state)
        return {
            "ok": False,
            "error": "script_generation_failure",
            "error_code": "script_generation_failure",
            "workflow": project_trs_workflow(state),
        }


def approve_script(
    login_id: str,
    channel_id: int,
    *,
    decision: str,
) -> Dict[str, Any]:
    state = load_workflow(login_id, channel_id)
    err = assert_workflow_owner(state, login_id, channel_id)
    if err:
        return err
    script = state.get("script") or {}
    if script.get("script_status") != "COMPLETED":
        return {"ok": False, "error": "script_not_ready", "error_code": "missing_prerequisite"}
    if script.get("quality", {}).get("status") == "FAIL":
        return {"ok": False, "error": "quality_failed_cannot_approve", "error_code": "script_quality_fail"}
    dec = (decision or "").strip().lower()
    if dec in ("approve", "approved"):
        if script.get("approval", {}).get("state") not in ("READY_FOR_REVIEW", "APPROVED", "REJECTED"):
            return {"ok": False, "error": "approval_not_ready", "error_code": "approval_not_ready"}
        script["approval"] = {
            "state": "APPROVED",
            "publishes": False,
            "means_generated": False,
            "updated_at": _now(),
            "note": "customer-approved script — not generated/rendered/published",
        }
        state["c05_handoff"] = {
            "ready": True,
            "status": "APPROVED_SCRIPT",
            "path": "ScriptPlan → C05-TRS → C05-S → C05-GA → C05-GP → C05-GX → C05-MR",
            "note": "Handoff ready — media generation is a later step",
            "topic_id": (state.get("topic") or {}).get("topic_id"),
            "topic_text": (state.get("topic") or {}).get("topic_text"),
            "script_plan_topic": (script.get("script_plan") or {}).get("topic"),
        }
    elif dec in ("reject", "rejected"):
        script["approval"] = {
            "state": "REJECTED",
            "publishes": False,
            "means_generated": False,
            "updated_at": _now(),
        }
        state["c05_handoff"] = {
            "ready": False,
            "status": "REJECTED",
            "path": "ScriptPlan → C05-TRS → C05-S → C05-GA → C05-GP → C05-GX → C05-MR",
            "note": "Rejected — regenerate script before C05 handoff",
        }
    else:
        return {"ok": False, "error": "invalid_decision", "error_code": "validation_failure"}
    state["script"] = script
    save_workflow(state)
    return {"ok": True, "approval": script["approval"], "c05_handoff": state["c05_handoff"], "workflow": project_trs_workflow(state)}


def project_trs_workflow(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Customer-safe projection (no secrets)."""
    if not state:
        return {}
    research = dict(state.get("research") or {})
    # Never claim live complete for local factpack
    cap = research.get("capability") or {}
    if not cap.get("is_external_live"):
        research["live_research_complete"] = False
        if research.get("research_status") == "COMPLETED":
            research["status_label"] = "Research complete (local FactPack)"
        else:
            research["status_label"] = research.get("research_status")
    else:
        research["status_label"] = "External live research complete"
    script = dict(state.get("script") or {})
    # Strip huge fact_pack from list views but keep counts
    research_out = {k: v for k, v in research.items() if k != "fact_pack"}
    research_out["has_fact_pack"] = bool(research.get("fact_pack"))
    script_out = {k: v for k, v in script.items() if k != "script_plan"}
    script_out["has_script_plan"] = bool(script.get("script_plan"))
    return {
        "contract": "C06-B",
        "project_id": state.get("project_id"),
        "owner_login_id": state.get("owner_login_id"),
        "channel_id": state.get("channel_id"),
        "updated_at": state.get("updated_at"),
        "revision": state.get("revision"),
        "topic": state.get("topic"),
        "suggestions": state.get("suggestions") or [],
        "reserved": state.get("reserved") or [],
        "research": research_out,
        "script": script_out,
        "script_plan": script.get("script_plan"),  # full for detail when needed
        "c05_handoff": state.get("c05_handoff"),
        "actions": derive_trs_actions(state),
    }


def derive_trs_actions(state: Dict[str, Any]) -> Dict[str, Any]:
    topic = state.get("topic") or {}
    research = state.get("research") or {}
    script = state.get("script") or {}
    approval = (script.get("approval") or {}).get("state")
    return {
        "select_topic": True,
        "research": topic.get("topic_status") == "COMPLETED",
        "generate_script": research.get("research_status") == "COMPLETED",
        "review_script": script.get("script_status") == "COMPLETED",
        "approve_script": approval == "READY_FOR_REVIEW",
        "c05_handoff_ready": bool((state.get("c05_handoff") or {}).get("ready")),
    }


def detect_duplicate_engines(source: str) -> List[str]:
    import re

    bad = []
    for pat in (
        r"(?m)^\s*class\s+TopicEngine\b",
        r"(?m)^\s*class\s+ResearchEngine\b",
        r"(?m)^\s*class\s+FactPackEngine\b",
        r"(?m)^\s*class\s+ScriptEngine\b",
        r"(?m)^\s*def\s+analyze_duplicate\s*\(",
        r"(?m)^\s*def\s+evaluate_script_quality\s*\(",
        r"(?m)^\s*def\s+discover_topic_candidates\s*\(",
    ):
        if re.search(pat, source):
            bad.append(pat)
    return bad
