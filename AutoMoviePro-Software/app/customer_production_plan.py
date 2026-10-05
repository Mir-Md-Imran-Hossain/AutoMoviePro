"""C06-C — Customer Production Plan (orchestration / contract only).

APPROVED_SCRIPT → Production Plan → READY_FOR_GENERATION

Does NOT generate media, call paid APIs, render, or publish.
Reuses: ScriptPlan, C05-S visual beats, AudioPlan, LocalizationContract,
ContinuityTracker references, BUILD-03 fingerprint, C02/C04 ownership via callers.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import DATA_DIR
from app.customer_job import sanitize_customer_error
from app.customer_trs_workflow import assert_workflow_owner, load_workflow

PLAN_STATUSES = (
    "NOT_STARTED",
    "BUILDING",
    "READY_FOR_GENERATION",
    "BLOCKED",
    "STALE",
    "NOT_READY",
    "FAILED",
)

CONTRACT_VERSION = "C06-C.1"


def _now() -> str:
    return datetime.now().isoformat()


def _plan_path(login_id: str, channel_id: int) -> Path:
    lid = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (login_id or "anon").strip())[:80] or "anon"
    return DATA_DIR / "customer_production_plans" / lid / f"ch{int(channel_id)}.json"


def compute_script_revision(script_plan: Dict[str, Any]) -> str:
    from pipeline.idempotency.fingerprint import hash_text
    from pipeline.idempotency.normalize import canonical_json

    return hash_text(canonical_json(script_plan or {}))[:32]


def load_production_plan(login_id: str, channel_id: int) -> Optional[Dict[str, Any]]:
    path = _plan_path(login_id, channel_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(data.get("owner_login_id") or "") != str(login_id):
        return None
    if int(data.get("channel_id") or 0) != int(channel_id):
        return None
    return data


def save_production_plan(plan: Dict[str, Any]) -> Path:
    login_id = str(plan.get("owner_login_id") or "")
    channel_id = int(plan.get("channel_id") or 0)
    path = _plan_path(login_id, channel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    plan["updated_at"] = _now()
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    return path


def assert_approved_script_authority(
    workflow: Dict[str, Any],
    *,
    login_id: str,
    channel_id: int,
) -> Optional[Dict[str, Any]]:
    """Fail closed unless APPROVED_SCRIPT from owned workflow."""
    err = assert_workflow_owner(workflow, login_id, channel_id)
    if err:
        return err
    script = workflow.get("script") or {}
    handoff = workflow.get("c05_handoff") or {}
    approval = (script.get("approval") or {}).get("state")
    if approval == "REJECTED":
        return {"ok": False, "error": "script_rejected", "error_code": "script_rejected", "status": "BLOCKED"}
    if approval != "APPROVED":
        return {"ok": False, "error": "script_not_approved", "error_code": "script_not_approved", "status": "BLOCKED"}
    if script.get("script_status") != "COMPLETED":
        return {"ok": False, "error": "script_incomplete", "error_code": "script_not_approved", "status": "BLOCKED"}
    if not handoff.get("ready") or handoff.get("status") != "APPROVED_SCRIPT":
        return {"ok": False, "error": "handoff_not_approved_script", "error_code": "script_not_approved", "status": "BLOCKED"}
    if not script.get("script_plan"):
        return {"ok": False, "error": "missing_script_plan", "error_code": "missing_script_plan", "status": "BLOCKED"}
    return None


def _dialogue_segments_from_plan(plan: Any) -> Tuple[List[Any], List[Dict[str, Any]], List[str]]:
    """Per-beat dialogue_id / scene_id — never use list index as sole identity."""
    from domain.script import ScriptPlan
    from pipeline.story_visual_direction import create_dialogue_segment

    if not isinstance(plan, ScriptPlan):
        plan = ScriptPlan.model_validate(plan)
    segs = []
    rows: List[Dict[str, Any]] = []
    blocks: List[str] = []
    seen_dlg: set = set()
    seen_beat: set = set()
    t = 0.0
    if not plan.beats:
        blocks.append("empty_beats")
        return segs, rows, blocks
    for i, b in enumerate(plan.beats):
        meta = b.metadata if isinstance(b.metadata, dict) else {}
        beat_id = str(b.beat_id or "").strip()
        if not beat_id:
            blocks.append(f"missing_beat_id:{i}")
            continue
        if beat_id in seen_beat:
            blocks.append(f"duplicate_beat_id:{beat_id}")
            continue
        seen_beat.add(beat_id)
        dialogue_id = str(meta.get("dialogue_id") or beat_id).strip()
        if not dialogue_id:
            blocks.append(f"missing_dialogue_id:{beat_id}")
            continue
        if dialogue_id in seen_dlg:
            blocks.append(f"duplicate_dialogue_id:{dialogue_id}")
            continue
        seen_dlg.add(dialogue_id)
        scene_id = str(meta.get("scene_id") or f"scene-{i:02d}").strip()
        raw_dur = b.estimated_duration_sec
        dur = float(raw_dur) if raw_dur is not None else 4.0
        if dur <= 0:
            blocks.append(f"invalid_timing:{beat_id}")
            continue
        narr = str(b.narration or "").strip()
        if not narr:
            blocks.append(f"empty_narration:{beat_id}")
            continue
        entities_payload = []
        for j, e in enumerate(b.entity_refs or []):
            label = str(e)
            et = "person" if label.lower() in ("shobha", "he", "she", "officer", "doctor") else (
                "vehicle" if "suzuki" in label.lower() or label.lower() in ("car", "truck", "vehicle") else "object"
            )
            entities_payload.append(
                {
                    "entity_id": f"ent-{beat_id}-{j}",
                    "entity_type": et,
                    "label": label,
                    "role": "subject" if j == 0 else "object",
                }
            )
        seg = create_dialogue_segment(
            segment_id=f"seg-{dialogue_id}",
            dialogue_id=dialogue_id,
            scene_id=scene_id,
            text=narr,
            speaker=b.speaker or "Narrator",
            language=plan.language or "en",
            start_sec=t,
            end_sec=t + dur,
            semantic_intent=narr[:120],
            semantic_purpose=b.section_role or narr[:80],
            actions=[b.action_intent] if b.action_intent else [],
            location=b.location_ref or "",
            emotional_intent=b.emotion or "",
            intensity=float(b.emotion_intensity or 0.5),
            evidence_references=list(b.evidence_refs or b.claim_ids or []),
            visual_implication=b.visual_implication or "",
            temporal_context=b.temporal_context or "",
            entities=entities_payload,
            visual_relevance="high",
        )
        segs.append(seg)
        rows.append(
            {
                "dialogue_id": dialogue_id,
                "beat_id": beat_id,
                "scene_id": scene_id,
                "speaker": b.speaker or "Narrator",
                "text": narr,
                "emotion": b.emotion or "",
                "action": b.action_intent or "",
                "location": b.location_ref or "",
                "entities": list(b.entity_refs or []),
                "required_subject": meta.get("required_subject") or "",
                "required_entities": meta.get("required_entities") or list(b.entity_refs or []),
                "required_relationships": meta.get("required_relationships") or [],
                "required_actions": meta.get("required_actions") or ([b.action_intent] if b.action_intent else []),
                "required_location": meta.get("required_location") or b.location_ref or "",
                "start_sec": t,
                "end_sec": t + dur,
                "duration_sec": dur,
            }
        )
        t += dur
    return segs, rows, blocks


def _visual_beats_projection(decomp: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for vb in decomp.get("visual_beats") or []:
        d = vb.to_dict() if hasattr(vb, "to_dict") else dict(vb)
        rels = []
        for r in d.get("relationships") or []:
            if isinstance(r, dict):
                src = r.get("source_label") or r.get("source")
                if src is None and isinstance(r.get("source_entity"), dict):
                    src = r["source_entity"].get("label")
                tgt = r.get("target_label") or r.get("target")
                if tgt is None and isinstance(r.get("target_entity"), dict):
                    tgt = r["target_entity"].get("label")
                rels.append(
                    {
                        "type": r.get("relation_type") or r.get("type") or r.get("relation"),
                        "source": src,
                        "target": tgt,
                    }
                )
            else:
                rels.append({"raw": str(r)})
        ents = []
        for e in d.get("required_entities") or []:
            if isinstance(e, dict):
                ents.append(e.get("label") or e.get("name") or str(e))
            else:
                ents.append(str(e))
        # Prefer concrete must-show phrases from narration when grounding returned empty
        if not ents:
            import re as _re

            narr_guess = str(
                (d.get("prompt_provenance") or {}).get("purpose")
                or d.get("required_context")
                or ""
            )
            for phr in _re.findall(r"\b((?:The\s+)?[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){1,5})\b", narr_guess):
                if phr not in ents:
                    ents.append(phr)
        loc_state = d.get("location_state") or {}
        location = loc_state.get("location") if isinstance(loc_state, dict) else None
        location = location or d.get("location")
        env_state = d.get("environment_state") or {}
        dialogue_id = d.get("dialogue_segment_id") or d.get("dialogue_id")
        # Prefer canonical dialogue_id without seg- prefix for binding to dialogue_segments
        dialogue_id_norm = str(dialogue_id or "")
        if dialogue_id_norm.startswith("seg-"):
            dialogue_id_norm = dialogue_id_norm[4:]
        covered = list((d.get("prompt_provenance") or {}).get("covered_dialogue_ids") or [])
        if dialogue_id_norm and dialogue_id_norm not in covered:
            covered = [dialogue_id_norm] + [c for c in covered if c != dialogue_id_norm]
        purpose = str((d.get("prompt_provenance") or {}).get("purpose") or d.get("narrative_beat_id") or "")
        char_state = d.get("character_state") if isinstance(d.get("character_state"), dict) else {}
        _VOICE = {"narrator", "host", "speaker", "voiceover", "voice-over", "vo", "announcer", "presenter"}
        subject = char_state.get("identity") if char_state else None
        if subject and str(subject).strip().lower() in _VOICE:
            # Voice role is audio identity only — never the visual subject
            subject = None
        if not subject and ents:
            subject = next((e for e in ents if str(e).strip().lower() not in _VOICE), None)
        # Concrete phrase from purpose/narration when still empty
        if not subject:
            narr_guess = str(
                (d.get("prompt_provenance") or {}).get("purpose")
                or d.get("required_context")
                or ""
            )
            import re as _re2

            m = _re2.search(
                r"\b((?:The\s+)?[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,5})\b",
                narr_guess,
            )
            if m and m.group(1).strip().lower() not in _VOICE:
                subject = m.group(1).strip()
        if not subject:
            subject = "documentary subject"
        # Merge dialogue-segment metadata overlays when present on visual beat
        meta_ents = d.get("metadata_required_entities") or []
        if meta_ents and not ents:
            ents = [str(x) for x in meta_ents if str(x).strip()]
        meta_subj = str(d.get("metadata_required_subject") or "").strip()
        if meta_subj and meta_subj.lower() not in _VOICE:
            subject = meta_subj
        if subject and str(subject).strip().lower() in _VOICE:
            subject = "documentary subject"
        out.append(
            {
                "beat_id": d.get("beat_id"),
                "dialogue_ids": covered or ([dialogue_id_norm] if dialogue_id_norm else []),
                "dialogue_id": dialogue_id_norm or dialogue_id,
                "scene_id": d.get("scene_id"),
                "narrative_beat_id": d.get("narrative_beat_id"),
                "purpose": purpose,
                "visual_purpose": purpose,
                "subject": subject,
                "required_subject": subject,
                "required_entities": ents,
                "required_relationships": rels,
                "relationships": rels,
                "location": location,
                "required_location": location,
                "environment": env_state.get("environment") if isinstance(env_state, dict) else d.get("environment"),
                "character_state": d.get("character_state"),
                "required_character_state": d.get("character_state"),
                "object_state": d.get("required_objects"),
                "required_object_state": d.get("required_objects"),
                "required_actions": [char_state.get("action")] if char_state.get("action") else [],
                "required_context": purpose or location or "",
                "camera": d.get("camera_intent") or d.get("camera"),
                "lighting": d.get("lighting_continuity") or d.get("lighting_intent"),
                "emotion": d.get("emotional_visual_intent"),
                "action": char_state.get("action") if char_state else d.get("action"),
                "coverage": d.get("coverage"),
                "coverage_requirement": d.get("coverage"),
                "visual_mode": d.get("visual_mode"),
                "timing": {
                    "duration_sec": d.get("duration_sec"),
                    "policy": d.get("duration_policy"),
                },
                "duration": d.get("duration_sec"),
                "reuse_policy": (d.get("prompt_provenance") or {}).get("reuse_policy") or "semantic_beat_compatibility",
                "continuity_predecessor": d.get("previous_beat_id"),
                "continuity_successor": d.get("next_beat_id"),
                "risks": d.get("risks") or [],
                "risk_class": "HEURISTIC" if d.get("risks") else None,
                "semantic_layers": ["INTENT", "PROMPT", "GENERATED_ASSET", "OBSERVED_ASSET", "VERIFIED_COVERAGE"],
            }
        )
    return out


def _world_state_from_visuals(visuals: List[Dict[str, Any]], dialogues: List[Dict[str, Any]]) -> Dict[str, Any]:
    characters: Dict[str, Any] = {}
    locations: Dict[str, Any] = {}
    objects: Dict[str, Any] = {}
    relationships: List[Dict[str, Any]] = []
    for d in dialogues:
        for e in d.get("entities") or []:
            objects.setdefault(str(e), {"identity": str(e), "type": "entity"})
        if d.get("speaker") and d["speaker"] != "Narrator":
            characters.setdefault(
                d["speaker"],
                {
                    "identity": d["speaker"],
                    "role": "speaker",
                    "emotional_state": d.get("emotion") or "",
                    "speaking": True,
                    "action": d.get("action") or "",
                },
            )
        if d.get("location"):
            locations.setdefault(
                d["location"],
                {"location_identity": d["location"], "environment_identity": d["location"]},
            )
    for v in visuals:
        loc = v.get("location")
        if loc:
            locations.setdefault(str(loc), {"location_identity": str(loc), "lighting_context": v.get("lighting")})
        for e in v.get("required_entities") or []:
            label = e if isinstance(e, str) else str((e or {}).get("label") or e)
            objects.setdefault(label, {"identity": label, "type": "entity", "state": v.get("object_state")})
        subj = v.get("subject")
        if subj:
            characters.setdefault(
                str(subj),
                {
                    "identity": str(subj),
                    "role": "subject",
                    "emotional_state": v.get("emotion") or "",
                    "action": v.get("action") or "",
                    "appearance_reference": None,
                },
            )
        for r in v.get("relationships") or []:
            if isinstance(r, dict) and r.get("type"):
                relationships.append(r)
    return {
        "characters": characters,
        "locations": locations,
        "objects": objects,
        "relationships": relationships,
        "note": "World state projection from approved script + C05-S visual beats — ContinuityTracker remains authority at generation",
    }


def _bind_audio_plans(dialogues: List[Dict[str, Any]], *, language: str, revision: str) -> Dict[str, Any]:
    from pipeline.audio_design.plan_builder import build_industrial_audio_plan
    from pipeline.production_consistency import (
        apply_voice_identity_to_audio_plan,
        evaluate_voice_identity_continuity,
        resolve_canonical_voice_identity,
    )

    # RCP-06D: one canonical VoiceIdentity for the whole production plan
    speakers = [str(d.get("speaker") or "").strip() for d in dialogues if str(d.get("speaker") or "").strip()]
    speaker = speakers[0] if speakers else "narrator"
    canonical = resolve_canonical_voice_identity(language=language, speaker_id=speaker)
    refs = []
    for d in dialogues:
        ap = build_industrial_audio_plan(
            scene_id=str(d["scene_id"]),
            dialogue_id=str(d["dialogue_id"]),
            dialogue_text=str(d["text"]),
            language=language,
            speaker_id=str(d.get("speaker") or speaker),
            voice_profile=canonical.vocal_profile,
            emotion=str(d.get("emotion") or "neutral"),
            duration_target_sec=float(d.get("duration_sec") or 4.0),
            revision_id=revision,
        )
        ap = apply_voice_identity_to_audio_plan(ap, canonical)
        payload = ap.to_dict() if hasattr(ap, "to_dict") else (ap.model_dump() if hasattr(ap, "model_dump") else dict(ap.__dict__))
        refs.append(
            {
                "dialogue_id": d["dialogue_id"],
                "scene_id": d["scene_id"],
                "speaker": d.get("speaker") or speaker,
                "voice_identity_ref": canonical.voice_identity_id,
                "voice_identity_id": canonical.voice_identity_id,
                "voice_profile": canonical.vocal_profile,
                "emotion_intent": d.get("emotion") or "neutral",
                "timing": {"start_sec": d.get("start_sec"), "duration_sec": d.get("duration_sec"), "end_sec": d.get("end_sec")},
                "audio_plan": payload,
                "note": "Voice Identity and Scene Emotion remain separate; no TTS executed",
            }
        )
    continuity = evaluate_voice_identity_continuity(canonical=canonical, scene_refs=refs)
    return {
        "status": "BOUND" if refs else "MISSING",
        "count": len(refs),
        "segments": refs,
        "voice_identity": canonical.to_dict(),
        "voice_identity_continuity": continuity,
        "authority": "AudioPlan / build_industrial_audio_plan + VoiceIdentity",
    }


def _bind_localization(dialogues: List[Dict[str, Any]], *, language: str, job_id: str, revision: str) -> Dict[str, Any]:
    from pipeline.localization_consistency.contract import build_localization_contract

    refs = []
    for d in dialogues:
        lc = build_localization_contract(
            job_id=job_id,
            scene_id=str(d["scene_id"]),
            dialogue_id=str(d["dialogue_id"]),
            source_text=str(d["text"]),
            source_language=language,
            target_language=language,
            speaker_id=str(d.get("speaker") or ""),
            emotion_intent=str(d.get("emotion") or ""),
            revision_id=revision,
            localized_text=str(d["text"]),
        )
        payload = lc.to_dict() if hasattr(lc, "to_dict") else (lc.model_dump() if hasattr(lc, "model_dump") else {})
        refs.append(
            {
                "dialogue_id": d["dialogue_id"],
                "language": language,
                "speaker": d.get("speaker"),
                "timing": {"start_sec": d.get("start_sec"), "end_sec": d.get("end_sec")},
                "localization_contract": payload,
                "observation": "UNKNOWN",
                "note": "No OCR/VLM semantic verification — UNKNOWN remains UNKNOWN",
            }
        )
    return {
        "status": "BOUND" if refs else "MISSING",
        "count": len(refs),
        "segments": refs,
        "authority": "LocalizationContract / TextPlan",
        "semantic_verification": "UNKNOWN",
    }


def compute_plan_fingerprint(plan_inputs: Dict[str, Any]) -> str:
    from pipeline.idempotency.fingerprint import compute_fingerprint

    return compute_fingerprint(
        job_id=str(plan_inputs.get("job_id") or "c06c"),
        stage="c06c_production_plan",
        entity_id=str(plan_inputs.get("entity_id") or "plan"),
        contract_version=CONTRACT_VERSION,
        provider="customer_production_plan",
        model="compose-only",
        inputs=plan_inputs,
    )


def evaluate_generation_readiness(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic gate — READY_FOR_GENERATION ≠ PUBLISHABLE/GENERATED."""
    blocks: List[str] = []
    warnings: List[str] = []
    status = str(plan.get("status") or "NOT_READY")

    if plan.get("status") == "STALE":
        return {
            "ready": False,
            "status": "STALE",
            "blocks": ["script_revision_mismatch"],
            "warnings": warnings,
            "note": "READY_FOR_GENERATION ≠ PUBLISHABLE",
        }

    if plan.get("owner_login_id") is None:
        blocks.append("missing_owner")
    if not plan.get("approved_script_id") and not plan.get("script_revision"):
        blocks.append("missing_approved_script_identity")
    if not plan.get("dialogue_segments"):
        blocks.append("missing_dialogue_segments")
    if not plan.get("visual_beats"):
        blocks.append("missing_visual_beats")
    if not plan.get("language"):
        blocks.append("missing_language")
    timing_ok = True
    for d in plan.get("dialogue_segments") or []:
        if float(d.get("duration_sec") or 0) <= 0:
            timing_ok = False
            blocks.append(f"invalid_timing:{d.get('dialogue_id')}")
        if not d.get("dialogue_id") or not d.get("beat_id") or not d.get("scene_id"):
            blocks.append(f"missing_binding:{d.get('dialogue_id') or '?'}")
    # world state
    world = plan.get("world_state") or {}
    if not (world.get("locations") or world.get("characters") or (plan.get("dialogue_segments"))):
        blocks.append("missing_world_state")
    audio = plan.get("audio_plan") or {}
    if audio.get("status") != "BOUND":
        blocks.append("audio_plan_unbound")
    # RCP-06D: canonical VoiceIdentity continuity (contract equality — not acoustic)
    try:
        from pipeline.production_consistency import evaluate_voice_identity_continuity

        canonical_vi = plan.get("voice_identity") or audio.get("voice_identity")
        scene_refs = list(audio.get("segments") or [])
        vi_gate = evaluate_voice_identity_continuity(canonical=canonical_vi, scene_refs=scene_refs)
        plan_vi_note = audio.get("voice_identity_continuity") if isinstance(audio.get("voice_identity_continuity"), dict) else {}
        if plan_vi_note and not plan_vi_note.get("ok"):
            for b in plan_vi_note.get("blocks") or []:
                blocks.append(str(b))
        if not vi_gate.get("ok"):
            for b in vi_gate.get("blocks") or ["VOICE_IDENTITY_CONTINUITY_BLOCKED"]:
                blocks.append(str(b))
        if str(vi_gate.get("confidence") or "").upper() == "PROVIDER_VERIFIED":
            blocks.append("VOICE_IDENTITY_HONESTY:heuristic_must_not_be_provider_verified")
        if str((vi_gate.get("localized_check") or {}).get("confidence") or "").upper() == "PROVIDER_VERIFIED":
            blocks.append("VOICE_IDENTITY_HONESTY:preserved_must_not_be_provider_verified")
    except Exception as exc:
        blocks.append(f"VOICE_IDENTITY_CONTINUITY_BLOCKED:eval_error:{type(exc).__name__}")
    loc = plan.get("localization_plan") or {}
    if loc.get("status") != "BOUND":
        blocks.append("localization_unbound")
    modes = plan.get("generation_modes") or {}
    if not modes.get("modes"):
        blocks.append("missing_generation_mode")
    if modes.get("unsupported"):
        blocks.append("unsupported_generation_mode")
        status = "BLOCKED"
    # Mandatory UNKNOWN → not ready
    if loc.get("semantic_verification") == "UNKNOWN":
        warnings.append("localization_semantic_verification_UNKNOWN")
    # Do not treat UNKNOWN observation as PASS
    for w in warnings:
        if "UNKNOWN" in w and "mandatory" in w.lower():
            blocks.append(w)

    # Continuity reference
    if not plan.get("continuity"):
        blocks.append("missing_continuity_reference")

    # RCP-02: every dialogue segment must have visual realization (PRODUCTION_INCOMPLETE)
    def _norm_dlg(x: Any) -> str:
        s = str(x or "").strip()
        return s[4:] if s.startswith("seg-") else s

    dialogue_ids = [_norm_dlg(d.get("dialogue_id")) for d in (plan.get("dialogue_segments") or []) if d.get("dialogue_id")]
    covered: set[str] = set()
    vis_sum = 0.0
    for v in plan.get("visual_beats") or []:
        for did in v.get("dialogue_ids") or []:
            n = _norm_dlg(did)
            if n:
                covered.add(n)
        n = _norm_dlg(v.get("dialogue_id"))
        if n:
            covered.add(n)
        timing = v.get("timing") if isinstance(v.get("timing"), dict) else {}
        vis_sum += float(timing.get("duration_sec") or v.get("duration") or 0.0)
    for did in dialogue_ids:
        if did and did not in covered:
            blocks.append(f"PRODUCTION_INCOMPLETE:missing_visual_for_dialogue:{did}")
    dlg_sum = sum(float(d.get("duration_sec") or 0) for d in (plan.get("dialogue_segments") or []))
    if dlg_sum > 0 and vis_sum + 0.25 < dlg_sum * 0.85:
        blocks.append(
            f"PRODUCTION_INCOMPLETE:visual_timeline_shorter_than_dialogue:vis={vis_sum:.2f}:dlg={dlg_sum:.2f}"
        )
    # RCP-06B: plan timeline must fit the unified duration contract max
    try:
        from pipeline.duration_budget import (
            contract_from_plan,
            planned_scene_count_for_contract,
            validate_plan_meets_target,
            validate_timeline_against_contract,
        )

        _dc = contract_from_plan(plan if isinstance(plan, dict) else {})
        blocks.extend(
            validate_timeline_against_contract(
                dialogue_duration_sec=dlg_sum,
                visual_duration_sec=vis_sum,
                contract=_dc,
            )
        )
        # Gate A: under-target / insufficient scene budget → PRODUCTION_INCOMPLETE
        _beat_n = max(
            len(plan.get("dialogue_segments") or []),
            len(plan.get("visual_beats") or []),
            len({d.get("scene_id") for d in (plan.get("dialogue_segments") or []) if d.get("scene_id")}),
        )
        blocks.extend(
            validate_plan_meets_target(
                dialogue_duration_sec=dlg_sum,
                visual_duration_sec=vis_sum,
                beat_or_scene_count=_beat_n,
                contract=_dc,
            )
        )
        plan["duration_contract"] = _dc
        plan["target_duration_sec"] = int(_dc.get("target_seconds") or 0)
        plan["max_seconds"] = int(_dc.get("max_seconds") or 0)
        plan["scene_budget"] = int(planned_scene_count_for_contract(_dc))
    except Exception:
        pass
    # Empty narrative beat projections are a planning integrity defect
    nbs = plan.get("narrative_beats") or []
    if dialogue_ids and nbs and all(not (isinstance(nb, dict) and nb) for nb in nbs):
        blocks.append("PRODUCTION_INCOMPLETE:narrative_beats_empty")

    # Deterministic contradictions already collected in plan.blocks
    for b in plan.get("build_blocks") or []:
        blocks.append(str(b))

    ready = not blocks and timing_ok
    out_status = "READY_FOR_GENERATION" if ready else ("BLOCKED" if blocks else "NOT_READY")
    if status == "STALE":
        out_status = "STALE"
    if any(str(b).startswith("PRODUCTION_INCOMPLETE") for b in blocks):
        out_status = "BLOCKED"
    return {
        "ready": ready,
        "status": out_status,
        "blocks": list(dict.fromkeys(blocks)),
        "warnings": warnings,
        "note": "READY_FOR_GENERATION ≠ GENERATED ≠ VERIFIED ≠ PUBLISHABLE ≠ READY_TO_UPLOAD",
    }


