"""Quality invalidation graph (BUILD-04F)."""
from __future__ import annotations

from typing import Iterable, Set

# Maps changed artifact stage → quality stages that become stale
INVALIDATION_GRAPH: dict[str, set[str]] = {
    "script": {"script", "scene", "visual", "audio", "subtitle", "cross_modal", "render", "final"},
    "dialogue": {"script", "scene", "visual", "audio", "subtitle", "cross_modal", "render", "final"},
    "visual": {"visual", "cross_modal", "render", "final"},
    "visual_plan": {"visual", "cross_modal", "render", "final"},
    "audio": {"audio", "subtitle", "cross_modal", "render", "final"},
    "subtitle": {"subtitle", "render", "final"},
    "render": {"render", "final"},
}


def invalidated_stages(changed_stage: str) -> Set[str]:
    return set(INVALIDATION_GRAPH.get(changed_stage.lower(), {changed_stage, "final"}))


def filter_stale_results(
    cached_stages: Iterable[str],
    changed_stage: str,
) -> set[str]:
    stale = invalidated_stages(changed_stage)
    return stale & set(cached_stages)


def scene_only_invalidation(scene_id: str) -> set[str]:
    """Visual-only change invalidates only that scene + dependent final."""
    return {f"visual:{scene_id}", f"cross_modal:{scene_id}", "render", "final"}


def audio_only_invalidation(scene_id: str) -> set[str]:
    return {f"audio:{scene_id}", f"subtitle:{scene_id}", "render", "final"}
