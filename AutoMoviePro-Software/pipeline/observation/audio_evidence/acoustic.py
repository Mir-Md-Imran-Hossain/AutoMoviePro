"""Phase 6I — acoustic feature / delivery / voice-evidence observation.

No speaker-embedding engine. Acoustic identity remains UNKNOWN unless a future
approved provider is wired. Generation voice hints are HEURISTIC only.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.audio_evidence.observe import (
    bind_voice_identity_contract,
    evaluate_voice_continuity_evidence,
    observe_audio_artifact,
    observe_speech_segments,
    repair_handoff_from_audio_evidence,
)
from pipeline.observation.common import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN, STATUS_UNAVAILABLE
from pipeline.retrieval.common import strip_secrets

SCHEMA_ACOUSTIC = "amp_observation_acoustic_voice_v1"

MATCH = "MATCH"
MISMATCH = "MISMATCH"
CONSISTENT = "CONSISTENT"
INCONSISTENT = "INCONSISTENT"
NORMAL = "NORMAL"
ANOMALOUS = "ANOMALOUS"
UNKNOWN = "UNKNOWN"

NATURALNESS_OBSERVATION_UNKNOWN = "UNKNOWN"
VOICE_IDENTITY_OBSERVATION_UNKNOWN = "UNKNOWN"


def _customer_ok(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[bool, str]:
    ca, cb = str(a.get("customer_id") or ""), str(b.get("customer_id") or "")
    if ca and cb and ca != cb:
        return False, "cross_customer_acoustic_compare_forbidden"
    cha, chb = str(a.get("channel_id") or ""), str(b.get("channel_id") or "")
    if cha and chb and cha != chb:
        return False, "cross_channel_acoustic_compare_forbidden"
    return True, ""


def observe_acoustic_features(
    audio_path: Path | str,
    *,
    audio_asset_id: str = "",
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
    speech_observation: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Feature observation from existing ffprobe/loudness/ASR — not VoiceIdentity PASS."""
    artifact = observe_audio_artifact(
        audio_path,
        audio_asset_id=audio_asset_id,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        customer_id=customer_id,
        channel_id=channel_id,
    )
    speech = dict(speech_observation or {})
    if not speech:
        speech = observe_speech_segments(
            audio_path,
            dialogue_ids=[dialogue_id] if dialogue_id else None,
            job_id=job_id,
            scene_id=scene_id,
            customer_id=customer_id,
            channel_id=channel_id,
        )

    duration = float(artifact.get("duration") or 0.0)
    segments = list(speech.get("segments") or [])
    speech_dur = sum(float(s.get("duration") or max(0.0, float(s.get("end") or 0) - float(s.get("start") or 0))) for s in segments)
    speech_ratio = (speech_dur / duration) if duration > 1e-6 else None

    # Silence intervals from ASR gaps
    gaps: list[dict[str, Any]] = []
    ordered = sorted(segments, key=lambda s: float(s.get("start") or 0))
    prev_end = 0.0
    for s in ordered:
        start = float(s.get("start") or 0.0)
        end = float(s.get("end") or start)
        if start - prev_end > 0.35:
            gaps.append({"start": round(prev_end, 3), "end": round(start, 3), "duration": round(start - prev_end, 3)})
        prev_end = max(prev_end, end)
    if duration > prev_end + 0.35:
        gaps.append({"start": round(prev_end, 3), "end": round(duration, 3), "duration": round(duration - prev_end, 3)})

    loud = dict(artifact.get("loudness") or {})
    asr_ok = bool(speech.get("provider_verified")) and str(speech.get("status") or "") == STATUS_PASS

    # Pitch/prosody / speaker embedding — not available without approved provider
    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "kind": "acoustic_features",
            "audio_asset_id": artifact.get("audio_asset_id") or audio_asset_id,
            "job_id": job_id,
            "scene_id": scene_id,
            "dialogue_id": dialogue_id,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "provider": "ffprobe+loudness+faster-whisper",
            "model": str(speech.get("provider") or "faster-whisper"),
            "observation_status": STATUS_PASS if artifact.get("observation_status") == STATUS_PASS else (
                STATUS_FAIL if artifact.get("observation_status") == STATUS_FAIL else STATUS_UNKNOWN
            ),
            "evidence_source": "TECHNICAL_AND_ASR",
            "timestamp": time.time(),
            "provenance": {
                "artifact_hash": artifact.get("content_hash"),
                "asr_authority": "pipeline.observation.speech_timing",
                "loudness_authority": "pipeline.audio_design.loudness",
                "ffmpeg_authority": "pipeline.compose.ffprobe",
            },
            "sample_rate": artifact.get("sample_rate"),
            "channels": artifact.get("channels"),
            "duration": artifact.get("duration"),
            "format": artifact.get("format"),
            "speech_ratio": None if speech_ratio is None else round(speech_ratio, 4),
            "silence_intervals": gaps,
            "pause_distribution": {
                "gap_count": len(gaps),
                "max_gap_sec": max((g["duration"] for g in gaps), default=0.0),
                "total_gap_sec": round(sum(g["duration"] for g in gaps), 3),
            },
            "rms_energy": loud.get("rms"),
            "peak": loud.get("peak"),
            "clipping": loud.get("clip_ratio") or loud.get("clipping"),
            "pitch_prosody": UNKNOWN,
            "speaker_embedding": UNKNOWN,
            "VOICE_IDENTITY_OBSERVATION": VOICE_IDENTITY_OBSERVATION_UNKNOWN,
            "NATURALNESS_OBSERVATION": NATURALNESS_OBSERVATION_UNKNOWN,
            "technical_is_not_voice_identity_pass": True,
            "tts_success_is_not_naturalness_pass": True,
            "asr_available": asr_ok,
            "second_asr_engine": False,
            "second_voice_identity_authority": False,
            "embedding_provider": None,
            "embedding_integrated": False,
            "unknown_as_pass": False,
            "authority": "observation_only",
        }
    )


