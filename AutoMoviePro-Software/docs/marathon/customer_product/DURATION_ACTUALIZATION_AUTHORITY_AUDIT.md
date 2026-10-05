# DURATION ACTUALIZATION — Authority Audit

**Date:** 2026-09-09  
**Phase:** DURATION_ACTUALIZATION_AND_SHORT_E2E_PUBLISH_CERT / Gate A

---

## Sole duration authority

| Concern | Authority |
|---------|-----------|
| Short/Long target & max | `pipeline.duration_budget.resolve_duration_contract` |
| Planning max overflow | `validate_timeline_against_contract` (RCP-06B) |
| Planning under-target | `validate_plan_meets_target` (Gate A; same module) |
| Rendered reconciliation | `reconcile_rendered_duration` (Gate A; same module) |
| Persist evidence | `DURATION_CONTRACT.json` + `DURATION_RECONCILIATION.json` |

**Second duration engine created:** NO

---

## Writers inventory

| Symbol | Writer | Routed to duration_budget? |
|--------|--------|----------------------------|
| `target_seconds` / `max_seconds` | `resolve_duration_contract` | YES (canonical) |
| `target_duration_sec` / `max_seconds` on plan | `build_production_plan` / readiness | YES via contract embed |
| Per-beat `duration_sec` | plan adapter / script | Planning clock only; not contract override |
| `actual_duration_sec` | ffprobe in `generate_video` | YES → reconcile |
| Agnes per-clip window | `av_quality_gates.detect_duration_window` | Per-scene only; not master contract |

No competing Short/Long resolver found.

---

## Integration points (Gate A)

1. `evaluate_generation_readiness` — under-target blocks READY_FOR_GENERATION  
2. `generate_video` — after ffprobe, reconcile + raise before ship/publishability  
3. `run_publishability_gate(..., require_duration_gate=True)` from production  
4. `set_customer_approval` — APPROVED requires reconciliation PASS  
5. Deterministic fixtures — duration UNKNOWN → not ready_to_upload  

---

## RCP-06B preserved

- Max ceiling, dropped scenes, mid-dialogue trim guard unchanged  
- Under-target is additive, not a replacement authority  

---

## BUILD-03

Unchanged. Fingerprint authority remains BUILD-03 / `pipeline.idempotency`.
