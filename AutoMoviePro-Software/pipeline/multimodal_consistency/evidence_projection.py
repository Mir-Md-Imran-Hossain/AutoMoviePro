"""Beat-level multimodal evidence projection — NOT a second semantic/publishability gate.

Joins Phase 6C–6I observation envelopes by reference for certification consumers.
Final authorities remain: semantic_coverage, ContinuityTracker, publishability, BUILD-04F.
"""
from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN
from pipeline.retrieval.common import strip_secrets

SCHEMA_EVIDENCE_PROJECTION = "amp_multimodal_evidence_projection_v1"

# Coverage vocabulary (C05-S) — strings only; do not import story_visual_direction (circular).
COVERAGE_FULL = "FULL"
COVERAGE_NONE = "NONE"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_UNKNOWN = "UNKNOWN"

CONF_DETERMINISTIC = "DETERMINISTIC"
CONF_HEURISTIC = "HEURISTIC"
CONF_PROVIDER_VERIFIED = "PROVIDER_VERIFIED"


def _d(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    return dict(obj or {})


def _st(v: Any, default: str = STATUS_UNKNOWN) -> str:
    s = str(v or default).upper()
    if s in ("OBSERVATION_UNAVAILABLE", "ABSENT"):
        return STATUS_UNKNOWN if s != "ABSENT" else "ABSENT"
    if s in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, "ABSENT", "PARTIAL", "NONE", "FULL"):
        return s
    return default


def _conf_from_obs(obs: Mapping[str, Any]) -> str:
    if obs.get("provider_verified") and not obs.get("heuristic"):
        return CONF_PROVIDER_VERIFIED
    if obs.get("heuristic"):
        return CONF_HEURISTIC
    if obs.get("evidence_source") in ("TECHNICAL_PROBE", "TECHNICAL_AND_ASR", "DETERMINISTIC"):
        return CONF_DETERMINISTIC
    if obs.get("provider_verified"):
        return CONF_PROVIDER_VERIFIED
    return CONF_HEURISTIC if obs else CONF_HEURISTIC