def compare_acoustic_voice_identity(
    *,
    reference: Optional[Mapping[str, Any]] = None,
    candidate: Mapping[str, Any],
    voice_identity: Any = None,
    generation_voice_hint: str = "",
    reference_generation_voice_hint: str = "",
) -> dict[str, Any]:
    """Acoustic identity comparison.

    Without approved embedding provider → acoustic status UNKNOWN.
    Optional generation_voice_hint mismatch is HEURISTIC only (not PROVIDER_VERIFIED).
    """
    ok, reason = _customer_ok(reference or {}, candidate)
    if not ok:
        return strip_secrets(
            {
                "schema": SCHEMA_ACOUSTIC,
                "acoustic_status": STATUS_FAIL,
                "generation_hint_status": STATUS_FAIL,
                "status": STATUS_FAIL,
                "class": MISMATCH,
                "reason": reason,
                "provider_verified": False,
                "heuristic": False,
                "fail_closed_customer_isolation": True,
            }
        )

    # No embedding provider in repo
    acoustic = UNKNOWN
    acoustic_reason = "no_approved_speaker_embedding_provider"

    hint_status = UNKNOWN
    hint_class = UNKNOWN
    ref_hint = str(reference_generation_voice_hint or "").strip().lower()
    cand_hint = str(generation_voice_hint or "").strip().lower()
    if ref_hint and cand_hint:
        if ref_hint == cand_hint:
            hint_status = MATCH
            hint_class = MATCH
        else:
            hint_status = MISMATCH
            hint_class = MISMATCH

    bind = None
    if voice_identity is not None:
        bind = bind_voice_identity_contract(
            voice_identity=voice_identity,
            dialogue_id=str(candidate.get("dialogue_id") or ""),
            scene_id=str(candidate.get("scene_id") or ""),
            acoustic_verification_available=False,
        )

    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "kind": "voice_identity_acoustic_compare",
            "acoustic_status": acoustic,
            "acoustic_reason": acoustic_reason,
            "generation_hint_status": hint_status,
            "generation_hint_class": hint_class,
            "generation_hint_confidence": "HEURISTIC" if hint_status != UNKNOWN else UNKNOWN,
            "HEURISTIC_is_not_PROVIDER_VERIFIED": True,
            "tts_requested_voice_is_not_actual_acoustic_proof": True,
            "VOICE_IDENTITY_OBSERVATION": VOICE_IDENTITY_OBSERVATION_UNKNOWN,
            "voice_identity_binding": bind,
            "provider_verified": False,
            "heuristic": hint_status != UNKNOWN,
            "embedding_integrated": False,
            "status": acoustic,  # overall acoustic remains UNKNOWN
            "class": acoustic,
            "unknown_as_pass": False,
            "unknown_as_fail": False,
            "second_voice_identity_authority": False,
        }
    )


