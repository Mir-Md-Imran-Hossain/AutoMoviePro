# H4 Final Report — Real Production Workflow QA + Hardening

**Date:** 2026-09-03  
**Baseline:** `AMP004-H4-PRE-AUDIT-PASS`  
**Plan:** `docs/marathon/production_hardening/H4_IMPLEMENTATION_PLAN.md`  
**Final status:** `H4-REAL-WORKFLOW-PASS-WITH-LIMITATION`  
**Checkpoint:** `AMP004-H4-REAL-WORKFLOW-PASS-WITH-LIMITATION`  
**Paid API calls:** **0**

---

## 1. Executive Summary

Canonical production workflow remains single-authority and fail-closed. H4 closed the multilingual packaging vs `ready_to_upload` ordering gap (DEF-H4-001), removed the scheduler alternate ready writer, and contained/documented offline E2E soft handoff (DEF-H4-002) without weakening publishability. Focused H4 suite **24/24 PASS**. H1–H3, BUILD-03/04A/04G/04G-H, and Phase-02→10 (**398 PASS**) regressions green. Deferred: VLM/ASR depth, long-form/batch certification, dual prompt LEGACY, plus H2/H3 carry-forwards.

---

## 2. Baseline

| Item | Checkpoint |
|------|------------|
| H1 | `H1-PRODUCTION-RELIABILITY-PASS` |
| H2 | `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION` |
| H3 | `AMP004-H3-PERFORMANCE-COST-PASS-WITH-LIMITATION` |
| H4 Pre-Audit | `AMP004-H4-PRE-AUDIT-PASS` |
| Phase-10 | `AMP004-PHASE10-PASS` |

---

## 3. H4 Pre-Audit Reference

See `H4_PRE_AUDIT.md`. Findings DEF-H4-001…006 + carry-forwards.

---

## 4. Implementation Plan

Executed per `H4_IMPLEMENTATION_PLAN.md`. No WorkflowEngine2. No new publishability/continuity/idempotency/render authorities.

---

## 5. Canonical Workflow

```
generate_video
→ SceneIntent / ContinuityTracker
→ generation (BUILD-03 bridges)
→ Artifact Verification
→ Audio / Localization / Creative / RI gates
→ BUILD-04F + evaluate_publishability
→ [multilingual] localize_master_clip + localization_packages_complete
→ upload_status=ready_to_upload
```

EN-only: packaging step skipped; ready after publishability.  
Multilingual: packaging **before** ready; incomplete/skip → raise; job stays `generated`.

---

## 6. Single-Scene E2E

| Result | Evidence |
|--------|----------|
| PASS | `run_e2e_industrial` + H4 `test_20` |
| Invalid/missing → no upload | H4 `test_21`–`23`, inject matrix |

---

## 7. Multi-Scene E2E

| Result | Evidence |
|--------|----------|
| ≥3 scenes, unique canonical IDs | H4 `test_32` |
| Continuity inject fail-closed | H4 `test_30` |
| Wrong project no upload | H4 `test_31` |

---

## 8. Continuity

ContinuityTracker sole authority. No second representation. Injects fail-closed (P09 + H4).

---

## 9. Artifact Verification

Mandatory. UNKNOWN ≠ PASS. Missing visual → FAIL_DETECTED, no ready. VLM depth still PARTIAL (DEF-H4-003).

---

## 10. Audio / TTS

AudioPlan + `tts_bridge` + audio gate retained. H3 TTS discipline preserved. No duplicate engine. Paid TTS = 0 this run.

---

## 11. Localization

Gate before publish (multilingual). Packaging now before ready. Helper: `localization_packages_complete`.

---

## 12. Multilingual E2E

| Aspect | Classification |
|--------|----------------|
| Gate + packaging order | PASS (source + unit + fail-closed) |
| Full paid-free remux of all locales this session | PARTIAL (offline unit + architecture; no live Google TTS) |
| Locale isolation | PASS (H3 dedupe + package completeness) |

