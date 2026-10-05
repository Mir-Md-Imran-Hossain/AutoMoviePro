"""Semantic observation boundary — honesty rules (AMP-004 Phase-04).

Uses existing multimodal_consistency / visual_semantic.
Does NOT create another semantic engine.
Does NOT convert UNKNOWN → PASS from prompt/metadata alone.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from pipeline.artifact_verification.contracts import (
    ObservationMethod,
    ObservationStatus,
    VerificationTier,
)


def classify_semantic_observation(
    *,
    expected: Optional[dict[str, Any]] = None,
    observed_labels: Optional[Sequence[str]] = None,
    contradiction_issues: Optional[Sequence[Any]] = None,
    has_pixel_or_asr_evidence: bool = False,
) -> dict[str, Any]:
    """
    Returns semantic observation result.

    Prompt/metadata expectation alone → UNKNOWN (never PASS).
    Explicit contradiction evidence → FAIL.
    Matching observed labels with real evidence → PASS (heuristic/L3 only if labeled).
    """
    expected = expected or {}
    issues = list(contradiction_issues or [])

    if issues:
        # Filter CRITICAL / known contradiction codes
        blocking = []
        for i in issues:
            if isinstance(i, dict):
                sev = str(i.get("severity") or "").upper()
                msg = str(i.get("message") or i.get("code") or "")
                if sev in ("CRITICAL", "HIGH") or "contradict" in msg.lower() or "mismatch" in msg.lower():
                    blocking.append(i)
            else:
                sev = getattr(i, "severity", "")
                msg = getattr(i, "message", str(i))
                if str(sev).upper() in ("CRITICAL", "HIGH") or "contradict" in str(msg).lower():
                    blocking.append(i)
        if blocking:
            return {
                "semantic_status": ObservationStatus.FAIL.value,
                "observation_method": ObservationMethod.HEURISTIC.value,
                "verification_tier": VerificationTier.L3.value,
                "confidence_label": "HEURISTIC",
                "issues": [str(getattr(b, "message", b)) for b in blocking],
                "claim": "semantic_contradiction",
            }

    if not has_pixel_or_asr_evidence and not observed_labels:
        # Expected smartphone in prompt is NOT proof
        return {
            "semantic_status": ObservationStatus.UNKNOWN.value,
            "observation_method": ObservationMethod.UNAVAILABLE.value,
            "verification_tier": VerificationTier.L3.value,
            "confidence_label": "NO_VISUAL_OBSERVATION",
            "issues": ["semantic_observation_unavailable"],
            "claim": "unknown_not_pass",
            "expected": expected,
        }

    if observed_labels is not None and expected:
        exp_objs = [str(x).lower() for x in (expected.get("objects") or expected.get("required_objects") or [])]
        obs = [str(x).lower() for x in observed_labels]
        missing = [o for o in exp_objs if o and not any(o in x or x in o for x in obs)]
        if missing and has_pixel_or_asr_evidence:
            return {
                "semantic_status": ObservationStatus.FAIL.value,
                "observation_method": ObservationMethod.HEURISTIC.value,
                "verification_tier": VerificationTier.L3.value,
                "confidence_label": "HEURISTIC",
                "issues": [f"entity_or_object_mismatch:{m}" for m in missing],
                "claim": "observed_mismatch",
            }
        if has_pixel_or_asr_evidence:
            return {
                "semantic_status": ObservationStatus.PASS.value,
                "observation_method": ObservationMethod.HEURISTIC.value,
                "verification_tier": VerificationTier.L3.value,
                "confidence_label": "HEURISTIC",
                "issues": [],
                "claim": "heuristic_match",
            }

    return {
        "semantic_status": ObservationStatus.UNKNOWN.value,
        "observation_method": ObservationMethod.UNAVAILABLE.value,
        "verification_tier": VerificationTier.L3.value,
        "confidence_label": "NO_VISUAL_OBSERVATION",
        "issues": ["semantic_observation_unavailable"],
        "claim": "unknown_not_pass",
    }


def technical_pass_is_not_semantic_pass(technical_status: str, semantic_status: str) -> bool:
    """Invariant: technical PASS must not be treated as semantic PASS."""
    return not (
        str(technical_status).upper() == "PASS" and str(semantic_status).upper() == "PASS"
        and technical_status == semantic_status  # trivial
    ) or str(semantic_status).upper() != "PASS"
