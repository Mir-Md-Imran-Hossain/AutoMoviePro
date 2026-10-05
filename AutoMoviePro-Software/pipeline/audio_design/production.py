"""Production audio design wiring (AMP-004 Phase-05).

Builds AudioPlan → preflight → persist → gate. Wired into scene handoff + video_pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.audio_design.gate import persist_audio_design_gate, persist_audio_plan
from pipeline.audio_design.loudness import analyze_wav_levels
from pipeline.audio_design.mix_policy import default_mix_policy, ducking_gain_db
from pipeline.audio_design.plan_builder import audio_plan_fingerprint, build_industrial_audio_plan
from pipeline.audio_design.preflight import AudioPreflightError, validate_industrial_audio_plan

logger = logging.getLogger(__name__)


def apply_production_audio_design(
    work_dir: Path,
    handoff_scenes: list[dict[str, Any]],
    *,
    job_id: str = "",
    block_on_critical: bool = True,
    canonical_voice: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """
    Attach canonical AudioPlan to each handoff scene and validate.
    Does not call TTS — prevention layer before generation.
    RCP-06D: all scenes share one VoiceIdentity; mismatch → block.
    """
    from pipeline.production_consistency import (
        apply_voice_identity_to_audio_plan,
        evaluate_voice_identity_continuity,
        resolve_canonical_voice_identity,
        voice_identity_from_mapping,
    )

    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    prepared: list[dict[str, Any]] = []
    seen_ids: list[str] = []
    plan_rows: list[dict[str, Any]] = []

    # Resolve one VoiceIdentity for the job (plan lock → declared consensus → MASTER)
    voice = None
    if canonical_voice is not None:
        voice = (
            canonical_voice
            if hasattr(canonical_voice, "voice_identity_id")
            else voice_identity_from_mapping(canonical_voice if isinstance(canonical_voice, dict) else {})
        )
    if voice is None:
        for sc in handoff_scenes or []:
            if isinstance(sc, dict) and isinstance(sc.get("voice_identity"), dict):
                voice = voice_identity_from_mapping(sc["voice_identity"])
                if voice:
                    break
    declared_profiles: list[str] = []
    for sc in handoff_scenes or []:
        if not isinstance(sc, dict):
            continue
        p = str(sc.get("voice_profile") or sc.get("voice_name") or "").strip()
        if p:
            declared_profiles.append(p)
    unique_declared = list(dict.fromkeys(x.lower() for x in declared_profiles))
    if voice is None:
        if len(unique_declared) == 1:
            voice = resolve_canonical_voice_identity(
                language=str((handoff_scenes[0] or {}).get("language") or "en") if handoff_scenes else "en",
                voice_profile=declared_profiles[0],
            )
        else:
            voice = resolve_canonical_voice_identity(
                language=str((handoff_scenes[0] or {}).get("language") or "en") if handoff_scenes else "en",
            )
    # Conflicting explicit declarations before lock → block
    if len(unique_declared) > 1 and block_on_critical:
        raise AudioPreflightError(
            "voice_identity_blocked:conflicting_scene_voice_profiles:" + ",".join(unique_declared),
            issues=[f"VOICE_IDENTITY_MISMATCH:profiles:{','.join(unique_declared)}"],
        )
    if len(unique_declared) == 1 and voice.vocal_profile and unique_declared[0] != voice.vocal_profile.lower():
        if block_on_critical:
            raise AudioPreflightError(
                f"voice_identity_blocked:scene_profile_vs_canonical:{unique_declared[0]}!={voice.vocal_profile}",
                issues=[f"VOICE_IDENTITY_MISMATCH:profile:{unique_declared[0]}!={voice.vocal_profile}"],
            )

    for i, sc in enumerate(handoff_scenes or []):
        if not isinstance(sc, dict):
            raise AudioPreflightError(f"scene[{i}]: handoff must be dict")
        out = dict(sc)
        narr = str(out.get("narration") or "").strip()
        dialogue_id = str(out.get("dialogue_id") or f"dlg-{i}")
        scene_id = str(out.get("canonical_scene_id") or out.get("scene_id") or i)
        seen_ids.append(dialogue_id)

        plan = build_industrial_audio_plan(
            scene_id=scene_id,
            dialogue_id=dialogue_id,
            dialogue_text=narr,
            language=str(out.get("language") or out.get("lang") or voice.language or "en"),
            speaker_id=str(out.get("speaker_id") or out.get("voice") or voice.speaker_id or ""),
            voice_profile=voice.vocal_profile,
            emotion=str(out.get("emotion") or out.get("emotional_intent") or "neutral"),
            intensity=float(out.get("emotion_intensity") or 0.5),
            delivery_style=str(out.get("delivery_style") or out.get("delivery") or "neutral"),
            speech_rate=float(out.get("speech_rate") or out.get("speaking_speed") or 1.0),
            location=str(out.get("location") or ""),
            environment=str(out.get("environment") or ""),
            primary_action=str(out.get("primary_action") or ""),
            duration_target_sec=float(out["duration_target_sec"]) if out.get("duration_target_sec") else None,
            segment_id=str(out.get("segment_id") or ""),
            revision_id=str(out.get("revision_id") or ""),
            pronunciation=list(out.get("pronunciation") or []),
            ambience=out.get("ambience") if isinstance(out.get("ambience"), dict) else None,
            sfx_events=list(out["sfx_events"]) if isinstance(out.get("sfx_events"), list) else None,
            music=out.get("music") if isinstance(out.get("music"), dict) else None,
        )
        plan = apply_voice_identity_to_audio_plan(plan, voice)
        # Allow scene to inject explicit contradictory ambience for validation
        if isinstance(out.get("ambience"), dict):
            plan.ambience = out["ambience"]
        if isinstance(out.get("music"), dict):
            plan.music = out["music"]
        if isinstance(out.get("sfx_events"), list):
            plan.sfx_events = list(out["sfx_events"])

        validation = validate_industrial_audio_plan(
            plan,
            dialogue_text=narr,
            location=str(out.get("location") or plan.metadata.get("location") or ""),
            environment=str(out.get("environment") or ""),
            primary_action=str(out.get("primary_action") or ""),
            known_dialogue_ids=seen_ids,
        )
        if validation["status"] == "BLOCK" and block_on_critical:
            raise AudioPreflightError(
                f"scene[{i}]: audio_plan_blocked:{validation['issues'][0]}",
                issues=validation["issues"],
            )

        plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan.dict()
        persist_audio_plan(work_dir, plan_dict, key=f"{scene_id}_{dialogue_id}")
        out["audio_plan"] = plan_dict
        out["voice_identity"] = voice.to_dict()
        out["voice_profile"] = voice.vocal_profile
        out["voice_name"] = voice.vocal_profile
        out["audio_plan_fingerprint"] = audio_plan_fingerprint(plan)
        out["audio_plan_validation"] = validation
        out["_audio_design_applied"] = True
        mix = default_mix_policy()
        out["mix_policy"] = mix.to_dict()
        out["ducking_music_db"] = ducking_gain_db("music", dialogue_active=True, policy=mix)
        prepared.append(out)
        plan_rows.append({"scene_id": scene_id, "dialogue_id": dialogue_id, "validation": validation})

    vi_gate = evaluate_voice_identity_continuity(canonical=voice, scene_refs=prepared)
    if not vi_gate.get("ok") and block_on_critical:
        raise AudioPreflightError(
            f"voice_identity_blocked:{','.join(vi_gate.get('blocks') or ['continuity'])}",
            issues=list(vi_gate.get("blocks") or []),
        )

    gate = {
        "status": "PASS",
        "job_id": job,
        "scene_count": len(prepared),
        "plans": plan_rows,
        "mix_policy": default_mix_policy().to_dict(),
        "authority": "pipeline.audio_design",
        "voice_identity": voice.to_dict(),
        "voice_identity_continuity": vi_gate,
    }
    if any(p["validation"]["status"] == "BLOCK" for p in plan_rows):
        gate["status"] = "BLOCKED"
        gate["reason"] = "audio_plan_blocked"
    if not vi_gate.get("ok"):
        gate["status"] = "BLOCKED"
        gate["reason"] = "voice_identity_continuity"
    persist_audio_design_gate(work_dir, gate)
    logger.info("audio design applied job=%s scenes=%s status=%s", job, len(prepared), gate["status"])
    return prepared


def run_production_audio_design_gate(
    work_dir: Path,
    *,
    job_id: str = "",
    audio_paths: Optional[list[Path]] = None,
    final_audio_or_video: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Observe actual audio artifacts + finalize AUDIO_DESIGN_GATE.
    Semantic emotion quality remains UNKNOWN without capable evaluator.
    """
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    observations: list[dict[str, Any]] = []
    issues: list[str] = []

    paths = list(audio_paths or [])
    for p in sorted(work_dir.glob("narration_*.wav"))[:24]:
        paths.append(p)
    for p in sorted(work_dir.glob("narration_*.m4a"))[:24]:
        paths.append(p)

    seen: set[str] = set()
    for p in paths:
        p = Path(p)
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.suffix.lower() == ".wav":
            levels = analyze_wav_levels(p)
        else:
            # Container exists — duration/stream via existing validator; loudness UNKNOWN
            from pipeline.idempotency.audio_validation import validate_audio_asset

            ok, reason = validate_audio_asset(str(p))
            levels = {
                "status": "PASS" if ok else "FAIL",
                "method": "DETERMINISTIC" if ok else "DETERMINISTIC",
                "issues": [] if ok else [reason],
                "loudness": "UNKNOWN",
                "claim": "emotion_and_pronunciation_unknown_without_evaluator",
            }
        observations.append({"path": str(p), "levels": levels})
        if levels.get("status") == "FAIL":
            issues.extend(list(levels.get("issues") or ["audio_fail"]))

    # Final mix: if video/audio provided, require stream presence via composite path elsewhere;
    # here mark final observation honesty
    final_status = "PASS"
    if final_audio_or_video and Path(final_audio_or_video).is_file():
        from pipeline.idempotency.render_validation import probe_render_metadata

        meta = probe_render_metadata(Path(final_audio_or_video))
        if not meta.get("has_audio"):
            issues.append("final_mix_missing_audio_stream")
            final_status = "FAIL"
        observations.append(
            {
                "path": str(final_audio_or_video),
                "final_mix": True,
                "has_audio": bool(meta.get("has_audio")),
                "duration": meta.get("duration_sec"),
                "semantic_emotion": "UNKNOWN",
                "method": "DETERMINISTIC",
            }
        )
    elif not observations:
        final_status = "UNKNOWN"
        issues.append("no_audio_observations")

    if issues:
        status = "BLOCKED" if final_status == "FAIL" or any("silence" in i or "clipping" in i for i in issues) else "BLOCKED"
    elif final_status == "UNKNOWN" and not observations:
        status = "UNKNOWN"
    else:
        status = "PASS"

    gate = {
        "status": status,
        "verdict": status,
        "job_id": job,
        "issues": issues,
        "observations": observations,
        "semantic_summary": {
            "emotion_quality": "UNKNOWN",
            "pronunciation_quality": "UNKNOWN",
            "unknown_is_not_pass": True,
            "technical_pass_implies_emotion_pass": False,
        },
        "mix_policy": default_mix_policy().to_dict(),
        "authority": "pipeline.audio_design",
    }
    persist_audio_design_gate(work_dir, gate)
    return gate