---

## 13. Creative Quality

BUILD-04F sole. Publishability AND retained. No fake PROVIDER_VERIFIED.

---

## 14. Cross-Modal

`multimodal_consistency` + publishability. UNKNOWN mandatory inject → no upload. VLM/ASR: UNKNOWN/PARTIAL documented.

---

## 15. Rendering

`idempotent_compose_final_video` + `ffmpeg_exec`. Inject `ffmpeg_fail` → no upload.

---

## 16. Rendering Integrity

RI gate fail-closed. Phase-08/10 regression PASS.

---

## 17. ready_to_upload Authority

| Writer | Status |
|--------|--------|
| `generate_video` | Sole production writer after publishability (+ multilingual packages) |
| E2E `UPLOAD_STATUS.json` | Only if `publishable` |
| `scheduler_service._pregenerate_one` | **No longer forces** ready (H4) |

Invariant: BLOCKED/UNKNOWN/missing gates → not ready. Proven by inject matrix + publishability unit tests.

---

## 18. Failure Injection

H4 matrix (8 injects) + P09: never `ready_to_upload`. Expected FAIL_DETECTED / IDENTITY_BREAK / NOT_PUBLISHABLE.

---

## 19. Recovery

BUILD-03 reuse/resume retained. Classification: SAFE_TO_RESUME for checkpointed stages; live paid mid-call still PARTIAL/UNKNOWN.

---

## 20. Repeated Requests

BUILD-03 fingerprint reuse (H4 `test_70` + BUILD-03 suite). Identical inputs → one provider execution.

---

## 21. Long-Form

**PARTIALLY_SUPPORTED** — largest safe offline fixture only; not industrial long-form certified.

---

## 22. Batch Isolation

**PARTIALLY_SUPPORTED** — two work_dir jobs isolated (H4 `test_80`); large multi-project load NOT_SUPPORTED as certified. Shared Google circuit: DEF-H3-009.

---

## 23. Resume/Crash

BUILD-03 crash-after-result reuse PASS. Full production crash matrix: PARTIAL (prior evidence).

---

## 24. Observability

E2E evidence includes job_id, stages, soft_handoff, publishability. H3 usage ledger when work_dir used. H2 redaction retained. No second telemetry.

---

## 25. Security Regression

H2 suite **20/20 PASS** (within 41 H1–H3). AMP_SKIP blocked in PRODUCTION. No admin/admin123 production fallback. dry_run retained.

---

## 26. H3 Performance/Cost Regression

H3 suite **12/12 PASS**. TTS/loc reuse, retry bounds, COST_NOT_DETERMINABLE retained.

---

## 27. Focused Tests

`scripts/test_amp004_h4_real_workflow.py` → **24/24 PASS**

---

## 28. Full Regression

| Suite | Result |
|-------|--------|
| H1 reliability | 9/9 PASS |
| H2 security/config | 20/20 PASS |
| H3 performance/cost | 12/12 PASS |
| BUILD-03 + 04A + 04G + 04G-H | 59/59 PASS |
| Phase-02 → Phase-10 | **398/398 PASS** |
| DEF-AMP004-011 (H1 stress) | PASS |

---

## 29. Paid API Usage

**0**

---

## 30. Findings Closed

| ID | Fix | Evidence |
|----|-----|----------|
| DEF-H4-001 | localize before ready; `localization_packages_complete`; multilingual fail-closed | `video_pipeline.py`, H4 tests 01/10–13 |
| DEF-H4-002 | `allow_soft_handoff`; evidence + UPLOAD_STATUS flags; hard mode available; production never soft-handoffs | `runner.py`, `evidence.py`, H4 40–41 |
| Scheduler alternate ready | Removed forced `ready_to_upload` | `scheduler_service.py`, H4 test_02 |
| DEF-H4-006 | NOT_APPLICABLE_WITH_EVIDENCE — H3 disciplined fallback remains; no H4 duplicate TTS | H3 regression |

