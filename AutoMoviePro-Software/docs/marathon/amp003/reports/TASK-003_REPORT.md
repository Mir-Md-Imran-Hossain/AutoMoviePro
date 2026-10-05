# TASK-003 প্রতিবেদন — Global Idempotency + Checkpoint + Recovery

**Marathon:** AMP-003  
**Task:** TASK-003  
**Checkpoint:** AMP003-T003-PASS  
**Verdict:** PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. উদ্দেশ্য

AutoMoviePro-এর global execution layer audit ও hardening — একই logical operation (একই input, identity, fingerprint) পুনরায় execute হলে নতুন provider/API call না হয়, যদি আগের valid result পুনর্ব্যবহারযোগ্য হয়। Canonical lifecycle: REQUEST → IDENTITY → FINGERPRINT → ATOMIC CLAIM → EXECUTE OR WAIT/REUSE → VALIDATE → PERSIST → CHECKPOINT → COMPLETE।

**মূল invariant:** `claimed=False` হলে `execute_fn()` কখনো চলবে না।

---

## ২. Pre-Audit

| Area | Location | Pre-Audit Status |
|------|----------|------------------|
| Core executor | `pipeline/idempotency/executor.py` | VERIFIED (wait/reuse) |
| Atomic store | `pipeline/idempotency/store.py` | **GAP** — stale IN_PROGRESS → UNKNOWN block |
| Fingerprint | `pipeline/idempotency/fingerprint.py` | VERIFIED |
| Identity | `pipeline/idempotency/identity.py` | VERIFIED |
| Retry policy | `pipeline/idempotency/retry_policy.py` | VERIFIED |
| Checkpoint | `pipeline/idempotency/checkpoint_store.py` | **GAP** — corrupt JSON silent empty |
| Unknown reconcile | `pipeline/idempotency/unknown_result.py` | PARTIAL — claim-fail path missing |
| Stage runtimes | `visual/audio/script/render/subtitle_runtime.py` | VERIFIED (IdempotentExecutor wrapper) |
| BUILD-03 tests | `scripts/test_build03_idempotency.py` | 14/14 PASS |
| BUILD-04G-H1 | `scripts/test_build04g_h1_idempotency_concurrency.py` | 6/6 PASS |
| Cross-process lock | — | **MISSING** (thread Lock only) |

---

## ৩. Idempotency Inventory

### Core modules (`pipeline/idempotency/`)

| Module | Role |
|--------|------|
| `executor.py` | Canonical orchestration: claim → execute/reuse → validate → persist → checkpoint |
| `store.py` | JSON-backed records, `atomic_claim()`, metrics, stale detection |
| `fingerprint.py` | Deterministic SHA256 fingerprint |
| `identity.py` | Job / Stage / Attempt / Execution hierarchy |
| `checkpoint_store.py` | Post-success checkpoint persistence |
| `unknown_result.py` | Safe reconciliation before blind retry |
| `retry_policy.py` | Retryable / non-retryable / unknown / terminal |
| `result_validation.py` | Artifact + JSON validation |
| `*_runtime.py` | Per-stage wrappers (visual, audio, script, render, subtitle) |
| `*_bridge.py` | Production entry bridges |

### Callsite matrix (production)

| FILE | FUNCTION | FINGERPRINT | CLAIM | EXECUTION | VALIDATION | PERSIST | CHECKPOINT | RETRY | UNKNOWN |
|------|----------|-------------|-------|-----------|------------|---------|------------|-------|---------|
| `executor.py` | `execute()` | ✓ | ✓ | gated | ✓ | ✓ | ✓ | ✓ | reconcile |
| `visual_runtime.py` | `execute_visual_request()` | ✓ | via executor | gated | ✓ | provenance | ✓ | via store | reconcile_visual |
| `audio_runtime.py` | `execute_audio_request()` | ✓ | via executor | gated | ✓ | provenance | ✓ | via store | reconcile |
| `script_runtime.py` | `execute_script_request()` | ✓ | via executor | gated | ✓ | provenance | ✓ | via store | reconcile |
| `render_runtime.py` | `execute_render_request()` | ✓ | via executor | gated | ✓ | manifest | ✓ | via store | reconcile |
| `subtitle_runtime.py` | `execute_subtitle_request()` | ✓ | via executor | gated | ✓ | provenance | ✓ | via store | reconcile |
| `generation_bridge.py` | plan/director bridges | ✓ | via executor | gated | ✓ | ✓ | ✓ | ✓ | reconcile |
| `factpack_bridge.py` | factpack generation | ✓ | via executor | gated | ✓ | ✓ | ✓ | ✓ | reconcile |

