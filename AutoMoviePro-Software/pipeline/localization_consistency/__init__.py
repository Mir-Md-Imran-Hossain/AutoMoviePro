"""Industrial localization / subtitle / text consistency (AMP-004 Phase-06).

Extends existing localization.py — does NOT create a second localization engine.
"""
from __future__ import annotations

from pipeline.localization_consistency.contract import (
    LocalizationContract,
    TextElement,
    TextPlan,
    build_localization_contract,
    localization_fingerprint,
)
from pipeline.localization_consistency.preflight import (
    LocalizationPreflightError,
    preflight_localization_request,
)
from pipeline.localization_consistency.drift import validate_translation_drift
from pipeline.localization_consistency.production import (
    apply_production_localization,
    run_production_localization_gate,
    validate_localized_pair,
)
from pipeline.localization_consistency.gate import LOCALIZATION_GATE_FILE, load_localization_gate

__all__ = [
    "LocalizationContract",
    "TextElement",
    "TextPlan",
    "build_localization_contract",
    "localization_fingerprint",
    "LocalizationPreflightError",
    "preflight_localization_request",
    "validate_translation_drift",
    "apply_production_localization",
    "run_production_localization_gate",
    "validate_localized_pair",
    "LOCALIZATION_GATE_FILE",
    "load_localization_gate",
]