def evaluate_cross_scene_voice_consistency(
    scene_evidences: Sequence[Mapping[str, Any]],
    *,
    generation_voice_hints: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Cross-scene consistency: acoustic UNKNOWN; optional HEURISTIC hint consistency."""
    rows = list(scene_evidences or [])
    if len(rows) < 2:
        return strip_secrets(
            {
                "acoustic_consistency": UNKNOWN,
                "hint_consistency": UNKNOWN,
                "status": UNKNOWN,
                "reason": "insufficient_scenes",
                "emotion_change_is_not_identity_failure": True,
            }
        )
    # Customer isolation across rows
    for i in range(1, len(rows)):
        ok, reason = _customer_ok(rows[0], rows[i])
        if not ok:
            return strip_secrets(
                {
                    "acoustic_consistency": STATUS_FAIL,
                    "status": STATUS_FAIL,
                    "reason": reason,
                    "fail_closed_customer_isolation": True,
                }
            )

    hints = [str(x or "").strip().lower() for x in (generation_voice_hints or [])]
    hint_consistency = UNKNOWN
    if hints and all(hints) and len(hints) == len(rows):
        hint_consistency = CONSISTENT if len(set(hints)) == 1 else INCONSISTENT

    # Contract continuity via VoiceIdentity ids if present
    ids = [str(r.get("voice_identity_id") or (r.get("voice_identity_binding") or {}).get("voice_identity_id") or "") for r in rows]
    ids = [x for x in ids if x]
    contract = evaluate_voice_continuity_evidence(
        [
            {
                "voice_identity_id": (r.get("voice_identity_binding") or {}).get("voice_identity_id") or r.get("voice_identity_id"),
                "emotion": r.get("emotion") or (r.get("voice_identity_binding") or {}).get("emotion"),
            }
            for r in rows
        ]
    ) if any((r.get("voice_identity_binding") or r.get("voice_identity_id")) for r in rows) else {
        "contract_stable": True,
        "emotion_change_is_not_identity_failure": True,
        "VOICE_IDENTITY_OBSERVATION": UNKNOWN,
    }

    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "kind": "cross_scene_voice_consistency",
            "acoustic_consistency": UNKNOWN,  # no embedding provider
            "hint_consistency": hint_consistency,
            "contract_continuity": contract,
            "status": UNKNOWN if hint_consistency == UNKNOWN else (
                STATUS_FAIL if hint_consistency == INCONSISTENT else UNKNOWN
            ),
            # Hint INCONSISTENT surfaces as HEURISTIC mismatch evidence, not acoustic FAIL-as-PASS coercion
            "heuristic_mismatch_detected": hint_consistency == INCONSISTENT,
            "provider_verified_acoustic": False,
            "emotion_change_is_not_identity_failure": True,
            "VOICE_IDENTITY_OBSERVATION": UNKNOWN,
            "unknown_as_pass": False,
            "second_voice_identity_authority": False,
        }
    )


def observe_speech_delivery_integrity(
    *,
    planned_dialogues: Sequence[Mapping[str, Any]],
    speech_observation: Mapping[str, Any],
    acoustic_features: Optional[Mapping[str, Any]] = None,
    max_internal_gap_sec: float = 2.5,
    min_speech_ratio: float = 0.15,
) -> dict[str, Any]:
    """Evidence-supported delivery issues only — no subjective naturalness score."""
    speech = dict(speech_observation or {})
    feats = dict(acoustic_features or {})
    if str(speech.get("status") or "") in (STATUS_UNKNOWN, STATUS_UNAVAILABLE) or not speech.get("provider_verified"):
        return strip_secrets(
            {
                "schema": SCHEMA_ACOUSTIC,
                "kind": "speech_delivery_integrity",
                "status": UNKNOWN,
                "class": UNKNOWN,
                "reason": "asr_unavailable",
                "NATURALNESS_OBSERVATION": NATURALNESS_OBSERVATION_UNKNOWN,
                "unknown_as_pass": False,
            }
        )

    issues: list[str] = []
    segments = list(speech.get("segments") or [])
    transcript = str(speech.get("transcript") or "").strip()
    if not transcript and not segments:
        issues.append("missing_speech")

    # Truncation: planned text much longer than ASR token count
    planned_text = " ".join(str(d.get("text") or "") for d in planned_dialogues)
    if planned_text and transcript:
        pt = planned_text.lower().split()
        ot = transcript.lower().split()
        if len(pt) >= 6 and len(ot) < max(3, int(0.4 * len(pt))):
            issues.append("truncated_speech")

    gaps = list(feats.get("silence_intervals") or [])
    max_gap = float(feats.get("pause_distribution", {}).get("max_gap_sec") or 0)
    if max_gap >= float(max_internal_gap_sec):
        # Ignore trailing/leading only if single gap at edges — still flag large internal gaps
        internal = [g for g in gaps if float(g.get("start") or 0) > 0.2]
        if any(float(g.get("duration") or 0) >= max_internal_gap_sec for g in internal) or max_gap >= max_internal_gap_sec * 1.5:
            issues.append("extreme_unexplained_silence")

    ratio = feats.get("speech_ratio")
    if ratio is not None and float(ratio) < float(min_speech_ratio) and float(feats.get("duration") or 0) > 1.0:
        issues.append("low_speech_ratio")

    # Speech outside intended window (last dialogue end)
    if planned_dialogues and segments:
        win_end = max(float(d.get("end") or d.get("end_sec") or 0) for d in planned_dialogues)
        if win_end > 0:
            for s in segments:
                if float(s.get("start") or 0) > win_end + 0.75:
                    issues.append("speech_outside_dialogue_window")
                    break

    if issues:
        cls = ANOMALOUS
        status = STATUS_FAIL
    else:
        cls = NORMAL
        status = STATUS_PASS

    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "kind": "speech_delivery_integrity",
            "status": status,
            "class": cls,
            "issues": issues,
            "NATURALNESS_OBSERVATION": NATURALNESS_OBSERVATION_UNKNOWN,
            "subjective_naturalness_score_forbidden": True,
            "tts_success_is_not_naturalness_pass": True,
            "unknown_as_pass": False,
            "authority": "observation_only",
        }
    )


def observe_emotion_evidence(
    *,
    intended_emotion: str,
    observed_emotion: str = "",
    emotion_classifier_available: bool = False,
) -> dict[str, Any]:
    """INTENT vs OBSERVATION — never invent emotion gate."""
    if not emotion_classifier_available or not str(observed_emotion or "").strip():
        return strip_secrets(
            {
                "INTENDED_EMOTION": intended_emotion,
                "OBSERVED_EMOTION": UNKNOWN,
                "class": UNKNOWN,
                "status": UNKNOWN,
                "intent_equals_actual_without_evidence": False,
                "creates_emotion_gate": False,
            }
        )
    a = str(intended_emotion or "").strip().lower()
    b = str(observed_emotion or "").strip().lower()
    if a == b:
        cls = MATCH
    elif a and b and (a in b or b in a):
        cls = "PARTIAL"
    else:
        cls = MISMATCH
    return strip_secrets(
        {
            "INTENDED_EMOTION": intended_emotion,
            "OBSERVED_EMOTION": observed_emotion,
            "class": cls,
            "status": cls,
            "creates_emotion_gate": False,
            "blocks_only_if_existing_contract_requires": True,
        }
    )


def observe_master_localized_voice(
    *,
    master_contract: Mapping[str, Any],
    localized_contract: Mapping[str, Any],
    master_acoustic: Optional[Mapping[str, Any]] = None,
    localized_acoustic: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Cross-language acoustic identity is unreliable → UNKNOWN; contract may still match."""
    from pipeline.production_consistency import voice_identity_from_mapping, voice_identity_preserved

    m = voice_identity_from_mapping(dict(master_contract)) if not hasattr(master_contract, "voice_identity_id") else master_contract
    loc = voice_identity_from_mapping(dict(localized_contract)) if not hasattr(localized_contract, "voice_identity_id") else localized_contract
    contract = None
    if m is not None and loc is not None and hasattr(m, "voice_identity_id"):
        contract = voice_identity_preserved(m, loc, language_changed=True)
    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "kind": "master_localized_voice",
            "contract": contract,
            "acoustic_cross_language_status": UNKNOWN,
            "reason": "cross_language_acoustic_identity_unreliable_without_approved_provider",
            "master_acoustic_recorded": bool(master_acoustic),
            "localized_acoustic_recorded": bool(localized_acoustic),
            "waveforms_identical_not_required": True,
            "unknown_as_pass": False,
            "second_voice_identity_authority": False,
        }
    )


