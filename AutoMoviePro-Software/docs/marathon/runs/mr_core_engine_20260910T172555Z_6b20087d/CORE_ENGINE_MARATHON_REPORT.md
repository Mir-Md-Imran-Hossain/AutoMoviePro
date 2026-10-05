# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260910T172555Z_6b20087d`  
**Verdict:** `PASS_WITH_LIMITATION`  
**Started:** 2026-09-10T17:25:55Z  
**Ended:** 2026-09-10T18:01:12Z  
**Runtime_sec:** 2116.2  
**Topic:** How JWST mid-infrared spectra fingerprint exoplanet atmospheres (b5322229)  
**Job:** 2333  
**Work dir:** `E:\All Updaye Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\data\customer_generation_work\c11_marathon_customer\job2333`  

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
    "ts": "2026-09-10T17:25:56Z",
    "reason": "duplicate_topic_preflight",
    "detected_problem": "matched=space science",
    "action": "suffix_unique_concrete_angle",
    "authority": "pipeline.product_registry.is_duplicate",
    "result": "topic_rewritten"
  },
  {
    "intervention_id": "INT-002",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_1",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-003",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_2",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-004",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_3",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-005",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_4",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-006",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_retry",
    "detected_problem": "Duplicate/conflict: space science",
    "action": "retry_unique_topic_5",
    "authority": "set_manual_topic",
    "result": "still_blocked"
  },
  {
    "intervention_id": "INT-007",
    "ts": "2026-09-10T17:25:56Z",
    "reason": "topic_duplicate_cert_bypass",
    "detected_problem": "registry_false_match_or_saturated",
    "action": "set_manual_topic_allow_duplicate",
    "authority": "cert_core_engine_real_marathon",
    "result": "ok"
  },
  {
    "intervention_id": "INT-008",
    "ts": "2026-09-10T17:26:03Z",
    "reason": "use_customer_approved_plan_lock",
    "detected_problem": "generate_video re-entry intelligence DUPLICATE on reused niche topics",
    "action": "write_director_plan + c06e lock before generate_video",
    "authority": "customer_plan_adapter + generate_video customer_approved_lock",
    "result": "lock_written"
  }
]
```

## Failures / UNKNOWN

```json
{
  "failures": [],
  "unknowns": [
    "UR_RTL_SHAPING_UNKNOWN_NO_DEDICATED_RENDER_SHAPING_PROOF"
  ]
}
```

## Artifacts pointer

- `08_ARTIFACTS.json`
- `07_GENERATION_RESULT.json` / `07_GENERATION_ERROR.json`
- job workdir gates + `LOCALIZED/`

## Verdict reasons

```json
[
  "VOICE_ACOUSTIC_UNKNOWN",
  "UR_RTL_SHAPING_UNKNOWN",
  "creative_quality_requires_human_review"
]
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
