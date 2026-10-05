# Open-Source Phase 6E — Implementation Report

**Date:** 2026-09-09  
**Verdict:** **PASS**  
**HARD STOP:** Phase 6F not started  
**New engines:** **None**

---

## Pre-audit

`OPEN_SOURCE_PHASE6E_PRE_AUDIT_REPORT.md` → **AUDIT PASS**

Root cause of Phase 6D temporal false FAIL: naïve location string inequality (`interior setting` vs `unspecified interior`).

---

## Files changed / added

| Path | Change |
|------|--------|
| `pipeline/observation/frame_evidence/normalize.py` | **Added** — conservative label normalization |
| `pipeline/observation/frame_evidence/temporal.py` | **Extended** — contract-aware + normalized compare |
| `pipeline/observation/frame_evidence/repair_loop.py` | **Added** — BUILD-04F → BUILD-03 → re-observe orchestration |
| `pipeline/observation/frame_evidence/__init__.py` | Exports |
| `scripts/test_phase6e_temporal_repair.py` | Focused tests |
| `docs/.../OPEN_SOURCE_PHASE6E_*.md` | Reports |
| `docs/.../phase6e_evidence/` | Certification artifacts |

---

## Semantic normalization

Conservative clusters only (spacecraft interior, hospital, desert, etc.).  
Equivalent labels → compatible. Clear contradictions → FAIL. Ambiguity → UNKNOWN (never force PASS).

---

## Temporal / explicit contract

Only dims required by Visual Contract / continuity constraints become hard checks.  
Unspecified camera/lighting → `NOT_REQUIRED` (no hard FAIL).  
Relationship transitions allowed when contract permits (`beside` → `inside`/`enters`).  
Camera/lighting reuse ContinuityTracker family helpers (no duplicated family tables as policy).

**Phase 6D pair after fix:** `PASS` (`compatible_sublocation`)  
**Hospital vs spacecraft:** still `FAIL`

---

## Real FAIL → repair → re-observe

| Step | Result |
|------|--------|
| FAIL source | Phase 6D negative (hospital required on astronaut still) |
| BUILD-04F handoff | `VISUAL_ASSET`, whole-video=false |
| Execution | **EXECUTED** via existing `fallback_image_video` + `idempotent_image_clip_via_build03` |
| Old hash | `b790e53e…34473` |
| New hash | `d11ac830…f046cb` |
| hash_changed | **true** |
| BUILD-03 action | `execute` (fingerprint `aa3949f7…`) |
| Re-observe | LIVE `PROVIDER_FRAME:gemini-3.6-flash` → **PASS** (`provider_verified=true`) |
| Observed | nurse, hospital bed, hospital room |
| Retry | 1 / max 1 |

Evidence: `phase6e_evidence/04_repair_loop.json`

---

## Paid API

| Metric | Value |
|--------|-------|
| Explicit re-observe attempts | **1** |
| Successes | **1** |
| Key mask | `…syGE` |
| Generation provider_invocations (BUILD-03) | **1** |
| Latency (repair+reobserve) | ~120s |
| Marathon / YouTube / multilingual | **0** |

Note: image generation may have used Pollinations/Google inside existing fallback; counted as BUILD-03 `provider_invocations=1` plus 1 critic re-observe.

---

## Tests / regressions

| Suite | Result |
|-------|--------|
| Phase 6E | **20/20 OK** |
| Phase 6A–6D | OK |
| RCP-06A–D, RCP-07 | OK |
| BUILD-03, C05-S, C05-MR | OK |

---

## Limitations

1. Normalization clusters are intentionally small — unclustered labels prefer UNKNOWN.  
2. Repair certification used IMAGE fallback path (BUILD-03), not full Agnes `build_dialogue_clip` stack.  
3. Re-observe expected fields were empty in loop (status PASS is provider visual verdict on repaired asset content); contract-matched hospital content confirmed in observed entities.  
4. No publishability PASS claimed for the job.

---

## OpenMontage AGPL

Imports/copies = **0**.

---

## Acceptance (1–18)

All met. Targeted VISUAL_ASSET repair **executed** with old/new lineage and LIVE re-observation PASS.

**HARD STOP — do not start Phase 6F.**
