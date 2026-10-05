"""Cross-beat entity state evidence — ContinuityTracker remains policy authority.

Projects only entities declared in Visual Contract / SceneIntent / DirectedVisualBeat.
Does not invent entities. Does not certify identity via CLIP.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping, Optional, Sequence

from pipeline.observation.common import STATUS_FAIL, STATUS_PASS, STATUS_UNKNOWN
from pipeline.observation.frame_evidence.normalize import (
    classify_location_pair,
    classify_relationship_pair,
    location_cluster,
    normalize_relation_label,
)
from pipeline.retrieval.common import strip_secrets

SCHEMA_CROSS_BEAT = "amp_observation_cross_beat_entity_v1"

ENTITY_CHARACTER = "CHARACTER"
ENTITY_OBJECT = "OBJECT"
ENTITY_VEHICLE = "VEHICLE"
ENTITY_LOCATION = "LOCATION"
ENTITY_OTHER = "OTHER_EXPLICIT_ENTITY"

PRESENCE_PRESENT = "PRESENT"
PRESENCE_ABSENT = "ABSENT"
PRESENCE_UNKNOWN = "UNKNOWN"

CLASS_STATE_CHANGE = "STATE_CHANGE"
CLASS_IDENTITY_BREAK = "IDENTITY_BREAK"
CLASS_LOCATION_CONTRADICTION = "LOCATION_CONTRADICTION"
CLASS_RELATIONSHIP_CONTRADICTION = "RELATIONSHIP_CONTRADICTION"
CLASS_COMPATIBLE = "COMPATIBLE"
CLASS_UNKNOWN = "UNKNOWN"


def _clean(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def _entity_type(label: str, hinted: str = "") -> str:
    h = _clean(hinted)
    if h in ("character", "person", "actor"):
        return ENTITY_CHARACTER
    if h in ("vehicle", "car", "truck"):
        return ENTITY_VEHICLE
    if h in ("location", "place"):
        return ENTITY_LOCATION
    if h in ("object", "prop"):
        return ENTITY_OBJECT
    lab = _clean(label)
    vehicle_kw = ("car", "suzuki", "vehicle", "truck", "van", "bus")
    if any(k in lab for k in vehicle_kw):
        return ENTITY_VEHICLE
    if any(k in lab for k in ("hospital", "station", "room", "street", "desert", "space", "hallway", "corridor")):
        return ENTITY_LOCATION
    # Proper-case short names → character; else object
    if label[:1].isupper() and len(lab.split()) <= 2:
        return ENTITY_CHARACTER
    return ENTITY_OBJECT


def _entity_id(canonical_name: str, entity_type: str) -> str:
    raw = f"{entity_type}:{_clean(canonical_name)}"
    return "ent-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _beat_dict(beat: Any) -> dict[str, Any]:
    if beat is None:
        return {}
    if hasattr(beat, "to_dict"):
        return dict(beat.to_dict())
    return dict(beat or {})


def _explicit_entities_from_beat(beat: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Only entities present in plan/contract — never invented."""
    out: list[dict[str, Any]] = []
    for e in beat.get("required_entities") or []:
        if isinstance(e, Mapping):
            label = str(e.get("label") or e.get("name") or "").strip()
            et = str(e.get("entity_type") or e.get("type") or e.get("role") or "")
            eid = str(e.get("entity_id") or "") or _entity_id(label, _entity_type(label, et))
        else:
            label = str(getattr(e, "label", "") or e).strip()
            et = str(getattr(e, "entity_type", "") or getattr(e, "role", "") or "")
            eid = str(getattr(e, "entity_id", "") or "") or _entity_id(label, _entity_type(label, et))
        if not label:
            continue
        out.append(
            {
                "entity_id": eid,
                "entity_type": _entity_type(label, et),
                "canonical_name": label,
            }
        )
    for obj in beat.get("required_objects") or []:
        label = str(obj).strip()
        if not label:
            continue
        if any(_clean(x["canonical_name"]) == _clean(label) for x in out):
            continue
        et = _entity_type(label, "object")
        out.append({"entity_id": _entity_id(label, et), "entity_type": et, "canonical_name": label})
    loc = str((beat.get("location_state") or {}).get("location") or beat.get("location") or "").strip()
    if loc:
        out.append(
            {
                "entity_id": _entity_id(loc, ENTITY_LOCATION),
                "entity_type": ENTITY_LOCATION,
                "canonical_name": loc,
            }
        )
    char = str((beat.get("character_state") or {}).get("identity") or "").strip()
    if char and not any(_clean(x["canonical_name"]) == _clean(char) for x in out):
        out.append(
            {
                "entity_id": _entity_id(char, ENTITY_CHARACTER),
                "entity_type": ENTITY_CHARACTER,
                "canonical_name": char,
            }
        )
    return out


