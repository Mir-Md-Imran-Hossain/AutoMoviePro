# Script Runtime Migration Matrix — BUILD-04C

| Callsite | Provider | Model | Topic | FactPack | Prompt Ver | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Retry | Recovery | Prod | Tests | Status |
|----------|----------|-------|-------|----------|------------|-------------|-------------|------------|------------|------------|-------|----------|------|-------|--------|
| video_pipeline director plan | llm_router | purpose-script | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | 01–24 | **PASSED** |
| script_bridge | llm_router/mock | purpose-script | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | 01–24 | **PASSED** |
| niche_director direct (fallback) | llm_router | chain | Yes | partial | partial | No | No | post | No | No | router | fallback | fallback | — | **BLOCKED** |
| generate_script_bundle | llm_router | script | Yes | No | partial | No | No | minimal | No | No | — | — | No | — | **BLOCKED** |
| wire_script | — | — | Yes | Yes | N/A | N/A | N/A | Yes | N/A | N/A | — | — | Contract | BUILD-01/02 | **PASSED** |

## Partial generation (04C-33)

Architecture generates **one complete director plan** per request — no section-level split. Not artificially split in BUILD-04C.