**CLOSED count:** 2 (DEF-H4-001, DEF-H4-002). Scheduler unsafe ready writer removed as part of 001 authority hardening. DEF-H4-006 = N/A.

---

## 31. Findings Deferred

| ID | Reason | Risk | Future |
|----|--------|------|--------|
| DEF-H4-003 | VLM/ASR incomplete | Semantic depth | Observation phases |
| DEF-H4-004 | Long-form/batch not load-certified | Ops scale | Dedicated cert |
| DEF-H4-005 | Dual prompt LEGACY | Complexity | Merge DEF-AMP004-005 |
| DEF-H2-007 | Channel keys at rest | Sec | KMS |
| DEF-H3-008/009/010 | Critic skip / shared circuit / repair overlap | Cost/quality | H3+ |

**DEFERRED count:** 3 H4 + carry-forwards documented.

---

## 32. Known Limitations

- Offline E2E soft handoff when SceneIntent enrichment absent (`allow_soft_handoff=True` default); production hard-fails.
- Full multilingual remux without paid/mock TTS not live-executed this session (order + completeness enforced).
- VLM/ASR semantic verification PARTIAL.
- Long-form / large batch not certified.
- Monetary cost COST_NOT_DETERMINABLE.

---

## 33. Evidence Matrix

| Workflow | Result | Evidence | Authority | Notes |
|----------|--------|----------|-----------|-------|
| Canonical call graph | PASS | Source + P09/P10 | generate_video | Connected |
| Single-scene E2E | PASS | H4 + P09 | e2e runner | Offline mock |
| Multi-scene | PASS | H4 + P09 | ContinuityTracker | Isolates |
| Continuity | PASS | Inject | ContinuityTracker | Fail-closed |
| Artifact verification | PASS | Inject/P04 | AV production | Mandatory |
| Audio/TTS | PASS | P05/H3 | AudioPlan/tts_bridge | Paid=0 |
| Localization packaging | PASS | Source+unit | localization | Pre-ready |
| Multilingual remux live | PARTIAL | Unit/arch | localize_master_clip | No paid TTS |
| Creative | PASS | P07/P02 | BUILD-04F | AND |
| Cross-modal | PASS | Inject | multimodal | UNKNOWN≠PASS |
| Render/RI | PASS | P08/P10 | render_bridge/RI | |
| ready_to_upload | PASS | Source+H4 | generate_video | One writer |
| Failure inject | PASS | H4 matrix | Gates | Never ready |
| Repeated request | PASS | H4+BUILD-03 | IdempotentExecutor | Reuse |
| Long-form | PARTIAL | Classification | — | Not certified |
| Batch | PARTIAL | H4 dual job | work_dir | Not load-cert |
| Resume | PARTIAL | BUILD-03 | CheckpointStore | Prior |
| Observability | PASS | Evidence JSON | e2e evidence | soft_handoff field |
| H1/H2/H3 | PASS | Suites | — | |
| Phase02–10 | PASS | 398 | — | |

---

## 34. Code Quality Audit

- No duplicate workflow/publishability/render/TTS engines.
- Soft handoff limited to offline E2E; labeled; cannot skip publishability.
- Scheduler no longer unsafe ready writer.
- No secret logging; H2 redaction intact.
- No speculative refactor.

---

## 35. Acceptance Criteria

All H4 PASS criteria met except honest PARTIAL classifications for long-form/batch/VLM → **PASS-WITH-LIMITATION**. No P0/P1. Paid APIs=0. Regressions green.

---

## 36. Final Status

```
H4-REAL-WORKFLOW-PASS-WITH-LIMITATION
```

---

## 37. Exact Checkpoint

```
AMP004-H4-REAL-WORKFLOW-PASS-WITH-LIMITATION
```

**STOP.** Do not start H5 or Phase-11.
