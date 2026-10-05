"""Quality gate bridge — production integration (BUILD-04F)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.quality.orchestrator import quality_gate_orchestrator
from pipeline.quality.publishability import evaluate_publishability, load_creative_gate

logger = logging.getLogger(__name__)

# Canonical production artifact written by video_pipeline.evaluate_job_semantic_gate
SEMANTIC_COVERAGE_GATE_NAME = "SEMANTIC_COVERAGE_GATE.json"
# Legacy/alias name (kept for older jobs + dual-write)
SEMANTIC_GATE_ALIAS_NAME = "SEMANTIC_GATE.json"


def load_semantic_certification_status(work_dir: Path) -> str:
    """
    RCP-06A: load semantic certification for publishability.

    Prefer SEMANTIC_COVERAGE_GATE.json (authoritative production write).
    Fall back to SEMANTIC_GATE.json alias. Missing → ABSENT (blocks publish).
    """
    work_dir = Path(work_dir)
    for name in (SEMANTIC_COVERAGE_GATE_NAME, SEMANTIC_GATE_ALIAS_NAME):
        sem_path = work_dir / name
        if not sem_path.is_file():
            continue
        try:
            sem = json.loads(sem_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("semantic gate unreadable: %s", sem_path.name)
            return "UNKNOWN"
        return str(sem.get("status") or sem.get("verdict") or "ABSENT").strip().upper() or "ABSENT"
    return "ABSENT"


def run_creative_quality_gate(
    work_dir: Path,
    *,
    job_id: str,
    plan: dict[str, Any],
    technical_ship: Optional[dict[str, Any]] = None,
    use_mock: bool = False,
    mock_evaluator=None,
) -> dict[str, Any]:
    """Canonical entry for creative quality evaluation."""
    return quality_gate_orchestrator(
        work_dir,
        job_id=job_id,
        plan=plan,
        technical_ship=technical_ship,
        use_mock=use_mock,
        mock_evaluator=mock_evaluator,
    )


def run_publishability_gate(
    work_dir: Path,
    *,
    technical_ship: Optional[dict[str, Any]] = None,
    multimodal_status: Optional[str] = None,
    multimodal_meta: Optional[dict[str, Any]] = None,
    artifact_status: Optional[str] = None,
    render_status: Optional[str] = None,
    semantic_status: Optional[str] = None,
    duration_status: Optional[str] = None,
    require_artifact_gate: bool = False,
    audio_status: Optional[str] = None,
    require_audio_design_gate: bool = False,
    localization_status: Optional[str] = None,
    require_localization_gate: bool = False,
    creative_production_status: Optional[str] = None,
    require_creative_production_gate: bool = False,
    rendering_integrity_status: Optional[str] = None,
    require_rendering_integrity_gate: bool = False,
    require_duration_gate: bool = False,
    asr_evidence_status: Optional[str] = None,
    scene_boundary_status: Optional[str] = None,
    audience_status: Optional[str] = None,
) -> dict[str, Any]:
    """
    Production publishability AND gate (AMP-004 Phase-02 + Phase-04 + Phase-05 + Gate A duration).
    Loads MULTIMODAL_QUALITY_GATE.json when multimodal_status not explicit.
    Hard BLOCKED / mandatory UNKNOWN cannot be averaged into PASS.

    require_artifact_gate=True (production after artifact verification):
    missing ARTIFACT_GATE → UNKNOWN (unverified final) → not publishable.

    require_audio_design_gate=True: missing AUDIO_DESIGN_GATE → UNKNOWN.
    require_duration_gate=True (production generate_video): missing/FAIL/UNKNOWN
    DURATION_RECONCILIATION → not publishable.
    ASR evidence FAIL blocks; ASR UNKNOWN never counts as dialogue PASS.
    Scene-boundary FAIL and audience FAIL block when statuses supplied/loaded.
    """
    work_dir = Path(work_dir)
    ship_path = work_dir / "MASTER_SHIP_GATE.json"
    ship = technical_ship
    if ship is None and ship_path.is_file():
        try:
            ship = json.loads(ship_path.read_text(encoding="utf-8"))
        except Exception:
            ship = {}
    technical_pass = bool(ship and ship.get("ok") and not ship.get("unshippable"))
    # Render dimension: ship failure already sets technical_pass False; explicit status optional
    if render_status is None and ship is not None:
        render_status = "PASS" if technical_pass else "BLOCKED"

    creative = load_creative_gate(work_dir)
    if creative is None:
        report_path = work_dir / "quality_report.json"
        if report_path.is_file():
            try:
                creative = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                creative = {}

    mm_meta = dict(multimodal_meta or {})
    mm_status = multimodal_status
    if mm_status is None:
        from pipeline.quality.multimodal_aggregate import load_multimodal_gate

        mm_gate = load_multimodal_gate(work_dir)
        if mm_gate:
            mm_status = str(mm_gate.get("status") or "ABSENT")
            mm_meta = dict(mm_gate)

    # Artifact gate (AMP-004 Phase-04): load ARTIFACT_GATE.json; optional require
    if artifact_status is None:
        art_path = work_dir / "ARTIFACT_GATE.json"
        if art_path.is_file():
            try:
                art = json.loads(art_path.read_text(encoding="utf-8"))
                artifact_status = str(art.get("status") or art.get("verdict") or "ABSENT")
            except Exception:
                if require_artifact_gate:
                    artifact_status = "UNKNOWN"
        elif require_artifact_gate:
            artifact_status = "UNKNOWN"

    if semantic_status is None:
        # RCP-06A: prefer SEMANTIC_COVERAGE_GATE (production writer), alias SEMANTIC_GATE.
        semantic_status = load_semantic_certification_status(work_dir)

    # Gate A: duration reconciliation (duration_budget authority)
    if duration_status is None:
        from pipeline.duration_budget import load_duration_reconciliation

        dur = load_duration_reconciliation(work_dir)
        if dur:
            duration_status = str(dur.get("status") or "UNKNOWN").upper()
        elif require_duration_gate:
            duration_status = "ABSENT"

    # Audio design gate (AMP-004 Phase-05)
    if audio_status is None:
        from pipeline.audio_design.gate import load_audio_design_gate

        aud = load_audio_design_gate(work_dir)
        if aud:
            audio_status = str(aud.get("status") or aud.get("verdict") or "ABSENT")
        elif require_audio_design_gate:
            audio_status = "UNKNOWN"

    # Localization gate (AMP-004 Phase-06)
    if localization_status is None:
        from pipeline.localization_consistency.gate import load_localization_gate

        loc = load_localization_gate(work_dir)
        if loc:
            localization_status = str(loc.get("status") or loc.get("verdict") or "ABSENT")
        elif require_localization_gate:
            localization_status = "UNKNOWN"

    # Creative production gate (AMP-004 Phase-07)
    if creative_production_status is None:
        from pipeline.creative_production.gate import load_creative_production_gate

        cr = load_creative_production_gate(work_dir)
        if cr:
            creative_production_status = str(cr.get("status") or cr.get("verdict") or "ABSENT")
        elif require_creative_production_gate:
            creative_production_status = "UNKNOWN"

    # Rendering integrity gate (AMP-004 Phase-08)
    if rendering_integrity_status is None:
        from pipeline.rendering_integrity.gate import load_rendering_integrity_gate

        ri = load_rendering_integrity_gate(work_dir)
        if ri:
            rendering_integrity_status = str(ri.get("status") or ri.get("verdict") or "ABSENT")
        elif require_rendering_integrity_gate:
            rendering_integrity_status = "UNKNOWN"

    # Phase 6H ASR evidence (faster-whisper) — FAIL blocks; UNKNOWN ≠ PASS
    if asr_evidence_status is None:
        from pipeline.observation.audio_evidence.production import load_audio_asr_gate_status

        asr_evidence_status = load_audio_asr_gate_status(work_dir)

    if scene_boundary_status is None:
        sb_path = work_dir / "SCENE_BOUNDARY_OBSERVATION_GATE.json"
        if sb_path.is_file():
            try:
                sb = json.loads(sb_path.read_text(encoding="utf-8"))
                scene_boundary_status = str(sb.get("status") or "UNKNOWN")
            except Exception:
                scene_boundary_status = "UNKNOWN"

    if audience_status is None:
        aq_path = work_dir / "AUDIENCE_QUALITY_GATE.json"
        if aq_path.is_file():
            try:
                aq = json.loads(aq_path.read_text(encoding="utf-8"))
                audience_status = str(aq.get("status") or aq.get("verdict") or "ABSENT")
            except Exception:
                audience_status = "UNKNOWN"

    pub = evaluate_publishability(
        technical_pass=technical_pass,
        creative_report=creative,
        multimodal_status=mm_status,
        multimodal_meta=mm_meta,
        artifact_status=artifact_status,
        render_status=render_status,
        semantic_status=semantic_status,
        duration_status=duration_status,
        audio_status=audio_status,
        localization_status=localization_status,
        creative_production_status=creative_production_status,
        rendering_integrity_status=rendering_integrity_status,
        asr_evidence_status=asr_evidence_status,
        scene_boundary_status=scene_boundary_status,
        audience_status=audience_status,
    )
    out = work_dir / "PUBLISHABILITY_GATE.json"
    out.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
    return pub
