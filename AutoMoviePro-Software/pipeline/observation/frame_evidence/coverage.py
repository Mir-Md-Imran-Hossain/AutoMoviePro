"""Beat coverage from frame evidence — reuses C05-S FULL/PARTIAL/NONE/UNKNOWN."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import SCHEMA_BEAT_COVERAGE, STATUS_UNKNOWN
from pipeline.retrieval.common import strip_secrets
from pipeline.story_visual_direction import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    COVERAGE_UNKNOWN,
)


def _dim_coverage(expected: str | Sequence[str], observed: Sequence[str] | str) -> str:
    if isinstance(expected, str):
        exp_list = [expected] if expected.strip() else []
    else:
        exp_list = [str(x).strip() for x in (expected or []) if str(x).strip()]
    if not exp_list:
        return COVERAGE_UNKNOWN
    obs = observed if isinstance(observed, (list, tuple)) else [observed]
    obs_l = " ".join(str(x).lower() for x in obs if x)
    if not obs_l.strip():
        # No actual observation → UNKNOWN not NONE (cannot prove absence without provider)
        return COVERAGE_UNKNOWN
    hits = sum(1 for e in exp_list if e.lower() in obs_l)
    if hits >= len(exp_list):
        return COVERAGE_FULL
    if hits > 0:
        return COVERAGE_PARTIAL
    return COVERAGE_NONE


def beat_frame_coverage(
    beat: Mapping[str, Any] | Any,
    frame_evidences: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Coverage vs DirectedVisualBeat — retrieval score is NOT coverage."""
    if hasattr(beat, "to_dict"):
        b = dict(beat.to_dict())
    else:
        b = dict(beat or {})

    frames = [dict(f) for f in (frame_evidences or [])]
    if not frames:
        dims = {
            k: COVERAGE_UNKNOWN
            for k in (
                "subject",
                "entity",
                "relationship",
                "action",
                "location",
                "environment",
                "camera",
                "lighting",
            )
        }
        return strip_secrets(
            {
                "schema": SCHEMA_BEAT_COVERAGE,
                "beat_id": str(b.get("beat_id") or ""),
                "scene_id": str(b.get("scene_id") or ""),
                "dimensions": dims,
                "overall": COVERAGE_UNKNOWN,
                "retrieval_score_is_not_coverage": True,
                "vocabulary": "C05-S VisualCoverage",
            }
        )

    # Aggregate observations
    subjects: list[str] = []
    entities: list[str] = []
    relationships: list[str] = []
    actions: list[str] = []
    locations: list[str] = []
    environments: list[str] = []
    cameras: list[str] = []
    lightings: list[str] = []
    any_provider = False
    all_unknown = True
    for f in frames:
        st = str(f.get("observation_status") or "").upper()
        if st not in ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "ABSENT", ""):
            all_unknown = False
        if f.get("provider_verified"):
            any_provider = True
        subjects.extend(list(f.get("observed_subjects") or []))
        entities.extend(list(f.get("observed_entities") or []))
        relationships.extend(list(f.get("observed_relationships") or []))
        actions.extend(list(f.get("observed_actions") or []))
        if f.get("observed_location"):
            locations.append(str(f.get("observed_location")))
        if f.get("observed_environment"):
            environments.append(str(f.get("observed_environment")))
        if f.get("camera_observation"):
            cameras.append(str(f.get("camera_observation")))
        if f.get("lighting_observation"):
            lightings.append(str(f.get("lighting_observation")))

    char = dict(b.get("character_state") or {})
    loc = dict(b.get("location_state") or {})
    env = dict(b.get("environment_state") or {})
    ent_labels = []
    for e in b.get("required_entities") or []:
        if isinstance(e, dict):
            ent_labels.append(str(e.get("label") or ""))
        else:
            ent_labels.append(str(getattr(e, "label", "") or e))
    rel_phrases = []
    for r in b.get("relationships") or []:
        if isinstance(r, dict):
            rel_phrases.append(
                " ".join(
                    str(x)
                    for x in (r.get("subject"), r.get("relation"), r.get("object"))
                    if x
                )
            )
        else:
            rel_phrases.append(str(r))

    dims = {
        "subject": _dim_coverage(str(char.get("identity") or ""), subjects),
        "entity": _dim_coverage(ent_labels + list(b.get("required_objects") or []), entities),
        "relationship": _dim_coverage(rel_phrases, relationships),
        "action": _dim_coverage(str(char.get("action") or ""), actions),
        "location": _dim_coverage(str(loc.get("location") or ""), locations),
        "environment": _dim_coverage(str(env.get("environment") or ""), environments),
        "camera": _dim_coverage(str(b.get("camera_intent") or ""), cameras),
        "lighting": _dim_coverage(str(b.get("lighting_intent") or ""), lightings),
    }

    # HEURISTIC frames cannot claim FULL as provider truth — cap at PARTIAL if not provider_verified
    if not any_provider:
        for k, v in list(dims.items()):
            if v == COVERAGE_FULL:
                dims[k] = COVERAGE_PARTIAL if not all_unknown else COVERAGE_UNKNOWN

    vals = list(dims.values())
    if all(v == COVERAGE_UNKNOWN for v in vals):
        overall = COVERAGE_UNKNOWN
    elif all(v == COVERAGE_FULL for v in vals if v != COVERAGE_UNKNOWN):
        overall = COVERAGE_FULL if COVERAGE_UNKNOWN not in vals else COVERAGE_PARTIAL
    elif any(v in (COVERAGE_FULL, COVERAGE_PARTIAL) for v in vals):
        overall = COVERAGE_PARTIAL
    else:
        overall = COVERAGE_NONE

    return strip_secrets(
        {
            "schema": SCHEMA_BEAT_COVERAGE,
            "beat_id": str(b.get("beat_id") or ""),
            "scene_id": str(b.get("scene_id") or ""),
            "dimensions": dims,
            "overall": overall,
            "retrieval_score_is_not_coverage": True,
            "provider_verified_any": any_provider,
            "vocabulary": "C05-S VisualCoverage",
            "unknown_as_pass": False,
        }
    )
