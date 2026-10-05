"""FAIL → BUILD-04F VISUAL_ASSET repair evidence; UNKNOWN → no repair."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from pipeline.observation.common import STATUS_FAIL, STATUS_UNKNOWN
from pipeline.retrieval.common import strip_secrets


def repair_handoff_from_frame_evidence(
    *,
    beat_id: str,
    scene_id: str,
    frame_bridge_or_temporal: Mapping[str, Any],
    old_fingerprint: str = "",
) -> dict[str, Any]:
    """
    Structured repair evidence for existing BUILD-04F.
    Does not implement a repair engine.
    """
    payload = dict(frame_bridge_or_temporal or {})
    temporal = dict(payload.get("temporal") or payload)
    coverage = dict(payload.get("coverage") or {})
    status = str(
        temporal.get("status")
        or payload.get("overall")
        or STATUS_UNKNOWN
    ).upper()

    # Aggregate FAIL from observations
    obs_fail = any(
        str(o.get("observation_status") or "").upper() == STATUS_FAIL
        for o in (payload.get("observations") or [])
    )
    if obs_fail:
        status = STATUS_FAIL

    if status == STATUS_UNKNOWN or status in ("OBSERVATION_UNAVAILABLE", "ABSENT", "OK"):
        if status != STATUS_FAIL:
            return strip_secrets(
                {
                    "repair_triggered": False,
                    "reason": "unknown_or_unavailable_does_not_trigger_repair",
                    "status": status,
                    "repair_scope": None,
                    "whole_video_regeneration": False,
                }
            )

    if status != STATUS_FAIL:
        return strip_secrets(
            {
                "repair_triggered": False,
                "reason": f"status_{status}_no_repair",
                "status": status,
                "whole_video_regeneration": False,
            }
        )

    from pipeline.semantic_coverage import plan_semantic_beat_repair

    issues = list(temporal.get("issues") or [])
    if coverage.get("overall") in ("NONE", "PARTIAL"):
        issues.append(f"beat_coverage:{coverage.get('overall')}")
    plan = plan_semantic_beat_repair(
        beat_id=beat_id,
        scene_id=scene_id,
        observation={"overall": STATUS_FAIL, "issues": issues or ["frame_evidence_fail"]},
        old_fingerprint=old_fingerprint,
    )
    return strip_secrets(
        {
            "repair_triggered": True,
            "status": STATUS_FAIL,
            "repair_scope": "VISUAL_ASSET",
            "repair_scope_forced": plan.get("repair_scope_forced") or "VISUAL_ASSET",
            "whole_video_regeneration": False,
            "plan": plan,
            "authority": "BUILD-04F plan_repair / plan_semantic_beat_repair",
            "second_repair_engine": False,
        }
    )
