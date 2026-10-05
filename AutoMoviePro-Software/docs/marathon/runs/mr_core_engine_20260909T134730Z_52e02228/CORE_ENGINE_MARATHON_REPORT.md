# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260909T134730Z_52e02228`  
**Verdict:** `FAIL`  
**Started:** 2026-09-09T13:47:30Z  
**Ended:** 2026-09-09T13:47:41Z  
**Runtime_sec:** 11.1  
**Topic:** How lunar polar permanently shadowed craters preserve water ice that Artemis prospectors can map with neutron spectrometers — angle 202609091347  
**Job:** 2301  
**Work dir:** `E:\All Updaye Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\data\customer_generation_work\c11_marathon_customer\job2301`  

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
    "ts": "2026-09-09T13:47:40Z",
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
  "failures": [
    {
      "stage": "TOPIC",
      "error": "suggest_topics() got an unexpected keyword argument 'use_mock'"
    },
    {
      "ok": false,
      "error": "scene_contract_blocked:creative_generation_preflight_blocked (unexplained_transformation)",
      "traceback": "tion.py\", line 43, in apply_production_creative_plan\n    pf = preflight_creative_generation(plan=src, cpp=cpp, scenes=merged_rows, block=block_on_critical)\n         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\creative_production\\preflight.py\", line 168, in preflight_creative_generation\n    raise CreativePreflightError(\"creative_generation_preflight_blocked\", issues=list(dict.fromkeys(issues)))\npipeline.creative_production.preflight.CreativePreflightError: creative_generation_preflight_blocked\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 706, in generate_video\n    _canonical_scenes, scenes = assert_production_scenes_validated(\n                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\scene_runtime.py\", line 338, in assert_production_scenes_validated\n    raise SceneValidationError(str(exc), issues=list(exc.issues)) from exc\npipeline.scene_runtime.SceneValidationError: creative_generation_preflight_blocked (unexplained_transformation)\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\scripts\\cert_core_engine_real_marathon.py\", line 402, in generate_real\n    result = generate_video(\n             ^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 715, in generate_video\n    raise RuntimeError(f\"scene_contract_blocked:{exc}\") from exc\nRuntimeError: scene_contract_blocked:creative_generation_preflight_blocked (unexplained_transformation)\n"
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
