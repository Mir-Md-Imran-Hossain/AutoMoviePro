# C11 Interventions

## INT-001 — CUSTOMER_APPROVED_PLAN missing SceneContract must_show

| Field | Value |
|-------|-------|
| intervention_id | INT-001 |
| timestamp | 2026-09-06T11:25:00Z |
| prior_run_id | mr_5c5e3931ff484ff5 |
| case_id | C11-LONG / C11-SHORT |
| defect | `scene_contract_blocked:scene_contract_report failed (scene[0]:missing_must_show)` |
| evidence | jobs 2030/2031 error field; director_plan.json scenes lacked `must_show`/`shot` |
| suspected_root_cause | `build_director_plan_from_production_plan` mapped C05-S beats but did not populate SceneContract-required `must_show` + `shot` fields; gate correctly failed closed |
| files_changed | `app/customer_plan_adapter.py` |
| functions_changed | `build_director_plan_from_production_plan` |
| change_summary | Derive `must_show`/`keyword_triggers`/`shot` from existing subject/objects/location/narration intent — does not weaken SceneContract gate |
| reason | Customer approved-plan → generate_video path was structurally unable to pass existing SceneContract preflight |
| targeted_tests | Manual contract preflight PASS; `scripts.test_c06e_canonical_customer_handoff` **169 OK** |
| regression_tests | C06E PASS; `test_scene_contract` still has 1 FAIL in history-plan attach path (unrelated to adapter; scenes 1–6 missing must_show in history plan) |
| pre_fix_state | GENERATION FAILED at scene_contract |
| post_fix_state | Adapter scenes produce SceneContract PASS in isolated probe |
| resume_decision | Invalidate failed run artifacts as pre-fix; start fresh C11 re-run with force_rebuild |

No architectural redesign. SceneContract authority unchanged.
