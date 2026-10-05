# C11 Interventions (run mr_a077c5b821db4464)

## INT-002 — should_skip_gemini_critic signature drift

| Field | Value |
|-------|-------|
| intervention_id | INT-002 |
| timestamp | 2026-09-06T11:34:00Z |
| run_id | mr_a077c5b821db4464 |
| case_id | C11-LONG / C11-SHORT |
| defect | `should_skip_gemini_critic() got an unexpected keyword argument 'visual_passed'` |
| evidence | jobs 2108/2109 error; scene_builder call sites pass visual_passed |
| suspected_root_cause | Function signature lagged callers/tests; TypeError aborted generation after SceneContract passed |
| files_changed | `pipeline/agent_playbook.py` |
| functions_changed | `should_skip_gemini_critic` |
| change_summary | Accept `visual_passed`; skip only when AMP_SKIP_GEMINI_CRITIC opted in + agent passed + visual_passed + not needs_visual_regen |
| reason | Restore documented quality-first cost-saver contract; unblock real generation |
| targeted_tests | Inline assertions + `test_skip_critic_opt_in_only` — PASS |
| pre_fix_state | GENERATION FAILED ~34s into execute |
| post_fix_state | Signature/semantics restored |
| resume_decision | Fresh C11 re-run (r3) |

Also references INT-001 from prior run (`customer_plan_adapter` must_show).
