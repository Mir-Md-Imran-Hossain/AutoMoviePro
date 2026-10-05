"""Semantic validation contracts (T004-C3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SemanticValidationStatus(str, Enum):
    TECHNICAL_PASS = "TECHNICAL_PASS"
    SEMANTIC_PASS = "SEMANTIC_PASS"
    SEMANTIC_PARTIAL = "SEMANTIC_PARTIAL"
    SEMANTIC_BLOCKED = "SEMANTIC_BLOCKED"
    UNKNOWN = "UNKNOWN"


class SemanticIssueCode(str, Enum):
    UNEXPECTED_ACTION = "UNEXPECTED_ACTION"
    CONFLICTING_ACTION = "CONFLICTING_ACTION"
    MULTI_ACTION_OVERLOAD = "MULTI_ACTION_OVERLOAD"
    UNEXPECTED_OBJECT = "UNEXPECTED_OBJECT"
    FORBIDDEN_OBJECT = "FORBIDDEN_OBJECT"
    MISSING_REQUIRED_OBJECT = "MISSING_REQUIRED_OBJECT"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    POSTURE_MISMATCH = "POSTURE_MISMATCH"
    CONTINUITY_BREAK = "CONTINUITY_BREAK"
    DIALOGUE_IDENTITY_MISMATCH = "DIALOGUE_IDENTITY_MISMATCH"
    TEMPORAL_CONTRADICTION = "TEMPORAL_CONTRADICTION"
    TECHNICAL_INVALID = "TECHNICAL_INVALID"
    HEURISTIC_ONLY = "HEURISTIC_ONLY"
    REPEATED_PATTERN = "REPEATED_PATTERN"
    DIALOGUE_VISUAL_CONTRADICTION = "DIALOGUE_VISUAL_CONTRADICTION"


@dataclass
class SemanticIssue:
    code: SemanticIssueCode
    message: str
    severity: str = "HIGH"  # INFO | LOW | MEDIUM | HIGH | CRITICAL
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity,
            "evidence": dict(self.evidence),
        }


@dataclass
class VisualSemanticResult:
    status: SemanticValidationStatus
    technical_ok: bool
    semantic_ok: bool
    issues: list[SemanticIssue] = field(default_factory=list)
    heuristic_only: bool = False
    intent_fingerprint: str = ""
    dialogue_id: str = ""
    scene_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status in (
            SemanticValidationStatus.TECHNICAL_PASS,
            SemanticValidationStatus.SEMANTIC_PASS,
        )

    @property
    def blocked(self) -> bool:
        return self.status == SemanticValidationStatus.SEMANTIC_BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "technical_ok": self.technical_ok,
            "semantic_ok": self.semantic_ok,
            "issues": [i.to_dict() for i in self.issues],
            "heuristic_only": self.heuristic_only,
            "intent_fingerprint": self.intent_fingerprint,
            "dialogue_id": self.dialogue_id,
            "scene_id": self.scene_id,
            "metadata": dict(self.metadata),
        }


@dataclass
class VisualAnalysisMetadata:
    """
    Adapter boundary for visual semantic analysis.
    OFFLINE_TEST_ONLY fixtures or HEURISTIC prompt-derived metadata in production.
    """

    source: str = "HEURISTIC"  # HEURISTIC | OFFLINE_TEST_ONLY | VLM
    actions: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    location: str = ""
    posture: str = ""
    simultaneous_actions: bool = False
    description: str = ""
    dialogue_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "actions": list(self.actions),
            "objects": list(self.objects),
            "location": self.location,
            "posture": self.posture,
            "simultaneous_actions": self.simultaneous_actions,
            "description": self.description,
            "dialogue_id": self.dialogue_id,
        }
