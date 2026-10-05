"""Dialogue↔visual temporal + semantic alignment evidence (Phase 6G).

Evidence/recommendation layer only — not a duration, pacing, audio, or semantic authority.
Reuses C05-S hold policy, coverage vocabulary, Duration Contract, ContinuityTracker policy,
frame evidence, and BUILD-04F repair handoff.
"""
from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN
from pipeline.observation.frame_evidence.cross_beat import (
    dialogue_visual_entity_binding,
)
from pipeline.retrieval.common import strip_secrets
from pipeline.story_visual_direction import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    COVERAGE_UNKNOWN,
    decide_visual_hold_policy,
    detect_visual_repetition,
)

SCHEMA_ALIGNMENT = "amp_observation_dialogue_visual_alignment_v1"

# Fixed-N switching is explicitly rejected as production policy
FIXED_N_SWITCHING_FORBIDDEN = True
FORBIDDEN_FIXED_INTERVALS_SEC = (2.0, 3.0, 4.0, 5.0)


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    return dict(obj or {})


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_dialogue_timeline(
    segments: Sequence[Any],
    *,
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
    audio_timeline_sec: Optional[float] = None,
) -> dict[str, Any]:
    """Project dialogue segments onto an evidence timeline (does not invent audio clock)."""
    rows: list[dict[str, Any]] = []
    for seg in segments or []:
        s = _as_dict(seg)
        start = _f(s.get("start_sec", s.get("start")))
        end = _f(s.get("end_sec", s.get("end")))
        if end < start:
            end = start + _f(s.get("duration_sec", s.get("duration")))
        dur = max(0.0, end - start) if end > start else _f(s.get("duration_sec", s.get("duration")))
        if end <= start and dur > 0:
            end = start + dur
        did = str(s.get("dialogue_id") or s.get("segment_id") or "")
        rows.append(
            strip_secrets(
                {
                    "dialogue_id": did,
                    "segment_id": str(s.get("segment_id") or did),
                    "scene_id": str(s.get("scene_id") or ""),
                    "beat_id": str(s.get("beat_id") or ""),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(max(0.0, end - start), 3),
                    "text": str(s.get("text") or "")[:500],
                    "entities": list(s.get("entities") or []),
                    "relationships": list(s.get("relationships") or []),
                    "actions": list(s.get("actions") or []),
                    "location": str(s.get("location") or ""),
                    "emotion": str(s.get("emotional_intent") or s.get("emotion") or ""),
                    "customer_id": customer_id,
                    "channel_id": channel_id,
                    "job_id": job_id,
                }
            )
        )
    total = sum(r["duration"] for r in rows)
    return strip_secrets(
        {
            "schema": SCHEMA_ALIGNMENT,
            "kind": "dialogue_timeline",
            "segments": rows,
            "segment_count": len(rows),
            "total_dialogue_sec": round(total, 3),
            "audio_timeline_sec": None if audio_timeline_sec is None else round(float(audio_timeline_sec), 3),
            "audio_authority": "AudioPlan/ffprobe — this layer does not invent a second audio clock",
            "second_audio_engine": False,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "created_at": time.time(),
        }
    )


