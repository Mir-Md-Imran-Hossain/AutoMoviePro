"""Idempotent render/assembly bridge — BUILD-04D."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from pipeline.idempotency.render_manifest import (
    RenderAssemblyManifest,
    RenderSceneInput,
    build_manifest_from_clips,
    load_script_fingerprint,
)
from pipeline.idempotency.render_request import RenderRequestSpec
from pipeline.idempotency.render_runtime import RenderGenerationResult, execute_render_request
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)


def build_render_spec(
    *,
    job_id: str,
    manifest: RenderAssemblyManifest,
    provider: str = "ffmpeg",
    model: str = "compose-v1",
) -> RenderRequestSpec:
    return RenderRequestSpec(job_id=job_id, manifest=manifest, provider=provider, model=model)


def idempotent_compose_final_video(
    work_dir: Path,
    *,
    job_id: str,
    clips: List[Path],
    logo: Optional[Path] = None,
    video_type: str = "short",
    size: str = "1080x1920",
    max_seconds: int = 120,
    script_fingerprint: str = "",
    subtitle_path: Optional[Path] = None,
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
) -> Path:
    """
    Canonical final video assembly: concat → logo → trim/re-encode.

    H3: Sole compose/render entry for production final masters.
    Legacy scene_builder / video_pipeline FFmpeg helpers remain the *provider*
    implementation behind this bridge — do not call parallel final-compose
    entry points for the same fingerprint.

    AMP-004 Phase-08: RenderIntegrityContract preflight before expensive re-render.
    """
    work_dir = Path(work_dir)
    job_id = job_id or work_dir.name
    final = work_dir / f"final_{video_type}.mp4"
    fp = script_fingerprint or load_script_fingerprint(work_dir)
    manifest = build_manifest_from_clips(
        job_id=job_id,
        clips=clips,
        script_fingerprint=fp,
        logo_path=logo,
        video_type=video_type,
        size=size,
        max_seconds=max_seconds,
        subtitle_path=subtitle_path,
    )
    spec = build_render_spec(job_id=job_id, manifest=manifest)

    if final.is_file() and final.stat().st_size > 8000:
        try:
            r = execute_render_request(
                work_dir,
                spec,
                final,
                skip_generation=True,
                skip_reference=str(final),
            )
            if r.success and r.path:
                return Path(r.path)
        except Exception:
            pass

    # AMP-004 Phase-08: deterministic render preflight BEFORE expensive provider
    if not use_mock:
        from pipeline.rendering_integrity.preflight import RenderPreflightError
        from pipeline.rendering_integrity.production import apply_production_render_preflight

        try:
            apply_production_render_preflight(
                work_dir,
                job_id=job_id,
                clips=[Path(c) for c in clips],
                size=size,
                block_on_critical=True,
            )
        except RenderPreflightError:
            raise
        except Exception as exc:
            logger.error("render integrity preflight failed closed: %s", exc)
            raise RuntimeError(f"render_integrity_preflight:{exc}") from exc

    if provider_fn is None and not use_mock:

        def _real(tmp: Path):
            from pipeline.scene_builder import concat_av_clips, mix_logo_safe
            from pipeline.video_pipeline import _trim_reencode

            body = work_dir / "body_av.mp4"
            concat_av_clips(clips, body, size)
            branded = work_dir / "branded_av.mp4"
            mix_logo_safe(body, logo, branded)
            src = branded if branded.exists() else body
            _trim_reencode(src, tmp, max_seconds, size)
            return tmp

        provider_fn = _real

    result = execute_render_request(
        work_dir,
        spec,
        final,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )

    if result.success and result.path:
        return Path(result.path)

    if result.state == IdempotencyState.UNKNOWN:
        raise RuntimeError("Render UNKNOWN — reconciliation required before retry")

    raise RuntimeError(f"render failed action={result.action} state={result.state}")


def idempotent_render_request(
    work_dir: Path,
    spec: RenderRequestSpec,
    out_path: Path,
    *,
    provider_fn=None,
    use_mock: bool = False,
    mock_provider=None,
) -> RenderGenerationResult:
    return execute_render_request(
        work_dir,
        spec,
        out_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        mock_provider=mock_provider,
    )