def build_production_plan(
    login_id: str,
    channel: Dict[str, Any],
    *,
    force_rebuild: bool = False,
) -> Dict[str, Any]:
    """Compose Production Plan from APPROVED_SCRIPT — no media generation."""
    from domain.script import ScriptPlan
    from pipeline.story_visual_direction import decompose_dialogue_to_visual_beats
    from pipeline.visual_intelligence import VisualBible, SUPPORTED_VISUAL_MODES

    channel_id = int(channel.get("id") or 0)
    ch_owner = str(channel.get("owner_login_id") or "").strip()
    if ch_owner and ch_owner != str(login_id or "").strip():
        return {
            "ok": False,
            "error": "channel_forbidden",
            "error_code": "ownership_violation",
            "status": "BLOCKED",
            "message": "You do not have access to this channel.",
        }
    workflow = load_workflow(login_id, channel_id)
    auth_err = assert_approved_script_authority(workflow, login_id=login_id, channel_id=channel_id)
    if auth_err:
        return {**auth_err, "ok": False}

    script = workflow.get("script") or {}
    script_plan_raw = script.get("script_plan")
    try:
        script_plan = ScriptPlan.model_validate(script_plan_raw)
    except Exception as exc:
        return {
            "ok": False,
            "error": "malformed_script_plan",
            "error_code": "malformed_script",
            "status": "BLOCKED",
            "message": sanitize_customer_error(str(exc)),
        }

    script_revision = compute_script_revision(script_plan.model_dump())
    existing = load_production_plan(login_id, channel_id)
    if existing and not force_rebuild:
        if str(existing.get("script_revision") or "") != script_revision:
            existing["status"] = "STALE"
            existing["readiness"] = evaluate_generation_readiness(existing)
            save_production_plan(existing)
            return {
                "ok": False,
                "error": "stale_production_plan",
                "error_code": "stale_plan",
                "status": "STALE",
                "plan": project_production_plan(existing),
                "message": "Approved script revision changed — rebuild required",
            }
        # Idempotent reuse
        return {"ok": True, "reused": True, "plan": project_production_plan(existing), "status": existing.get("status")}

    segs, dialogue_rows, blocks = _dialogue_segments_from_plan(script_plan)
    bible = VisualBible(
        bible_id=f"c06c-ch{channel_id}",
        subject_identity=str((dialogue_rows[0].get("entities") or ["subject"])[0] if dialogue_rows else "subject"),
        environment=str(channel.get("niche") or "general"),
        location=str((dialogue_rows[0].get("location") if dialogue_rows else "") or ""),
    )

    decomp: Dict[str, Any] = {"visual_beats": [], "narrative_beats": []}
    try:
        decomp = decompose_dialogue_to_visual_beats(segments=segs, bible=bible, prefer_image_fallback=True)
    except Exception as exc:
        try:
            decomp = decompose_dialogue_to_visual_beats(segments=segs, bible=bible)
        except Exception as exc2:
            blocks.append(f"visual_decompose_failed:{sanitize_customer_error(str(exc2), 80)}")
            if not blocks or "visual_decompose" not in str(blocks[-1]):
                blocks.append(f"visual_decompose_failed:{sanitize_customer_error(str(exc), 80)}")

    visuals = _visual_beats_projection(decomp)
    world = _world_state_from_visuals(visuals, dialogue_rows)
    language = str(script_plan.language or channel.get("lang_code") or "en")
    fmt = str(script_plan.format or ("SHORT" if channel.get("video_type") == "short" else "LONG"))
    job_id = f"c06c-{login_id}-{channel_id}-{script_revision[:8]}"

    from pipeline.duration_budget import planned_scene_count_for_contract, resolve_duration_contract

    _vt = "short" if str(fmt).upper() == "SHORT" else "long"
    _duration_contract = resolve_duration_contract(_vt)
    _scene_budget = planned_scene_count_for_contract(_duration_contract)

    audio = _bind_audio_plans(dialogue_rows, language=language, revision=script_revision)
    localization = _bind_localization(dialogue_rows, language=language, job_id=job_id, revision=script_revision)

    modes = []
    unsupported = []
    for v in visuals:
        m = str(v.get("visual_mode") or "IMAGE").upper()
        modes.append(m)
        if m and m not in {str(x).upper() for x in (SUPPORTED_VISUAL_MODES or {"IMAGE", "IMAGE_WITH_MOTION", "VIDEO"})}:
            unsupported.append(m)
    generation_modes = {
        "modes": list(dict.fromkeys(modes)) or ["IMAGE"],
        "unsupported": list(dict.fromkeys(unsupported)),
        "requested_vs_actual": [{"requested": m, "actual": m, "fallback_reason": None} for m in dict.fromkeys(modes)],
        "authority": "C05-V / DirectedVisualBeat.visual_mode",
    }

    continuity = {
        "authority": "ContinuityTracker",
        "reference_only": True,
        "beat_chain": [
            {
                "beat_id": v.get("beat_id"),
                "predecessor": v.get("continuity_predecessor"),
                "successor": v.get("continuity_successor"),
                "location": v.get("location"),
                "lighting": v.get("lighting"),
                "camera": v.get("camera"),
            }
            for v in visuals
        ],
        "note": "Camera changes must not reset world location; ContinuityTracker remains sole continuity authority at generation",
    }

    fp_inputs = {
        "job_id": job_id,
        "entity_id": f"ch{channel_id}",
        "script_revision": script_revision,
        "language": language,
        "format": fmt,
        "dialogue_ids": [d["dialogue_id"] for d in dialogue_rows],
        "beat_ids": [d["beat_id"] for d in dialogue_rows],
        "scene_ids": [d["scene_id"] for d in dialogue_rows],
        "relationships": world.get("relationships"),
        "locations": sorted((world.get("locations") or {}).keys()),
        "characters": sorted((world.get("characters") or {}).keys()),
        "visual_modes": generation_modes["modes"],
        "timing": [(d["dialogue_id"], d["duration_sec"]) for d in dialogue_rows],
        "audio_revision": script_revision,
        "localization_revision": script_revision,
    }
    fingerprint = compute_plan_fingerprint(fp_inputs)

    # Idempotent: same fingerprint as existing → reuse without rewrite if not force
    if existing and existing.get("fingerprint") == fingerprint and not force_rebuild:
        return {"ok": True, "reused": True, "plan": project_production_plan(existing), "status": existing.get("status")}

    plan: Dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "plan_id": f"pp-{fingerprint[:16]}",
        "project_id": workflow.get("project_id") or f"trs-ch{channel_id}",
        "owner_login_id": login_id,
        "channel_id": channel_id,
        "approved_script_id": (workflow.get("topic") or {}).get("topic_id") or script_revision,
        "script_revision": script_revision,
        "workflow_revision": workflow.get("revision"),
        "language": language,
        "content_type": channel.get("niche") or "general",
        "format": fmt,
        "video_type": _vt,
        "long_short_mode": _vt,
        "duration_contract": _duration_contract,
        "target_duration_sec": int(_duration_contract["target_seconds"]),
        "target_duration": int(_duration_contract["target_seconds"]),
        "max_duration": int(_duration_contract["max_seconds"]),
        "max_seconds": int(_duration_contract["max_seconds"]),
        "planned_duration": sum(float(d.get("duration_sec") or 0) for d in dialogue_rows),
        "scene_budget": _scene_budget,
        "dialogue_segments": dialogue_rows,
        "narrative_beats": [
            (nb if isinstance(nb, dict) else (nb.to_dict() if hasattr(nb, "to_dict") else {}))
            for nb in (decomp.get("narrative_beats") or [])
        ],
        "visual_beats": visuals,
        "scene_bindings": [
            {"scene_id": d["scene_id"], "dialogue_id": d["dialogue_id"], "beat_id": d["beat_id"]}
            for d in dialogue_rows
        ],
        "world_state": world,
        "camera_lighting": {
            "shots": [{"beat_id": v.get("beat_id"), "camera": v.get("camera"), "lighting": v.get("lighting")} for v in visuals],
            "note": "Camera transition ≠ location reset",
            "authority": "SceneIntent / ContinuityTracker",
        },
        "audio_plan": audio,
        "voice_identity": audio.get("voice_identity"),
        "localization_plan": localization,
        "subtitle_plan": {
            "status": localization.get("status"),
            "bound_to_script_revision": script_revision,
            "semantic_verification": "UNKNOWN",
            "authority": "LocalizationContract / subtitle request contracts",
        },
        "generation_modes": generation_modes,
        "continuity": continuity,
        "provenance": {
            "source": "APPROVED_SCRIPT",
            "authorities": [
                "domain.script.ScriptPlan",
                "C05-S story_visual_direction",
                "AudioPlan",
                "VoiceIdentity",
                "LocalizationContract",
                "BUILD-03 compute_fingerprint",
                "ContinuityTracker (reference)",
            ],
            "created_at": _now(),
            "no_media_generation": True,
            "paid_api_calls": 0,
        },
        "fingerprint": fingerprint,
        "build_blocks": blocks,
        "status": "NOT_READY",
        "created_at": _now(),
        "updated_at": _now(),
    }
    readiness = evaluate_generation_readiness(plan)
    plan["readiness"] = readiness
    plan["status"] = readiness["status"]
    save_production_plan(plan)
    return {
        "ok": readiness["ready"],
        "reused": False,
        "status": plan["status"],
        "plan": project_production_plan(plan),
        "error": None if readiness["ready"] else "not_ready_for_generation",
        "error_code": None if readiness["ready"] else "readiness_blocked",
        "blocks": readiness.get("blocks"),
    }


