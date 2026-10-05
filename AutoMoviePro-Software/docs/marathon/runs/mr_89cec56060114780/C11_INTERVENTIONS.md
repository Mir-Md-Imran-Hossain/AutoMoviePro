# C11 Interventions (canonical)

See also prior-run notes under mr_5c5e3931ff484ff5 and mr_a077c5b821db4464.

## INT-001
- file: `app/customer_plan_adapter.py`
- function: `build_director_plan_from_production_plan`
- reason: populate SceneContract `must_show`/`shot` from plan intent

## INT-002
- file: `pipeline/agent_playbook.py`
- function: `should_skip_gemini_critic`
- reason: accept `visual_passed`; opt-in skip only

No further interventions applied after publishability/provider critic exhaustion.