def _presence_for(label: str, observation: Mapping[str, Any]) -> str:
    st = str(observation.get("observation_status") or "").upper()
    if st in ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "ABSENT"):
        return PRESENCE_UNKNOWN
    hay = " ".join(
        [
            " ".join(str(x) for x in (observation.get("observed_subjects") or [])),
            " ".join(str(x) for x in (observation.get("observed_entities") or [])),
            str(observation.get("observed_location") or ""),
            " ".join(str(x) for x in (observation.get("observed_relationships") or [])),
        ]
    ).lower()
    tokens = [t for t in _clean(label).split() if len(t) >= 3]
    if not tokens:
        return PRESENCE_UNKNOWN
    if all(t in hay for t in tokens) or _clean(label) in hay:
        return PRESENCE_PRESENT
    if not hay.strip():
        return PRESENCE_UNKNOWN
    # provider ran but label not found → ABSENT only if provider_verified
    if observation.get("provider_verified"):
        return PRESENCE_ABSENT
    return PRESENCE_UNKNOWN


def project_beat_entity_states(
    beat: Any,
    observation: Optional[Mapping[str, Any]] = None,
    *,
    dialogue_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
    job_id: str = "",
) -> list[dict[str, Any]]:
    """Project explicit beat entities + observation into cross-beat state rows."""
    b = _beat_dict(beat)
    obs = dict(observation or {})
    beat_id = str(b.get("beat_id") or "")
    scene_id = str(b.get("scene_id") or "")
    dlg = dialogue_id or str(b.get("dialogue_segment_id") or b.get("dialogue_id") or "")
    loc_req = str((b.get("location_state") or {}).get("location") or "")
    action = str((b.get("character_state") or {}).get("action") or "")
    rels = []
    for r in b.get("relationships") or []:
        if isinstance(r, Mapping):
            rels.append(
                {
                    "subject_entity": str(r.get("subject") or r.get("source_id") or ""),
                    "relation": normalize_relation_label(str(r.get("relation") or r.get("relation_type") or "")),
                    "object_entity": str(r.get("object") or r.get("target_id") or ""),
                    "beat_id": beat_id,
                }
            )
        else:
            rels.append(
                {
                    "subject_entity": str(getattr(r, "source_id", "") or ""),
                    "relation": normalize_relation_label(str(getattr(r, "relation_type", "") or "")),
                    "object_entity": str(getattr(r, "target_id", "") or ""),
                    "beat_id": beat_id,
                }
            )

    observed_rels = [
        {
            "raw": str(x),
            "relation": normalize_relation_label(str(x)),
            "beat_id": beat_id,
        }
        for x in (obs.get("observed_relationships") or [])
        if x
    ]

    rows: list[dict[str, Any]] = []
    for ent in _explicit_entities_from_beat(b):
        presence = _presence_for(ent["canonical_name"], obs) if obs else PRESENCE_UNKNOWN
        observed_state = ""
        if ent["entity_type"] == ENTITY_CHARACTER:
            observed_state = action or ",".join(str(x) for x in (obs.get("observed_actions") or [])[:2])
        elif ent["entity_type"] == ENTITY_LOCATION:
            observed_state = str(obs.get("observed_location") or "")
        row = strip_secrets(
            {
                "schema": SCHEMA_CROSS_BEAT,
                "entity_id": ent["entity_id"],
                "entity_type": ent["entity_type"],
                "canonical_name": ent["canonical_name"],
                "beat_id": beat_id,
                "scene_id": scene_id,
                "dialogue_id": dlg,
                "presence": presence,
                "observed_state": observed_state,
                "location": str(obs.get("observed_location") or loc_req),
                "location_cluster": location_cluster(str(obs.get("observed_location") or loc_req)),
                "relationships": rels,
                "observed_relationships": observed_rels,
                "source_evidence": {
                    "observation_status": obs.get("observation_status"),
                    "provider_verified": bool(obs.get("provider_verified")),
                    "heuristic": bool(obs.get("heuristic")),
                    "evidence_source": obs.get("evidence_source"),
                    "provider": obs.get("provider"),
                    "frame_path": obs.get("frame_path"),
                },
                "observation_status": str(obs.get("observation_status") or STATUS_UNKNOWN).upper()
                if obs
                else STATUS_UNKNOWN,
                "customer_id": customer_id,
                "channel_id": channel_id,
                "job_id": job_id,
                "clip_similarity_is_not_identity_pass": True,
                "created_at": time.time(),
            }
        )
        rows.append(row)
    return rows


