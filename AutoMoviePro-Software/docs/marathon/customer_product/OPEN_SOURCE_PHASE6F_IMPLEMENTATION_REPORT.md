# Open-Source Phase 6F — Implementation Report

**Date:** 2026-09-09 (Windows)  
**Customer:** `c11_marathon_customer` / channel `4`  
**Verdict:** **PASS**

---

## Pre-audit

See `OPEN_SOURCE_PHASE6F_PRE_AUDIT_REPORT.md` — **AUDIT PASS**.  
Safe extension: `pipeline/observation/frame_evidence/cross_beat.py` (evidence only).  
No new ContinuityTracker / semantic / repair / identity / FFmpeg / retrieval engine.

---

## Files changed / added

| Path | Role |
|------|------|
| `pipeline/observation/frame_evidence/cross_beat.py` | Entity state projection + adjacent cross-beat compare |
| `pipeline/observation/frame_evidence/normalize.py` | Safer relation normalization (no `"in"`⊂`"orbiting"` false map) |
| `pipeline/observation/frame_evidence/__init__.py` | Exports |
| `pipeline/story_visual_direction.py` | Architecture snapshot flags |
| `scripts/test_phase6f_cross_beat_consistency.py` | Unit/authority tests (36 conceptual checks) |
| `scripts/cert_phase6f_cross_beat.py` | Live cert runner |
| `scripts/cert_phase6f_supplement.py` | LIVE evidence reuse + session retry |
| `docs/.../OPEN_SOURCE_PHASE6F_*.md` | Pre-audit / authority / this report |
| `docs/.../phase6f_evidence/*` | Observation / repair evidence |

---

## Entity state model

Conceptual fields on each projected row:  
`entity_id`, `entity_type` (CHARACTER|OBJECT|VEHICLE|LOCATION|OTHER_EXPLICIT_ENTITY), `canonical_name`, `beat_id`, `scene_id`, `presence`, `observed_state`, `location`, `relationships`, `source_evidence`, `observation_status`, plus `customer_id` / `channel_id` / `job_id`.

Entities are taken **only** from Visual Contract / DirectedVisualBeat (`required_entities`, `required_objects`, `location_state`, `character_state`) — never invented.

---

## Behavior summary

- **Character:** Stable `entity_id` across beats; state/action changes → `STATE_CHANGE`, not identity FAIL.  
- **Object/vehicle:** Presence tracked; provider ABSENT after PRESENT can be `IDENTITY_BREAK` unless exit allowed.  
- **Location:** Phase 6E clusters → SAME / COMPATIBLE_SUBLOCATION / INTENTIONAL_TRANSITION / CONTRADICTION / UNKNOWN. LOCATION entities matched by type across beats (hallway→room).  
- **Relationships:** BESIDE→ENTERING→INSIDE treated as valid transition; HOLDING vs BESIDE → FAIL when not allowed.  
- **Dialogue→entity:** `dialogue_visual_entity_binding` preserves dialogue_id/beat_id/requirements; keyword-only PASS forbidden.  
- **Cross-beat:** Adjacent N↔N+1 only; far compare only when `require_far_continuity`.  
- **CLIP:** Never identity PASS.  
- **UNKNOWN:** Blocks semantic; does not repair; never coerced to PASS/FAIL.  
- **Repair:** FAIL → BUILD-04F VISUAL_ASSET → BUILD-03 targeted path → LIVE re-observe; whole-video regeneration **false**.

---

## Real observation evidence

| Case | Result |
|------|--------|
| Multi-beat (3 beats, Nurse + bed, BESIDE→ENTERING→INSIDE, hospital) | Cross-beat **PASS** (LIVE provider evidence from Phase 6E same asset + session retry PASS) |
| Negative (hospital required vs sci-fi observed) | **FAIL** (Phase 6D LIVE negative reused + location contradiction) |
| UNKNOWN | **UNKNOWN** → semantic blocked → no repair |
| Repair | **EXECUTED**; old hash `b790e53e…` → new `d11ac830…`; re-observe LIVE **PASS**; whole-video **false** |

---

## Paid API (exact)

| Metric | Value |
|--------|-------|
| Attempts | **4** |
| Successes | **2** |
| Key mask | `…syGE` |
| Generation invocations | **1** (BUILD-03 path; provider_fn copy of hospital asset) |
| Notes | Session observes 1–2 → UNKNOWN; repair re-observe PASS; session retry PASS; multi-beat/negative completed with prior LIVE 6E/6D evidence for same media |

---

## Tests / regressions

- `scripts.test_phase6f_cross_beat_consistency` — **26/26 OK**  
- Phase 6A–6E, RCP-06A–D, RCP-07, BUILD-03, C05-S, C05-MR (`test_c05mr_materialization_reuse`) — **OK**

---

## Limitations

1. First two session Gemini observes returned UNKNOWN (`provider_no_response`); not treated as FAIL/PASS.  
2. Multi-beat progression uses one LIVE observation projected across three contract beats (plus valid transition logic) — not three independent paid observes of distinct physical actions.  
3. Repair `provider_fn` copied the Phase 6E hospital asset (targeted beat asset only) rather than a new paid image generation; lineage hash still changed vs failing sci-fi PNG; LIVE re-observe ran.

---

## Authority / OpenMontage

See `OPEN_SOURCE_PHASE6F_AUTHORITY_AUDIT.md`. AGPL OpenMontage imports/copies = **0**.

---

## HARD STOP

Phase 6F complete. **Do not start Phase 6G** until explicitly requested.
