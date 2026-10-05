"""Multimodal consistency + prompt grounding boundary (AMP-003 T004-C3).

Evidence projection is imported lazily to avoid circular imports with
production_consistency → multimodal_consistency → story_visual_direction.
"""
from pipeline.multimodal_consistency.boundary import multimodal_gate_for_spec, run_multimodal_consistency_gate
from pipeline.multimodal_consistency.industrial_status import IndustrialValidationReport
from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt
from pipeline.multimodal_consistency.quality_bridge import multimodal_report_to_quality, plan_multimodal_repair

__all__ = [
    "run_multimodal_consistency_gate",
    "multimodal_gate_for_spec",
    "IndustrialValidationReport",
    "compile_provider_prompt",
    "multimodal_report_to_quality",
    "plan_multimodal_repair",
    "project_beat_evidence",
    "fuse_production_evidence",
    "attach_evidence_projection_to_semantic_report",
    "repair_handoff_from_evidence_projection",
]


def __getattr__(name: str):
    if name in {
        "project_beat_evidence",
        "fuse_production_evidence",
        "attach_evidence_projection_to_semantic_report",
        "repair_handoff_from_evidence_projection",
    }:
        from pipeline.multimodal_consistency import evidence_projection as _ep

        return getattr(_ep, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