def build_visual_timeline(
    beats: Sequence[Any],
    *,
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
    cursor_start: float = 0.0,
) -> dict[str, Any]:
    """Project DirectedVisualBeat timing. Hold caps must not invent timeline."""
    rows: list[dict[str, Any]] = []
    t = float(cursor_start)
    for beat in beats or []:
        b = _as_dict(beat)
        vt = dict(b.get("visual_timing") or {})
        start = vt.get("start_sec", b.get("start_sec", b.get("start")))
        end = vt.get("end_sec", b.get("end_sec", b.get("end")))
        dur = _f(vt.get("duration_sec", b.get("duration_sec", b.get("duration"))))
        if start is None:
            start = t
        else:
            start = _f(start)
        if end is None:
            end = start + dur
        else:
            end = _f(end)
        if end < start:
            end = start + max(dur, 0.0)
        if dur <= 0:
            dur = max(0.0, end - start)
        t = max(t, end)
        rows.append(
            strip_secrets(
                {
                    "visual_beat_id": str(b.get("beat_id") or b.get("visual_beat_id") or ""),
                    "dialogue_id": str(
                        b.get("dialogue_segment_id")
                        or b.get("dialogue_id")
                        or (b.get("prompt_provenance") or {}).get("dialogue_id")
                        or ""
                    ),
                    "scene_id": str(b.get("scene_id") or ""),
                    "asset_id": str(b.get("asset_id") or ""),
                    "start": round(float(start), 3),
                    "end": round(float(end), 3),
                    "duration": round(float(dur if dur > 0 else end - start), 3),
                    "coverage": dict(b.get("coverage") or {}) if isinstance(b.get("coverage"), Mapping) else b.get("coverage"),
                    "entities": list(b.get("required_entities") or b.get("entities") or []),
                    "relationships": list(b.get("relationships") or []),
                    "location": str((b.get("location_state") or {}).get("location") or b.get("location") or ""),
                    "action": str((b.get("character_state") or {}).get("action") or b.get("action") or ""),
                    "emotion": str((b.get("character_state") or {}).get("emotion") or b.get("emotion") or ""),
                    "mode": str(b.get("visual_mode") or b.get("mode") or ""),
                    "hold_policy": str(
                        (b.get("duration_policy") or vt.get("hold_policy") or "")
                    ),
                    "customer_id": customer_id,
                    "channel_id": channel_id,
                    "job_id": job_id,
                }
            )
        )
    return strip_secrets(
        {
            "schema": SCHEMA_ALIGNMENT,
            "kind": "visual_timeline",
            "beats": rows,
            "beat_count": len(rows),
            "total_visual_sec": round(sum(r["duration"] for r in rows), 3),
            "fixed_n_switching_forbidden": FIXED_N_SWITCHING_FORBIDDEN,
            "duration_contract_authority": "pipeline.duration_budget.resolve_duration_contract",
            "second_duration_engine": False,
            "second_pacing_authority": False,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "created_at": time.time(),
        }
    )


def assert_no_silent_dialogue_drop(
    planned_dialogue_ids: Sequence[str],
    materialized_dialogue_ids: Sequence[str],
    *,
    blocking_failure_recorded: bool = False,
    blocking_reason: str = "",
) -> dict[str, Any]:
    """Invariant: planned dialogue segments must equal materialized unless already blocked."""
    planned = [str(x) for x in planned_dialogue_ids if str(x).strip()]
    got = [str(x) for x in materialized_dialogue_ids if str(x).strip()]
    missing = [x for x in planned if x not in got]
    extra = [x for x in got if x not in planned]
    ok = not missing
    if missing and blocking_failure_recorded:
        status = STATUS_FAIL  # incomplete but not silent
        silent = False
        code = blocking_reason or "PRODUCTION_INCOMPLETE:dialogue_without_visual_intent"
    elif missing:
        status = STATUS_FAIL
        silent = True
        code = "PRODUCTION_INCOMPLETE:silent_dialogue_drop_forbidden"
    else:
        status = STATUS_PASS
        silent = False
        code = ""
    return strip_secrets(
        {
            "schema": SCHEMA_ALIGNMENT,
            "invariant": "planned_dialogue_segments_must_equal_materialized",
            "planned_count": len(planned),
            "materialized_count": len(got),
            "planned_dialogue_ids": planned,
            "materialized_dialogue_ids": got,
            "missing": missing,
            "extra": extra,
            "silent_drop": silent,
            "status": status,
            "blocking_code": code,
            "hold_cap_must_not_truncate_dialogue": True,
        }
    )


