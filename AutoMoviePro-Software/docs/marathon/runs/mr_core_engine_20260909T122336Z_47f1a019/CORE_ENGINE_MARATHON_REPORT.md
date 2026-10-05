# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260909T122336Z_47f1a019`  
**Verdict:** `FAIL`  
**Started:** 2026-09-09T12:23:36Z  
**Ended:** 2026-09-09T12:23:53Z  
**Runtime_sec:** 16.9  
**Topic:** How James Webb Space Telescope mid-infrared images reveal dust-hidden star nurseries that optical telescopes cannot map  
**Job:** 2298  
**Work dir:** `E:\All Updaye Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\data\customer_generation_work\c11_marathon_customer\job2298`  

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
[]
```

## Failures / UNKNOWN

```json
{
  "failures": [
    {
      "stage": "TOPIC",
      "error": "suggest_topics() got an unexpected keyword argument 'use_mock'"
    },
    {
      "ok": false,
      "error": "INTELLIGENCE_GATE_BLOCKED: c05_trs stage=intelligence detail=DUPLICATE",
      "traceback": "Traceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\scripts\\cert_core_engine_real_marathon.py\", line 338, in generate_real\n    result = generate_video(\n             ^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 229, in generate_video\n    raise RuntimeError(f\"{GATE_BLOCKED_MARKER}: c05_trs stage={trs_handoff.get('stage')} detail={reason}\")\nRuntimeError: INTELLIGENCE_GATE_BLOCKED: c05_trs stage=intelligence detail=DUPLICATE\n"
    }
  ],
  "unknowns": [
    "TOPIC_SUGGEST_FALLBACK_TO_MANUAL_CONCRETE",
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
  "generation_failed_or_no_local_path"
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
