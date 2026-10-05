# Open-Source Phase 6F — Pre-Audit Report

**Date:** 2026-09-09  
**Verdict:** **AUDIT PASS** — no new ContinuityTracker / semantic gate required

---

## Canonical identity locations

| Concept | Canonical source |
|---------|------------------|
| Character / entity | C05-S `GroundedEntity` / `DirectedVisualBeat.required_entities` + SceneIntent `entities` |
| Object / vehicle | Same + `required_objects` |
| Location | `location_state` / SceneIntent `location` + Phase 6E `normalize.location_cluster` |
| Relationship | `GroundedRelation` / SceneIntent `relations` + Phase 6E `classify_relationship_pair` |
| State transition | ContinuityTracker policy + explicit Visual Contract; observation evidence only in frame_evidence |
| Dialogue↔beat | C05-S `dialogue_id` + `beat_id`; C05-MR `dialogue_id+beat_id` binding |

---

## Safe extension point

`pipeline/observation/frame_evidence/cross_beat.py`

- Projects explicit-contract entities into evidence states  
- Adjacent-beat compare only (N↔N+1)  
- Passes policy questions to ContinuityTracker helpers / Phase 6E normalize  
- **Not** a continuity engine, identity certifier, or semantic gate  

Reuse: `normalize.py`, `temporal.py` patterns, `repair_loop.py`, `ContinuityTracker._relationships_contradict` / extractors.

---

## Decision

Implement evidence-only cross-beat projection + comparison. ContinuityTracker remains sole continuity authority.
