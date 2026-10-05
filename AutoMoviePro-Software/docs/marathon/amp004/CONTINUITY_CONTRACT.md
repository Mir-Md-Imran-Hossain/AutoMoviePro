# Continuity Contract (Frozen)

**Authority:** একমাত্র `ContinuityTracker` architecture  
**Module:** `pipeline/visual_semantic/continuity.py` (extend later — নতুন engine নয়)  
**Production code changed:** `false`

---

## Scope (minimum frozen fields)

| Domain | Track |
|--------|-------|
| CHARACTER | identity / appearance_ref |
| OBJECT / PROP | important_objects, state |
| WARDROBE | wardrobe |
| LOCATION | location |
| ENVIRONMENT | environment cues |
| TIME | time_context |
| LIGHTING | lighting (future field) |
| CAMERA LANGUAGE | camera_language (future) |
| ACTION STATE | ongoing_action |
| POSE/POSTURE | posture |
| SPATIAL RELATIONSHIP | via SceneIntent EntityRelation |
| STATE TRANSITIONS | causal/state notes |

---

## Binding

Continuity state **canonical scene identity**-এর সাথে bind:

`scene_id` + `dialogue_id` + `revision_id` (+ job_id)

---

## Policy

| Situation | Behavior |
|-----------|----------|
| `continuity_expected=true` + unexplained break | HARD (critical) or HIGH → block/repair |
| `narrative_change_allowed=true` + `continuity_exception_reason` | Allowed |
| Tracker not passed | Mandatory scenes: treat as gap (PHASE-03 wires always-on) |

---

## Forbidden

- Multiple independent continuity engines  
- Continuity state without scene identity  
- Silent accept of unexplained wardrobe/location/character drift when expected  

---

## PHASE-03

Production Continuity — implement later; এই freeze শুধু authority।
