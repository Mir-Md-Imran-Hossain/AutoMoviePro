# Complete Script Callsite Matrix — BUILD-04C

| Callsite | Caller | Provider | Model | Input | Output | Script Contract | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Retry | Recovery | Prod | Status |
|----------|--------|----------|-------|-------|--------|-----------------|-------------|-------------|------------|------------|------------|-------|----------|------|--------|
| `script_bridge.idempotent_plan_niche_production` | video_pipeline | llm_router | purpose-script | ScriptRequestSpec | director_plan.json | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `script_runtime.execute_script_request` | bridge, tests | mock/llm | configurable | ScriptRequestSpec | plan JSON | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `video_pipeline._plan_niche_production_idempotent` | generate_video | via bridge | via bridge | niche/topic/notes | plan | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `niche_director.plan_niche_production` | bridge fallback | llm_router | chain | prompt | plan dict | partial | No* | No* | post-hoc | No | No | router | fallback | Yes | **COVERED** (via bridge) |
| `contract_wiring.wire_script` | trace pipeline | — | — | plan dict | Script | Yes | N/A | N/A | Yes | N/A | N/A | — | — | Contract | **INTENTIONALLY_NON_GENERATING** |
| `domain.adapters.script_from_plan` | wire_script | — | — | plan | Script | Yes | N/A | N/A | pydantic | N/A | N/A | — | — | Contract | **INTENTIONALLY_NON_GENERATING** |
| `ai_providers.generate_script_bundle` | none | llm_router | script | bundle prompt | script bundle | partial | No | No | minimal | No | No | — | — | No | **DOCUMENTED_NON_PRODUCTION** |
| `content_humanizer` rewrite | post-plan | llm_router | script | narration text | rewritten text | N/A | N/A | N/A | N/A | N/A | N/A | — | — | Yes | **INTENTIONALLY_NON_GENERATING** (rewrite, not new script) |
| Dev scripts calling `generate_video` | scripts/* | via pipeline | — | — | — | — | via pipeline | — | — | — | — | — | — | No | **DOCUMENTED_NON_PRODUCTION** |

*Direct calls only occur as bridge fallback on bridge exception.

## Production coverage

All production script **generation** flows through `_plan_niche_production_idempotent` → canonical bridge.