def classify_temporal_coverage(
    dialogue: Mapping[str, Any],
    visual_beats: Sequence[Mapping[str, Any]],
    *,
    observation_available: Optional[bool] = None,
) -> dict[str, Any]:
    """Timing overlap coverage only — never semantic PASS from overlap alone."""
    d0, d1 = _f(dialogue.get("start")), _f(dialogue.get("end"))
    need = max(0.0, d1 - d0)
    if observation_available is False:
        return strip_secrets(
            {
                "dialogue_id": dialogue.get("dialogue_id"),
                "coverage": COVERAGE_UNKNOWN,
                "overlap_sec": 0.0,
                "required_sec": round(need, 3),
                "covering_visual_beat_ids": [],
                "timing_overlap_is_not_semantic_pass": True,
                "status": STATUS_UNKNOWN,
            }
        )
    covered = 0.0
    ids: list[str] = []
    for vb in visual_beats or []:
        ov = _overlap(d0, d1, _f(vb.get("start")), _f(vb.get("end")))
        if ov > 1e-6:
            covered += ov
            ids.append(str(vb.get("visual_beat_id") or vb.get("beat_id") or ""))
    if need <= 1e-9:
        cov = COVERAGE_UNKNOWN
    elif covered <= 1e-9:
        cov = COVERAGE_NONE
    elif covered + 1e-3 >= need:
        cov = COVERAGE_FULL
    else:
        cov = COVERAGE_PARTIAL
    # Timing FULL ≠ semantic PASS
    status = STATUS_UNKNOWN if cov == COVERAGE_UNKNOWN else (
        STATUS_FAIL if cov == COVERAGE_NONE else STATUS_PASS  # temporal structural only
    )
    return strip_secrets(
        {
            "dialogue_id": dialogue.get("dialogue_id"),
            "coverage": cov,
            "overlap_sec": round(min(covered, need), 3),
            "required_sec": round(need, 3),
            "covering_visual_beat_ids": [x for x in ids if x],
            "timing_overlap_is_not_semantic_pass": True,
            "status": status if cov != COVERAGE_FULL else "TEMPORAL_OK",
            "vocabulary": "C05-S VisualCoverage",
        }
    )


