"""AMP-owned documentary montage discipline.

Inspired by OpenMontage production methodology (stage skills, concrete slots,
retrieval-first B-roll, checkpoints) — **rewritten AMP-owned contracts**.

LEGAL: Does NOT import ``third_party.OpenMontage`` (AGPL). Ideas only.
Canonical AMP authorities remain: TRS, C05-S, scene_builder, media_mode_engine, FFmpeg.
"""
from __future__ import annotations

from pipeline.montage_brain.discipline import (
    MONTAGE_BRAIN_VERSION,
    montage_compose_checklist,
    montage_discipline_prompt_block,
    montage_stage_manifest,
)
from pipeline.montage_brain.slot_planner import (
    enrich_plan_with_montage_slots,
    slot_search_queries_for_scene,
)
from pipeline.montage_brain.production import (
    apply_montage_brain_to_plan,
    prefer_retrieved_stock_for_scene,
)

__all__ = [
    "MONTAGE_BRAIN_VERSION",
    "montage_compose_checklist",
    "montage_discipline_prompt_block",
    "montage_stage_manifest",
    "enrich_plan_with_montage_slots",
    "slot_search_queries_for_scene",
    "apply_montage_brain_to_plan",
    "prefer_retrieved_stock_for_scene",
]
