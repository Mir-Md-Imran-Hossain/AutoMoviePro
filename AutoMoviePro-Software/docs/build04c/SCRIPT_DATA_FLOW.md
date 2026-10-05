# Script Data Flow — BUILD-04C

```
Topic (forced or auto-selected)
      ↓
Research notes / trending context
      ↓
FactPack (optional — FACT_PACK.json / factpack/*.json)
      ↓
ScriptRequestSpec
   • topic_identity
   • fact_pack_hash
   • prompt_version / template_hash
   • niche, video_type, max_seconds
   • blocked_products, channel_specials
      ↓
Fingerprint (BUILD-03 compute_fingerprint, stage=script)
      ↓
IdempotentExecutor claim / reuse
      ↓
plan_niche_production (LLM or fallback)
      ↓
Raw director plan JSON
      ↓
validate_director_plan + validate_script_contract
      ↓
director_plan.json persistence
      ↓
script_provenance record
      ↓
checkpoint
      ↓
Scene generation (scene_builder — out of BUILD-04C scope)
```

## Revision vs retry

| Event | fingerprint |
|-------|-------------|
| Transient failure retry | unchanged |
| Intentional revision (`revision_id`) | new |
| Topic / FactPack / prompt change | new |
| Duplicate-topic replan (blocked list grows) | new (inputs differ) |
