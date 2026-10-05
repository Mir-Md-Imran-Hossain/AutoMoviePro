# H1 Implementation Plan — Production Reliability & Concurrency Hardening

**Baseline checkpoint:** `AMP004-H1-PRE-AUDIT-PASS`  
**Date:** 2026-09-03  

## Canonical authorities (DO NOT REPLACE)

| Concern | Canonical location |
|---------|-------------------|
| Idempotency lookup / claim | `pipeline.idempotency.store.IdempotencyStore` (`get`, `atomic_claim`, `put`) |
| Orchestration | `pipeline.idempotency.executor.IdempotentExecutor.execute` |
| Fingerprint | `pipeline.idempotency.fingerprint.compute_fingerprint` |
| Retry classification | `pipeline.idempotency.retry_policy.retry_decision` |
| Checkpoint | `pipeline.idempotency.checkpoint_store.CheckpointStore` |
| Resume | `pipeline.idempotency.resume_resolver.ResumeResolver` |
| Reserve consume | `pipeline.intelligence.reserve_queue.consume_top` / `update_reserve` |
| Visual provider gate | `pipeline.idempotency.visual_runtime.execute_visual_request` → executor |
| GenerationCache | `pipeline.generation_cache.GenerationCache` (legacy nested; not second authority) |

## DEF-AMP004-011 root cause (proven)

Windows `Path.resolve()` may return either:

- `C:\Users\...\IDEMPOTENCY.json`
- `\\?\C:\Users\...\IDEMPOTENCY.json`

`IdempotencyStore._store_lock` keyed on `str(path.resolve())` without normalizing → **two thread locks for one file** → both workers `atomic_claim` succeed → dual `provider_fn` entry.

## Fix plan (extend existing only)

1. Normalize lock keys (strip `\\?\`, case-fold on Windows).
2. Add minimal process advisory file lock around store/reserve/checkpoint/cache critical sections.
3. No new engines; fingerprints/retry/publishability unchanged.
