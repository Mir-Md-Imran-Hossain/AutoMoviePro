"""Creative quality contracts (BUILD-04F)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class QualityVerdict(str, Enum):
    PASS = "PASS"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    REGENERATE_REQUIRED = "REGENERATE_REQUIRED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class IssueSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RepairScope(str, Enum):
    SCRIPT = "SCRIPT"
    SCRIPT_SECTION = "SCRIPT_SECTION"
    DIALOGUE = "DIALOGUE"
    SCENE = "SCENE"
    VISUAL_PLAN = "VISUAL_PLAN"
    VISUAL_ASSET = "VISUAL_ASSET"
    AUDIO_PLAN = "AUDIO_PLAN"
    AUDIO_ASSET = "AUDIO_ASSET"
    SFX_ASSET = "SFX_ASSET"
    MUSIC_ASSET = "MUSIC_ASSET"
    AUDIO_MIX = "AUDIO_MIX"
    SUBTITLE = "SUBTITLE"
    LOCALIZATION = "LOCALIZATION"
    TEXT_LAYOUT = "TEXT_LAYOUT"
    TEXT_RENDER = "TEXT_RENDER"
    RENDER = "RENDER"
    FINAL_VIDEO = "FINAL_VIDEO"


class QualityDimension(str, Enum):
    CONTENT_RELEVANCE = "CONTENT_RELEVANCE"
    FACTUAL_COHERENCE = "FACTUAL_COHERENCE"
    SCRIPT_STRUCTURE = "SCRIPT_STRUCTURE"
    HOOK_STRENGTH = "HOOK_STRENGTH"
    RETENTION_STRUCTURE = "RETENTION_STRUCTURE"
    DIALOGUE_NATURALNESS = "DIALOGUE_NATURALNESS"
    SCENE_COHERENCE = "SCENE_COHERENCE"
    VISUAL_DIALOGUE_ALIGNMENT = "VISUAL_DIALOGUE_ALIGNMENT"
    VISUAL_QUALITY = "VISUAL_QUALITY"
    VISUAL_CONTINUITY = "VISUAL_CONTINUITY"
    AUDIO_QUALITY = "AUDIO_QUALITY"
    VOICE_CONSISTENCY = "VOICE_CONSISTENCY"
    EMOTION_ALIGNMENT = "EMOTION_ALIGNMENT"
    PACING = "PACING"
    SUBTITLE_ALIGNMENT = "SUBTITLE_ALIGNMENT"
    TIMING = "TIMING"
    TECHNICAL_MEDIA_QUALITY = "TECHNICAL_MEDIA_QUALITY"
    CROSS_MODAL_CONSISTENCY = "CROSS_MODAL_CONSISTENCY"
    FINAL_VIDEO_COHERENCE = "FINAL_VIDEO_COHERENCE"


@dataclass
class QualityIssue:
    issue_id: str
    stage: str
    severity: IssueSeverity
    category: str
    subject_id: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    repair_scope: RepairScope = RepairScope.SCENE
    recommended_action: str = "review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "stage": self.stage,
            "severity": self.severity.value,
            "category": self.category,
            "subject_id": self.subject_id,
            "description": self.description,
            "evidence": dict(self.evidence),
            "confidence": round(float(self.confidence), 4),
            "repair_scope": self.repair_scope.value,
            "recommended_action": self.recommended_action,
        }


@dataclass
class CreativeQualityResult:
    subject: str
    subject_id: str
    stage: str
    verdict: QualityVerdict
    score: float
    dimensions: dict[str, float] = field(default_factory=dict)
    issues: list[QualityIssue] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    repair_scope: Optional[RepairScope] = None
    recommended_action: str = ""
    evaluator_version: str = "1.0.0"
    rule_version: str = "1.0.0"
    artifact_fingerprint: str = ""
    revision_id: str = "r001"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict == QualityVerdict.PASS

    @property
    def publishable(self) -> bool:
        return self.verdict == QualityVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "subject_id": self.subject_id,
            "stage": self.stage,
            "verdict": self.verdict.value,
            "score": round(float(self.score), 4),
            "dimensions": {k: round(float(v), 4) for k, v in self.dimensions.items()},
            "issues": [i.to_dict() for i in self.issues],
            "evidence": dict(self.evidence),
            "confidence": round(float(self.confidence), 4),
            "repair_scope": self.repair_scope.value if self.repair_scope else "",
            "recommended_action": self.recommended_action,
            "evaluator_version": self.evaluator_version,
            "rule_version": self.rule_version,
            "artifact_fingerprint": self.artifact_fingerprint,
            "revision_id": self.revision_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CreativeQualityResult":
        issues = [
            QualityIssue(
                issue_id=str(i.get("issue_id") or ""),
                stage=str(i.get("stage") or ""),
                severity=IssueSeverity(str(i.get("severity") or "MEDIUM")),
                category=str(i.get("category") or ""),
                subject_id=str(i.get("subject_id") or ""),
                description=str(i.get("description") or ""),
                evidence=dict(i.get("evidence") or {}),
                confidence=float(i.get("confidence") or 1.0),
                repair_scope=RepairScope(str(i.get("repair_scope") or RepairScope.SCENE.value)),
                recommended_action=str(i.get("recommended_action") or "review"),
            )
            for i in (data.get("issues") or [])
        ]
        rs = data.get("repair_scope") or ""
        return cls(
            subject=str(data.get("subject") or ""),
            subject_id=str(data.get("subject_id") or ""),
            stage=str(data.get("stage") or ""),
            verdict=QualityVerdict(str(data.get("verdict") or QualityVerdict.UNKNOWN.value)),
            score=float(data.get("score") or 0.0),
            dimensions={str(k): float(v) for k, v in (data.get("dimensions") or {}).items()},
            issues=issues,
            evidence=dict(data.get("evidence") or {}),
            confidence=float(data.get("confidence") or 1.0),
            repair_scope=RepairScope(rs) if rs else None,
            recommended_action=str(data.get("recommended_action") or ""),
            evaluator_version=str(data.get("evaluator_version") or "1.0.0"),
            rule_version=str(data.get("rule_version") or "1.0.0"),
            artifact_fingerprint=str(data.get("artifact_fingerprint") or ""),
            revision_id=str(data.get("revision_id") or "r001"),
            metadata=dict(data.get("metadata") or {}),
        )


EVALUATOR_VERSION = "1.0.1"
RULE_VERSION = "1.0.1"
QUALITY_CONTRACT_VERSION = "1.0.0"
