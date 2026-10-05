# C11 Certification — Final (canonical run)

**Checkpoint:** `C11-REAL-MARATHON-BLOCKED`  
**Primary run ID:** `mr_89cec56060114780`  
**Session:** `ms_97920ba404d74f35`  
**Prior failed runs (pre-fix):** `mr_5c5e3931ff484ff5`, `mr_a077c5b821db4464`  
**Niche:** `space science`  
**Topic:** `space science topic angle 6 for C11 Marathon Channel` (BUILD-04G reserve / manual commit; placeholder-quality topic — documented limitation)  
**Total runtime (final attempt):** ~381.5 s  
**Code changes during C11:** **YES** (2 minimal interventions)

---

## Executive verdict

The Marathon **attempted REAL** customer-queue generation (`CUSTOMER_APPROVED_PLAN`, `deterministic_fixtures=False`) with configured Google / Agnes / YouTube / Groq / Cerebras / OpenRouter keys present.

Two **genuine code defects** were discovered and minimally fixed (INT-001, INT-002). After those fixes, generation progressed past SceneContract into AV critic / publishability, then **fail-closed** on:

`Publishability gate blocked: creative_regenerate_required (creative=REGENERATE_REQUIRED)`

with concurrent **provider environment failures**:

- Groq script/critic models: 404 model not accessible
- Cerebras models: 404 model_not_found
- Gemini critic: `gemini-flash-latest` 503 UNAVAILABLE; `gemini-2.5-flash` 404 no longer available to new users
- AV critic exhausted keys

**No final LONG/SHORT video files were verified.**  
**No false PUBLISHED / COMPLETED claims.**

Checkpoint chosen: **BLOCKED** — provider/model availability prevents completing a valid end-to-end certification without weakening quality/publishability gates (forbidden).

---

## Honesty matrix

| Stage | Classification |
|-------|----------------|
| Topic intelligence research | REAL attempted (Google keys) |
| Script LLM (Groq/Cerebras primary) | PROVIDER_NOT_CONFIGURED / model access FAIL → chain/fallback |
| Generation path | REAL (`generate_video`, not fixtures) |
| SceneContract | PASS after INT-001 |
| AV critic / Gemini | BLOCKED / exhausted |
| Publishability | FAIL-CLOSED (`REGENERATE_REQUIRED`) — correct |
| Customer approval | APPROVAL_BLOCKED (no artifact) |
| YouTube publish | MOCK path labeled (no OAuth channel session / no CAPTCHA bypass) |

---

## Interventions applied

### INT-001 — `customer_plan_adapter.build_director_plan_from_production_plan`
- Defect: `missing_must_show` → SceneContract blocked all jobs
- Fix: derive `must_show` + `shot` from existing plan intent
- Regression: C06E **169 OK**

### INT-002 — `agent_playbook.should_skip_gemini_critic`
- Defect: unexpected kwarg `visual_passed` TypeError mid-generation
- Fix: restore opt-in skip semantics matching existing tests
- Targeted: `test_skip_critic_opt_in_only` PASS

---

## Video inventory

### LONG
- final video path: **NOT PRODUCED**
- verification: N/A
- publishability: BLOCKED / REGENERATE_REQUIRED
- publication: not attempted successfully

### SHORT
- final video path: **NOT PRODUCED**
- verification: N/A
- publishability: BLOCKED / REGENERATE_REQUIRED
- publication: not attempted successfully

---

## Carry-forward issues

1. Groq/Cerebras configured keys cannot access expected model IDs (environment/provider).
2. Gemini critic model IDs include retired/`high demand` models — needs careful provider-contract update (not done here to avoid global provider redesign mid-Marathon).
3. Topic reserve produced placeholder “topic angle N” text — niche selection quality poor for certification storytelling.
4. Live YouTube OAuth channel session not established — publish remains MOCK-labeled.
5. Pre-existing `test_scene_contract.test_attach_history_plan` FAIL (history plan missing must_show) — not modified; not used to weaken gates.

---

## Authority audit

C11 did **not** create second job/queue/scheduler/retry/idempotency/quality/repair/render/publish/event/continuity engines.  
C10 remains observation-only.  
SceneContract / publishability gates were **not** weakened.

---

## NEXT ACTION

**STOP AND REVIEW REPORT**

Do not start C12 / website / payment / mobile / marketing / autonomous self-repair.
