"""Conservative observation label normalization — not a semantic gate or model.

Prefer UNKNOWN over PASS when ambiguous. Never hides clear contradictions.
"""
from __future__ import annotations

import re
from typing import Any

# Conservative location clusters (small, explicit — not open synonym expansion)
_LOCATION_CLUSTERS: dict[str, frozenset[str]] = {
    "spacecraft_interior": frozenset(
        {
            "spacecraft interior",
            "spacecraft cabin",
            "spaceship interior",
            "spaceship cabin",
            "cockpit",
            "cabin interior",
            "futuristic interior",
            "sci-fi interior",
            "futuristic/sci-fi interior",
            "interior setting",
            "unspecified interior",
            "interior",
        }
    ),
    "outer_space": frozenset(
        {
            "outer space",
            "space",
            "orbit",
            "in space",
            "deep space",
        }
    ),
    "hospital": frozenset(
        {
            "hospital",
            "hospital interior",
            "hospital hallway",
            "hospital corridor",
            "hospital room",
            "clinic",
            "ward",
            "indoor hospital",
        }
    ),
    "police_station": frozenset(
        {
            "police station",
            "outside a police station",
            "police precinct",
            "station exterior",
        }
    ),
    "outdoor_road": frozenset(
        {
            "road",
            "street",
            "outdoor road",
            "highway",
            "daytime street",
        }
    ),
    "desert": frozenset({"desert", "unrelated desert", "dunes"}),
}

# Clusters that contradict each other when both are explicit
_LOCATION_CONTRADICTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("spacecraft_interior", "hospital"),
        ("spacecraft_interior", "desert"),
        ("spacecraft_interior", "outdoor_road"),
        ("outer_space", "hospital"),
        ("outer_space", "desert"),
        ("hospital", "desert"),
        ("hospital", "outdoor_road"),
        ("police_station", "desert"),
        ("police_station", "hospital"),
    }
)

_RELATION_COMPAT: dict[str, frozenset[str]] = {
    "beside": frozenset({"beside", "next_to", "near", "standing beside", "standing near"}),
    "inside": frozenset({"inside", "in", "sitting in", "enters", "entering", "entered"}),
    "outside": frozenset({"outside", "exterior"}),
    "above": frozenset({"above", "over", "orbiting", "orbiting above"}),
    "wearing": frozenset({"wearing", "in", "dressed in"}),
    "looking_at": frozenset({"looking at", "looking forward", "looking directly forward", "staring"}),
}

# Allowed transitions when contract permits narrative change
_RELATION_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("beside", "inside"),
        ("outside", "inside"),
        ("beside", "entering"),
        ("near", "inside"),
    }
)


