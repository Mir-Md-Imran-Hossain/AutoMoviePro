"""Industrial validation status layers (T004-C3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationLayer(str, Enum):
    TECHNICAL = "TECHNICAL_VALIDATION"
    SEMANTIC = "SEMANTIC_VALIDATION"
    CROSS_MODAL = "CROSS_MODAL_VALIDATION"
    CONTINUITY = "CONTINUITY_VALIDATION"
    LOCALIZATION = "LOCALIZATION_VALIDATION"
    PROMPT = "PROMPT_VALIDATION"


class LayerStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    VERIFIED = "VERIFIED"  # provider-verified (future)


class ConfidenceLevel(str, Enum):
    HEURISTIC = "HEURISTIC"
    OFFLINE_TEST_ONLY = "OFFLINE_TEST_ONLY"
    PROVIDER_VERIFIED = "PROVIDER_VERIFIED"


@dataclass
class LayerResult:
    layer: ValidationLayer
    status: LayerStatus
    confidence: ConfidenceLevel = ConfidenceLevel.HEURISTIC
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.value,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "issues": list(self.issues),
        }


@dataclass
class IndustrialValidationReport:
    scene_id: str
    dialogue_id: str
    revision_id: str = ""
    intent_fingerprint: str = ""
    layers: list[LayerResult] = field(default_factory=list)
    final_status: LayerStatus = LayerStatus.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.final_status == LayerStatus.BLOCKED

    @property
    def passed(self) -> bool:
        return self.final_status in (LayerStatus.PASS, LayerStatus.VERIFIED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "dialogue_id": self.dialogue_id,
            "revision_id": self.revision_id,
            "intent_fingerprint": self.intent_fingerprint,
            "layers": [l.to_dict() for l in self.layers],
            "final_status": self.final_status.value,
            "metadata": dict(self.metadata),
        }


def aggregate_final_status(layers: list[LayerResult]) -> LayerStatus:
    if any(l.status == LayerStatus.BLOCKED for l in layers):
        return LayerStatus.BLOCKED
    if any(l.status == LayerStatus.UNKNOWN for l in layers):
        return LayerStatus.UNKNOWN
    if any(l.status == LayerStatus.PARTIAL for l in layers):
        return LayerStatus.PARTIAL
    return LayerStatus.PASS
