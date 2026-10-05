# BUILD-04C Pre-Build Architecture

## Current script generator

**Primary engine:** `pipeline/niche_director.py` → `plan_niche_production()`

- Resolves niche pack from `nish_catalog`
- Assembles director prompt (system rules, style pack, AV sync, JSON schema)
- Calls `llm_router.chat_text(purpose="script")`
- Post-processes scenes, English master lock, fallback plan on LLM failure

**Output:** `director_plan.json` dict — `title`, `topic`, `description`, `tags`, `scenes[]` with `narration`, visual fields.

**Canonical domain contract:** `domain/script.py` — `Script`, `ScriptSection`, `Dialogue` built via `domain/adapters.py` → `script_from_plan()`.

## Entry points

| Entry | Production? |
|-------|-------------|
| `video_pipeline.generate_video` → `_plan_niche_production_idempotent` | Yes |
| `app/main.py` `/api/generate` | Yes |
| `app/scheduler_service.py` | Yes |
| `pipeline/live_lab.py` | Yes |
| `ai_providers.generate_script_bundle` | No (no active callers) |
| `contract_wiring/stages.wire_script` | Contract validation only |

## Provider / model

- Router purpose `script`: groq → cerebras → openrouter → huggingface → freetheai → google
- Recorded on plan as `director_provider` when LLM succeeds
- Fallback `_fallback_plan` when all providers fail (no paid API in fallback)

## Prompt source / versioning

- `niche_director.DIRECTOR_SYSTEM`, `ELEMENT_GUIDE`, niche style packs
- `prompt_engineering.director_av_sync_rules`, `director_json_scene_example`
- `prompt_registry.get_prompt_meta("director_system")` → version `v12`
- Template hash: SHA-256 of DIRECTOR_SYSTEM + ELEMENT_GUIDE

## Persistence

- `{work_dir}/director_plan.json` — primary artifact
- `{work_dir}/script_provenance/{fingerprint[:24]}.json` — BUILD-04C provenance
- `{work_dir}/idempotency/` — BUILD-03 store
- `{work_dir}/checkpoints/` — BUILD-03 checkpoints

## BUILD-04C integration (pilot)

```
plan_niche_production (unchanged engine)
        ↓
script_bridge.idempotent_plan_niche_production
        ↓
script_runtime.execute_script_request
        ↓
BUILD-03 IdempotentExecutor
        ↓
script_validation.validate_plan_and_script
        ↓
script_provenance.save_script_provenance
        ↓
checkpoint
```

Pilot entry: `video_pipeline._plan_niche_production_idempotent` wrapping all director plan calls.
