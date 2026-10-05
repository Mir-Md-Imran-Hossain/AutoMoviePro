"""Visual semantic consistency boundary (AMP-003 T004-C3)."""
from pipeline.visual_semantic.boundary import (
    SemanticValidationStatus,
    VisualSemanticResult,
    run_visual_semantic_gate,
    validate_visual_complete,
)
from pipeline.visual_semantic.continuity import ContinuityTracker, ContinuityConstraints, ContinuityError
from pipeline.visual_semantic.continuity_runtime import apply_production_continuity, prepare_scene_with_continuity
from pipeline.visual_semantic.fallback import FallbackAssetRecord, validate_fallback_asset
from pipeline.visual_semantic.scene_intent import build_scene_intent_from_dialogue

__all__ = [
    "SemanticValidationStatus",
    "VisualSemanticResult",
    "run_visual_semantic_gate",
    "validate_visual_complete",
    "ContinuityTracker",
    "ContinuityConstraints",
    "ContinuityError",
    "apply_production_continuity",
    "prepare_scene_with_continuity",
    "FallbackAssetRecord",
    "validate_fallback_asset",
    "build_scene_intent_from_dialogue",
]
