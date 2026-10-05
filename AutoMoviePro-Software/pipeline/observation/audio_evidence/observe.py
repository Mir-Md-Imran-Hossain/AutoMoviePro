"""Audio artifact + speech observation evidence — not a second audio/TTS/ASR authority."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import (
    SCHEMA_AUDIO,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    STATUS_UNAVAILABLE,
)
from pipeline.observation.frame_evidence.alignment import (
    assert_no_silent_dialogue_drop,
    build_dialogue_timeline,
)
from pipeline.retrieval.common import content_hash_file, strip_secrets
from pipeline.story_visual_direction import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    COVERAGE_UNKNOWN,
)

MATCH = "MATCH"
PARTIAL = "PARTIAL"
MISMATCH = "MISMATCH"
UNKNOWN = "UNKNOWN"

VOICE_IDENTITY_OBSERVATION_UNKNOWN = "UNKNOWN"


def _probe_audio_streams(path: Path) -> dict[str, Any]:
    """Technical probe via existing ffprobe binary — not a new FFmpeg engine."""
    from pipeline.compose import ffprobe_bin, ffprobe_duration

    meta: dict[str, Any] = {
        "duration": None,
        "sample_rate": None,
        "channels": None,
        "format": path.suffix.lstrip(".").lower() or "",
        "codec": "",
        "probe_ok": False,
    }
    try:
        meta["duration"] = float(ffprobe_duration(path))
    except Exception:
        meta["duration"] = None
    try:
        cmd = [
            ffprobe_bin(),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=30)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        fmt = dict(data.get("format") or {})
        if fmt.get("format_name"):
            meta["format"] = str(fmt.get("format_name") or meta["format"])
        if meta["duration"] is None and fmt.get("duration"):
            meta["duration"] = float(fmt["duration"])
        for st in data.get("streams") or []:
            if str(st.get("codec_type") or "") != "audio":
                continue
            meta["codec"] = str(st.get("codec_name") or "")
            if st.get("sample_rate"):
                meta["sample_rate"] = int(float(st["sample_rate"]))
            if st.get("channels"):
                meta["channels"] = int(st["channels"])
            meta["probe_ok"] = True
            break
    except Exception as exc:
        meta["probe_error"] = str(exc)[:200]
    return meta


def observe_audio_artifact(
    audio_path: Path | str,
    *,
    audio_asset_id: str = "",
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    """Observe actual audio artifact technical metadata. Never semantic PASS from metadata alone."""
    path = Path(audio_path)
    base = {
        "schema": SCHEMA_AUDIO,
        "schema_version": "amp_audio_evidence_v1",
        "audio_asset_id": audio_asset_id or path.stem,
        "job_id": job_id,
        "scene_id": scene_id,
        "dialogue_id": dialogue_id,
        "customer_id": customer_id,
        "channel_id": channel_id,
        "audio_path": str(path),
        "provider": "ffprobe",
        "evidence_source": "TECHNICAL_PROBE",
        "technical_is_not_semantic_pass": True,
        "second_ffmpeg_engine": False,
        "created_at": time.time(),
    }
    if not path.is_file():
        return strip_secrets(
            {
                **base,
                "observation_status": STATUS_FAIL,
                "reason": "missing_audio",
                "issues": ["missing_audio"],
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "format": "",
            }
        )
    if path.stat().st_size < 64:
        return strip_secrets(
            {
                **base,
                "observation_status": STATUS_FAIL,
                "reason": "corrupted_or_tiny_audio",
                "issues": ["corrupted_or_tiny_audio"],
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "format": path.suffix.lstrip("."),
                "content_hash": content_hash_file(path) if path.is_file() else "",
            }
        )

    from pipeline.idempotency.audio_validation import validate_audio_asset

    ok, why = validate_audio_asset(str(path))
    meta = _probe_audio_streams(path)
    # Optional loudness if WAV — never invent LUFS
    loudness: dict[str, Any] = {"status": STATUS_UNKNOWN, "claim": "no_broadcast_lufs"}
    try:
        from pipeline.audio_design.loudness import analyze_wav_levels

        loudness = analyze_wav_levels(path)
        if "claim" not in loudness:
            loudness["claim"] = "no_broadcast_lufs"
    except Exception:
        pass

    status = STATUS_PASS if ok and meta.get("probe_ok") else (
        STATUS_FAIL if not ok else STATUS_UNKNOWN
    )
    return strip_secrets(
        {
            **base,
            "observation_status": status,
            "duration": meta.get("duration"),
            "sample_rate": meta.get("sample_rate"),
            "channels": meta.get("channels"),
            "format": meta.get("format"),
            "codec": meta.get("codec"),
            "validation_ok": ok,
            "validation_reason": why,
            "loudness": loudness,
            "content_hash": content_hash_file(path),
            "naturalness_pass_forbidden_without_evidence": True,
            "tts_success_is_not_naturalness_pass": True,
            "issues": [] if status == STATUS_PASS else [why or "probe_incomplete"],
            "unknown_as_pass": False,
            "authority": "observation_only",
            "does_not_replace": ["AudioPlan", "VoiceIdentity", "av_quality_gates"],
        }
    )


def observe_speech_segments(
    audio_path: Path | str,
    *,
    dialogue_ids: Optional[Sequence[str]] = None,
    language_hint: str = "en",
    job_id: str = "",
    scene_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    """Reuse Phase 6A faster-whisper — never fabricate transcript."""
    from pipeline.observation.speech_timing.observe import observe_speech_timing, speech_tool_available

    avail = speech_tool_available()
    if not avail.get("available"):
        return strip_secrets(
            {
                "schema": SCHEMA_AUDIO,
                "kind": "speech_segments",
                "observation_status": STATUS_UNAVAILABLE,
                "status": STATUS_UNKNOWN,
                "reason": "asr_unavailable",
                "provider": "faster-whisper",
                "provider_verified": False,
                "segments": [],
                "transcript": "",
                "second_asr_engine": False,
                "asr_authority": "pipeline.observation.speech_timing.observe_speech_timing",
                "unknown_as_pass": False,
                "customer_id": customer_id,
                "channel_id": channel_id,
                "job_id": job_id,
                "scene_id": scene_id,
            }
        )

    raw = observe_speech_timing(audio_path, language_hint=language_hint)
    st = str(raw.get("status") or STATUS_UNKNOWN).upper()
    if st in (STATUS_UNAVAILABLE, "OBSERVATION_UNAVAILABLE"):
        return strip_secrets(
            {
                "schema": SCHEMA_AUDIO,
                "kind": "speech_segments",
                "observation_status": STATUS_UNAVAILABLE,
                "status": STATUS_UNKNOWN,
                "reason": raw.get("reason") or "asr_unavailable",
                "provider": "faster-whisper",
                "provider_verified": False,
                "segments": [],
                "transcript": "",
                "raw_status": st,
                "second_asr_engine": False,
                "asr_authority": "pipeline.observation.speech_timing.observe_speech_timing",
                "unknown_as_pass": False,
            }
        )

    dids = [str(x) for x in (dialogue_ids or [])]
    segments = []
    for i, seg in enumerate(raw.get("segments") or []):
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        mapped = dids[i] if i < len(dids) else (dids[0] if len(dids) == 1 else "")
        segments.append(
            {
                "segment_id": f"asr-{i+1}",
                "dialogue_id": mapped,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(max(0.0, end - start), 3),
                "text": str(seg.get("text") or ""),
                "confidence": None,
                "provider": "faster-whisper",
                "observation_status": STATUS_PASS if str(seg.get("text") or "").strip() else STATUS_UNKNOWN,
            }
        )

    return strip_secrets(
        {
            "schema": SCHEMA_AUDIO,
            "kind": "speech_segments",
            "observation_status": STATUS_PASS if segments else STATUS_UNKNOWN,
            "status": st if st in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN) else STATUS_UNKNOWN,
            "provider": "faster-whisper",
            "provider_verified": bool(raw.get("provider_verified")),
            "heuristic": False,
            "evidence_source": "LOCAL_ASR",
            "transcript": str(raw.get("transcript") or ""),
            "segments": segments,
            "words": list(raw.get("words") or [])[:200],
            "speaker_observation": raw.get("speaker_observation") or "UNAVAILABLE",
            "second_asr_engine": False,
            "asr_authority": "pipeline.observation.speech_timing.observe_speech_timing",
            "does_not_replace": list(raw.get("does_not_replace") or ["AudioPlan", "VoiceIdentity", "planned_srt"]),
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
            "scene_id": scene_id,
            "unknown_as_pass": False,
        }
    )


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def classify_dialogue_speech_coverage(
    dialogue: Mapping[str, Any],
    speech_segments: Sequence[Mapping[str, Any]],
    *,
    observation_available: bool = True,
) -> dict[str, Any]:
    if not observation_available:
        return strip_secrets(
            {
                "dialogue_id": dialogue.get("dialogue_id"),
                "coverage": COVERAGE_UNKNOWN,
                "timing_overlap_is_not_semantic_pass": True,
                "status": STATUS_UNKNOWN,
            }
        )
    d0 = float(dialogue.get("start") or dialogue.get("start_sec") or 0.0)
    d1 = float(dialogue.get("end") or dialogue.get("end_sec") or d0)
    need = max(0.0, d1 - d0)
    covered = 0.0
    ids = []
    for s in speech_segments or []:
        ov = _overlap(d0, d1, float(s.get("start") or 0), float(s.get("end") or 0))
        if ov > 1e-6:
            covered += ov
            ids.append(str(s.get("segment_id") or ""))
    if need <= 1e-9 and not speech_segments:
        cov = COVERAGE_UNKNOWN
    elif covered <= 1e-9:
        # If dialogue has no explicit window but ASR text exists for mapped id
        did = str(dialogue.get("dialogue_id") or "")
        mapped = [s for s in speech_segments if str(s.get("dialogue_id") or "") == did and str(s.get("text") or "").strip()]
        if mapped:
            cov = COVERAGE_FULL
        elif speech_segments and any(str(s.get("text") or "").strip() for s in speech_segments):
            cov = COVERAGE_PARTIAL if did else COVERAGE_PARTIAL
        else:
            cov = COVERAGE_NONE
    elif covered + 1e-3 >= need:
        cov = COVERAGE_FULL
    else:
        cov = COVERAGE_PARTIAL
    return strip_secrets(
        {
            "dialogue_id": dialogue.get("dialogue_id"),
            "coverage": cov,
            "overlap_sec": round(min(covered, need), 3) if need else 0.0,
            "required_sec": round(need, 3),
            "speech_segment_ids": [x for x in ids if x],
            "timing_overlap_is_not_semantic_pass": True,
            "vocabulary": "C05-S VisualCoverage",
        }
    )


def normalize_transcript_text(text: str) -> str:
    t = str(text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def align_transcript_texts(planned: str, observed: str, *, confidence_ok: bool = True) -> dict[str, Any]:
    if not confidence_ok or not str(observed or "").strip():
        return strip_secrets(
            {
                "class": UNKNOWN,
                "reason": "insufficient_transcript_confidence_or_empty",
                "similarity_is_not_production_pass": True,
            }
        )
    a = normalize_transcript_text(planned)
    b = normalize_transcript_text(observed)
    if not a:
        return strip_secrets({"class": UNKNOWN, "reason": "empty_planned", "similarity_is_not_production_pass": True})
    if a == b:
        return strip_secrets({"class": MATCH, "similarity_is_not_production_pass": True})
    aw, bw = set(a.split()), set(b.split())
    if not aw or not bw:
        return strip_secrets({"class": UNKNOWN, "similarity_is_not_production_pass": True})
    inter = len(aw & bw)
    ratio = inter / max(len(aw), 1)
    if ratio >= 0.85:
        return strip_secrets({"class": MATCH, "token_overlap": round(ratio, 3), "similarity_is_not_production_pass": True})
    if ratio >= 0.4:
        return strip_secrets({"class": PARTIAL, "token_overlap": round(ratio, 3), "similarity_is_not_production_pass": True})
    return strip_secrets({"class": MISMATCH, "token_overlap": round(ratio, 3), "similarity_is_not_production_pass": True})


def bind_voice_identity_contract(
    *,
    voice_identity: Any,
    dialogue_id: str = "",
    scene_id: str = "",
    emotion: str = "",
    acoustic_verification_available: bool = False,
) -> dict[str, Any]:
    """Contract binding only — TTS request ≠ acoustic PASS."""
    v = voice_identity
    if hasattr(v, "to_dict"):
        vd = dict(v.to_dict())
    elif isinstance(v, Mapping):
        vd = dict(v)
    else:
        vd = {
            "voice_identity_id": getattr(v, "voice_identity_id", ""),
            "canonical_voice_name": getattr(v, "canonical_voice_name", "") or getattr(v, "tts_voice_name", ""),
            "vocal_profile": getattr(v, "vocal_profile", ""),
        }
    return strip_secrets(
        {
            "voice_identity_id": str(vd.get("voice_identity_id") or ""),
            "canonical_voice_name": str(
                vd.get("canonical_voice_name")
                or vd.get("tts_voice_name")
                or vd.get("voice_name")
                or vd.get("vocal_profile")
                or ""
            ),
            "dialogue_id": dialogue_id,
            "scene_id": scene_id,
            "emotion": emotion,
            "VOICE_IDENTITY_OBSERVATION": (
                STATUS_PASS if acoustic_verification_available else VOICE_IDENTITY_OBSERVATION_UNKNOWN
            ),
            "tts_request_is_not_acoustic_verification": True,
            "voice_identity_authority": "pipeline.production_consistency.VoiceIdentity",
            "second_voice_identity_authority": False,
            "acoustic_verification_available": bool(acoustic_verification_available),
        }
    )


def evaluate_voice_continuity_evidence(
    scene_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Contract continuity across scenes; emotion changes are NOT identity failures."""
    ids = [str(s.get("voice_identity_id") or "") for s in scene_bindings if s.get("voice_identity_id")]
    emotions = [str(s.get("emotion") or "") for s in scene_bindings]
    stable = len(set(ids)) <= 1 if ids else False
    return strip_secrets(
        {
            "contract_stable": stable,
            "voice_identity_ids": ids,
            "emotions": emotions,
            "emotion_change_is_not_identity_failure": True,
            "VOICE_IDENTITY_OBSERVATION": VOICE_IDENTITY_OBSERVATION_UNKNOWN,
            "status": STATUS_PASS if stable else STATUS_FAIL,
            "authority": "pipeline.production_consistency.evaluate_voice_identity_continuity",
            "second_voice_identity_authority": False,
        }
    )