def project_beat_evidence(
    *,
    beat_id: str,
    scene_id: str = "",
    dialogue_id: str = "",
    visual_asset_id: str = "",
    audio_asset_id: str = "",
    intent: Optional[Mapping[str, Any]] = None,
    visual_observation: Optional[Mapping[str, Any]] = None,
    audio_observation: Optional[Mapping[str, Any]] = None,
    acoustic_observation: Optional[Mapping[str, Any]] = None,
    alignment: Optional[Mapping[str, Any]] = None,
    continuity: Optional[Mapping[str, Any]] = None,
    timing: Optional[Mapping[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Project one beat's multimodal evidence. Does not certify publishability."""
    intent_d = _d(intent)
    vis = _d(visual_observation)
    aud = _d(audio_observation)
    aco = _d(acoustic_observation)
    aln = _d(alignment)
    cont = _d(continuity)
    tim = _d(timing)

    voice_status = str(
        aco.get("VOICE_IDENTITY_OBSERVATION")
        or (aco.get("acoustic_compare") or {}).get("VOICE_IDENTITY_OBSERVATION")
        or STATUS_UNKNOWN
    ).upper()

    matrix = {
        "TECHNICAL": {
            "status": _st(aud.get("observation_status") or vis.get("observation_status")),
            "confidence": CONF_DETERMINISTIC,
        },
        "AUDIO": {
            "status": _st(
                (aud.get("speech") or aud).get("observation_status")
                or aud.get("status")
                or (aud.get("speech") or {}).get("status")
            ),
            "confidence": _conf_from_obs(aud.get("speech") or aud),
            "dialogue_coverage": (aud.get("coverages") or [None])[0] if aud.get("coverages") else aud.get("coverage"),
            "transcript": (aud.get("transcript_alignments") or [None])[0] if aud.get("transcript_alignments") else None,
            "delivery": (aco.get("delivery") or aud.get("delivery") or {}).get("class")
            or (aco.get("delivery") or {}).get("status"),
            "voice_identity_observation": voice_status,
        },
        "VISUAL": {
            "status": _st(vis.get("observation_status") or vis.get("status")),
            "confidence": _conf_from_obs(vis),
            "observed_entities": list(vis.get("observed_entities") or []),
            "observed_location": vis.get("observed_location"),
            "observed_actions": list(vis.get("observed_actions") or []),
            "observed_relationships": list(vis.get("observed_relationships") or []),
            "temporal_status": (vis.get("temporal") or {}).get("status") or vis.get("temporal_status"),
        },
        "DIALOGUE": {
            "status": _st((aln.get("semantic_alignment") or aln).get("status") if isinstance(aln.get("semantic_alignment"), list) else aln.get("status")),
            "dialogue_id": dialogue_id,
            "text": intent_d.get("dialogue") or intent_d.get("text"),
        },
        "TIMING": {
            "status": STATUS_PASS if tim else STATUS_UNKNOWN,
            "planned_start": tim.get("planned_start") or tim.get("start"),
            "planned_end": tim.get("planned_end") or tim.get("end"),
            "actual_audio_start": tim.get("actual_audio_start"),
            "actual_audio_end": tim.get("actual_audio_end"),
            "visual_coverage": tim.get("visual_coverage"),
            "dialogue_coverage": tim.get("dialogue_coverage"),
            "fixed_n_switching_forbidden": True,
        },
        "CONTINUITY": {
            "status": _st(cont.get("status")),
            "location": cont.get("location") or cont.get("location_class"),
            "character": cont.get("character"),
            "object": cont.get("object"),
            "authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
            "second_continuity_engine": False,
        },
        "CROSS_MODAL": {
            "status": STATUS_UNKNOWN,
            "confidence": CONF_HEURISTIC,
        },
        "SEMANTIC": {
            "status": STATUS_UNKNOWN,
            "confidence": CONF_HEURISTIC,
            "authority": "pipeline.semantic_coverage",
            "second_semantic_gate": False,
        },
    }

    # Cross-modal join from available observations (evidence only)
    cross = _evaluate_cross_modal(
        intent=intent_d,
        visual=vis,
        audio=aud,
        alignment=aln,
    )
    matrix["CROSS_MODAL"] = cross
    # Semantic projection is NOT a gate decision — mirror cross-modal for consumers
    matrix["SEMANTIC"] = {
        "status": cross.get("status"),
        "confidence": cross.get("confidence"),
        "authority": "pipeline.semantic_coverage",
        "note": "projection_only_not_publishability",
        "second_semantic_gate": False,
        "creates_final_gate": False,
    }

    return strip_secrets(
        {
            "schema": SCHEMA_EVIDENCE_PROJECTION,
            "beat_id": beat_id,
            "scene_id": scene_id,
            "dialogue_id": dialogue_id,
            "visual_asset_id": visual_asset_id,
            "audio_asset_id": audio_asset_id,
            "intent": {
                "subject": intent_d.get("subject"),
                "entities": intent_d.get("entities") or intent_d.get("required_entities"),
                "relationships": intent_d.get("relationships"),
                "actions": intent_d.get("actions"),
                "location": intent_d.get("location"),
                "camera": intent_d.get("camera"),
                "lighting": intent_d.get("lighting"),
                "emotion": intent_d.get("emotion") or intent_d.get("emotional_intent"),
                "dialogue": intent_d.get("dialogue") or intent_d.get("text"),
            },
            "observed_visual": {
                "status": matrix["VISUAL"]["status"],
                "confidence": matrix["VISUAL"]["confidence"],
                "entities": matrix["VISUAL"]["observed_entities"],
                "location": matrix["VISUAL"]["observed_location"],
                "actions": matrix["VISUAL"]["observed_actions"],
                "relationships": matrix["VISUAL"]["observed_relationships"],
                "temporal_status": matrix["VISUAL"]["temporal_status"],
            },
            "observed_audio": {
                "status": matrix["AUDIO"]["status"],
                "confidence": matrix["AUDIO"]["confidence"],
                "dialogue_coverage": matrix["AUDIO"]["dialogue_coverage"],
                "transcript": matrix["AUDIO"]["transcript"],
                "delivery": matrix["AUDIO"]["delivery"],
                "voice_identity_observation": voice_status,
            },
            "timing": matrix["TIMING"],
            "continuity": matrix["CONTINUITY"],
            "certification_matrix": matrix,
            "provenance": {
                "visual_provider": vis.get("provider"),
                "visual_evidence_source": vis.get("evidence_source"),
                "audio_provider": (aud.get("speech") or aud).get("provider"),
                "audio_evidence_source": (aud.get("speech") or aud).get("evidence_source") or aud.get("evidence_source"),
                "visual_hash": vis.get("content_hash") or vis.get("asset_hash"),
                "audio_hash": aud.get("content_hash") or (aud.get("artifact") or {}).get("content_hash"),
                "observation_timestamp": time.time(),
                "HEURISTIC_is_not_PROVIDER_VERIFIED": True,
                "generation_success_is_not_semantic_pass": True,
                "prompt_compliance_is_not_observed_pass": True,
            },
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "creates_final_gate": False,
            "creates_publishability_gate": False,
            "second_multimodal_engine": False,
            "second_semantic_gate": False,
            "second_quality_score": False,
            "second_repair_engine": False,
            "second_pacing_engine": False,
            "unknown_as_pass": False,
            "unknown_as_fail": False,
            "voice_acoustic_remains_unknown_per_phase6i": True,
            "adaptive_pacing_reuses_phase6g": True,
            "fixed_n_switching_forbidden": True,
            "authority_chain": [
                "observation→semantic_coverage→quality_gates→publishability",
            ],
            "never_directly_publishable": True,
        }
    )


def _evaluate_cross_modal(
    *,
    intent: Mapping[str, Any],
    visual: Mapping[str, Any],
    audio: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """Evidence-only cross-modal coherence. Not publishability."""
    issues: list[str] = []
    vis_st = _st(visual.get("observation_status") or visual.get("status"))
    aud_speech = audio.get("speech") or audio
    aud_st = _st(aud_speech.get("observation_status") or aud_speech.get("status") or audio.get("status"))

    # UNKNOWN propagation when mandatory observations missing
    if not visual and not audio:
        return {
            "status": STATUS_UNKNOWN,
            "confidence": CONF_HEURISTIC,
            "issues": ["no_modal_observations"],
            "timing_overlap_is_not_semantic_pass": True,
        }
    if visual and vis_st in (STATUS_UNKNOWN, "ABSENT") and intent.get("location"):
        # visual mandatory for location-intent coherence when visual expected
        issues.append("visual_observation_unknown")
    if audio and aud_st in (STATUS_UNKNOWN, "ABSENT") and (intent.get("dialogue") or intent.get("text")):
        issues.append("audio_observation_unknown")

    conf = CONF_HEURISTIC
    if visual.get("provider_verified") or aud_speech.get("provider_verified"):
        conf = CONF_PROVIDER_VERIFIED

    # Explicit location contradiction (hospital vs spacecraft etc.)
    req_loc = str(intent.get("location") or "").lower()
    obs_loc = str(visual.get("observed_location") or "").lower()
    if req_loc and obs_loc and visual.get("provider_verified"):
        contradict_pairs = (
            ("hospital", "spacecraft"),
            ("hospital", "space"),
            ("hospital", "orbit"),
            ("hospital", "desert"),
            ("police", "desert"),
            ("hospital", "futuristic"),
        )
        for a, b in contradict_pairs:
            if a in req_loc and b in obs_loc:
                issues.append(f"location_contradiction:{req_loc}->{obs_loc}")
                return {
                    "status": STATUS_FAIL,
                    "confidence": conf,
                    "issues": issues,
                    "timing_overlap_is_not_semantic_pass": True,
                    "relationship_collapsed_to_located_at": False,
                }
            if b in req_loc and a in obs_loc:
                issues.append(f"location_contradiction:{req_loc}->{obs_loc}")
                return {
                    "status": STATUS_FAIL,
                    "confidence": conf,
                    "issues": issues,
                    "timing_overlap_is_not_semantic_pass": True,
                    "relationship_collapsed_to_located_at": False,
                }

    # Relationship contradiction if provider FAIL visual vs required relations
    if vis_st == STATUS_FAIL and visual.get("provider_verified"):
        issues.append("visual_provider_fail")
        return {
            "status": STATUS_FAIL,
            "confidence": conf,
            "issues": issues,
            "timing_overlap_is_not_semantic_pass": True,
            "relationship_collapsed_to_located_at": False,
        }

    # Transcript MISMATCH from audio bundle
    for ta in audio.get("transcript_alignments") or []:
        if str(ta.get("class") or "").upper() == "MISMATCH":
            issues.append("transcript_mismatch")
            return {
                "status": STATUS_FAIL,
                "confidence": _conf_from_obs(aud_speech),
                "issues": issues,
                "timing_overlap_is_not_semantic_pass": True,
            }

    # Alignment FAIL
    if _st(alignment.get("status")) == STATUS_FAIL:
        issues.append("alignment_fail")
        return {
            "status": STATUS_FAIL,
            "confidence": conf,
            "issues": issues,
            "timing_overlap_is_not_semantic_pass": True,
        }

    # If any mandatory UNKNOWN remains
    if "visual_observation_unknown" in issues or "audio_observation_unknown" in issues:
        return {
            "status": STATUS_UNKNOWN,
            "confidence": CONF_HEURISTIC,
            "issues": issues,
            "timing_overlap_is_not_semantic_pass": True,
            "unknown_as_pass": False,
        }
    if vis_st == STATUS_UNKNOWN or aud_st == STATUS_UNKNOWN:
        return {
            "status": STATUS_UNKNOWN,
            "confidence": CONF_HEURISTIC,
            "issues": issues or ["modal_unknown"],
            "timing_overlap_is_not_semantic_pass": True,
            "unknown_as_pass": False,
        }

    # Coherent when provider-verified visual PASS and no contradictions
    if vis_st == STATUS_PASS and visual.get("provider_verified"):
        return {
            "status": STATUS_PASS,
            "confidence": CONF_PROVIDER_VERIFIED,
            "issues": issues,
            "timing_overlap_is_not_semantic_pass": True,
            "relationship_collapsed_to_located_at": False,
            "note": "evidence_coherence_not_publishability",
        }

    return {
        "status": STATUS_UNKNOWN,
        "confidence": conf,
        "issues": issues or ["insufficient_provider_verified_evidence"],
        "timing_overlap_is_not_semantic_pass": True,
        "unknown_as_pass": False,
    }


def fuse_production_evidence(
    *,
    beats: Sequence[Mapping[str, Any]],
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Fuse multiple beat projections. Never directly publishable."""
    rows: list[dict[str, Any]] = []
    for b in beats or []:
        bd = dict(b or {})
        if bd.get("certification_matrix"):
            rows.append(bd)
            continue
        rows.append(
            project_beat_evidence(
                beat_id=str(bd.get("beat_id") or ""),
                scene_id=str(bd.get("scene_id") or ""),
                dialogue_id=str(bd.get("dialogue_id") or ""),
                visual_asset_id=str(bd.get("visual_asset_id") or ""),
                audio_asset_id=str(bd.get("audio_asset_id") or ""),
                intent=bd.get("intent"),
                visual_observation=bd.get("visual_observation"),
                audio_observation=bd.get("audio_observation"),
                acoustic_observation=bd.get("acoustic_observation"),
                alignment=bd.get("alignment"),
                continuity=bd.get("continuity"),
                timing=bd.get("timing"),
                customer_id=str(bd.get("customer_id") or customer_id or ""),
                channel_id=str(bd.get("channel_id") or channel_id or ""),
                job_id=str(bd.get("job_id") or job_id or ""),
            )
        )

    for r in rows:
        ca = str(r.get("customer_id") or "")
        if customer_id and ca and ca != str(customer_id):
            return strip_secrets(
                {
                    "schema": SCHEMA_EVIDENCE_PROJECTION,
                    "status": STATUS_FAIL,
                    "reason": "cross_customer_evidence_fusion_forbidden",
                    "creates_final_gate": False,
                    "never_directly_publishable": True,
                }
            )

    statuses = [
        str((r.get("certification_matrix") or {}).get("CROSS_MODAL", {}).get("status") or STATUS_UNKNOWN)
        for r in rows
    ]
    overall = STATUS_PASS
    for s in statuses:
        if s == STATUS_FAIL:
            overall = STATUS_FAIL
            break
        if s in (STATUS_UNKNOWN, "ABSENT"):
            overall = STATUS_UNKNOWN

    return strip_secrets(
        {
            "schema": SCHEMA_EVIDENCE_PROJECTION,
            "kind": "production_evidence_fusion",
            "status": overall,
            "beats": rows,
            "beat_count": len(rows),
            "creates_final_gate": False,
            "creates_publishability_gate": False,
            "never_directly_publishable": True,
            "authority_chain": ["evidence_projection→semantic_coverage→publishability"],
            "second_multimodal_engine": False,
            "second_semantic_gate": False,
            "second_publishability_engine": False,
            "unknown_as_pass": False,
            "HEURISTIC_is_not_PROVIDER_VERIFIED": True,
            "voice_acoustic_remains_unknown_per_phase6i": True,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "created_at": time.time(),
        }
    )


def attach_evidence_projection_to_semantic_report(
    semantic_report: Mapping[str, Any],
    evidence_fusion: Mapping[str, Any],
    *,
    mandatory: bool = True,
) -> dict[str, Any]:
    """Attach projection to semantic report — does not replace semantic_coverage authority."""
    from pipeline.semantic_coverage import attach_frame_evidence_to_semantic_report

    out = dict(semantic_report or {})
    fusion = dict(evidence_fusion or {})
    out["multimodal_evidence_projection"] = {
        "schema": fusion.get("schema"),
        "status": fusion.get("status"),
        "beat_count": fusion.get("beat_count"),
        "never_directly_publishable": True,
        "creates_final_gate": False,
    }
    # Reuse existing attach path for UNKNOWN blocking when mandatory
    bridge = {
        "observations": [],
        "temporal": {"status": fusion.get("status")},
        "multimodal_evidence_projection": fusion,
    }
    # If fusion UNKNOWN/FAIL, synthesize observation markers for attach rules
    st = str(fusion.get("status") or STATUS_UNKNOWN).upper()
    if st == STATUS_UNKNOWN:
        bridge["observations"] = [{"observation_status": STATUS_UNKNOWN, "mandatory_evidence": "ABSENT" if mandatory else ""}]
    elif st == STATUS_FAIL:
        bridge["observations"] = [{"observation_status": STATUS_FAIL}]
        bridge["temporal"] = {"status": STATUS_FAIL}
    out = attach_frame_evidence_to_semantic_report(out, bridge)
    out["evidence_projection_authority"] = "pipeline.multimodal_consistency.evidence_projection"
    out["second_semantic_gate"] = False
    out["never_directly_publishable_from_projection"] = True
    return strip_secrets(out)


def repair_handoff_from_evidence_projection(
    *,
    beat_id: str,
    scene_id: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """FAIL → existing BUILD-04F visual/audio handoff; UNKNOWN → no repair."""
    st = str(
        (evidence.get("certification_matrix") or {}).get("CROSS_MODAL", {}).get("status")
        or evidence.get("status")
        or STATUS_UNKNOWN
    ).upper()
    if st in (STATUS_UNKNOWN, "ABSENT"):
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": "unknown_does_not_trigger_repair",
                "status": st,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
            }
        )
    if st != STATUS_FAIL:
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": f"status_{st}_no_repair",
                "whole_video_regeneration": False,
            }
        )
    # Prefer visual handoff path (existing frame evidence repair hook)
    from pipeline.observation.frame_evidence.repair_hook import repair_handoff_from_frame_evidence

    return repair_handoff_from_frame_evidence(
        beat_id=beat_id,
        scene_id=scene_id,
        frame_bridge_or_temporal={
            "temporal": {"status": STATUS_FAIL, "issues": list(((evidence.get("certification_matrix") or {}).get("CROSS_MODAL") or {}).get("issues") or ["cross_modal_fail"])},
            "observations": [{"observation_status": STATUS_FAIL}],
            "multimodal_evidence_projection": evidence,
        },
    )