def _clean(text: str) -> str:
    t = str(text or "").lower().strip()
    t = re.sub(r"[/_,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def location_cluster(label: str) -> str:
    t = _clean(label)
    if not t:
        return ""
    for cid, words in _LOCATION_CLUSTERS.items():
        if t in words:
            return cid
        # substring membership for sub-locations
        for w in words:
            if len(w) >= 5 and (w in t or t in w):
                return cid
    return ""


def classify_location_pair(a: str, b: str) -> dict[str, Any]:
    """same | compatible_sublocation | intentional_transition | contradiction | unknown"""
    ca, cb = _clean(a), _clean(b)
    if not ca or not cb:
        return {"class": "unknown", "reason": "insufficient_location_observation"}
    if ca == cb:
        return {"class": "same", "reason": "exact_match"}
    ha, hb = location_cluster(ca), location_cluster(cb)
    if ha and hb:
        pair = tuple(sorted((ha, hb)))
        if ha == hb:
            return {"class": "compatible_sublocation", "cluster": ha, "reason": "same_cluster"}
        if pair in _LOCATION_CONTRADICTIONS or (ha, hb) in _LOCATION_CONTRADICTIONS or (hb, ha) in _LOCATION_CONTRADICTIONS:
            return {"class": "contradiction", "clusters": [ha, hb], "reason": "cluster_contradiction"}
        return {"class": "unknown", "clusters": [ha, hb], "reason": "distinct_clusters_no_rule"}
    # one or both unclustered — prefer UNKNOWN over PASS
    if ca in cb or cb in ca:
        return {"class": "compatible_sublocation", "reason": "substring_compatible"}
    return {"class": "unknown", "reason": "unclustered_labels"}


def normalize_relation_label(label: str) -> str:
    t = _clean(label)
    if not t:
        return t
    # Exact / alt-set membership first
    for canon, alts in _RELATION_COMPAT.items():
        if t == canon or t.replace("_", " ") == canon.replace("_", " ") or t in alts:
            return canon
    # Phrase containment — longest first; short tokens (e.g. "in") require word boundaries
    phrases: list[tuple[str, str]] = []
    for canon, alts in _RELATION_COMPAT.items():
        phrases.append((canon.replace("_", " "), canon))
        for a in alts:
            phrases.append((a, canon))
    phrases.sort(key=lambda x: len(x[0]), reverse=True)
    for phrase, canon in phrases:
        if len(phrase) <= 2:
            if re.search(rf"\b{re.escape(phrase)}\b", t):
                return canon
            continue
        if phrase in t:
            return canon
    return t


def classify_relationship_pair(
    a_labels: list[str],
    b_labels: list[str],
    *,
    narrative_change_allowed: bool = False,
    allowed_transitions: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if not a_labels or not b_labels:
        return {"class": "unknown", "reason": "insufficient_relationship_observation"}
    na = {normalize_relation_label(x) for x in a_labels if x}
    nb = {normalize_relation_label(x) for x in b_labels if x}
    if not na or not nb:
        return {"class": "unknown", "reason": "empty_after_normalize"}
    if na & nb:
        return {"class": "same", "reason": "shared_relation", "relations": sorted(na & nb)}
    allowed = set(_RELATION_TRANSITIONS)
    for t in allowed_transitions or []:
        if len(t) == 2:
            allowed.add((str(t[0]), str(t[1])))
            allowed.add((normalize_relation_label(t[0]), normalize_relation_label(t[1])))
    for x in na:
        for y in nb:
            if (x, y) in allowed or (y, x) in allowed:
                if narrative_change_allowed or (x, y) in _RELATION_TRANSITIONS:
                    return {
                        "class": "valid_transition",
                        "from": x,
                        "to": y,
                        "reason": "allowed_relationship_transition",
                    }
    if narrative_change_allowed:
        return {"class": "valid_transition", "reason": "contract_allows_narrative_change", "from": sorted(na), "to": sorted(nb)}
    # opposite check via ContinuityTracker helper when possible
    try:
        from pipeline.visual_semantic.continuity import _relationships_contradict

        hit = _relationships_contradict(list(a_labels), list(b_labels))
        if hit:
            return {"class": "contradiction", "reason": "continuity_opposite", "evidence": hit}
    except Exception:
        pass
    return {"class": "contradiction", "reason": "relationship_mismatch", "from": sorted(na), "to": sorted(nb)}


def normalize_observation_fields(obs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with normalized labels for comparison (evidence still keeps raw)."""
    out = dict(obs or {})
    out["_normalized"] = {
        "location": _clean(str(out.get("observed_location") or "")),
        "location_cluster": location_cluster(str(out.get("observed_location") or "")),
        "relationships": [normalize_relation_label(x) for x in (out.get("observed_relationships") or []) if x],
        "subjects": [_clean(x) for x in (out.get("observed_subjects") or []) if x],
        "entities": [_clean(x) for x in (out.get("observed_entities") or []) if x],
        "actions": [_clean(x) for x in (out.get("observed_actions") or []) if x],
        "environment": _clean(str(out.get("observed_environment") or "")),
        "camera": _clean(str(out.get("camera_observation") or "")),
        "lighting": _clean(str(out.get("lighting_observation") or "")),
    }
    return out


def contract_requires(contract: dict[str, Any], constraints: dict[str, Any], dim: str) -> bool:
    """Only explicit contract/constraint dims become hard checks."""
    c = dict(contract or {})
    k = dict(constraints or {})
    if dim == "location":
        return bool(k.get("require_location") or c.get("require_location") or c.get("location") or c.get("required_location"))
    if dim == "relationship":
        return bool(
            k.get("require_relationship")
            or c.get("must_persist_relationships")
            or c.get("relationships")
            or c.get("required_relationships")
        )
    if dim == "entity":
        return bool(k.get("require_entity") or c.get("required_entities") or c.get("entities") or c.get("must_appear"))
    if dim == "camera":
        return bool(k.get("explicit_camera") or c.get("explicit_camera") or c.get("camera_continuity"))
    if dim == "lighting":
        return bool(k.get("explicit_lighting") or c.get("explicit_lighting") or c.get("lighting_continuity"))
    return False
