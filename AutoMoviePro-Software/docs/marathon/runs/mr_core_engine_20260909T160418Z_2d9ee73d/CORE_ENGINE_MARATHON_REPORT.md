# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260909T160418Z_2d9ee73d`  
**Verdict:** `FAIL`  
**Started:** 2026-09-09T16:04:18Z  
**Ended:** 2026-09-09T17:05:59Z  
**Runtime_sec:** 3700.5  
**Topic:** How lunar polar permanently shadowed craters preserve water ice that Artemis prospectors can map with neutron spectrometers — angle 202609091604  
**Job:** 2303  
**Work dir:** `E:\All Updaye Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\data\customer_generation_work\c11_marathon_customer\job2303`  

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
    "ts": "2026-09-09T16:05:34Z",
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
      "error": "Scene 5 (beat) AV sync failed hard (best_score=55). Issues: ['wrong_subject', 'visual_anchors_missing'] critical=['wrong_subject', 'visual_anchors_missing']",
      "traceback": "Traceback (most recent call last):\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\scripts\\cert_core_engine_real_marathon.py\", line 402, in generate_real\n    result = generate_video(\n             ^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\video_pipeline.py\", line 1050, in generate_video\n    clip = build_dialogue_clip(\n           ^^^^^^^^^^^^^^^^^^^^\n  File \"E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\pipeline\\scene_builder.py\", line 1835, in build_dialogue_clip\n    raise RuntimeError(\nRuntimeError: Scene 5 (beat) AV sync failed hard (best_score=55). Issues: ['wrong_subject', 'visual_anchors_missing'] critical=['wrong_subject', 'visual_anchors_missing']\n"
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
