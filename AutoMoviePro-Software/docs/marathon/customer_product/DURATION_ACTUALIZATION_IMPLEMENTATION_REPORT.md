# DURATION ACTUALIZATION — Implementation Report

**Date:** 2026-09-09  
**Gate A verdict:** **PASS**

---

## Pre-audit

See `DURATION_ACTUALIZATION_AND_SHORT_E2E_PUBLISH_PRE_AUDIT.md`.

**Bypass:** RCP-06B enforced max/scene-drop/trim only. Master ffprobe duration was never reconciled to Short 60/120 or Long 180/300 target floors. Plans with 1×~8s beat passed readiness; artifact/render/publishability/`ready_to_upload`/APPROVED all ignored under-target masters.

**Authority conflict:** None (incomplete enforcement, not dual resolver).

---

## Changes (no new engine)

| Area | Change |
|------|--------|
| `pipeline/duration_budget.py` | `validate_plan_meets_target`, `reconcile_rendered_duration`, persist helpers, C11 regression cases; `MIN_ACTUAL_FRACTION_OF_TARGET=0.70` |
| `pipeline/video_pipeline.py` | After `ffprobe_duration(final)` → reconcile → fail-closed before ship |
| `pipeline/quality/publishability.py` | Explicit `duration_status` mandatory when supplied |
| `pipeline/quality/bridge.py` | Load `DURATION_RECONCILIATION.json`; production passes `require_duration_gate=True` |
| `app/customer_production_plan.py` | Embed duration contract; readiness under-target blocks |
| `app/customer_job.py` | APPROVED blocked unless reconciliation PASS |
| `app/customer_plan_adapter.py` | Fixtures → duration UNKNOWN → not publishable / not ready_to_upload |
| `app/customer_generation_orchestrator.py` / `customer_job_automation.py` | Fixtures only set `ready_to_upload` when publishable+ready plane true |

---

## Acceptance checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | C11 short 7.2s blocked | PASS (test_09) |
| 2 | C11 long 8.85s blocked | PASS (test_10) |
| 3 | COMPLETED bypass blocked | PASS |
| 4 | APPROVED bypass blocked | PASS (test_19) |
| 5 | PUBLISHABLE bypass blocked | PASS (test_20 + bridge) |
| 6 | READY_TO_UPLOAD bypass blocked | PASS (test_21 + pipeline raise) |
| 7 | Actual from observation | PASS (ffprobe → reconcile) |
| 8 | Sole Duration Contract authority | PASS |
| 9 | Planned ≠ actual | PASS |
| 10 | UNKNOWN blocks | PASS |
| 11–13 | No silent drop/trim/pad | PASS (policy + tests) |
| 14 | RCP-06B intact | PASS (`test_rcp06b` 15 OK) |
| 15 | BUILD-03 unchanged | PASS |
| 16 | No second duration engine | PASS |

---

## Tests

```
python scripts/test_duration_actualization_short_publish.py  → OK (36, 1 skipped Gate B live)
python scripts/test_rcp06b_duration_contract.py              → OK
python scripts/test_rcp06a_semantic_certification.py         → OK
python scripts/test_phase6j_multimodal_certification.py      → OK
python scripts/test_c05mr_materialization_reuse.py           → OK (140)
```

---

## Notes

- Material floor = **70% of target** (42s short / 126s long). Still fails C11 ~7–9s; does not invent padding.
- Positive duration certification for a real ~60s master is **not** claimed in this Gate A unit suite (controlled numeric PASS only). Full short media proof is Gate B / later runtime cert.