---

## ৪. Identity Audit

| Level | Field | Distinct | Verdict |
|-------|-------|----------|---------|
| JOB | `job_id` | ✓ | VERIFIED |
| STAGE | `stage` + `entity_id` | ✓ | VERIFIED |
| ATTEMPT | `attempt_number` (same fingerprint) | ✓ | VERIFIED |
| EXECUTION | `execution_key` | ✓ | VERIFIED |

**Retry vs revision:** একই inputs → একই fingerprint (TEST-02)। Intentional regeneration → `force_regenerate` + নতুন entity_id প্রয়োজন। Retry নতুন logical generation তৈরি করে না।

---

## ৫. Fingerprint Audit

- `compute_fingerprint()` — canonical JSON normalize → SHA256
- Volatile fields (`timestamp`, random UUID, temp filename) exclude — TEST-04 PASS
- `BUILD03_FINGERPRINT_VERSION` present — TEST-05 PASS
- Same logical input → same hash — TEST-03 PASS
- Provider, model, configuration, inputs included

---

## ৬. Atomic Claim Audit

`atomic_claim()` line-by-line verified:

| State | Behavior |
|-------|----------|
| No record | CLAIM → IN_PROGRESS |
| SUCCEEDED | NO CLAIM → reuse path |
| IN_PROGRESS (active) | NO CLAIM → wait |
| IN_PROGRESS (stale) | RECLAIM → IN_PROGRESS + metric |
| FAILED_RETRYABLE | CLAIM (attempt++) |
| FAILED_FINAL | NO CLAIM |
| UNKNOWN | NO CLAIM → reconcile |

**INVARIANT-02 verified:** TEST-06 — `claimed=False` → `execute_fn` never called (mock assertion).

**Single owner:** TEST-07 — 10 concurrent claims → exactly 1 owner.

---

## ৭. Concurrency Audit

**Stress test:** `scripts/test_amp003_task003_concurrency.py`
- 100 rounds × 20 workers = 2000 attempts
- **duplicate_execution_rounds = 0**
- **max provider executions per round = 1**

BUILD-04G-H1: 6/6 PASS (includes concurrent duplicate prevention).

**সীমাবদ্ধতা:** Thread-level lock only — cross-process PARTIAL (Section 17)।

---

## ৮. Wait/Reuse

Lifecycle verified (TEST-08):
1. Worker A claims → executes
2. Worker B claim fail → waits
3. Worker A persists SUCCEEDED
4. Worker B recheck → **reuse**

BUILD-04A TEST-06 assertion updated: `execute` + `reuse` valid (পূর্বে ভুলভাবে মাত্র 1 success action expected)। Provider invocation count = 1 invariant preserved.

---

## ৯. Stale Execution

**Pre-fix gap (P1):** Stale IN_PROGRESS → UNKNOWN mark → permanent block, reclaim impossible.

**Fix:** Stale IN_PROGRESS directly reclaimed with `stale_reclaimed` metadata + `stale_reclaim_count` metric (TEST-09 PASS).

Active (non-stale) IN_PROGRESS never duplicate-executed — wait path used.

---

## ১০. UNKNOWN Handling