def build_audio_timeline(
    *,
    dialogue_segments: Sequence[Any],
    speech_observation: Mapping[str, Any],
    artifact: Mapping[str, Any],
    visual_beats: Optional[Sequence[Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    dlg = build_dialogue_timeline(
        dialogue_segments,
        customer_id=customer_id,
        channel_id=channel_id,
        job_id=job_id,
        audio_timeline_sec=artifact.get("duration"),
    )
    rows = []
    for d in dlg.get("segments") or []:
        rows.append(
            {
                "dialogue_id": d.get("dialogue_id"),
                "planned_start": d.get("start"),
                "planned_end": d.get("end"),
                "speech_segments": [
                    s
                    for s in (speech_observation.get("segments") or [])
                    if not s.get("dialogue_id") or s.get("dialogue_id") == d.get("dialogue_id")
                ],
                "audio_asset_id": artifact.get("audio_asset_id"),
                "scene_id": d.get("scene_id") or artifact.get("scene_id"),
                "visual_beat_ids": [
                    str(getattr(b, "beat_id", None) or (b.get("beat_id") if isinstance(b, Mapping) else "") or "")
                    for b in (visual_beats or [])
                    if str(
                        getattr(b, "dialogue_segment_id", None)
                        or (b.get("dialogue_segment_id") if isinstance(b, Mapping) else "")
                        or (b.get("dialogue_id") if isinstance(b, Mapping) else "")
                        or ""
                    )
                    == str(d.get("dialogue_id") or "")
                ],
            }
        )
    return strip_secrets(
        {
            "schema": SCHEMA_AUDIO,
            "kind": "audio_timeline",
            "rows": rows,
            "dialogue_timeline": dlg,
            "artifact": {
                "audio_asset_id": artifact.get("audio_asset_id"),
                "duration": artifact.get("duration"),
                "content_hash": artifact.get("content_hash"),
            },
            "second_audio_clock": False,
            "audio_authority": "AudioPlan/ffprobe",
            "customer_id": customer_id,
            "channel_id": channel_id,
            "job_id": job_id,
        }
    )


def align_dialogue_audio_visual(
    *,
    dialogue: Mapping[str, Any],
    speech_observation: Mapping[str, Any],
    frame_observation: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Join planned dialogue ↔ speech ↔ visual observation. Not a new semantic gate."""
    from pipeline.observation.frame_evidence.alignment import semantic_align_dialogue_to_observation

    planned_text = str(dialogue.get("text") or "")
    observed_text = str(speech_observation.get("transcript") or "")
    text_al = align_transcript_texts(
        planned_text,
        observed_text,
        confidence_ok=bool(speech_observation.get("provider_verified"))
        and str(speech_observation.get("status") or "") not in (STATUS_UNKNOWN, STATUS_UNAVAILABLE),
    )
    vis = None
    if frame_observation is None:
        vis = {
            "status": STATUS_UNKNOWN,
            "reason": "visual_observation_unavailable",
        }
    else:
        vis = semantic_align_dialogue_to_observation(dialogue, frame_observation)

    # Overall: UNKNOWN if either unknown; FAIL if clear mismatch
    statuses = [text_al.get("class"), vis.get("status")]
    overall = STATUS_PASS
    if text_al.get("class") == MISMATCH or vis.get("status") == STATUS_FAIL:
        overall = STATUS_FAIL
    elif text_al.get("class") == UNKNOWN or vis.get("status") == STATUS_UNKNOWN or not frame_observation:
        if text_al.get("class") == MISMATCH:
            overall = STATUS_FAIL
        elif text_al.get("class") in (MATCH, PARTIAL) and vis.get("status") == STATUS_PASS:
            overall = STATUS_PASS
        else:
            overall = STATUS_UNKNOWN if vis.get("status") == STATUS_UNKNOWN or text_al.get("class") == UNKNOWN else overall
        if frame_observation is None:
            overall = STATUS_UNKNOWN if overall == STATUS_PASS and text_al.get("class") != MISMATCH else overall
            if text_al.get("class") == MISMATCH:
                overall = STATUS_FAIL
            elif text_al.get("class") != MATCH:
                overall = STATUS_UNKNOWN

    # Simplify overall rules
    if text_al.get("class") == MISMATCH:
        overall = STATUS_FAIL
    elif frame_observation is None:
        overall = STATUS_UNKNOWN if text_al.get("class") != MISMATCH else STATUS_FAIL
        if text_al.get("class") == MATCH:
            overall = STATUS_UNKNOWN  # visual missing → UNKNOWN not PASS
    elif vis.get("status") == STATUS_FAIL:
        overall = STATUS_FAIL
    elif vis.get("status") == STATUS_UNKNOWN or text_al.get("class") == UNKNOWN:
        overall = STATUS_UNKNOWN
    elif text_al.get("class") in (MATCH, PARTIAL) and vis.get("status") == STATUS_PASS:
        overall = STATUS_PASS
    else:
        overall = STATUS_UNKNOWN

    return strip_secrets(
        {
            "dialogue_id": dialogue.get("dialogue_id"),
            "transcript_alignment": text_al,
            "visual_alignment": vis,
            "status": overall,
            "second_semantic_gate": False,
            "timing_overlap_is_not_semantic_pass": True,
            "creates_final_gate": False,
        }
    )


def repair_handoff_from_audio_evidence(
    *,
    subject_id: str,
    audio_bridge: Mapping[str, Any],
    old_fingerprint: str = "",
    work_dir: Optional[Path | str] = None,
) -> dict[str, Any]:
    """FAIL → existing AUDIO_ASSET repair planner. UNKNOWN → no repair."""
    payload = dict(audio_bridge or {})
    status = str(
        payload.get("status")
        or payload.get("observation_status")
        or (payload.get("alignment") or {}).get("status")
        or STATUS_UNKNOWN
    ).upper()

    if status in (STATUS_UNKNOWN, STATUS_UNAVAILABLE, "OBSERVATION_UNAVAILABLE", "ABSENT"):
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": "unknown_or_unavailable_does_not_trigger_repair",
                "status": status,
                "repair_scope": None,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
            }
        )
    if status != STATUS_FAIL:
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": f"status_{status}_no_repair",
                "status": status,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
            }
        )

    from pipeline.audio_design.repair_bridge import plan_audio_design_repair

    issues = list(payload.get("issues") or ["audio_observation_fail"])
    plan = plan_audio_design_repair(
        issues=issues,
        subject_id=subject_id,
        attempt=1,
        old_fingerprint=old_fingerprint,
        work_dir=work_dir,
    )
    if plan is None:
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": "repair_cycle_blocked_or_no_plan",
                "status": STATUS_FAIL,
                "whole_video_regeneration": False,
                "second_repair_engine": False,
                "execution": "NOT_AVAILABLE",
            }
        )
    scope = getattr(plan.repair_scope, "value", str(plan.repair_scope))
    return strip_secrets(
        {
            "repair_triggered": True,
            "status": STATUS_FAIL,
            "repair_scope": scope,
            "whole_video_regeneration": False,
            "plan": {
                "repair_scope": scope,
                "subject_id": plan.subject_id,
                "attempt": plan.attempt,
                "max_attempts": plan.max_attempts,
                "old_fingerprint": plan.old_fingerprint,
                "recommended_action": plan.recommended_action,
            },
            "authority": "BUILD-04F plan_repair / plan_audio_design_repair",
            "second_repair_engine": False,
        }
    )


def observe_audio_production(
    *,
    audio_path: Path | str,
    dialogue_segments: Sequence[Any],
    voice_identity: Any = None,
    visual_beats: Optional[Sequence[Any]] = None,
    frame_observations_by_dialogue: Optional[Mapping[str, Mapping[str, Any]]] = None,
    language_hint: str = "en",
    job_id: str = "",
    scene_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
    audio_asset_id: str = "",
    materialized_dialogue_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Full evidence bundle for Phase 6H certification."""
    artifact = observe_audio_artifact(
        audio_path,
        audio_asset_id=audio_asset_id,
        job_id=job_id,
        scene_id=scene_id,
        customer_id=customer_id,
        channel_id=channel_id,
    )
    dlg = build_dialogue_timeline(
        dialogue_segments,
        customer_id=customer_id,
        channel_id=channel_id,
        job_id=job_id,
        audio_timeline_sec=artifact.get("duration"),
    )
    planned_ids = [r["dialogue_id"] for r in dlg["segments"]]
    speech = observe_speech_segments(
        audio_path,
        dialogue_ids=planned_ids,
        language_hint=language_hint,
        job_id=job_id,
        scene_id=scene_id,
        customer_id=customer_id,
        channel_id=channel_id,
    )
    asr_ok = speech.get("provider_verified") and speech.get("observation_status") == STATUS_PASS

    # Audio-covered dialogue ids: mapped segments with text, else all planned if single-asset FULL coverage
    covered_ids = []
    for s in speech.get("segments") or []:
        if s.get("dialogue_id") and str(s.get("text") or "").strip():
            covered_ids.append(str(s["dialogue_id"]))
    if not covered_ids and asr_ok and planned_ids:
        # whole-file speech present — coverage by timing against cumulative windows
        covered_ids = list(planned_ids)

    mat_ids = list(materialized_dialogue_ids) if materialized_dialogue_ids is not None else list(planned_ids)
    drop = assert_no_silent_dialogue_drop(planned_ids, mat_ids)
    # Also require audio coverage unless ASR UNKNOWN
    audio_drop = assert_no_silent_dialogue_drop(planned_ids, covered_ids if asr_ok else planned_ids)
    if asr_ok and audio_drop.get("missing"):
        # Prefer reporting incomplete audio coverage via existing vocabulary
        drop = assert_no_silent_dialogue_drop(
            planned_ids,
            covered_ids,
            blocking_failure_recorded=True,
            blocking_reason="PRODUCTION_INCOMPLETE:dialogue_without_audio_coverage",
        )

    coverages = [
        classify_dialogue_speech_coverage(d, speech.get("segments") or [], observation_available=bool(asr_ok))
        for d in dlg["segments"]
    ]
    transcript_rows = [
        {
            "dialogue_id": d["dialogue_id"],
            **align_transcript_texts(
                str(d.get("text") or ""),
                str(speech.get("transcript") or ""),
                confidence_ok=bool(asr_ok),
            ),
        }
        for d in dlg["segments"]
    ]
    # Whole-script alignment against master ASR (per-beat vs full-file token ratio
    # under-reports when each short beat is scored against the entire transcript).
    joined_planned = " ".join(str(d.get("text") or "") for d in dlg["segments"]).strip()
    whole_align = align_transcript_texts(
        joined_planned,
        str(speech.get("transcript") or ""),
        confidence_ok=bool(asr_ok),
    )

    voice_rows = []
    if voice_identity is not None:
        for d in dlg["segments"]:
            voice_rows.append(
                bind_voice_identity_contract(
                    voice_identity=voice_identity,
                    dialogue_id=str(d["dialogue_id"]),
                    scene_id=str(d.get("scene_id") or scene_id),
                    emotion=str(d.get("emotion") or ""),
                    acoustic_verification_available=False,
                )
            )
    continuity = evaluate_voice_continuity_evidence(voice_rows) if voice_rows else {
        "status": STATUS_UNKNOWN,
        "VOICE_IDENTITY_OBSERVATION": VOICE_IDENTITY_OBSERVATION_UNKNOWN,
    }

    timeline = build_audio_timeline(
        dialogue_segments=dialogue_segments,
        speech_observation=speech,
        artifact=artifact,
        visual_beats=visual_beats,
        customer_id=customer_id,
        channel_id=channel_id,
        job_id=job_id,
    )
    fo = dict(frame_observations_by_dialogue or {})
    dva = [
        align_dialogue_audio_visual(
            dialogue=d,
            speech_observation=speech,
            frame_observation=fo.get(str(d["dialogue_id"])),
        )
        for d in dlg["segments"]
    ]

    overall = STATUS_PASS
    issues: list[str] = []

    def _bump(cur: str, new: str) -> str:
        if cur == STATUS_FAIL or new == STATUS_FAIL:
            return STATUS_FAIL
        if cur == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
            return STATUS_UNKNOWN
        return STATUS_PASS

    if artifact.get("observation_status") == STATUS_FAIL:
        overall = STATUS_FAIL
        issues.append("audio_artifact_fail")
    if not asr_ok:
        overall = _bump(overall, STATUS_UNKNOWN)
        issues.append("asr_unavailable_or_unknown")
    if drop.get("silent_drop"):
        overall = STATUS_FAIL
        issues.append("silent_dialogue_drop")
    # Prefer whole-script transcript class for master-file ASR
    whole_class = str(whole_align.get("class") or UNKNOWN)
    if whole_class == MISMATCH:
        overall = STATUS_FAIL
        issues.append("transcript_mismatch:whole_script")
    elif whole_class == UNKNOWN:
        overall = _bump(overall, STATUS_UNKNOWN)
    # Per-beat rows kept as evidence; do not escalate FAIL when whole script matches
    for t in transcript_rows:
        if t.get("class") == MISMATCH and whole_class not in (MATCH, PARTIAL):
            overall = STATUS_FAIL
            issues.append(f"transcript_mismatch:{t.get('dialogue_id')}")
        elif t.get("class") == UNKNOWN and whole_class == UNKNOWN:
            overall = _bump(overall, STATUS_UNKNOWN)
    for a in dva:
        overall = _bump(overall, str(a.get("status") or STATUS_UNKNOWN))

    return strip_secrets(
        {
            "schema": SCHEMA_AUDIO,
            "status": overall,
            "issues": issues,
            "artifact": artifact,
            "speech": speech,
            "dialogue_timeline": dlg,
            "coverages": coverages,
            "transcript_alignments": transcript_rows,
            "whole_script_alignment": whole_align,
            "no_silent_drop": drop,
            "voice_bindings": voice_rows,
            "voice_continuity": continuity,
            "audio_timeline": timeline,
            "dialogue_audio_visual": dva,
            "second_audio_engine": False,
            "second_asr_engine": False,
            "second_voice_identity_authority": False,
            "second_subtitle_engine": False,
            "second_quality_engine": False,
            "second_repair_engine": False,
            "second_ffmpeg_engine": False,
            "second_duration_engine": False,
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
