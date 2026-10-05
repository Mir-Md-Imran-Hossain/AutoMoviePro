"""Actual rendered-media observation — extends BUILD-04D + P04; does not replace them."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.render_validation import probe_render_metadata, validate_render_output
from pipeline.rendering_integrity.contract import RenderIntegrityContract


def observe_rendered_output(
    path: Path | str,
    *,
    contract: Optional[RenderIntegrityContract] = None,
    require_audio: bool = True,
    require_video: bool = True,
    reference_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """
    Layer-E observation of final media.
    Successful FFmpeg return code alone is NOT proof — this inspects the file.
    Optional VMAF perceptual evidence attaches when reference_path is provided;
    missing reference → UNKNOWN perceptual block (never invented PASS).
    """
    p = Path(path)
    issues: list[str] = []
    if not p.is_file():
        return {
            "status": "FAIL",
            "issues": ["missing_output_file"],
            "method": "DETERMINISTIC",
            "layer": "E",
            "subprocess_success_is_not_proof": True,
        }
    if p.stat().st_size < 8000:
        issues.append("partial_or_tiny_output")

    expected_size = contract.geometry.size_str() if contract else ""
    ok, reason = validate_render_output(
        str(p),
        expected_size=expected_size,
        require_audio=require_audio,
        require_video=require_video,
    )
    meta = probe_render_metadata(p)
    if not ok:
        issues.append(reason or "validate_render_output_failed")

    if contract:
        geo = contract.geometry
        if meta.get("width") and meta.get("height"):
            if int(meta["width"]) != int(geo.width) or int(meta["height"]) != int(geo.height):
                issues.append(
                    f"geometry_mismatch:{meta['width']}x{meta['height']}!={geo.width}x{geo.height}"
                )
        if geo.fps > 0 and meta.get("fps"):
            if abs(float(meta["fps"]) - float(geo.fps)) > 1.5:
                issues.append(f"fps_mismatch:{meta['fps']}!={geo.fps}")
        if contract.timeline:
            expected = max(s.end_sec for s in contract.timeline) - min(s.start_sec for s in contract.timeline)
            actual = float(meta.get("duration_sec") or 0)
            if expected > 0 and actual > 0 and abs(expected - actual) > max(2.0, expected * 0.08):
                issues.append(f"duration_integrity_mismatch:expected={expected:.2f},actual={actual:.2f}")

    if require_video and not meta.get("has_video"):
        issues.append("missing_video_stream")
    if require_audio and not meta.get("has_audio"):
        issues.append("missing_audio_stream")

    sync_status = "PASS"
    if meta.get("has_video") and meta.get("has_audio"):
        # True lip-sync offset not observable without dedicated tooling
        if not meta.get("duration_sec"):
            sync_status = "UNKNOWN"
            issues.append("av_sync_unobserved")
    elif require_audio or require_video:
        sync_status = "UNKNOWN"

    if reason == "ok_container_only" and not meta.get("has_video"):
        issues.append("probe_incomplete_unknown")

    # Perceptual quality observation (VMAF) — evidence only; does not invent PASS without reference
    perceptual: dict[str, Any] = {}
    try:
        from pipeline.observation.perceptual_quality import observe_perceptual_quality

        perceptual = observe_perceptual_quality(p, reference_path=reference_path)
    except Exception as exc:
        perceptual = {
            "status": "OBSERVATION_UNAVAILABLE",
            "reason": "adapter_exception",
            "detail": str(exc)[:200],
            "unknown_as_pass": False,
        }
    # VMAF FAIL can contribute issues but UNKNOWN reference must not be treated as PASS
    pstat = str(perceptual.get("status") or "").upper()
    if pstat == "FAIL":
        for i in perceptual.get("issues") or ["vmaf_fail"]:
            issues.append(f"perceptual:{i}")
    elif pstat in ("UNKNOWN", "OBSERVATION_UNAVAILABLE"):
        # record only — do not escalate to PASS
        pass

    hard = [
        i
        for i in issues
        if i.startswith("missing_")
        or i.startswith("partial_")
        or i.startswith("geometry_")
        or i.startswith("fps_")
        or i.startswith("duration_")
        or i == "validate_render_output_failed"
        or i.startswith("perceptual:vmaf_low")
    ]
    unknown_only = [
        i
        for i in issues
        if i.endswith("_unknown") or i.endswith("_unobserved") or i == "probe_incomplete_unknown"
    ]

    if hard:
        status = "FAIL"
    elif unknown_only and not hard:
        status = "UNKNOWN"
    elif issues:
        status = "FAIL"
    else:
        status = "PASS"

    return {
        "status": status,
        "issues": list(dict.fromkeys(issues)),
        "metadata": meta,
        "sync_status": sync_status,
        "validation_reason": reason,
        "perceptual_quality": perceptual,
        "method": "DETERMINISTIC",
        "layer": "E",
        "path": str(p),
        "subprocess_success_is_not_proof": True,
        "unknown_as_pass": False,
    }