- Provider crash / timeout → `IdempotencyState.UNKNOWN`
- **No blind regenerate** — TEST-11 PASS
- `reconcile_unknown()` — local artifact / remote metadata inspect
- Executor claim-fail + UNKNOWN → reconcile attempt before return (post-fix)
- Unresolved → UNKNOWN preserved — TEST-10 reconcile from artifact PASS

---

## ১১. Crash Recovery

TEST-20: persist SUCCEEDED record, simulate re-entry → **reuse** (no duplicate execution).

Checkpoint corrupt → quarantine to `.corrupt`, empty recovery (TEST-13).

Injection points covered by dedicated tests + BUILD-03 suite.

---

## ১২. Checkpoint

- Created only after validated persist (`executor.py` L270–280)
- Contains: job_id, stage, input_hash, output_hash, result_reference, state
- No secrets in checkpoint payload
- Corrupt JSON → quarantine (post-fix `checkpoint_store.py`)
- TEST-12: checkpoint exists after success

---

## ১৩. Retry Policy

| Category | Behavior | Test |
|----------|----------|------|
| Retryable | FAILED_RETRYABLE, attempt++ | TEST-14 |
| Non-retryable | FAILED_FINAL | TEST-15 |
| Unknown | UNKNOWN, no blind retry | TEST-16 |
| Terminal | max_attempts → FAILED_FINAL | TEST-14 |

**INVARIANT-07:** Infinite retry impossible — `max_attempts=3` default, hard stop at FAILED_FINAL.

Retry same fingerprint — TEST-02.

---

## ১৪. Cache Validation

TEST-17: corrupt/tampered cache (hash mismatch) → **reject**, not silent reuse.

`_validate_existing()` checks reference + hash before reuse.

---

## ১৫. Provenance

Per-stage provenance modules (`visual_provenance.py`, etc.) track:
- job_id, scene/entity_id, fingerprint, provider, model, asset_hash, generation_id, created_at

Secrets excluded from provenance payloads.

---

## ১৬. Bypass Audit

| Bypass | Class | Action |
|--------|-------|--------|
| `video_pipeline.py` idempotent bridges | PRODUCTION | VERIFIED wired — TEST-18 |
| Legacy script/render fallbacks | LEGACY | DOCUMENTED — TEST-19, defer TASK-004 |
| Direct mock in tests | TEST_ONLY | OK |
| `GenerationCache` legacy key | PRODUCTION (compat) | Wrapped inside idempotent `_execute` |

**INVARIANT-09:** No unexplained production bypass.

---

## ১৭. Multi-Process Limitation

**PARTIAL / DEFERRED**

- `threading.Lock` per store path — process-local only
- Thread concurrency: VERIFIED (100×20 stress PASS)
- Multi-process: NOT production-safe — documented P2
- **Test PASS ≠ global cross-process PASS**

---

## ১৮. Cost Audit

Duplicate prevention verified at infrastructure layer:
- Same fingerprint → max 1 provider execution (stress + BUILD-04A–E)
- Idempotency metrics: `duplicate_prevented`, `result_reused`, `generation_started`

Stage-specific cost (TTS, visual, render) guarded by same executor — no new provider integration in this task.

---

## ১৯. Root Causes

| ID | Severity | Root Cause |
|----|----------|------------|
| RC-003-01 | P1 | Stale IN_PROGRESS marked UNKNOWN → blocked reclaim forever |
| RC-003-02 | P1 | UNKNOWN on claim-fail path skipped reconcile |
| RC-003-03 | P2 | Corrupt checkpoint JSON silently returned empty |
| RC-003-04 | P2 | BUILD-04A TEST-06 wrong expectation (execute+reuse is valid) |
| RC-003-05 | P2 | No cross-process file locking |

---

## ২০. Surgical Changes

### `pipeline/idempotency/store.py`
- Stale IN_PROGRESS → direct reclaim (not UNKNOWN block)
- `stale_reclaim_count` metric
- FAILED_FINAL check preserved after stale branch

### `pipeline/idempotency/executor.py`
- Claim-fail + UNKNOWN → `reconcile_unknown()` before return
- `execute_fn()` only when `claimed=True` (unchanged invariant)

