# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260910T150238Z_9816c146`  
**Verdict:** `FAIL`  
**Started:** 2026-09-10T15:02:38Z  
**Ended:** 2026-09-10T15:02:39Z  
**Runtime_sec:** 0.8  
**Topic:** How JWST mid-infrared spectra fingerprint exoplanet atmospheres — cert 202609101502-7cf9870d  
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
    "ts": "2026-09-10T15:02:39Z",
    "reason": "research_live_failed",
    "detected_problem": "None",
    "root_cause": "provider_or_research_runtime",
    "action": "retry_research_mock_labeled",
    "authority": "customer_trs_workflow.run_research"
  }
]
```

## Failures / UNKNOWN

```json
{
  "failures": [],
  "unknowns": [
    "TOPIC_SUGGEST_FALLBACK_TO_MANUAL_CONCRETE"
  ]
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
