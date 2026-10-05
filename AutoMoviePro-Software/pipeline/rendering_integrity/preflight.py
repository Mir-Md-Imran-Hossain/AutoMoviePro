"""Render preflight BEFORE expensive FFmpeg work."""
from __future__ import annotations

from typing import Any, Optional

from pipeline.rendering_integrity.contract import RenderIntegrityContract
from pipeline.rendering_integrity.filtergraph import validate_filtergraph, validate_geometry
from pipeline.rendering_integrity.text_render import validate_render_text
from pipeline.rendering_integrity.timeline import validate_av_sync_plan, validate_timeline
from pipeline.rendering_integrity.vfx import validate_transition_directives, validate_vfx_directives


class RenderPreflightError(RuntimeError):
    def __init__(self, message: str, *, issues: Optional[list[str]] = None, classification: str = "DETERMINISTIC_INPUT_ERROR") -> None:
        super().__init__(message)
        self.issues = list(issues or [])
        self.classification = classification


def preflight_render_contract(contract: RenderIntegrityContract, *, block: bool = True) -> dict[str, Any]:
    issues: list[str] = []
    if not (contract.project_id or "").strip():
        issues.append("missing_project_id")
    if not (contract.render_id or "").strip():
        issues.append("missing_render_id")
    if not contract.timeline:
        issues.append("missing_timeline")
    tl = validate_timeline(contract.timeline)
    issues.extend(tl.get("issues") or [])
    fg = validate_filtergraph(contract.filtergraph)
    issues.extend(fg.get("issues") or [])
    geo = validate_geometry(contract.geometry)
    issues.extend(geo.get("issues") or [])
    bounds = {s.scene_id: (s.start_sec, s.end_sec) for s in contract.timeline}
    vfx = validate_vfx_directives(contract.vfx, scene_bounds=bounds)
    issues.extend(vfx.get("issues") or [])
    intervals = {}
    for i in range(len(contract.timeline) - 1):
        a, b = contract.timeline[i], contract.timeline[i + 1]
        intervals[f"{a.scene_id}->{b.scene_id}"] = max(0.0, a.duration_sec)
    tr = validate_transition_directives(contract.transitions, scene_interval=intervals)
    if tr.get("status") == "BLOCK":
        issues.extend(tr.get("issues") or [])
    for overlay in contract.text_overlays:
        if not isinstance(overlay, dict):
            continue
        tx = validate_render_text(
            text=str(overlay.get("text") or ""),
            language=str(overlay.get("language") or "en"),
            font_path=str(overlay.get("font_path") or ""),
            overflow=bool(overlay.get("overflow")),
            safe_area=bool(overlay.get("safe_area", True)),
        )
        if tx.get("status") in ("BLOCK", "UNKNOWN"):
            issues.extend(tx.get("issues") or [])
    # Encode sanity
    if not (contract.encode.video_codec or "").strip():
        issues.append("missing_video_codec")
    if not (contract.encode.audio_codec or "").strip():
        issues.append("missing_audio_codec")

    unknown = [i for i in issues if i.endswith("_unknown") or i == "av_sync_unobserved"]
    hard = [i for i in issues if i not in unknown]
    if hard:
        status = "BLOCK"
        classification = "DETERMINISTIC_INPUT_ERROR"
        if any("filter" in i or "stream" in i for i in hard):
            classification = "FILTERGRAPH_ERROR"
    elif unknown:
        status = "UNKNOWN"
        classification = "UNKNOWN"
    else:
        status = "PASS"
        classification = "ok"

    result = {
        "status": status,
        "issues": list(dict.fromkeys(issues)),
        "timeline": tl,
        "filtergraph": fg,
        "geometry": geo,
        "vfx": vfx,
        "transitions": tr,
        "classification": classification,
        "method": "DETERMINISTIC",
        "provider_allowed": status == "PASS",
        "contract_fingerprint": contract.contract_fingerprint,
    }
    if block and status == "BLOCK":
        raise RenderPreflightError("render_preflight_blocked", issues=result["issues"], classification=classification)
    if block and status == "UNKNOWN":
        # Mandatory UNKNOWN before expensive work: block
        raise RenderPreflightError("render_preflight_unknown", issues=result["issues"], classification="UNKNOWN")
    return result


def preflight_clip_inputs(clips: list[Any], *, block: bool = True) -> dict[str, Any]:
    issues: list[str] = []
    from pathlib import Path

    if not clips:
        issues.append("no_input_clips")
    for i, c in enumerate(clips):
        p = Path(c)
        if not p.is_file():
            issues.append(f"missing_clip:{i}")
        elif p.stat().st_size < 100:
            issues.append(f"empty_clip:{i}")
    status = "BLOCK" if issues else "PASS"
    if block and status == "BLOCK":
        raise RenderPreflightError("render_input_preflight_blocked", issues=issues)
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}
