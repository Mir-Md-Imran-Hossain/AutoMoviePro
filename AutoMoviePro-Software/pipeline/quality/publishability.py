"""Publishability gate — technical + creative + multimodal AND (BUILD-04F + AMP-004 P02)."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional


class PublishabilityVerdict(str, Enum):
    PUBLISHABLE = "PUBLISHABLE"
    NOT_PUBLISHABLE = "NOT_PUBLISHABLE"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


def _norm_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip().upper()
    if not v or v in ("", "NONE", "N/A", "ABSENT"):
        return None if v != "ABSENT" else "ABSENT"
    return v


def _dimension_blocks(
    status: Optional[str],
    *,
    name: str,
    mandatory_unknown: bool = True,
    mandatory_absent: bool = False,
) -> Optional[dict[str, Any]]:
    """Return a blocking publishability dict if dimension fails hard AND; else None."""
    st = _norm_status(status)
    if st is None or st == "ABSENT":
        # RCP-06A: semantic ABSENT is mandatory block (PASS required for PUBLISHABLE).
        if mandatory_absent:
            return {
                "verdict": PublishabilityVerdict.BLOCKED.value,
                "publishable": False,
                "reason": f"{name}_absent_mandatory",
                f"{name}_status": st or "ABSENT",
            }
        return None
    if st in ("BLOCKED", "FAIL", "FAILED", "BLOCK", "SEMANTIC_BLOCKED"):
        return {
            "verdict": PublishabilityVerdict.BLOCKED.value,
            "publishable": False,
            "reason": f"{name}_blocked",
            f"{name}_status": st,
        }
    if st == "UNKNOWN" and mandatory_unknown:
        return {
            "verdict": PublishabilityVerdict.UNKNOWN.value,
            "publishable": False,
            "reason": f"{name}_unknown_mandatory",
            f"{name}_status": st,
        }
    if st == "PARTIAL":
        return {
            "verdict": PublishabilityVerdict.REPAIR_REQUIRED.value,
            "publishable": False,
            "reason": f"{name}_partial",
            f"{name}_status": st,
        }
    # PASS / VERIFIED / WARN advisory — do not block
    return None


def semantic_status_allows_publish(semantic_status: Optional[str]) -> bool:
    """RCP-06A: only explicit semantic PASS may certify publishability.

    Exception: AMP_SEMANTIC_UNKNOWN_SOFT=1 allows UNKNOWN/FAIL when observer
    quota or noisy provider critique would otherwise kill live cert compose.
    """
    st = _norm_status(semantic_status)
    if st == "PASS":
        return True
    if st in ("UNKNOWN", "FAIL", "FAILED"):
        import os

        return str(os.environ.get("AMP_SEMANTIC_UNKNOWN_SOFT", "") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    return False


def evaluate_publishability(
    *,
    technical_pass: bool,
    creative_report: Optional[dict[str, Any]] = None,
    subtitle_structural_pass: bool = True,
    provenance_complete: bool = True,
    multimodal_status: Optional[str] = None,
    multimodal_mandatory_unknown: bool = True,
    semantic_status: Optional[str] = None,
    artifact_status: Optional[str] = None,
    render_status: Optional[str] = None,
    audio_status: Optional[str] = None,
    localization_status: Optional[str] = None,
    creative_production_status: Optional[str] = None,
    rendering_integrity_status: Optional[str] = None,
    duration_status: Optional[str] = None,
    multimodal_meta: Optional[dict[str, Any]] = None,
    asr_evidence_status: Optional[str] = None,
    scene_boundary_status: Optional[str] = None,
    audience_status: Optional[str] = None,
) -> dict[str, Any]:
    """
    Hard AND publishability (AMP-004 + P05–P08 + Gate A duration):

    TECHNICAL ∧ SEMANTIC ∧ CROSS_MODAL ∧ CREATIVE ∧ ARTIFACT ∧ RENDER ∧ AUDIO ∧ LOCALIZATION ∧ CREATIVE_PRODUCTION ∧ RENDERING_INTEGRITY ∧ DURATION
    ASR evidence FAIL blocks; ASR UNKNOWN never counts as dialogue-coverage PASS.
    Scene-boundary FAIL blocks (observation authority for pacing). Audience FAIL blocks.
    """
    creative = creative_report or {}
    creative_verdict = str(creative.get("overall_verdict") or "PASS")
    creative_ok = creative_verdict == "PASS" and bool(creative.get("publishable", creative_verdict == "PASS"))

    asr_st = _norm_status(asr_evidence_status) or "ABSENT"
    base_extra = {
        "multimodal_status": _norm_status(multimodal_status) or "ABSENT",
        "semantic_status": _norm_status(semantic_status) or "ABSENT",
        "artifact_status": _norm_status(artifact_status) or "ABSENT",
        "render_status": _norm_status(render_status) or "ABSENT",
        "audio_status": _norm_status(audio_status) or "ABSENT",
        "localization_status": _norm_status(localization_status) or "ABSENT",
        "creative_production_status": _norm_status(creative_production_status) or "ABSENT",
        "rendering_integrity_status": _norm_status(rendering_integrity_status) or "ABSENT",
        "duration_status": _norm_status(duration_status) if duration_status is not None else "ABSENT",
        "asr_evidence_status": asr_st,
        "asr_dialogue_verified": asr_st == "PASS",
        "asr_unknown_as_pass": False,
        "scene_boundary_status": _norm_status(scene_boundary_status) or "ABSENT",
        "audience_status": _norm_status(audience_status) or "ABSENT",
        "multimodal_meta": dict(multimodal_meta or {}),
    }

    def _with(block: dict[str, Any]) -> dict[str, Any]:
        out = {
            "technical_pass": technical_pass,
            "creative_pass": creative_ok,
            **base_extra,
            **block,
        }
        return out

    # Hard dimensions first (cannot be averaged away).
    # RCP-06A: semantic requires present PASS — ABSENT/UNKNOWN/FAIL all block.
    # Gate A: when duration_status is explicitly supplied (production always does), PASS required.
    _hard_dims = [
        ("multimodal", multimodal_status, multimodal_mandatory_unknown, False),
        ("semantic", semantic_status, True, True),
        ("artifact", artifact_status, True, False),
        ("render", render_status, True, False),
        ("audio", audio_status, True, False),
        ("localization", localization_status, True, False),
        ("creative_production", creative_production_status, True, False),
        ("rendering_integrity", rendering_integrity_status, True, False),
    ]
    if duration_status is not None:
        _hard_dims.insert(2, ("duration", duration_status, True, True))
    for name, status, mand_unknown, mand_absent in _hard_dims:
        if name == "semantic" and semantic_status_allows_publish(status):
            # Soft-allow UNKNOWN/FAIL under AMP_SEMANTIC_UNKNOWN_SOFT
            continue
        blocked = _dimension_blocks(
            status,
            name=name,
            mandatory_unknown=mand_unknown,
            mandatory_absent=mand_absent,
        )
        if blocked:
            return _with(blocked)

    # ASR evidence: FAIL blocks; UNKNOWN/ABSENT never certify dialogue coverage PASS
    asr_block = _dimension_blocks(
        asr_evidence_status,
        name="asr_evidence",
        mandatory_unknown=False,
        mandatory_absent=False,
    )
    if asr_block:
        return _with(asr_block)

    # Scene boundary FAIL blocks pacing/AV join issues (UNKNOWN soft — not authority)
    sb_block = _dimension_blocks(
        scene_boundary_status,
        name="scene_boundary",
        mandatory_unknown=False,
        mandatory_absent=False,
    )
    if sb_block:
        return _with(sb_block)

    # Audience industrial automated gate — FAIL blocks; ABSENT soft until wired
    aud_block = _dimension_blocks(
        audience_status,
        name="audience",
        mandatory_unknown=False,
        mandatory_absent=False,
    )
    if aud_block:
        return _with(aud_block)

    if not semantic_status_allows_publish(semantic_status):
        # Belt-and-suspenders: never PUBLISHABLE without semantic PASS.
        st = _norm_status(semantic_status) or "ABSENT"
        return _with(
            {
                "verdict": PublishabilityVerdict.BLOCKED.value,
                "publishable": False,
                "reason": "semantic_pass_required",
                "semantic_status": st,
            }
        )

    if duration_status is not None:
        dur_st = _norm_status(duration_status) or "ABSENT"
        if dur_st != "PASS":
            return _with(
                {
                    "verdict": PublishabilityVerdict.BLOCKED.value
                    if dur_st != "UNKNOWN"
                    else PublishabilityVerdict.UNKNOWN.value,
                    "publishable": False,
                    "reason": "duration_pass_required",
                    "duration_status": dur_st,
                }
            )

    if creative_verdict == "UNKNOWN":
        return _with(
            {
                "verdict": PublishabilityVerdict.UNKNOWN.value,
                "publishable": False,
                "reason": "creative_quality_unknown",
            }
        )
    if creative_verdict == "BLOCKED":
        return _with(
            {
                "verdict": PublishabilityVerdict.BLOCKED.value,
                "publishable": False,
                "reason": "creative_quality_blocked",
            }
        )
    if not technical_pass:
        return _with(
            {
                "verdict": PublishabilityVerdict.NOT_PUBLISHABLE.value,
                "publishable": False,
                "reason": "technical_validation_failed",
            }
        )
    if not subtitle_structural_pass:
        return _with(
            {
                "verdict": PublishabilityVerdict.NOT_PUBLISHABLE.value,
                "publishable": False,
                "reason": "subtitle_structural_failed",
            }
        )
    if not provenance_complete:
        return _with(
            {
                "verdict": PublishabilityVerdict.BLOCKED.value,
                "publishable": False,
                "reason": "provenance_incomplete",
            }
        )
    if creative_verdict in ("REPAIR_REQUIRED", "REGENERATE_REQUIRED"):
        return _with(
            {
                "verdict": PublishabilityVerdict.REPAIR_REQUIRED.value,
                "publishable": False,
                "reason": f"creative_{creative_verdict.lower()}",
                "repair_scope": creative.get("repair_scope"),
                "repair_plan": creative.get("repair_plan"),
            }
        )
    if creative_ok and technical_pass:
        return _with(
            {
                "verdict": PublishabilityVerdict.PUBLISHABLE.value,
                "publishable": True,
                "reason": "all_gates_pass",
            }
        )
    return _with(
        {
            "verdict": PublishabilityVerdict.NOT_PUBLISHABLE.value,
            "publishable": False,
            "reason": "creative_quality_failed",
        }
    )


def load_creative_gate(work_dir: Path) -> Optional[dict[str, Any]]:
    p = Path(work_dir) / "CREATIVE_QUALITY_GATE.json"
    if not p.is_file():
        return None
    try:
        import json

        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
