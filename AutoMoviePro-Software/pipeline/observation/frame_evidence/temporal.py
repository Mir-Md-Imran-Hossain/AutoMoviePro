"""Bounded temporal evidence — ContinuityTracker remains policy authority."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import (
    SCHEMA_TEMPORAL,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
)
from pipeline.observation.frame_evidence.normalize import (
    classify_location_pair,
    classify_relationship_pair,
    contract_requires,
    normalize_observation_fields,
)
from pipeline.retrieval.common import strip_secrets


def _bump(overall: str, new: str) -> str:
    if overall == STATUS_FAIL or new == STATUS_FAIL:
        return STATUS_FAIL
    if overall == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
        return STATUS_UNKNOWN
    return STATUS_PASS


def compare_temporal_frames(
    frame_evidences: Sequence[Mapping[str, Any]],
    *,
    visual_contract: Optional[Mapping[str, Any]] = None,
    continuity_constraints: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Compare ordered frame observations only for properties the Visual Contract /
    ContinuityTracker explicit constraints require.

    Uses conservative semantic normalization to reduce false FAIL from label drift.
    Prefers UNKNOWN over PASS when ambiguous. Does NOT create a second ContinuityTracker.
    """
    frames = [normalize_observation_fields(dict(f)) for f in (frame_evidences or [])]
    contract = dict(visual_contract or {})
    constraints = dict(continuity_constraints or {})

    require_location = contract_requires(contract, constraints, "location")
    require_relationship = contract_requires(contract, constraints, "relationship")
    require_entity = contract_requires(contract, constraints, "entity")
    explicit_lighting = contract_requires(contract, constraints, "lighting")
    explicit_camera = contract_requires(contract, constraints, "camera")
    narrative_change_allowed = bool(
        constraints.get("narrative_change_allowed") or contract.get("narrative_change_allowed")
    )
    location_transition_allowed = bool(
        constraints.get("location_transition_allowed") or contract.get("location_transition_allowed")
    )
    intentional_lighting = str(
        constraints.get("lighting_continuity") or contract.get("lighting_continuity") or ""
    ).upper() == "INTENTIONAL_CHANGE"
    allowed_rel_transitions = list(
        constraints.get("allowed_relationship_transitions")
        or contract.get("allowed_relationship_transitions")
        or []
    )

    issues: list[str] = []
    comparisons: list[dict[str, Any]] = []
    overall = STATUS_PASS
    normalization_applied = True

    if len(frames) < 2:
        return strip_secrets(
            {
                "schema": SCHEMA_TEMPORAL,
                "status": STATUS_UNKNOWN,
                "reason": "insufficient_frames_for_temporal",
                "comparisons": [],
                "normalization_applied": normalization_applied,
                "continuity_tracker_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
                "second_continuity_engine": False,
                "unknown_as_pass": False,
            }
        )

    if any(
        str(f.get("observation_status") or "").upper() in ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "ABSENT")
        for f in frames
    ):
        overall = STATUS_UNKNOWN

    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        na, nb = a.get("_normalized") or {}, b.get("_normalized") or {}
        row: dict[str, Any] = {
            "from_index": i - 1,
            "to_index": i,
            "from_ts": a.get("timestamp"),
            "to_ts": b.get("timestamp"),
            "dims": {},
        }

        # RELATIONSHIP — only if explicit
        if require_relationship:
            rel = classify_relationship_pair(
                list(a.get("observed_relationships") or []),
                list(b.get("observed_relationships") or []),
                narrative_change_allowed=narrative_change_allowed,
                allowed_transitions=allowed_rel_transitions,
            )
            cls = rel.get("class")
            if cls in ("same", "valid_transition"):
                row["dims"]["relationship"] = STATUS_PASS
                row["dims"]["relationship_class"] = cls
            elif cls == "unknown":
                row["dims"]["relationship"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
            else:
                row["dims"]["relationship"] = STATUS_FAIL
                issues.append(f"relationship_{cls}:{rel}")
                overall = STATUS_FAIL
        else:
            row["dims"]["relationship"] = "NOT_REQUIRED"

        # LOCATION — only if explicit; no naïve raw-string FAIL
        if require_location:
            loc = classify_location_pair(str(na.get("location") or ""), str(nb.get("location") or ""))
            cls = loc.get("class")
            if cls in ("same", "compatible_sublocation"):
                row["dims"]["location"] = STATUS_PASS
                row["dims"]["location_class"] = cls
            elif cls == "intentional_transition" or (cls != "contradiction" and location_transition_allowed):
                if location_transition_allowed and cls != "contradiction":
                    row["dims"]["location"] = STATUS_PASS
                    row["dims"]["location_class"] = "intentional_transition_allowed"
                elif cls == "unknown":
                    row["dims"]["location"] = STATUS_UNKNOWN
                    overall = _bump(overall, STATUS_UNKNOWN)
                else:
                    row["dims"]["location"] = STATUS_FAIL
                    issues.append(f"location_{cls}:{loc}")
                    overall = STATUS_FAIL
            elif cls == "contradiction":
                row["dims"]["location"] = STATUS_FAIL
                issues.append(f"location_contradiction:{loc}")
                overall = STATUS_FAIL
            else:
                # ambiguous unclustered → UNKNOWN (never force PASS)
                row["dims"]["location"] = STATUS_UNKNOWN
                row["dims"]["location_class"] = cls
                overall = _bump(overall, STATUS_UNKNOWN)
        else:
            row["dims"]["location"] = "NOT_REQUIRED"

        # ENTITY presence — only if explicit
        if require_entity:
            ea = set(na.get("entities") or []) | set(na.get("subjects") or [])
            eb = set(nb.get("entities") or []) | set(nb.get("subjects") or [])
            if not ea or not eb:
                row["dims"]["entity"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
            elif ea & eb:
                row["dims"]["entity"] = STATUS_PASS
            else:
                row["dims"]["entity"] = STATUS_FAIL
                issues.append(f"entity_discontinuity:{sorted(ea)}->{sorted(eb)}")
                overall = STATUS_FAIL
        else:
            row["dims"]["entity"] = "NOT_REQUIRED"

        # LIGHTING — only explicit; reuse ContinuityTracker families, do not duplicate definitions
        if explicit_lighting:
            la = str(na.get("lighting") or "")
            lb = str(nb.get("lighting") or "")
            if not la or not lb:
                row["dims"]["lighting"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
            else:
                day_night = ("day" in la and "night" in lb) or ("night" in la and "day" in lb)
                if day_night and not intentional_lighting:
                    row["dims"]["lighting"] = STATUS_FAIL
                    issues.append("explicit_lighting_day_night_without_transition")
                    overall = STATUS_FAIL
                else:
                    try:
                        from pipeline.visual_semantic.continuity import _LIGHTING_FAMILIES, _family_hits

                        fa = _family_hits(la, _LIGHTING_FAMILIES)
                        fb = _family_hits(lb, _LIGHTING_FAMILIES)
                        if fa and fb and fa.isdisjoint(fb) and not intentional_lighting:
                            row["dims"]["lighting"] = STATUS_FAIL
                            issues.append(f"explicit_lighting_family_clash:{sorted(fa)}->{sorted(fb)}")
                            overall = STATUS_FAIL
                        else:
                            row["dims"]["lighting"] = STATUS_PASS
                    except Exception:
                        row["dims"]["lighting"] = STATUS_PASS if not day_night or intentional_lighting else STATUS_FAIL
        else:
            row["dims"]["lighting"] = "NOT_REQUIRED"

        # CAMERA — only explicit; reuse ContinuityTracker families
        if explicit_camera:
            ca = str(na.get("camera") or "")
            cb = str(nb.get("camera") or "")
            if not ca or not cb:
                row["dims"]["camera"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
            elif constraints.get("camera_change_allowed") or contract.get("camera_change_allowed"):
                row["dims"]["camera"] = STATUS_PASS
                row["dims"]["camera_note"] = "contract_allows_camera_change"
            else:
                try:
                    from pipeline.visual_semantic.continuity import _CAMERA_FAMILIES, _family_hits

                    fa = _family_hits(ca, _CAMERA_FAMILIES)
                    fb = _family_hits(cb, _CAMERA_FAMILIES)
                    if fa and fb and fa.isdisjoint(fb):
                        row["dims"]["camera"] = STATUS_FAIL
                        issues.append(f"explicit_camera_contradiction:{ca}->{cb}")
                        overall = STATUS_FAIL
                    else:
                        row["dims"]["camera"] = STATUS_PASS
                except Exception:
                    row["dims"]["camera"] = STATUS_UNKNOWN
                    overall = _bump(overall, STATUS_UNKNOWN)
        else:
            row["dims"]["camera"] = "NOT_REQUIRED"

        comparisons.append(row)

    if overall == STATUS_PASS and any(
        str(f.get("observation_status")) == STATUS_UNKNOWN for f in frames
    ):
        overall = STATUS_UNKNOWN

    return strip_secrets(
        {
            "schema": SCHEMA_TEMPORAL,
            "status": overall,
            "comparisons": comparisons,
            "issues": issues,
            "normalization_applied": normalization_applied,
            "explicit_dims_checked": {
                "location": require_location,
                "relationship": require_relationship,
                "entity": require_entity,
                "camera": explicit_camera,
                "lighting": explicit_lighting,
            },
            "continuity_tracker_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
            "second_continuity_engine": False,
            "invents_unspecified_rules": False,
            "unknown_as_pass": False,
            "creates_final_gate": False,
            "prefers_unknown_over_pass": True,
        }
    )
