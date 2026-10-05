# Script API Cost Report — BUILD-04C

Offline mock suite (`scripts/test_build04c_script_runtime.py`).

| Metric | Value |
|--------|-------|
| Script requests (duplicate pairs) | 50 |
| Mock provider invocations | 25 |
| Results reused | 25 |
| Duplicates prevented | 25 |
| Retries (bounded network) | ≤15 (max_attempts=3) |
| Paid API calls in automated tests | **0** |

## Key metric

**duplicate_prevented:** Same ScriptRequest twice → invocation_count remains 1 (test_01, test_24).

## Real provider test

Deferred — requires explicit opt-in (Phase 04C-49). Offline mock coverage complete.
