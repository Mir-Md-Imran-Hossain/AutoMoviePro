"""Idempotent subtitle bridge — BUILD-04E."""
from __future__ import annotations

import logging
from pathlib import Path

from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.subtitle_engine import cues_to_srt_file, generate_bound_cues
from pipeline.idempotency.subtitle_request import SubtitleRequestSpec
from pipeline.idempotency.subtitle_runtime import SubtitleGenerationResult, execute_subtitle_request
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)


def build_subtitle_spec(
    *,
    job_id: str,
    scene_id: str,
    dialogue_id: str,
    localized_text: str,
    audio_path: Path,
    language: str = "en",
    segment_id: str = "",
    scene_duration_sec: float = 0.0,
    leading_gap_sec: float = 0.5,
    trailing_gap_sec: float = 0.5,
) -> SubtitleRequestSpec:
    from pipeline.compose import ffprobe_duration

    ap = Path(audio_path)
    dur = max(1.0, float(ffprobe_duration(ap) or 1.0))
    audio_fp = hash_artifact(str(ap))[:32] if ap.is_file() else ""
    return SubtitleRequestSpec(
        job_id=job_id,
        scene_id=str(scene_id),
        dialogue_id=dialogue_id,
        segment_id=segment_id,
        language=language,
        localized_text=localized_text,
        audio_fingerprint=audio_fp,
        audio_duration_sec=dur,
        scene_duration_sec=float(scene_duration_sec or 0),
        leading_gap_sec=leading_gap_sec,
        trailing_gap_sec=trailing_gap_sec,
    )


def idempotent_write_srt(
    text: str,
    audio_path: Path,
    srt_path: Path,
    *,
    work_dir: Path,
    job_id: str,
    scene_id: str,
    dialogue_id: str,
    language: str = "en",
    segment_id: str = "",
    scene_duration_sec: float = 0.0,
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
) -> Path:
    """Canonical subtitle generation with identity binding and idempotency."""
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    srt_path = Path(srt_path)
    spec = build_subtitle_spec(
        job_id=job_id,
        scene_id=str(scene_id),
        dialogue_id=dialogue_id,
        localized_text=text,
        audio_path=audio_path,
        language=language,
        segment_id=segment_id,
        scene_duration_sec=scene_duration_sec,
    )

    if srt_path.is_file() and srt_path.stat().st_size > 20:
        try:
            r = execute_subtitle_request(
                work_dir,
                spec,
                srt_path,
                skip_generation=True,
                skip_reference=str(srt_path),
            )
            if r.success and r.path:
                return Path(r.path)
        except Exception:
            pass

    if provider_fn is None and not use_mock:

        def _real():
            cues = generate_bound_cues(
                text,
                spec.audio_duration_sec,
                scene_id=spec.scene_id,
                dialogue_id=spec.dialogue_id,
                segment_id=spec.segment_id,
                language=spec.language,
            )
            return {"cues": cues, "srt": cues_to_srt_file(cues)}

        provider_fn = _real

    result = execute_subtitle_request(
        work_dir,
        spec,
        srt_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )

    if result.success and result.path:
        return Path(result.path)

    if result.state == IdempotencyState.UNKNOWN:
        raise RuntimeError("Subtitle UNKNOWN — reconciliation required")

    raise RuntimeError(f"subtitle generation failed action={result.action} state={result.state}")


def idempotent_subtitle_request(
    work_dir: Path,
    spec: SubtitleRequestSpec,
    out_path: Path,
    **kwargs,
) -> SubtitleGenerationResult:
    return execute_subtitle_request(work_dir, spec, out_path, **kwargs)
