# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260910T035455Z_7e0eafce`  
**Verdict:** `FAIL`  
**Started:** 2026-09-10T03:54:55Z  
**Ended:** 2026-09-10T03:55:05Z  
**Runtime_sec:** 10.2  
**Topic:** How Artemis crews use neutron spectrometers to map lunar polar water ice in 2026  
**Job:** 2310  
**Work dir:** `E:\All Updaye Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\data\customer_generation_work\c11_marathon_customer\job2310`  

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
    "ts": "2026-09-10T03:55:05Z",
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
      "ok": false,
      "error": "scene_contract_blocked:scene[0]: audio_plan_blocked:duplicated_word:twenty (duplicated_word:twenty)",
      "traceback": "Traceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\scene_runtime.py\", line 312, in assert_production_scenes_validated\n    handoff = apply_production_audio_design(\n              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\audio_design\\production.py\", line 140, in apply_production_audio_design\n    raise AudioPreflightError(\npipeline.audio_design.preflight.AudioPreflightError: scene[0]: audio_plan_blocked:duplicated_word:twenty\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 706, in generate_video\n    _canonical_scenes, scenes = assert_production_scenes_validated(\n                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\scene_runtime.py\", line 319, in assert_production_scenes_validated\n    raise SceneValidationError(str(exc), issues=list(exc.issues)) from exc\npipeline.scene_runtime.SceneValidationError: scene[0]: audio_plan_blocked:duplicated_word:twenty (duplicated_word:twenty)\n\nThe above exception was the direct cause of the following exception:\n\nTraceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\scripts\\cert_core_engine_real_marathon.py\", line 495, in generate_real\n    result = generate_video(\n             ^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 715, in generate_video\n    raise RuntimeError(f\"scene_contract_blocked:{exc}\") from exc\nRuntimeError: scene_contract_blocked:scene[0]: audio_plan_blocked:duplicated_word:twenty (duplicated_word:twenty)\n"
    }
  ],
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
