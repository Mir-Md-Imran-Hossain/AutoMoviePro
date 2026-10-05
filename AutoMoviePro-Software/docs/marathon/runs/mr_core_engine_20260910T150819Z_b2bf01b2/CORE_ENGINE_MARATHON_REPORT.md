# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260910T150819Z_b2bf01b2`  
**Verdict:** `FAIL`  
**Started:** 2026-09-10T15:08:19Z  
**Ended:** 2026-09-10T15:08:20Z  
**Runtime_sec:** 0.8  
**Topic:** Verified space science mechanism brief 20260910150820-6a5aafef: how mission telemetry confirms instrument calibration under flight stress  
**Job:** None  
**Work dir:** `None`  

## Scope separation

- Customer entitlement / payment / website admin: **OUT OF SCOPE** (not forged)
- DB `languages_json` before: `['en', 'bn']`
- Cert overlay languages (in-memory only): `['en', 'bn', 'hi', 'ur', 'ta', 'ml']`
- YouTube publish: **NO**
- Mock production claimed as PASS: **NO**

## Checkpoints

See `HEALTH_TIMELINE.jsonl` and `checkpoints.json` (≈10 min watchdog).

## Interventions

```json
[
  {
    "intervention_id": "INT-001",
    "ts": "2026-09-10T15:08:19Z",
    "reason": "duplicate_topic_preflight",
    "detected_problem": "matched=space science",
    "action": "suffix_unique_concrete_angle",
    "authority": "pipeline.product_registry.is_duplicate",
    "result": "topic_rewritten"
  },
  {
    "intervention_id": "INT-002",
    "ts": "2026-09-10T15:08:20Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_1",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-003",
    "ts": "2026-09-10T15:08:20Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_2",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-004",
    "ts": "2026-09-10T15:08:20Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_3",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-005",
    "ts": "2026-09-10T15:08:20Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_4",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-006",
    "ts": "2026-09-10T15:08:20Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_5",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  }
]
```

## Failures / UNKNOWN

```json
{
  "failures": [],
  "unknowns": []
}
```

## Artifacts pointer

- `08_ARTIFACTS.json`
- `07_GENERATION_RESULT.json` / `07_GENERATION_ERROR.json`
- job workdir gates + `LOCALIZED/`

## Verdict reasons

```json
[]
```


## POST-MARATHON IMPROVEMENT BACKLOG

| ID | Sev | Issue | Recommended |
|----|-----|-------|-------------|
| BL-01 | P1 | Duration actualization vs short target if under-length | Extend planning/materialization until observed duration meets contract |
| BL-02 | P1 | Six localized packages incomplete if TTS/localize fails | Provider quota + SCENE_LOCAL completeness |
| BL-03 | P2 | UR RTL shaping UNKNOWN | FriBidi/HarfBuzz or observed burn-in proof (future) |
| BL-04 | P2 | Acoustic VoiceIdentity UNKNOWN | Optional approved embedding provider |
| BL-05 | P2 | Creative/audience retention largely HEURISTIC | Human review + BUILD-04F signals |
| BL-06 | P3 | Cert language overlay vs customer C04 separation UX | Document operator runbook; do not merge into entitlement |


## HARD STOP

No post-marathon feature implementation in this run.