### `pipeline/idempotency/checkpoint_store.py`
- Corrupt JSON → quarantine `.corrupt`, return empty state

### `scripts/test_amp003_task003.py` (NEW)
- 20 dedicated tests

### `scripts/test_amp003_task003_concurrency.py` (NEW)
- 100 rounds × 20 workers stress

### `scripts/test_build04a_visual_runtime.py`
- TEST-06: accept execute + reuse (provider count = 1 invariant)

---

## ২১. Tests

| Suite | Result |
|-------|--------|
| `scripts/test_amp003_task003.py` | **20/20 PASS** |
| `scripts/test_amp003_task003_concurrency.py` | **1/1 PASS** (2000 attempts) |

### Test quality audit
- Real `IdempotentExecutor` + `IdempotencyStore` path (no production bypass mock)
- Provider invocation counted via side-effect counters / locks
- No weakened assertions
- Concurrency: actual duplicate execution count verified

---

## ২২. Regression

| Suite | Result |
|-------|--------|
| TASK-001 | 35/35 PASS |
| TASK-002 | 21/21 PASS |
| BUILD-00R | 5/5 PASS |
| BUILD-01 | 18/18 PASS |
| BUILD-02 | 17/17 PASS |
| BUILD-03 | 14/14 PASS |
| BUILD-04A | 18/18 PASS |
| BUILD-04B | 21/21 PASS |
| BUILD-04B-H | 19/19 PASS |
| BUILD-04C | 25/25 PASS |
| BUILD-04D | 35/35 PASS (2 skipped) |
| BUILD-04E | 40/40 PASS |
| BUILD-04G-H1 | 6/6 PASS |

**Regression: ALL PASS**

---

## ২৩. Evidence

```
AMP-003 TASK-003: 20/20 PASS
AMP-003 TASK-003 CONCURRENCY: 1/1 (100 rounds × 20 workers, max 1 execution/round)
Regression: ALL PASS (see Section 22)
Checkpoint: AMP003-T003-PASS
```

---

## ২৪. Limitations

1. Thread-level locking only — multi-process duplicate prevention not guaranteed
2. `reconcile_unknown()` uses local evidence only — no live provider poll in core layer
3. Legacy fallbacks in `video_pipeline.py` remain until TASK-004
4. Windows file replace occasional flake (BUILD-04E) — environment, not idempotency logic

---

## ২৫. Deferred Issues

| ID | Issue | Task |
|----|-------|------|
| DEF-AMP003-003 | Cross-process file locking (fcntl/msvcrt advisory) | TASK-004+ |
| DEF-AMP003-006 | Legacy script/render fallbacks full rewiring | TASK-004 |
| DEF-AMP003-007 | Live provider poll for UNKNOWN reconciliation | Future |

---

## ২৬. Final Verdict

### Mandatory pass criteria

- [x] identity verified
- [x] deterministic fingerprint verified
- [x] atomic claim verified
- [x] claimed=False cannot execute
- [x] concurrent duplicate prevention verified
- [x] wait/reuse verified
- [x] stale execution handled
- [x] UNKNOWN state handled safely
- [x] crash recovery verified
- [x] checkpoint verified
- [x] retry budget verified
- [x] cache validation verified
- [x] provenance verified
- [x] production bypass audit complete
- [x] cost-control audit complete
- [x] dedicated tests PASS
- [x] regression PASS
- [x] test quality audit PASS
- [x] no unexplained P0
- [x] no unresolved P1
- [x] report complete
- [x] state persisted

### Gap severity summary

| Severity | Count | Status |
|----------|-------|--------|
| P0 | 0 | — |
| P1 | 0 | All fixed |
| P2 | 3 | Documented / deferred |

**TASK-003 = PASS**  
**Checkpoint = AMP003-T003-PASS**  
**Next = TASK-004 NOT_STARTED**

---

**STOP — TASK-004 implementation শুরু করা হয়নি।**
