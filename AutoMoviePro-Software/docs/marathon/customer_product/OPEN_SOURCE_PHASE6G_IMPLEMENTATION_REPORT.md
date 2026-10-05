# Open-Source Phase 6G — Implementation Report

**Date:** 2026-09-09 (Windows)  
**Customer:** `c11_marathon_customer` / channel `4`  
**Verdict:** **PASS**

---

## Pre-audit

`OPEN_SOURCE_PHASE6G_PRE_AUDIT_REPORT.md` — **AUDIT PASS**.  
No new duration/pacing/audio authority required.

---

## Files

| Path | Role |
|------|------|
| `pipeline/observation/frame_evidence/alignment.py` | Dialogue/visual timelines, temporal coverage, semantic align, adaptive hold recommendation, no-drop invariant |
| `pipeline/observation/frame_evidence/__init__.py` | Exports |
| `pipeline/story_visual_direction.py` | Architecture snapshot flags |
| `scripts/test_phase6g_dialogue_visual_alignment.py` | Tests |
| `scripts/cert_phase6g_dialogue_visual.py` | Live cert |
| `docs/.../OPEN_SOURCE_PHASE6G_*.md` | Reports |
| `docs/.../phase6g_evidence/*` | Evidence |

---

## Behavior

- **Dialogue timeline:** preserves dialogue_id, scene, start/end/duration, text, entities, relationships, actions, location, emotion + customer/job scope.  
- **Visual timeline:** visual_beat_id ↔ dialogue_id, timing, coverage, mode; Duration Contract cited, not overridden.  
- **Temporal coverage:** FULL / PARTIAL / NONE / UNKNOWN (C05-S vocabulary); timing overlap ≠ semantic PASS.  
- **Semantic alignment:** provider_verified observation vs dialogue requirements; keyword-only PASS forbidden.  
- **Boundaries:** meaningful action/entity/relationship/location/emotion changes only — not every sentence; fixed-N switching forbidden.  
- **Adaptive hold:** wraps `decide_visual_hold_policy`; long coherent holds allowed; semantic change recommends new beat; never overrides Duration Contract / audio / dialogue coverage.  
- **No silent drop:** planned dialogue IDs must equal materialized (incl. `covered_dialogue_ids`); else `PRODUCTION_INCOMPLETE:silent_dialogue_drop_forbidden`.

---

## Certification evidence

| Case | Result |
|------|--------|
| 4 dialogues / 3 visual beats / ≥2 semantic changes | Alignment **PASS**; dialogues complete; LIVE observe **PASS** |
| Negative (hospital dialogue vs sci-fi visual) | **FAIL** (LIVE) |
| UNKNOWN | UNKNOWN → semantic blocked → no repair |
| Repair | BUILD-04F VISUAL_ASSET → EXECUTED; whole-video **false**; LIVE re-observe **PASS**; old/new hashes retained |

---

## Paid API

| Metric | Value |
|--------|-------|
| Attempts | **3** |
| Successes | **3** |
| Key mask | `…syGE` |
| Generation invocations | **1** |
| Notes | multi_beat PASS; negative FAIL; repair re-observe PASS |

---

## Tests / regressions

- Phase 6G tests: **27/27 OK**  
- Regressions 6A–6F + RCP-06A–D + RCP-07 + BUILD-03 + C05-S + C05-MR: **REGRESSION_FAILS=0**

---

## Limitations

1. Multi-beat cert uses one LIVE observation projected across dialogue segments for semantic support (plus structural 4↔3 timeline).  
2. Repair `provider_fn` copied the hospital asset as targeted beat replacement (hash changed vs failing PNG); LIVE re-observe still ran.  
3. Adaptive hold is a **recommendation**; production still executes via existing C05-S decompose path.

---

## Authority / AGPL

See `OPEN_SOURCE_PHASE6G_AUTHORITY_AUDIT.md`. OpenMontage AGPL imports/copies = **0**.

---

## HARD STOP

Phase 6G complete. **Do not start Phase 6H** until explicitly requested.