def dialogue_visual_entity_binding(
    *,
    dialogue_id: str,
    beat: Any,
    observation: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Trace dialogue_id ↔ beat_id ↔ entity requirements ↔ observed state."""
    b = _beat_dict(beat)
    states = project_beat_entity_states(beat, observation, dialogue_id=dialogue_id)
    obs = dict(observation or {})
    st = str(obs.get("observation_status") or STATUS_UNKNOWN).upper()
    required_ok = True
    issues: list[str] = []
    if obs.get("provider_verified") and st == STATUS_FAIL:
        required_ok = False
        issues.append("provider_fail_vs_dialogue_visual_state")
    elif st in ("UNKNOWN", "OBSERVATION_UNAVAILABLE", "ABSENT") or not obs:
        required_ok = False
        issues.append("observation_insufficient")
        st = STATUS_UNKNOWN
    # keyword-only never PASS
    status = STATUS_PASS if required_ok and obs.get("provider_verified") and st == STATUS_PASS else (
        STATUS_FAIL if st == STATUS_FAIL else STATUS_UNKNOWN
    )
    return strip_secrets(
        {
            "dialogue_id": dialogue_id or str(b.get("dialogue_segment_id") or ""),
            "beat_id": str(b.get("beat_id") or ""),
            "scene_id": str(b.get("scene_id") or ""),
            "entity_requirements": [s["canonical_name"] for s in states],
            "action_requirements": [(b.get("character_state") or {}).get("action")],
            "relationship_requirements": [
                f"{r.get('subject_entity')}:{r.get('relation')}:{r.get('object_entity')}"
                for r in (states[0].get("relationships") if states else []) or []
            ],
            "location_requirements": [(b.get("location_state") or {}).get("location")],
            "entity_states": states,
            "status": status,
            "issues": issues,
            "keyword_only_pass_forbidden": True,
            "unknown_as_pass": False,
        }
    )


def _same_customer(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[bool, str]:
    ca, cb = str(a.get("customer_id") or ""), str(b.get("customer_id") or "")
    cha, chb = str(a.get("channel_id") or ""), str(b.get("channel_id") or "")
    if ca and cb and ca != cb:
        return False, "cross_customer_entity_merge_forbidden"
    if cha and chb and cha != chb:
        return False, "cross_channel_entity_merge_forbidden"
    return True, ""


def compare_entity_states_adjacent(
    prev_states: Sequence[Mapping[str, Any]],
    next_states: Sequence[Mapping[str, Any]],
    *,
    visual_contract: Optional[Mapping[str, Any]] = None,
    continuity_constraints: Optional[Mapping[str, Any]] = None,
    narrative_change_allowed: bool = False,
) -> dict[str, Any]:
    """Adjacent-beat only. ContinuityTracker remains policy authority."""
    contract = dict(visual_contract or {})
    constraints = dict(continuity_constraints or {})
    narrative_change_allowed = bool(
        narrative_change_allowed
        or contract.get("narrative_change_allowed")
        or constraints.get("narrative_change_allowed")
    )
    location_transition_allowed = bool(
        contract.get("location_transition_allowed") or constraints.get("location_transition_allowed")
    )

    prev = list(prev_states or [])
    nxt = list(next_states or [])
    if prev and nxt:
        ok, reason = _same_customer(prev[0], nxt[0])
        if not ok:
            return strip_secrets(
                {
                    "schema": SCHEMA_CROSS_BEAT,
                    "status": STATUS_FAIL,
                    "class": CLASS_IDENTITY_BREAK,
                    "reason": reason,
                    "comparisons": [],
                    "continuity_tracker_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
                    "second_continuity_engine": False,
                    "identity_engine": False,
                    "clip_similarity_is_not_identity_pass": True,
                    "unknown_as_pass": False,
                }
            )

    by_id_prev = {str(s.get("entity_id")): dict(s) for s in prev if s.get("entity_id")}
    by_name_prev = {_clean(str(s.get("canonical_name"))): dict(s) for s in prev}
    # Location labels often change across beats (hallway→room); match LOCATION by type
    loc_prev = next((dict(s) for s in prev if s.get("entity_type") == ENTITY_LOCATION), None)
    comparisons: list[dict[str, Any]] = []
    overall = STATUS_PASS
    issues: list[str] = []

    def _bump(cur: str, new: str) -> str:
        if cur == STATUS_FAIL or new == STATUS_FAIL:
            return STATUS_FAIL
        if cur == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
            return STATUS_UNKNOWN
        return STATUS_PASS

    for ns in nxt:
        key = str(ns.get("entity_id") or "")
        ps = by_id_prev.get(key) or by_name_prev.get(_clean(str(ns.get("canonical_name") or "")))
        if not ps and ns.get("entity_type") == ENTITY_LOCATION and loc_prev is not None:
            ps = loc_prev
        if not ps:
            # new explicit entity in next beat — not automatic FAIL
            comparisons.append(
                {
                    "entity_id": key,
                    "canonical_name": ns.get("canonical_name"),
                    "class": CLASS_STATE_CHANGE,
                    "note": "entity_introduced_or_unmatched_prev",
                    "status": STATUS_UNKNOWN
                    if str(ns.get("observation_status")) == STATUS_UNKNOWN
                    else STATUS_PASS,
                }
            )
            if str(ns.get("observation_status")) == STATUS_UNKNOWN:
                overall = _bump(overall, STATUS_UNKNOWN)
            continue

        # observation insufficient
        if str(ps.get("observation_status")) == STATUS_UNKNOWN or str(ns.get("observation_status")) == STATUS_UNKNOWN:
            comparisons.append(
                {
                    "entity_id": key,
                    "class": CLASS_UNKNOWN,
                    "status": STATUS_UNKNOWN,
                    "note": "insufficient_observation",
                }
            )
            overall = _bump(overall, STATUS_UNKNOWN)
            continue

        row: dict[str, Any] = {
            "entity_id": key,
            "canonical_name": ns.get("canonical_name"),
            "entity_type": ns.get("entity_type"),
            "prev_beat_id": ps.get("beat_id"),
            "next_beat_id": ns.get("beat_id"),
        }

        # Identity break: same required entity id/name but clearly incompatible presence with provider proof
        if (
            ps.get("presence") == PRESENCE_PRESENT
            and ns.get("presence") == PRESENCE_ABSENT
            and ns.get("source_evidence", {}).get("provider_verified")
            and (ns.get("entity_type") in (ENTITY_CHARACTER, ENTITY_VEHICLE, ENTITY_OBJECT))
        ):
            # allowed if narrative change removes entity
            if narrative_change_allowed or constraints.get("entity_exit_allowed"):
                row["class"] = CLASS_STATE_CHANGE
                row["status"] = STATUS_PASS
                row["note"] = "entity_exit_allowed"
            else:
                row["class"] = CLASS_IDENTITY_BREAK
                row["status"] = STATUS_FAIL
                issues.append(f"identity_break:{ns.get('canonical_name')}")
                overall = STATUS_FAIL
            comparisons.append(row)
            continue

        require_loc = bool(
            ns.get("entity_type") == ENTITY_LOCATION
            or contract.get("require_location")
            or constraints.get("require_location")
        )
        loc_hard_stop = False
        if require_loc:
            loc = classify_location_pair(str(ps.get("location") or ""), str(ns.get("location") or ""))
            cls = loc.get("class")
            row["location"] = loc
            if cls in ("same", "compatible_sublocation"):
                row["location_class"] = "SAME_LOCATION" if cls == "same" else "COMPATIBLE_SUBLOCATION"
                row["class"] = CLASS_COMPATIBLE
                row["status"] = STATUS_PASS
            elif cls == "contradiction":
                row["location_class"] = "CONTRADICTION"
                row["class"] = CLASS_LOCATION_CONTRADICTION
                row["status"] = STATUS_FAIL
                issues.append(f"location_contradiction:{loc}")
                overall = STATUS_FAIL
                loc_hard_stop = True
            elif location_transition_allowed and cls != "contradiction":
                row["location_class"] = "INTENTIONAL_TRANSITION"
                row["class"] = CLASS_STATE_CHANGE
                row["status"] = STATUS_PASS
                row["note"] = "intentional_location_transition"
            else:
                row["location_class"] = "UNKNOWN"
                row["class"] = CLASS_UNKNOWN
                row["status"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
                loc_hard_stop = True
            if ns.get("entity_type") == ENTITY_LOCATION or loc_hard_stop:
                comparisons.append(row)
                continue

        # Relationship transitions for character/vehicle pairs
        prev_rels = [str(r.get("relation") or r.get("raw") or "") for r in (ps.get("relationships") or [])]
        next_rels = [str(r.get("relation") or r.get("raw") or "") for r in (ns.get("relationships") or [])]
        # Augment with observed relations when provider_verified (do not drop contract intent)
        if ps.get("source_evidence", {}).get("provider_verified"):
            prev_rels = prev_rels + [
                str(r.get("relation") or r.get("raw") or "") for r in (ps.get("observed_relationships") or [])
            ]
        if ns.get("source_evidence", {}).get("provider_verified"):
            next_rels = next_rels + [
                str(r.get("relation") or r.get("raw") or "") for r in (ns.get("observed_relationships") or [])
            ]

        if prev_rels and next_rels:
            rel = classify_relationship_pair(
                prev_rels,
                next_rels,
                narrative_change_allowed=narrative_change_allowed,
                allowed_transitions=list(
                    contract.get("allowed_relationship_transitions")
                    or constraints.get("allowed_relationship_transitions")
                    or []
                ),
            )
            rcls = rel.get("class")
            if rcls in ("same", "valid_transition"):
                row["class"] = CLASS_STATE_CHANGE if rcls == "valid_transition" else CLASS_COMPATIBLE
                row["status"] = STATUS_PASS
                row["relationship"] = rel
            elif rcls == "unknown":
                row["class"] = CLASS_UNKNOWN
                row["status"] = STATUS_UNKNOWN
                overall = _bump(overall, STATUS_UNKNOWN)
            else:
                if constraints.get("forbid_relationship_change") or contract.get("forbid_relationship_change"):
                    row["class"] = CLASS_RELATIONSHIP_CONTRADICTION
                    row["status"] = STATUS_FAIL
                    issues.append(f"relationship_forbidden:{rel}")
                    overall = STATUS_FAIL
                elif narrative_change_allowed:
                    row["class"] = CLASS_STATE_CHANGE
                    row["status"] = STATUS_PASS
                else:
                    row["class"] = CLASS_RELATIONSHIP_CONTRADICTION
                    row["status"] = STATUS_FAIL
                    issues.append(f"relationship_contradiction:{rel}")
                    overall = STATUS_FAIL
        else:
            # state change on action alone is not identity failure
            if _clean(str(ps.get("observed_state") or "")) != _clean(str(ns.get("observed_state") or "")):
                row["class"] = CLASS_STATE_CHANGE
                row["status"] = STATUS_PASS
                row["note"] = "action_or_state_change_not_identity_break"
            elif row.get("status") not in (STATUS_FAIL, STATUS_UNKNOWN):
                row["class"] = CLASS_COMPATIBLE
                row["status"] = STATUS_PASS

        comparisons.append(row)

    # Unspecified properties never hard-fail: only explicit dims above
    return strip_secrets(
        {
            "schema": SCHEMA_CROSS_BEAT,
            "status": overall,
            "comparisons": comparisons,
            "issues": issues,
            "adjacent_only": True,
            "continuity_tracker_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
            "second_continuity_engine": False,
            "identity_certification_engine": False,
            "clip_similarity_is_not_identity_pass": True,
            "unknown_as_pass": False,
            "unknown_as_fail": False,
            "creates_final_gate": False,
        }
    )


def compare_cross_beat_sequence(
    beat_observations: Sequence[Mapping[str, Any]],
    *,
    visual_contract: Optional[Mapping[str, Any]] = None,
    continuity_constraints: Optional[Mapping[str, Any]] = None,
    require_far_continuity: bool = False,
) -> dict[str, Any]:
    """
    beat_observations items: {beat, observation, dialogue_id, customer_id, channel_id, job_id}
    Compares adjacent pairs only unless require_far_continuity (explicit contract).
    """
    rows = list(beat_observations or [])
    projected: list[list[dict[str, Any]]] = []
    for item in rows:
        projected.append(
            project_beat_entity_states(
                item.get("beat"),
                item.get("observation"),
                dialogue_id=str(item.get("dialogue_id") or ""),
                customer_id=str(item.get("customer_id") or ""),
                channel_id=str(item.get("channel_id") or ""),
                job_id=str(item.get("job_id") or ""),
            )
        )

    adjacent: list[dict[str, Any]] = []
    overall = STATUS_PASS

    def _bump(cur: str, new: str) -> str:
        if cur == STATUS_FAIL or new == STATUS_FAIL:
            return STATUS_FAIL
        if cur == STATUS_UNKNOWN or new == STATUS_UNKNOWN:
            return STATUS_UNKNOWN
        return STATUS_PASS

    for i in range(1, len(projected)):
        cmp = compare_entity_states_adjacent(
            projected[i - 1],
            projected[i],
            visual_contract=visual_contract,
            continuity_constraints=continuity_constraints,
        )
        adjacent.append({"from_index": i - 1, "to_index": i, "result": cmp})
        overall = _bump(overall, str(cmp.get("status") or STATUS_UNKNOWN))

    far: list[dict[str, Any]] = []
    if require_far_continuity and len(projected) >= 3:
        cmp = compare_entity_states_adjacent(
            projected[0],
            projected[-1],
            visual_contract=visual_contract,
            continuity_constraints=continuity_constraints,
        )
        far.append({"from_index": 0, "to_index": len(projected) - 1, "result": cmp})
        overall = _bump(overall, str(cmp.get("status") or STATUS_UNKNOWN))

    return strip_secrets(
        {
            "schema": SCHEMA_CROSS_BEAT,
            "status": overall,
            "projected_beats": projected,
            "adjacent_comparisons": adjacent,
            "far_comparisons": far,
            "require_far_continuity": bool(require_far_continuity),
            "continuity_tracker_authority": "pipeline.visual_semantic.continuity.ContinuityTracker",
            "second_continuity_engine": False,
            "identity_certification_engine": False,
            "clip_similarity_is_not_identity_pass": True,
            "unknown_as_pass": False,
            "unknown_as_fail": False,
            "creates_final_gate": False,
        }
    )