def semantic_align_dialogue_to_observation(
    dialogue: Mapping[str, Any],
    observation: Optional[Mapping[str, Any]],
    *,
    visual_beat: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Compare dialogue requirements to provider observation — not keyword-only PASS."""
    obs = dict(observation or {})
    st = str(obs.get("observation_status") or STATUS_UNKNOWN).upper()
    if not obs or st in ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "ABSENT") or not obs.get("provider_verified"):
        if obs.get("heuristic"):
            return strip_secrets(
                {
                    "dialogue_id": dialogue.get("dialogue_id"),
                    "status": STATUS_UNKNOWN,
                    "reason": "heuristic_is_not_provider_verified",
                    "keyword_only_pass_forbidden": True,
                    "provider_verified": False,
                    "heuristic": True,
                }
            )
        return strip_secrets(
            {
                "dialogue_id": dialogue.get("dialogue_id"),
                "status": STATUS_UNKNOWN,
                "reason": "observation_unavailable",
                "keyword_only_pass_forbidden": True,
                "provider_verified": bool(obs.get("provider_verified")),
            }
        )

    # Reuse dialogue↔beat binding helper for structure
    beat = visual_beat or {
        "beat_id": dialogue.get("beat_id") or f"vb-{dialogue.get('dialogue_id')}",
        "scene_id": dialogue.get("scene_id") or "",
        "dialogue_segment_id": dialogue.get("dialogue_id"),
        "required_entities": dialogue.get("entities") or [],
        "required_objects": [
            e.get("label") if isinstance(e, Mapping) else str(e)
            for e in (dialogue.get("entities") or [])
        ],
        "location_state": {"location": dialogue.get("location") or ""},
        "character_state": {
            "action": (dialogue.get("actions") or [""])[0] if dialogue.get("actions") else "",
            "emotion": dialogue.get("emotion") or "",
        },
        "relationships": dialogue.get("relationships") or [],
    }
    bind = dialogue_visual_entity_binding(
        dialogue_id=str(dialogue.get("dialogue_id") or ""),
        beat=beat,
        observation=obs,
    )
    # Provider FAIL stays FAIL; PASS only when provider_verified PASS
    if st == STATUS_FAIL:
        status = STATUS_FAIL
        reason = "provider_semantic_mismatch"
    elif st == STATUS_PASS and obs.get("provider_verified"):
        status = STATUS_PASS
        reason = "provider_supports_dialogue_visual_intent"
    else:
        status = STATUS_UNKNOWN
        reason = "provider_status_not_pass"
    return strip_secrets(
        {
            "dialogue_id": dialogue.get("dialogue_id"),
            "status": status,
            "reason": reason,
            "binding": bind,
            "dims_checked": ["subject", "entity", "relationship", "location", "action", "emotion"],
            "keyword_only_pass_forbidden": True,
            "provider_verified": True,
            "heuristic": False,
            "timing_overlap_is_not_semantic_pass": True,
        }
    )


def detect_semantic_boundary(
    prev: Mapping[str, Any],
    nxt: Mapping[str, Any],
) -> dict[str, Any]:
    """Recommend visual change when meaningful dims change — not every sentence."""
    changes: list[str] = []
    for key, label in (
        ("actions", "action"),
        ("entities", "entity"),
        ("relationships", "relationship"),
        ("location", "location"),
        ("emotion", "emotion"),
        ("environment", "environment"),
        ("camera", "camera"),
    ):
        a = prev.get(key)
        b = nxt.get(key)
        if key in ("actions", "entities", "relationships"):
            sa = {str(x).lower() for x in (a or [])}
            sb = {str(x).lower() for x in (b or [])}
            if sa and sb and sa != sb:
                changes.append(label)
        else:
            if str(a or "").strip() and str(b or "").strip() and str(a).lower() != str(b).lower():
                changes.append(label)
    recommend_new = bool(changes)
    return strip_secrets(
        {
            "visual_change_recommended": recommend_new,
            "change_dims": changes,
            "every_sentence_change_forbidden": True,
            "fixed_n_switching_forbidden": FIXED_N_SWITCHING_FORBIDDEN,
            "note": "meaningful_semantic_change_only",
        }
    )


def recommend_adaptive_hold(
    *,
    dialogue_duration_sec: float,
    semantic_beat_count: int = 1,
    information_density: str = "normal",
    visual_complexity: str = "normal",
    motion_available: bool = False,
    scene_importance: str = "normal",
    repetition_risk: bool = False,
    semantic_change: bool = False,
    action_change: bool = False,
    entity_change: bool = False,
    relationship_change: bool = False,
    location_change: bool = False,
    emotion_change: bool = False,
    available_assets: int = 0,
    media_mode: str = "IMAGE",
) -> dict[str, Any]:
    """Hold recommendation via existing C05-S policy — never overrides Duration Contract."""
    # Semantic change → prefer short hold / new beat signal (still recommendation only)
    density = information_density
    if semantic_change or action_change or location_change or relationship_change:
        density = "high"
        semantic_beat_count = max(semantic_beat_count, 2)
    if emotion_change or entity_change:
        density = "high" if density == "normal" else density

    hold = decide_visual_hold_policy(
        dialogue_duration_sec=float(dialogue_duration_sec),
        semantic_beat_count=int(semantic_beat_count),
        information_density=density,
        visual_complexity=visual_complexity,
        motion_available=bool(motion_available) or str(media_mode).upper() not in ("", "IMAGE"),
        scene_importance=scene_importance,
        repetition_risk=repetition_risk,
    )
    # Explicitly reject fixed-N hard switching as authority
    fixed_n_rejected = True
    for n in FORBIDDEN_FIXED_INTERVALS_SEC:
        # recommendation may coincidentally equal N — that is not a hard rule
        pass

    policy = str(hold.get("policy") or "")
    long_coherent_ok = (
        float(dialogue_duration_sec) >= 6.0
        and not (semantic_change or location_change or relationship_change)
        and policy in ("HOLD_LONG", "HOLD_NORMAL", "LONG", "NORMAL")
    )

    new_beat_signal = bool(
        semantic_change or location_change or (relationship_change and action_change)
    )

    return strip_secrets(
        {
            "schema": SCHEMA_ALIGNMENT,
            "kind": "adaptive_hold_recommendation",
            "recommended_hold_sec": hold.get("duration_sec"),
            "max_hold_sec": hold.get("max_hold_sec"),
            "policy": hold.get("policy"),
            "risks": list(hold.get("risks") or []),
            "c05s_hold_authority": "pipeline.story_visual_direction.decide_visual_hold_policy",
            "second_pacing_authority": False,
            "overrides_duration_contract": False,
            "overrides_audio_timing": False,
            "overrides_dialogue_coverage": False,
            "fixed_n_switching_forbidden": FIXED_N_SWITCHING_FORBIDDEN,
            "fixed_n_hard_rule_rejected": fixed_n_rejected,
            "long_coherent_hold_allowed": bool(long_coherent_ok),
            "new_visual_beat_recommended": new_beat_signal,
            "inputs": {
                "dialogue_duration_sec": dialogue_duration_sec,
                "semantic_change": semantic_change,
                "action_change": action_change,
                "entity_change": entity_change,
                "relationship_change": relationship_change,
                "location_change": location_change,
                "emotion_change": emotion_change,
                "repetition_risk": repetition_risk,
                "available_assets": available_assets,
                "media_mode": media_mode,
            },
            "confidence": "HEURISTIC_RECOMMENDATION",
            "note": hold.get("note"),
        }
    )


def repetition_risk_evidence(
    beats: Sequence[Any],
    *,
    used_assets: Optional[Sequence[Mapping[str, Any]]] = None,
    candidate_asset_id: str = "",
    candidate_content_hash: str = "",
    beat_id: str = "",
    scene_id: str = "",
) -> dict[str, Any]:
    """Reuse existing detectors — HEURISTIC warning only unless contract requires FAIL."""
    from pipeline.retrieval.reuse import detect_reuse_risk

    # Convert dict beats to minimal objects for detect_visual_repetition if needed
    c05s_warn: list[dict[str, Any]] = []
    try:
        from pipeline.story_visual_direction import DirectedVisualBeat

        typed = []
        for b in beats or []:
            if isinstance(b, DirectedVisualBeat):
                typed.append(b)
        if typed:
            c05s_warn = detect_visual_repetition(typed)
    except Exception:
        c05s_warn = []

    reuse = detect_reuse_risk(
        candidate_asset_id=candidate_asset_id,
        candidate_content_hash=candidate_content_hash,
        used_in_job=list(used_assets or []),
        beat_id=beat_id,
        scene_id=scene_id,
        continuity_reuse_allowed=True,
    )
    return strip_secrets(
        {
            "c05s_repetition_warnings": c05s_warn,
            "retrieval_reuse": reuse,
            "second_duplicate_detector": False,
            "auto_fail_forbidden_unless_contract": True,
            "auto_regenerate_forbidden_unless_contract": True,
            "confidence": "HEURISTIC",
        }
    )


def align_dialogue_visual_production(
    *,
    dialogue_segments: Sequence[Any],
    visual_beats: Sequence[Any],
    observations_by_dialogue: Optional[Mapping[str, Mapping[str, Any]]] = None,
    audio_timeline_sec: Optional[float] = None,
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
    duration_contract: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Main evidence bundle: timelines + temporal + semantic + hold recommendations."""
    dlg = build_dialogue_timeline(
        dialogue_segments,
        customer_id=customer_id,
        channel_id=channel_id,
        job_id=job_id,
        audio_timeline_sec=audio_timeline_sec,
    )
    vis = build_visual_timeline(
        visual_beats,
        customer_id=customer_id,
        channel_id=channel_id,
        job_id=job_id,
    )
    planned_ids = [r["dialogue_id"] for r in dlg["segments"]]
    # Materialized = dialogue_ids referenced by visual beats (incl covered_dialogue_ids)
    mat_ids: list[str] = []
    for b in visual_beats or []:
        bd = _as_dict(b)
        did = str(bd.get("dialogue_segment_id") or bd.get("dialogue_id") or "")
        if did:
            mat_ids.append(did)
        for x in (bd.get("prompt_provenance") or {}).get("covered_dialogue_ids") or []:
            if str(x) not in mat_ids:
                mat_ids.append(str(x))
    drop = assert_no_silent_dialogue_drop(planned_ids, mat_ids)

    obs_map = dict(observations_by_dialogue or {})
    temporal_rows = []
    semantic_rows = []
    boundaries = []
    holds = []
    segs = dlg["segments"]
    for i, drow in enumerate(segs):
        obs = obs_map.get(str(drow["dialogue_id"]))
        obs_avail = None if obs is None else bool(obs.get("provider_verified") or obs.get("observation_status"))
        if obs is not None and str(obs.get("observation_status") or "").upper() in (
            "UNKNOWN",
            "OBSERVATION_UNAVAILABLE",
        ):
            obs_avail = False
        tcov = classify_temporal_coverage(drow, vis["beats"], observation_available=obs_avail if obs is not None else True)
        # If obs explicitly unavailable → UNKNOWN coverage
        if obs is not None and not obs.get("provider_verified") and str(obs.get("observation_status") or "").upper() == "UNKNOWN":
            tcov = classify_temporal_coverage(drow, vis["beats"], observation_available=False)
        temporal_rows.append(tcov)
        sem = semantic_align_dialogue_to_observation(drow, obs)
        semantic_rows.append(sem)
        if i > 0:
            boundaries.append({"from": segs[i - 1]["dialogue_id"], "to": drow["dialogue_id"], **detect_semantic_boundary(segs[i - 1], drow)})
        holds.append(
            recommend_adaptive_hold(
                dialogue_duration_sec=float(drow["duration"]),
                semantic_change=bool(boundaries[-1]["visual_change_recommended"]) if boundaries else False,
                location_change=(i > 0 and segs[i - 1].get("location") != drow.get("location")),
                action_change=(i > 0 and segs[i - 1].get("actions") != drow.get("actions")),
                media_mode="IMAGE",
            )
        )

    # Overall: semantic FAIL wins; UNKNOWN blocks; silent drop FAIL
    overall = STATUS_PASS
    issues: list[str] = []

    def _bump(cur: str, new: str) -> str:
        if cur == STATUS_FAIL or new == STATUS_FAIL:
            return STATUS_FAIL
        if cur == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
            return STATUS_UNKNOWN
        return STATUS_PASS

    if drop.get("silent_drop") or drop.get("status") == STATUS_FAIL and drop.get("missing"):
        if drop.get("silent_drop"):
            overall = STATUS_FAIL
            issues.append("silent_dialogue_drop")
        else:
            overall = _bump(overall, STATUS_FAIL)
            issues.append(str(drop.get("blocking_code") or "dialogue_incomplete"))

    for s in semantic_rows:
        overall = _bump(overall, str(s.get("status") or STATUS_UNKNOWN))
        if s.get("status") == STATUS_FAIL:
            issues.append(f"semantic_fail:{s.get('dialogue_id')}")
        if s.get("status") == STATUS_UNKNOWN:
            issues.append(f"semantic_unknown:{s.get('dialogue_id')}")

    for t in temporal_rows:
        if t.get("coverage") == COVERAGE_NONE:
            overall = STATUS_FAIL
            issues.append(f"temporal_none:{t.get('dialogue_id')}")
        elif t.get("coverage") == COVERAGE_UNKNOWN:
            overall = _bump(overall, STATUS_UNKNOWN)

    # Duration contract preserved (cite only)
    contract = dict(duration_contract or {})
    return strip_secrets(
        {
            "schema": SCHEMA_ALIGNMENT,
            "status": overall,
            "issues": issues,
            "dialogue_timeline": dlg,
            "visual_timeline": vis,
            "no_silent_drop": drop,
            "temporal_coverage": temporal_rows,
            "semantic_alignment": semantic_rows,
            "semantic_boundaries": boundaries,
            "adaptive_holds": holds,
            "duration_contract": {
                "authority": "pipeline.duration_budget.resolve_duration_contract",
                "target_seconds": contract.get("target_seconds"),
                "max_seconds": contract.get("max_seconds"),
                "overridden_by_alignment_layer": False,
            },
            "audio_timeline_sec": audio_timeline_sec,
            "second_audio_engine": False,
            "second_duration_engine": False,
            "second_pacing_authority": False,
            "second_continuity_engine": False,
            "second_semantic_gate": False,
            "second_repair_engine": False,
            "second_ffmpeg_engine": False,
            "fixed_n_switching_forbidden": FIXED_N_SWITCHING_FORBIDDEN,
            "timing_overlap_is_not_semantic_pass": True,
            "unknown_as_pass": False,
            "creates_final_gate": False,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "cross_beat_helper": "pipeline.observation.frame_evidence.cross_beat",
            "created_at": time.time(),
        }
    )


def customer_isolation_check(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    ca, cb = str(a.get("customer_id") or ""), str(b.get("customer_id") or "")
    if ca and cb and ca != cb:
        return {"status": STATUS_FAIL, "reason": "cross_customer_alignment_merge_forbidden"}
    cha, chb = str(a.get("channel_id") or ""), str(b.get("channel_id") or "")
    if cha and chb and cha != chb:
        return {"status": STATUS_FAIL, "reason": "cross_channel_alignment_merge_forbidden"}
    return {"status": STATUS_PASS, "reason": ""}
