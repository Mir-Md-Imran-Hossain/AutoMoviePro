"""Per-media-type artifact verifiers (AMP-004 Phase-04).

Reuses existing L0/L1 validators — does not fork validation engines.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pipeline.artifact_verification.contracts import (
    ArtifactObservation,
    MediaType,
    ObservationMethod,
    ObservationStatus,
    VerificationTier,
)
from pipeline.idempotency.audio_validation import probe_duration_sec, validate_audio_asset
from pipeline.idempotency.render_validation import probe_render_metadata, validate_render_output
from pipeline.idempotency.visual_validation import validate_visual_asset
from pipeline.artifact_verification.media_probe import (
    detect_blank_image,
    detect_near_silence_wav,
    probe_media,
)
from pipeline.artifact_verification.semantic_boundary import classify_semantic_observation


def _wav_duration_sec(path: Path) -> Optional[float]:
    try:
        import struct

        raw = path.read_bytes()
        if raw[:4] != b"RIFF" or len(raw) < 44:
            return None
        # PCM WAV: byte rate at 28, data size at 40
        byte_rate = struct.unpack_from("<I", raw, 28)[0]
        data_size = struct.unpack_from("<I", raw, 40)[0]
        if byte_rate <= 0:
            return None
        return data_size / float(byte_rate)
    except Exception:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fp(path: Path) -> str:
    try:
        from pipeline.idempotency.fingerprint import hash_artifact

        return hash_artifact(str(path))
    except Exception:
        h = hashlib.sha256()
        try:
            h.update(path.read_bytes()[:65536])
            return h.hexdigest()
        except Exception:
            return ""


def _base(
    *,
    artifact_id: str,
    path: Path,
    media_type: MediaType,
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    layer: str = "C",
    intent_fp: str = "",
    prompt_fp: str = "",
    expected_fp: str = "",
) -> ArtifactObservation:
    return ArtifactObservation(
        artifact_id=artifact_id,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        media_type=media_type,
        layer=layer,
        source_intent_fingerprint=intent_fp,
        prompt_fingerprint=prompt_fp,
        artifact_fingerprint=_fp(path) if path.is_file() else "",
        observation_time=_now(),
        path=str(path),
    )


def verify_visual_artifact(
    path: str | Path,
    *,
    artifact_id: str = "",
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    mode: str = "video",
    expected_hash: str = "",
    expected: Optional[dict[str, Any]] = None,
    contradiction_issues: Optional[list] = None,
    observed_labels: Optional[list[str]] = None,
    has_pixel_evidence: bool = False,
    intent_fp: str = "",
    prompt_fp: str = "",
    min_bytes: int = 8000,
) -> ArtifactObservation:
    path = Path(path)
    aid = artifact_id or f"visual:{path.name}"
    obs = _base(
        artifact_id=aid,
        path=path,
        media_type=MediaType.VIDEO if mode == "video" else MediaType.IMAGE,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        layer="C",
        intent_fp=intent_fp,
        prompt_fp=prompt_fp,
        expected_fp=expected_hash,
    )
    issues: list[str] = []

    if not path.is_file():
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.observation_method = ObservationMethod.DETERMINISTIC
        obs.verification_tier = VerificationTier.L0
        obs.issues = ["missing_artifact"]
        obs.confidence_label = "DETERMINISTIC"
        return obs

    ok, reason = validate_visual_asset(str(path), mode=mode, min_bytes=min_bytes, expected_hash=expected_hash)
    if not ok:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.observation_method = ObservationMethod.DETERMINISTIC
        obs.verification_tier = VerificationTier.L0
        obs.issues = [reason or "invalid_visual"]
        obs.confidence_label = "DETERMINISTIC"
        if expected_hash and reason == "hash_mismatch":
            obs.issues.append("fingerprint_mismatch")
        return obs

    if mode == "image":
        blank = detect_blank_image(path)
        if blank is True:
            obs.technical_status = ObservationStatus.FAIL
            obs.observation_status = ObservationStatus.FAIL
            obs.issues = ["blank_or_near_empty_image"]
            obs.observation_method = ObservationMethod.DETERMINISTIC
            obs.verification_tier = VerificationTier.L1
            obs.confidence_label = "DETERMINISTIC"
            return obs
        obs.width = 0
        obs.height = 0
    else:
        probe = probe_media(path)
        obs.duration = float(probe.get("duration") or 0)
        obs.width = int(probe.get("width") or 0)
        obs.height = int(probe.get("height") or 0)
        obs.fps = float(probe.get("fps") or 0)
        obs.frame_count = int(probe.get("frame_count") or 0)
        obs.video_streams = int(probe.get("video_streams") or 0)
        obs.audio_streams = int(probe.get("audio_streams") or 0)
        obs.evidence["probe"] = {k: probe[k] for k in ("decodable", "video_codec", "format_name", "size_bytes") if k in probe}
        if not probe.get("decodable"):
            issues.append("not_decodable")
        if obs.video_streams < 1:
            issues.append("stream_mismatch:no_video")
        if obs.duration <= 0:
            issues.append("invalid_video:zero_duration")
        if issues:
            obs.technical_status = ObservationStatus.FAIL
            obs.observation_status = ObservationStatus.FAIL
            obs.issues = issues
            obs.observation_method = ObservationMethod.DETERMINISTIC
            obs.verification_tier = VerificationTier.L1
            obs.confidence_label = "DETERMINISTIC"
            return obs

    obs.technical_status = ObservationStatus.PASS
    obs.verification_tier = VerificationTier.L1
    obs.observation_method = ObservationMethod.DETERMINISTIC
    obs.confidence_label = "STRUCTURAL_ONLY"

    sem = classify_semantic_observation(
        expected=expected,
        observed_labels=observed_labels,
        contradiction_issues=contradiction_issues,
        has_pixel_or_asr_evidence=has_pixel_evidence,
    )
    obs.semantic_status = ObservationStatus(sem["semantic_status"])
    obs.evidence["semantic"] = sem
    # Overall observation for publishability uses technical; semantic kept honest
    if obs.semantic_status == ObservationStatus.FAIL:
        obs.observation_status = ObservationStatus.FAIL
        obs.issues.extend(list(sem.get("issues") or []))
    else:
        obs.observation_status = ObservationStatus.PASS
        if obs.semantic_status == ObservationStatus.UNKNOWN:
            obs.issues.append("semantic_unknown_not_pass")
    return obs


def verify_audio_artifact(
    path: str | Path,
    *,
    artifact_id: str = "",
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    expected_hash: str = "",
    expected_duration_sec: Optional[float] = None,
    duration_tolerance_sec: float = 2.0,
    intent_fp: str = "",
    min_bytes: int = 800,
) -> ArtifactObservation:
    path = Path(path)
    aid = artifact_id or f"audio:{path.name}"
    obs = _base(
        artifact_id=aid,
        path=path,
        media_type=MediaType.AUDIO,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        intent_fp=intent_fp,
    )
    if not path.is_file():
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = ["missing_artifact"]
        obs.observation_method = ObservationMethod.DETERMINISTIC
        obs.confidence_label = "DETERMINISTIC"
        return obs

    ok, reason = validate_audio_asset(str(path), min_bytes=min_bytes, expected_hash=expected_hash)
    if not ok:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = [reason or "invalid_audio"]
        if reason == "hash_mismatch":
            obs.issues.append("fingerprint_mismatch")
        obs.observation_method = ObservationMethod.DETERMINISTIC
        obs.confidence_label = "DETERMINISTIC"
        return obs

    dur = probe_duration_sec(str(path))
    probe = probe_media(path)
    if dur is None:
        dur = float(probe.get("duration") or 0) or None
    if dur is None or dur <= 0:
        dur = _wav_duration_sec(path)
    obs.duration = float(dur or 0)
    obs.audio_streams = max(1, int(probe.get("audio_streams") or 0)) if probe.get("decodable") else 0
    obs.sample_rate = int(probe.get("sample_rate") or 0)
    obs.channels = int(probe.get("channels") or 0)
    obs.evidence["probe"] = probe

    issues: list[str] = []
    if not probe.get("decodable") and path.suffix.lower() not in (".mp3", ".m4a", ".wav"):
        issues.append("not_decodable")
    if obs.duration <= 0 and path.suffix.lower() == ".wav":
        # wav without duration still may be valid bytes — try silence check only
        pass
    silence = detect_near_silence_wav(path)
    if silence is True:
        issues.append("near_silence")

    if expected_duration_sec is not None and expected_duration_sec > 0 and obs.duration > 0:
        if abs(obs.duration - expected_duration_sec) > duration_tolerance_sec:
            issues.append(
                f"duration_mismatch:expected={expected_duration_sec:.2f},actual={obs.duration:.2f}"
            )

    # Dialogue identity must be present when claimed
    if dialogue_id:
        obs.evidence["dialogue_identity"] = dialogue_id
    if scene_id:
        obs.evidence["scene_identity"] = scene_id

    # Semantic of spoken content without ASR → UNKNOWN
    sem = classify_semantic_observation(has_pixel_or_asr_evidence=False)
    obs.semantic_status = ObservationStatus(sem["semantic_status"])
    obs.evidence["semantic"] = sem

    if issues:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = issues
    else:
        obs.technical_status = ObservationStatus.PASS
        obs.observation_status = ObservationStatus.PASS
        if obs.semantic_status == ObservationStatus.UNKNOWN:
            obs.issues.append("semantic_unknown_not_pass")
    obs.observation_method = ObservationMethod.DETERMINISTIC
    obs.verification_tier = VerificationTier.L1
    obs.confidence_label = "STRUCTURAL_ONLY"
    return obs


def verify_subtitle_artifact(
    path: str | Path,
    *,
    artifact_id: str = "",
    job_id: str = "",
    scene_id: str = "",
    dialogue_id: str = "",
    language: str = "en",
    audio_duration_sec: Optional[float] = None,
) -> ArtifactObservation:
    path = Path(path)
    aid = artifact_id or f"subtitle:{path.name}"
    obs = _base(
        artifact_id=aid,
        path=path,
        media_type=MediaType.SUBTITLE,
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        layer="C",
    )
    if not path.is_file():
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = ["missing_artifact"]
        return obs

    from pipeline.idempotency.subtitle_validation import parse_srt, validate_cue_timestamps

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = [f"unreadable:{exc}"]
        return obs

    cues = parse_srt(content)
    if not cues:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = ["invalid_subtitle:no_cues"]
        return obs

    issues: list[str] = []
    ok, reason = validate_cue_timestamps(cues)
    if not ok:
        issues.append(reason)

    # Ordering / empty / orphan
    for i, c in enumerate(cues):
        if not str(c.get("text") or "").strip():
            issues.append(f"empty_cue:{i}")
        if dialogue_id and c.get("dialogue_id") and str(c["dialogue_id"]) != dialogue_id:
            issues.append(f"dialogue_identity_mismatch:{i}")
        if scene_id and c.get("scene_id") and str(c["scene_id"]) != scene_id:
            issues.append(f"scene_identity_mismatch:{i}")

    if audio_duration_sec and cues:
        last_end = float(cues[-1].get("end_time") or 0)
        if last_end > float(audio_duration_sec) + 1.0:
            issues.append("subtitle_audio_timing_mismatch")

    obs.evidence["cue_count"] = len(cues)
    obs.duration = float(cues[-1].get("end_time") or 0) if cues else 0
    obs.observation_method = ObservationMethod.DETERMINISTIC
    obs.verification_tier = VerificationTier.L1
    obs.confidence_label = "DETERMINISTIC"
    # Subtitle text alignment to speech without ASR → semantic UNKNOWN
    obs.semantic_status = ObservationStatus.UNKNOWN
    obs.evidence["semantic"] = {"semantic_status": "UNKNOWN", "claim": "no_asr"}

    if issues:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = issues
    else:
        obs.technical_status = ObservationStatus.PASS
        obs.observation_status = ObservationStatus.PASS
        obs.issues = ["semantic_unknown_not_pass"]
    return obs


def verify_composite_artifact(
    path: str | Path,
    *,
    artifact_id: str = "",
    job_id: str = "",
    expected_duration_sec: Optional[float] = None,
    require_audio: bool = True,
    require_video: bool = True,
    expected_hash: str = "",
    intent_fp: str = "",
    contradiction_issues: Optional[list] = None,
) -> ArtifactObservation:
    """Independent final composite verification (Layer E) — not inferred from sources alone."""
    path = Path(path)
    aid = artifact_id or f"composite:{path.name}"
    obs = _base(
        artifact_id=aid,
        path=path,
        media_type=MediaType.COMPOSITE,
        job_id=job_id,
        layer="E",
        intent_fp=intent_fp,
    )
    if not path.is_file():
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = ["missing_artifact"]
        return obs

    ok, reason = validate_render_output(
        str(path),
        expected_duration_sec=expected_duration_sec,
        require_audio=require_audio,
        require_video=require_video,
    )
    meta = probe_render_metadata(path)
    obs.duration = float(meta.get("duration_sec") or 0)
    obs.width = int(meta.get("width") or 0)
    obs.height = int(meta.get("height") or 0)
    obs.fps = float(meta.get("fps") or 0)
    obs.video_streams = 1 if meta.get("has_video") else 0
    obs.audio_streams = 1 if meta.get("has_audio") else 0
    obs.evidence["render_meta"] = meta
    obs.artifact_fingerprint = _fp(path)

    if expected_hash and obs.artifact_fingerprint and obs.artifact_fingerprint != expected_hash:
        ok = False
        reason = "fingerprint_mismatch"

    issues: list[str] = []
    if not ok:
        issues.append(reason or "invalid_composite")
    if require_video and not meta.get("has_video"):
        issues.append("stream_mismatch:no_video")
    if require_audio and not meta.get("has_audio"):
        issues.append("stream_mismatch:no_audio")
    if expected_duration_sec and obs.duration > 0:
        # Truncation: actual much shorter
        if obs.duration < expected_duration_sec * 0.7:
            issues.append("render_truncation_suspected")

    # Independent of source validity
    obs.evidence["independent_of_sources"] = True
    obs.observation_method = ObservationMethod.DETERMINISTIC
    obs.verification_tier = VerificationTier.L1
    obs.confidence_label = "STRUCTURAL_ONLY"

    sem = classify_semantic_observation(
        contradiction_issues=contradiction_issues,
        has_pixel_or_asr_evidence=False,
    )
    obs.semantic_status = ObservationStatus(sem["semantic_status"])
    obs.evidence["semantic"] = sem

    if issues:
        obs.technical_status = ObservationStatus.FAIL
        obs.observation_status = ObservationStatus.FAIL
        obs.issues = issues
    else:
        obs.technical_status = ObservationStatus.PASS
        obs.observation_status = ObservationStatus.PASS
        if obs.semantic_status == ObservationStatus.UNKNOWN:
            obs.issues.append("semantic_unknown_not_pass")
        if obs.semantic_status == ObservationStatus.FAIL:
            obs.observation_status = ObservationStatus.FAIL
            obs.issues.extend(list(sem.get("issues") or []))
    return obs
