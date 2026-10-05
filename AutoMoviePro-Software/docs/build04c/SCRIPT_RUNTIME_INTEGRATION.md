# Script Runtime Integration — BUILD-04C

## New modules

| Module | Role |
|--------|------|
| `script_request.py` | ScriptRequestSpec, fingerprint |
| `script_validation.py` | Structural validation |
| `script_provenance.py` | Provenance persistence |
| `mock_script_provider.py` | Offline deterministic provider |
| `script_runtime.py` | execute_script_request lifecycle |
| `script_bridge.py` | idempotent_plan_niche_production |

## Modified

| Module | Change |
|--------|--------|
| `video_pipeline.py` | `_plan_niche_production_idempotent` wrapper |

## Lifecycle

```
ScriptRequestSpec → fingerprint → claim → provider → validate → persist → provenance → checkpoint
```

## Pilot

**Entry:** `video_pipeline.generate_video` when `director_plan.json` absent  
**Engine:** `plan_niche_production` unchanged  
**Artifact:** `director_plan.json`

## Reuse paths

1. Idempotency store SUCCEEDED + valid plan
2. Existing `director_plan.json` on disk (skip_generation)
3. GenerationCache by fingerprint-scoped key

Invalid cached plans invalidated before regeneration.
