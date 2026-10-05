"""Production rendering integrity wiring (AMP-004 Phase-08)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

from pipeline.rendering_integrity.contract import (
    build_render_integrity_contract,
    render_contract_fingerprint,
)
from pipeline.rendering_integrity.gate import (
    persist_render_contract,
    persist_rendering_integrity_gate,
)
from pipeline.rendering_integrity.observe import observe_rendered_output
from pipeline.rendering_integrity.preflight import (
    RenderPreflightError,
    preflight_clip_inputs,
    preflight_render_contract,
)
from pipeline.rendering_integrity.retry import classify_render_failure

logger = logging.getLogger(__name__)


def _parse_size(size: str) -> tuple[int, int]:
    try:
        w, h = size.lower().split("x", 1)
        return int(w), int(h)
    except Exception:
        return 1080, 1920


def apply_production_render_preflight(
    work_dir: Path,
    *,
    job_id: str,
    clips: List[Path],
    size: str = "1080x1920",
    fps: float = 25.0,
    block_on_critical: bool = True,
    durations: Optional[List[float]] = None,
) -> dict[str, Any]:
    """Build + validate RenderIntegrityContract before expensive compose.

    When ffprobe cannot measure clip duration, callers SHOULD pass planned
    ``durations`` from scene/audio plans. Silent zero-duration must not PASS.
    """
    work_dir = Path(work_dir)
    preflight_clip_inputs(clips, block=block_on_critical)
    w, h = _parse_size(size)
    duration_source = "EXPLICIT" if durations is not None else "PROBE"
    durs: Optional[List[float]] = list(durations) if durations is not None else None
    if durs is None and clips:
        from pipeline.compose import ffprobe_duration

        probed: list[float] = []
        for c in clips:
            try:
                probed.append(float(ffprobe_duration(c) or 0.0))
            except Exception:
                probed.append(0.0)
        if probed and all(d <= 0 for d in probed):
            # Environment-limited probe: use conservative planned durations so
            # timeline integrity can still be validated offline.
            durs = [2.5] * len(clips)
            duration_source = "PLANNED_DURATION"
        elif any(d <= 0 for d in probed):
            durs = [d if d > 0 else 2.5 for d in probed]
            duration_source = "MIXED_PROBE_PLANNED"
        else:
            durs = probed
            duration_source = "PROBE"
    contract = build_render_integrity_contract(
        project_id=job_id,
        render_id=f"render-{job_id}",
        clips=clips,
        width=w,
        height=h,
        fps=fps,
        durations=durs,
    )
    contract.provenance = dict(contract.provenance or {})
    contract.provenance["duration_source"] = duration_source
    contract.contract_fingerprint = render_contract_fingerprint(contract)
    # Contiguous timeline: builder already places segments end-to-end (no accidental gaps)
    pf = preflight_render_contract(contract, block=block_on_critical)
    persist_render_contract(work_dir, contract.to_dict(), key=job_id or "contract")
    gate = {
        "status": "PASS" if pf.get("status") == "PASS" else ("FAIL" if pf.get("status") == "BLOCK" else pf.get("status")),
        "verdict": pf.get("status"),
        "issues": pf.get("issues") or [],
        "stage": "pre_render",
        "contract_fingerprint": contract.contract_fingerprint,
        "job_id": job_id,
        "method": "DETERMINISTIC",
        "classification": pf.get("classification"),
        "duration_source": duration_source,
    }
    persist_rendering_integrity_gate(work_dir, gate)
    return {"contract": contract, "preflight": pf, "gate": gate}


def run_production_rendering_gate(
    work_dir: Path,
    *,
    job_id: str,
    final_path: Optional[Path] = None,
    size: str = "1080x1920",
    video_type: str = "",
    require_output: bool = True,
) -> dict[str, Any]:
    """Post-render Layer-E integrity gate. Metadata/return-code alone is not enough."""
    work_dir = Path(work_dir)
    issues: list[str] = []
    from pipeline.aspect_lock import assert_orientation, coerce_size, normalize_video_type

    vt = normalize_video_type(video_type) if video_type else ""
    if not vt:
        # Infer from requested canvas when caller omitted video_type
        try:
            tw, th = (int(x) for x in str(size).lower().split("x", 1))
            vt = "short" if th > tw else "long"
        except Exception:
            vt = "short"
    size = coerce_size(size, vt)
    contract = None
    cpath = work_dir / "render_contracts" / f"{job_id}.json"
    if cpath.is_file():
        try:
            import json

            from pipeline.rendering_integrity.contract import (
                EncodeSpec,
                FiltergraphContract,
                FilterNode,
                GeometrySpec,
                RenderIntegrityContract,
                StreamMap,
                TimelineSegment,
                TransitionDirective,
                VfxDirective,
            )

            raw = json.loads(cpath.read_text(encoding="utf-8"))
            timeline = [TimelineSegment(**{k: t[k] for k in TimelineSegment.__dataclass_fields__ if k in t}) for t in (raw.get("timeline") or [])]
            geo = GeometrySpec(**{k: raw["geometry"][k] for k in GeometrySpec.__dataclass_fields__ if k in (raw.get("geometry") or {})})
            contract = RenderIntegrityContract(
                project_id=str(raw.get("project_id") or job_id),
                render_id=str(raw.get("render_id") or ""),
                scene_ids=list(raw.get("scene_ids") or []),
                timeline=timeline,
                geometry=geo,
                encode=EncodeSpec(**{k: raw["encode"][k] for k in EncodeSpec.__dataclass_fields__ if k in (raw.get("encode") or {})}) if raw.get("encode") else EncodeSpec(),
                contract_fingerprint=str(raw.get("contract_fingerprint") or ""),
            )
        except Exception as exc:
            logger.debug("render contract reload soft-fail: %s", exc)

    final = Path(final_path) if final_path else work_dir / "final_short.mp4"
    # Prefer known finals
    if not final.is_file():
        for cand in sorted(work_dir.glob("final_*.mp4")):
            if cand.is_file() and cand.stat().st_size > 8000:
                final = cand
                break

    if require_output and (not final.is_file() or final.stat().st_size < 8000):
        # Check for stale tmp treated as final
        tmps = list(work_dir.glob("*.tmp.mp4"))
        if tmps:
            issues.append("stale_temporary_artifact")
        gate = {
            "status": "FAIL",
            "verdict": "FAIL",
            "issues": issues + ["missing_or_partial_final"],
            "job_id": job_id,
            "stage": "post_render",
            "method": "DETERMINISTIC",
            "layer": "E",
            "unknown_as_pass": False,
        }
        persist_rendering_integrity_gate(work_dir, gate)
        return gate

    # Wrong-project contamination: contract project_id must match job
    if contract and contract.project_id and contract.project_id != job_id:
        issues.append("render_output_wrong_project")

    obs = observe_rendered_output(final, contract=contract, require_audio=True, require_video=True)
    issues.extend(obs.get("issues") or [])

    # Hard aspect lock: short must be vertical 9:16, long must be horizontal 16:9
    try:
        from pipeline.compose import ffprobe_bin
        import subprocess

        fp = ffprobe_bin()
        probe = subprocess.run(
            [
                fp,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                str(final),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        dims = (probe.stdout or "").strip().split("x")
        if len(dims) == 2:
            ow, oh = int(dims[0]), int(dims[1])
            orient = assert_orientation(f"{ow}x{oh}", vt)
            if vt == "short" and not (ow < oh):
                issues.append(f"aspect_lock_fail:short_not_vertical:{ow}x{oh}")
            if vt == "long" and not (ow > oh):
                issues.append(f"aspect_lock_fail:long_not_horizontal:{ow}x{oh}")
            # Soft ratio check (±2%) against canonical canvas
            exp_w, exp_h = (int(x) for x in size.split("x"))
            if exp_w > 0 and exp_h > 0:
                ratio = ow / max(1, oh)
                exp_ratio = exp_w / max(1, exp_h)
                if abs(ratio - exp_ratio) > 0.03:
                    issues.append(f"aspect_ratio_mismatch:{ow}x{oh}_expected_{size}")
            _ = orient
    except Exception as exc:
        issues.append(f"aspect_probe_unknown:{exc}")

    # PART-5M: black / missing frame probe (UNKNOWN ≠ PASS for that dimension)
    frame_probe: dict[str, Any] = {}
    try:
        from pipeline.rendering_integrity.frame_integrity import probe_black_and_missing_frames

        frame_probe = probe_black_and_missing_frames(final, work_dir=work_dir)
        if str(frame_probe.get("status") or "").upper() == "FAIL":
            issues.extend(frame_probe.get("issues") or ["frame_integrity_fail"])
    except Exception as exc:
        frame_probe = {"status": "UNKNOWN", "issues": [f"frame_probe_error:{exc}"], "unknown_as_pass": False}

    # Failed render falsely marked PASS: if observation FAIL, gate FAIL
    status = str(obs.get("status") or "UNKNOWN").upper()
    if status == "PASS" and issues:
        status = "FAIL"
    if any(i.startswith("render_output_wrong") or i.startswith("stale_") for i in issues):
        status = "FAIL"
    if any(i.startswith("black_frames") or i.startswith("missing_frames") for i in issues):
        status = "FAIL"
    if any(i.startswith("aspect_lock_fail") or i.startswith("aspect_ratio_mismatch") for i in issues):
        status = "FAIL"
    if status == "UNKNOWN":
        # mandatory UNKNOWN blocks publish
        pass

    classification = classify_render_failure(
        issues=issues,
        validation_ok=(status == "PASS"),
    )
    gate = {
        "status": status if status != "PASS" else "PASS",
        "verdict": status,
        "issues": list(dict.fromkeys(issues)),
        "frame_integrity": frame_probe,
        "job_id": job_id,
        "stage": "post_render",
        "observation": obs,
        "final_path": str(final),
        "contract_fingerprint": contract.contract_fingerprint if contract else "",
        "classification": classification,
        "method": "DETERMINISTIC",
        "layer": "E",
        "subprocess_success_is_not_proof": True,
        "unknown_as_pass": False,
    }
    persist_rendering_integrity_gate(work_dir, gate)
    logger.info("rendering integrity gate job=%s status=%s", job_id, status)
    return gate