def observe_acoustic_voice_bundle(
    *,
    audio_path: Path | str,
    dialogue_segments: Sequence[Mapping[str, Any]],
    voice_identity: Any = None,
    generation_voice_hint: str = "",
    scene_id: str = "",
    job_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
    audio_asset_id: str = "",
    peer_scene_bundles: Optional[Sequence[Mapping[str, Any]]] = None,
    peer_generation_voice_hints: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Full Phase 6I evidence bundle for one audio asset / scene group."""
    speech = observe_speech_segments(
        audio_path,
        dialogue_ids=[str(d.get("dialogue_id") or "") for d in dialogue_segments],
        job_id=job_id,
        scene_id=scene_id,
        customer_id=customer_id,
        channel_id=channel_id,
    )
    feats = observe_acoustic_features(
        audio_path,
        audio_asset_id=audio_asset_id,
        job_id=job_id,
        scene_id=scene_id,
        customer_id=customer_id,
        channel_id=channel_id,
        speech_observation=speech,
    )
    delivery = observe_speech_delivery_integrity(
        planned_dialogues=list(dialogue_segments),
        speech_observation=speech,
        acoustic_features=feats,
    )
    emotions = [
        observe_emotion_evidence(intended_emotion=str(d.get("emotion") or d.get("emotional_intent") or ""))
        for d in dialogue_segments
    ]
    voice_bind = (
        bind_voice_identity_contract(
            voice_identity=voice_identity,
            scene_id=scene_id,
            dialogue_id=str((dialogue_segments[0] or {}).get("dialogue_id") or "") if dialogue_segments else "",
            emotion=str((dialogue_segments[0] or {}).get("emotion") or "") if dialogue_segments else "",
            acoustic_verification_available=False,
        )
        if voice_identity is not None
        else None
    )
    compare = compare_acoustic_voice_identity(
        candidate={**feats, "voice_identity_binding": voice_bind},
        voice_identity=voice_identity,
        generation_voice_hint=generation_voice_hint,
        reference_generation_voice_hint=generation_voice_hint,
    )

    peers = list(peer_scene_bundles or [])
    consistency = None
    if peers:
        consistency = evaluate_cross_scene_voice_consistency(
            [feats, *peers],
            generation_voice_hints=[generation_voice_hint, *(peer_generation_voice_hints or [])],
        )

    overall = STATUS_PASS
    issues: list[str] = []

    def _bump(cur: str, new: str) -> str:
        if cur == STATUS_FAIL or new == STATUS_FAIL:
            return STATUS_FAIL
        if cur == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
            return STATUS_UNKNOWN
        return STATUS_PASS

    # Acoustic identity UNKNOWN does not FAIL; delivery FAIL does
    if delivery.get("status") == STATUS_FAIL:
        overall = STATUS_FAIL
        issues.extend(list(delivery.get("issues") or []))
    overall = _bump(overall, STATUS_UNKNOWN)  # acoustic identity always UNKNOWN in Option A
    issues.append("acoustic_voice_identity_unknown_no_embedding_provider")

    if consistency and consistency.get("heuristic_mismatch_detected"):
        issues.append("generation_voice_hint_inconsistent_heuristic")
        # Do not convert to acoustic FAIL; keep UNKNOWN overall unless delivery failed
        overall = _bump(overall, STATUS_UNKNOWN)

    return strip_secrets(
        {
            "schema": SCHEMA_ACOUSTIC,
            "status": overall,
            "issues": issues,
            "features": feats,
            "speech": speech,
            "delivery": delivery,
            "emotions": emotions,
            "voice_binding": voice_bind,
            "acoustic_compare": compare,
            "cross_scene": consistency,
            "VOICE_IDENTITY_OBSERVATION": UNKNOWN,
            "NATURALNESS_OBSERVATION": UNKNOWN,
            "embedding_integrated": False,
            "selected_approach": "OPTION_A_EXISTING_TOOLS_ONLY",
            "second_voice_identity_authority": False,
            "second_asr_engine": False,
            "second_tts_engine": False,
            "second_quality_engine": False,
            "second_repair_engine": False,
            "second_ffmpeg_engine": False,
            "second_semantic_gate": False,
            "unknown_as_pass": False,
            "unknown_as_fail": False,
            "creates_final_gate": False,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "created_at": time.time(),
        }
    )
