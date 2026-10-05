"""Fallback asset quality boundary (T004-C3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.scene_intent import SceneIntent
from pipeline.visual_semantic.boundary import run_visual_semantic_gate, validate_visual_complete
from pipeline.visual_semantic.contracts import SemanticValidationStatus, VisualAnalysisMetadata, VisualSemanticResult
from pipeline.visual_semantic.scene_intent import intent_fingerprint


@dataclass
class FallbackAssetRecord:
    asset_path: str
    fallback_reason: str
    source_provider: str  # image_fallback | agnes_failed | exception
    scene_id: str
    dialogue_id: str
    script_id: str = ""
    revision_id: str = ""
    intent_fingerprint: str = ""
    validation_status: str = ""
    is_agnes_success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_path": self.asset_path,
            "fallback_reason": self.fallback_reason,
            "source_provider": self.source_provider,
            "scene_id": self.scene_id,
            "dialogue_id": self.dialogue_id,
            "script_id": self.script_id,
            "revision_id": self.revision_id,
            "intent_fingerprint": self.intent_fingerprint,
            "validation_status": self.validation_status,
            "is_agnes_success": self.is_agnes_success,
            "metadata": dict(self.metadata),
        }


def validate_fallback_asset(
    record: FallbackAssetRecord,
    intent: SceneIntent,
    analysis: VisualAnalysisMetadata,
    *,
    mode: str = "video",
) -> VisualSemanticResult:
    """
    Fallback assets must NOT bypass semantic validation.
    Fallback SUCCESS ≠ Agnes SUCCESS (is_agnes_success must be False).
    """
    record.intent_fingerprint = intent_fingerprint(intent)
    record.is_agnes_success = False
    result = validate_visual_complete(
        record.asset_path,
        intent,
        analysis,
        mode=mode,
        request_dialogue_id=record.dialogue_id,
        strict=True,
    )
    record.validation_status = result.status.value
    record.metadata["semantic_issues"] = [i.to_dict() for i in result.issues if i.code.value != "HEURISTIC_ONLY"]
    return result


def fallback_semantic_allowed(record: FallbackAssetRecord, result: VisualSemanticResult) -> bool:
    """Explicit fallback may proceed only when not semantically blocked."""
    return result.status != SemanticValidationStatus.SEMANTIC_BLOCKED