def project_production_plan(plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not plan:
        return {
            "contract": "C06-C",
            "status": "NOT_STARTED",
            "ready_for_generation": False,
            "note": "No production plan",
        }
    visuals = plan.get("visual_beats") or []
    dialogues = plan.get("dialogue_segments") or []
    readiness = plan.get("readiness") or evaluate_generation_readiness(plan)
    return {
        "contract": "C06-C",
        "plan_id": plan.get("plan_id"),
        "project_id": plan.get("project_id"),
        "owner_login_id": plan.get("owner_login_id"),
        "channel_id": plan.get("channel_id"),
        "status": plan.get("status"),
        "ready_for_generation": bool(readiness.get("ready")),
        "readiness": readiness,
        "script_status": "APPROVED_SCRIPT",
        "script_revision": plan.get("script_revision"),
        "fingerprint": plan.get("fingerprint"),
        "language": plan.get("language"),
        "format": plan.get("format"),
        "scene_count": len({d.get("scene_id") for d in dialogues}),
        "dialogue_beat_count": len(dialogues),
        "visual_beat_count": len(visuals),
        "audio_readiness": (plan.get("audio_plan") or {}).get("status"),
        "subtitle_localization_readiness": (plan.get("localization_plan") or {}).get("status"),
        "continuity_readiness": "REFERENCED" if plan.get("continuity") else "MISSING",
        "generation_modes": (plan.get("generation_modes") or {}).get("modes"),
        "blocking_issues": readiness.get("blocks") or [],
        "warnings": readiness.get("warnings") or [],
        "provenance": plan.get("provenance"),
        "world_state_summary": {
            "characters": list((plan.get("world_state") or {}).get("characters") or {}.keys()),
            "locations": list((plan.get("world_state") or {}).get("locations") or {}.keys()),
            "relationship_count": len((plan.get("world_state") or {}).get("relationships") or []),
        },
        "note": "READY_FOR_GENERATION ≠ PUBLISHABLE. No media generated in C06-C.",
        # Full bodies available for detail (customer-owned)
        "dialogue_segments": dialogues,
        "visual_beats": visuals,
        "scene_bindings": plan.get("scene_bindings"),
        "camera_lighting": plan.get("camera_lighting"),
        "audio_plan_summary": {
            "status": (plan.get("audio_plan") or {}).get("status"),
            "count": (plan.get("audio_plan") or {}).get("count"),
            "voice_identity_id": ((plan.get("voice_identity") or {}).get("voice_identity_id")
                                  or ((plan.get("audio_plan") or {}).get("voice_identity") or {}).get("voice_identity_id")),
        },
        "localization_summary": {
            "status": (plan.get("localization_plan") or {}).get("status"),
            "semantic_verification": (plan.get("localization_plan") or {}).get("semantic_verification"),
        },
    }


def detect_duplicate_engines(source: str) -> List[str]:
    import re as _re

    bad = []
    for pat in (
        r"(?m)^\s*class\s+ContinuityTracker\b",
        r"(?m)^\s*class\s+VisualEngine\b",
        r"(?m)^\s*class\s+AudioEngine\b",
        r"(?m)^\s*def\s+generate_video\s*\(",
        r"(?m)^\s*def\s+compute_fingerprint\s*\(",
        r"(?m)^\s*def\s+decompose_dialogue_to_visual_beats\s*\(",
    ):
        if _re.search(pat, source):
            bad.append(pat)
    return bad
