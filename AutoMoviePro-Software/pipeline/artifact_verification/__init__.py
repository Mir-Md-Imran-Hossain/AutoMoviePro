"""Industrial artifact verification — Layer C/D/E observation (AMP-004 Phase-04).

Does NOT create a second quality score, repair, idempotency, or continuity engine.
Reuses existing visual/audio/subtitle/render validators + multimodal/visual_semantic.
"""
from __future__ import annotations

from pipeline.artifact_verification.contracts import (
    ArtifactObservation,
    ObservationMethod,
    ObservationStatus,
    VerificationTier,
    MediaType,
)
from pipeline.artifact_verification.production import (
    run_production_artifact_verification,
    load_artifact_gate,
)
from pipeline.artifact_verification.gate import (
    aggregate_artifact_gate,
    persist_artifact_gate,
    ARTIFACT_GATE_FILE,
)
from pipeline.artifact_verification.repair_bridge import (
    plan_artifact_repair,
    may_regenerate_artifact,
)

__all__ = [
    "ArtifactObservation",
    "ObservationMethod",
    "ObservationStatus",
    "VerificationTier",
    "MediaType",
    "run_production_artifact_verification",
    "load_artifact_gate",
    "aggregate_artifact_gate",
    "persist_artifact_gate",
    "ARTIFACT_GATE_FILE",
    "plan_artifact_repair",
    "may_regenerate_artifact",
]
