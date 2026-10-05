"""Idempotent TTS bridge — BUILD-04B / BUILD-04B-H."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Sequence

from pipeline.idempotency.audio_request import AudioRequestSpec
from pipeline.idempotency.audio_runtime import AudioGenerationResult, execute_audio_request
from pipeline.idempotency.embedded_audio import should_skip_english_tts_generation
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)

GOOGLE_TTS_MODEL = "gemini-2.5-flash-preview-tts"
EDGE_TTS_MODEL = "edge-neural"


def build_audio_spec(
    *,
    job_id: str,
    scene_id: int,
    dialogue_id: str,
    dialogue_text: str,
    language_hint: str,
    provider: str,
    model: str,
    voice_name: str = "",
    voice_id: str = "",
    emotion: str = "neutral",
    delivery_style: str = "neutral",
    emotion_intensity: float = 0.5,
    speaking_speed: float = 1.0,
    part_index: int = 0,
    segment_id: str = "",
    revision_id: str = "",
    audio_plan_id: str = "",
    audio_plan_fingerprint: str = "",
    skip_preflight: bool = False,
    audio_plan=None,
) -> AudioRequestSpec:
    did = dialogue_id or f"d{scene_id:02d}"
    try:
        from pipeline.lang_config import resolve_locked_voice, resolve_edge_voice

        if provider == "edge_tts":
            voice = resolve_edge_voice(voice_name, language_hint=language_hint)
        else:
            voice = resolve_locked_voice(voice_name, language_hint=language_hint)
    except Exception:
        voice = voice_id or voice_name or "Charon"

    # AMP-004 Phase-05: deterministic preflight BEFORE provider (cost protection)
    if not skip_preflight:
        from pipeline.audio_design.preflight import preflight_audio_request

        preflight_audio_request(
            dialogue_text=dialogue_text,
            language=language_hint,
            speaker_id=voice_id or voice,
            voice_id=voice_id or voice,
            emotion=emotion,
            delivery_style=delivery_style,
            intensity=float(emotion_intensity),
            speech_rate=float(speaking_speed),
            dialogue_id=did,
            scene_id=str(scene_id),
            segment_id=segment_id,
            audio_plan=audio_plan,
            block=True,
        )

    return AudioRequestSpec(
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=did,
        audio_plan_id=audio_plan_id or f"plan-{did}",
        dialogue_text=dialogue_text,
        language=language_hint,
        provider=provider,
        model=model,
        voice_profile=voice_name or voice,
        voice_id=voice_id or voice,
        emotion=emotion,
        delivery_style=delivery_style,
        emotion_intensity=float(emotion_intensity),
        speaking_speed=speaking_speed,
        part_index=part_index,
        segment_id=segment_id,
        revision_id=revision_id,
        audio_plan_fingerprint=audio_plan_fingerprint,
    )


def idempotent_synthesize_narration(
    work_dir: Path,
    *,
    job_id: str,
    scene_id: int,
    dialogue_text: str,
    out_path: Path,
    language_hint: str = "en",
    google_api_keys: Optional[List[str]] = None,
    voice_name: str = "",
    emotion: str = "neutral",
    speaking_speed: float = 1.0,
    dialogue_id: str = "",
    part_index: int = 0,
    segment_id: str = "",
    model: str = GOOGLE_TTS_MODEL,
    provider_fn=None,
    use_mock: bool = False,
    check_embedded_english: bool = True,
    allow_edge_fallback: bool = False,
) -> Path:
    """Surgical wrapper around synthesize_narration (Google primary)."""
    return idempotent_reuse_or_synthesize_tts(
        dialogue_text,
        out_path,
        work_dir=work_dir,
        job_id=job_id,
        scene_id=scene_id,
        language_hint=language_hint,
        google_api_keys=google_api_keys,
        voice_name=voice_name,
        emotion=emotion,
        speaking_speed=speaking_speed,
        dialogue_id=dialogue_id,
        part_index=part_index,
        segment_id=segment_id,
        provider_fn=provider_fn,
        use_mock=use_mock,
        check_embedded_english=check_embedded_english,
        allow_edge_fallback=allow_edge_fallback,
        prefer_edge=False,
    )


def idempotent_edge_tts(
    work_dir: Path,
    *,
    job_id: str,
    scene_id: int,
    dialogue_text: str,
    out_path: Path,
    language_hint: str = "en",
    voice_name: str = "",
    dialogue_id: str = "",
    part_index: int = 0,
    segment_id: str = "",
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
) -> Path:
    """Canonical edge_tts path with distinct provider identity."""
    spec = build_audio_spec(
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        dialogue_text=dialogue_text,
        language_hint=language_hint,
        provider="edge_tts",
        model=EDGE_TTS_MODEL,
        voice_name=voice_name,
        part_index=part_index,
        segment_id=segment_id,
    )

    if provider_fn is None and not use_mock:

        def _edge():
            from pipeline.edge_tts_fallback import synthesize_edge_tts

            return synthesize_edge_tts(
                dialogue_text,
                out_path,
                language_hint=language_hint,
                voice_name=voice_name,
            )

        provider_fn = _edge

    result = execute_audio_request(
        work_dir,
        spec,
        out_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )
    if result.success and result.path:
        return result.path
    raise RuntimeError(f"edge_tts failed action={result.action} state={result.state}")


def idempotent_reuse_or_synthesize_tts(
    text: str,
    dest: Path,
    *,
    work_dir: Path,
    job_id: str,
    scene_id: int = 0,
    language_hint: str = "en",
    google_api_keys: Optional[List[str]] = None,
    voice_name: str = "",
    emotion: str = "neutral",
    speaking_speed: float = 1.0,
    dialogue_id: str = "",
    part_index: int = 0,
    segment_id: str = "",
    extra_candidates: Optional[Sequence[Path]] = None,
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
    check_embedded_english: bool = True,
    allow_edge_fallback: bool = True,
    prefer_edge: bool = False,
) -> Path:
    """
    Unified TTS entry for localization, split-path, and reuse flows.
    Google primary; edge_tts only after documented FAILED (never UNKNOWN).
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty text for TTS")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name

    # Legacy sidecar reuse — validate then register via idempotency if file matches
    try:
        from pipeline.tts_reuse import find_reusable_tts, write_tts_sidecar

        hit = find_reusable_tts(
            dest,
            text,
            extra_candidates=extra_candidates,
            lang=language_hint,
            voice_name=voice_name,
        )
        if hit is not None and hit.is_file():
            spec = build_audio_spec(
                job_id=job_id,
                scene_id=scene_id,
                dialogue_id=dialogue_id,
                dialogue_text=text,
                language_hint=language_hint,
                provider="google" if not prefer_edge else "edge_tts",
                model=GOOGLE_TTS_MODEL if not prefer_edge else EDGE_TTS_MODEL,
                voice_name=voice_name,
                part_index=part_index,
                segment_id=segment_id,
            )
            r = execute_audio_request(
                work_dir,
                spec,
                dest,
                skip_generation=True,
                skip_reference=str(hit),
            )
            if r.path:
                return r.path
    except Exception:
        pass

    if language_hint in ("bn", "ta", "ml") and google_api_keys:
        prefer_edge = False

    if prefer_edge or (
        os.environ.get("AMP_PREFER_EDGE_TTS", "0").strip().lower() in {"1", "true", "yes"}
        and not google_api_keys
    ):
        return idempotent_edge_tts(
            work_dir,
            job_id=job_id,
            scene_id=scene_id,
            dialogue_text=text,
            out_path=dest,
            language_hint=language_hint,
            voice_name=voice_name,
            dialogue_id=dialogue_id,
            part_index=part_index,
            segment_id=segment_id,
            provider_fn=provider_fn if prefer_edge else None,
            use_mock=use_mock,
            mock_provider=mock_provider,
        )

    spec = build_audio_spec(
        job_id=job_id,
        scene_id=scene_id,
        dialogue_id=dialogue_id,
        dialogue_text=text,
        language_hint=language_hint,
        provider="google",
        model=GOOGLE_TTS_MODEL,
        voice_name=voice_name,
        emotion=emotion,
        speaking_speed=speaking_speed,
        part_index=part_index,
        segment_id=segment_id,
    )

    if check_embedded_english and language_hint.lower().startswith("en"):
        skip, reason, ref = should_skip_english_tts_generation(work_dir, scene_id)
        if skip and ref:
            logger.info("audio_bridge skip TTS scene=%s reason=%s", scene_id, reason)
            r = execute_audio_request(
                work_dir, spec, dest, skip_generation=True, skip_reference=str(ref)
            )
            if r.path:
                return r.path

    if provider_fn is None and not use_mock:

        def _google():
            from pipeline.tts_google import synthesize_narration

            return synthesize_narration(
                text,
                dest.with_suffix("") if dest.suffix else dest,
                google_api_keys=list(google_api_keys or []),
                voice_name=voice_name,
                language_hint=language_hint,
                idempotency_work_dir=work_dir,
                idempotency_job_id=job_id,
                idempotency_scene_id=scene_id,
                idempotency_dialogue_id=dialogue_id or spec.dialogue_id,
                idempotency_part_index=part_index,
                idempotency_segment_id=segment_id,
                allow_idempotent_edge_fallback=False,
            )

        provider_fn = _google

    result = execute_audio_request(
        work_dir,
        spec,
        dest,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )

    if result.success and result.path:
        try:
            from pipeline.tts_reuse import write_tts_sidecar

            write_tts_sidecar(result.path, text, voice_name=voice_name)
        except Exception:
            pass
        return result.path

    if result.state == IdempotencyState.UNKNOWN:
        raise RuntimeError("TTS UNKNOWN — reconciliation required before fallback")

    if allow_edge_fallback and result.action in ("failed",):
        fp = spec.fingerprint() if callable(spec.fingerprint) else str(spec.fingerprint)
        logger.info("google TTS failed — controlled edge_tts fallback fp=%s", fp[:12])
        return idempotent_edge_tts(
            work_dir,
            job_id=job_id,
            scene_id=scene_id,
            dialogue_text=text,
            out_path=dest,
            language_hint=language_hint,
            voice_name=voice_name,
            dialogue_id=dialogue_id,
            part_index=part_index,
            segment_id=segment_id,
            use_mock=use_mock,
            mock_provider=mock_provider,
        )

    raise RuntimeError(f"audio generation failed action={result.action} state={result.state}")
