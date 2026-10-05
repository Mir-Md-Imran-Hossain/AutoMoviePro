# DURATION_ACTUALIZATION_AND_SHORT_E2E_PUBLISH — Pre-Audit

**Date:** 2026-09-09  
**Phase:** Gate A before any Gate B  
**Mode:** Forensic — find bypass; no second duration engine

---

## C11 failure facts

| Job | Type | Actual (ffprobe) | Contract | Job status | Approval | Publishability historically |
|-----|------|------------------|----------|------------|----------|-------------------------------|
| 2273 | short | ~7.2s | target 60 / max 120 | COMPLETED | APPROVED | PUBLISHABLE claimed |
| 2272 | long | ~8.85s | target 180 / max 300 | COMPLETED | APPROVED | PUBLISHABLE claimed |

Plans contained **1 scene / ~8s beat** — not the ~8–18 (short) / ~14–32 (long) beats implied by `planned_scene_count_for_contract`.

---

## Trace: where 8–9s became COMPLETED + APPROVED

```
resolve_duration_contract (duration_budget)     ✅ resolved; DURATION_CONTRACT.json written in generate_video
  → script / production plan                    ⚠️ under-target timeline NOT blocked
  → evaluate_generation_readiness               ⚠️ validate_timeline_against_contract = MAX ONLY
  → director / materialization                  ⚠️ 1 planned scene produced → assert_all_planned_scenes_produced(1,1) OK
  → audio / visual / compose                    ✅ produces ~7–9s master honestly
  → ffprobe_duration(final)                     ✅ observed; NEVER compared to target
  → evaluate_master_shippable                   ⚠️ no master vs contract duration
  → artifact verification                       ⚠️ expected_duration_sec NOT passed from pipeline
  → rendering integrity                         ⚠️ compares to clip-built timeline (self-consistent ~7s)
  → evaluate_publishability                     ⚠️ NO duration dimension
  → upload_status = ready_to_upload             ⚠️ sole writer after publishability PASS
  → set_customer_approval                       ⚠️ requires ready_to_upload only; no duration
  → C11 marathon COMPLETED                      ⚠️ result.ok + file exists
```

### Exact bypass locations

1. **`pipeline/duration_budget.validate_timeline_against_contract`** — max overflow only; no under-target / min scene count.
2. **`pipeline/video_pipeline.generate_video`** — records `duration = ffprobe_duration(final)` then never reconciles to `duration_contract["target_seconds"]`.
3. **`pipeline/quality/publishability.evaluate_publishability`** — no `duration_status`.
4. **`app/customer_job.set_customer_approval`** — trusts `ready_to_upload` only.
5. **Secondary:** deterministic fixture handoff can claim `ready_to_upload` without observed duration (C06E path; not C11 REAL path but same class of false success).

### RCP-06B status

RCP-06B correctly prevents: max overflow, silent scene drop, mid-dialogue hard trim when over max.  
RCP-06B does **not** enforce: actual/rendered duration ≥ material fraction of target.  
**Do not assume RCP-06B alone was sufficient.**

---

## Authority conflict?

| Question | Answer |
|----------|--------|
| Competing Short/Long resolvers? | **No** — `resolve_duration_contract` remains sole |
| Incomplete enforcement? | **Yes** — wiring gap, not a second engine |
| STOP for architecture conflict? | **No** — proceed by integrating reconciliation into `duration_budget` + existing gates |

---

## Minimal fix (Gate A) — no new engine

Extend `pipeline.duration_budget` with:

- `reconcile_rendered_duration(...)` → PASS | FAIL | UNKNOWN + PRODUCTION_INCOMPLETE codes  
- `validate_plan_meets_target(...)` → planning under-target / under-scene blocks  

Wire:

1. `evaluate_generation_readiness` — plan must meet target (not max-only)  
2. `generate_video` after ffprobe — write `DURATION_RECONCILIATION.json`; block before ready_to_upload  
3. `evaluate_publishability` / `run_publishability_gate` — mandatory `duration_status`  
4. `set_customer_approval` — refuse APPROVED if reconciliation FAIL/UNKNOWN/missing when media present  
5. Deterministic handoff — duration_status must not silently PASS without real duration observation  

Preserve RCP-06B max / trim / drop-scene rules unchanged.

---

## Gate B

**Blocked until Gate A PASS.**
