# H1 Pre-Audit — Production Reliability & Concurrency Hardening

**Milestone:** H1 = PRODUCTION RELIABILITY & CONCURRENCY HARDENING  
**Type:** READ-ONLY PRE-AUDIT (no implementation)  
**Baseline:** `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS` (Phase-10)  
**Date:** 2026-09-03  
**Paid API calls:** 0  

```
H1_PRE_AUDIT_STATUS: PASS
CHECKPOINT: AMP004-H1-PRE-AUDIT-PASS
```

**STOP.** Do not start H1 implementation automatically. Do not create H2 / Phase-11.

---

## 1. Executive summary

Phase-10 certified media quality, gates, and publishability. This pre-audit asks a different question:

> Can AutoMovie Pro safely run multiple jobs / threads / OS processes without duplicate paid work, lock corruption, or false `ready_to_upload`?

**Verdict: GO for a bounded H1 implementation** — extend the **existing** BUILD-03 / BUILD-04G authorities. Do **not** invent a second idempotency, lock, quality, or publishability engine.

### Headline findings

| ID | Sev | Finding |
|----|-----|---------|
| DEF-AMP004-011 | **P1** | BUILD-04A `test_06_concurrent_duplicate` intermittent failure is **reproducible** (~3/15 unittest; ~15/40 stress). Not resolved by a clean re-run. Evidence shows second entry into `provider_fn` under thread contention (`error=duplicate provider invocation`) with `generation_started=1` + `retry_count=1`. |
| DEF-001 (AMP-001) | **P2→P1 if multi-process deploy** | Idempotency store + reserve queue still use **`threading.Lock` only**. `os.replace` atomic write ≠ cross-process mutual exclusion. Multi-process same `work_dir` / shared reserve can double-execute. |
| CheckpointStore | **P2** | No lock around load/modify/save of `CHECKPOINTS.json`. |
| GenerationCache | **P2 / LEGACY** | Second filesystem cache without locks; sits *inside* claimed `execute_fn` (BUILD-04A). Not a second authority, but concurrent-unsafe. |

Phase-10 quality certification remains valid. H1 is **reliability hardening**, not a reopen of publishability/FFmpeg/quality architecture.

---

## 2. Current production concurrency graph

```
generate_video(work_dir?)
  ├─ work_dir mkdir (job folder = identity boundary; job_id often work.name)
  ├─ pick_topic_from_reserve / consume_top          [reserve_queue + threading.Lock]
  ├─ idempotent script / factpack bridges          [IdempotentExecutor]
  ├─ assert_production_scenes_validated            [P03–P07 preflight; per work_dir]
  ├─ per-scene visual (Agnes / visual_runtime)     [IdempotentExecutor + GenerationCache]
  ├─ TTS / audio_runtime                           [IdempotentExecutor]
  ├─ subtitle_runtime                              [IdempotentExecutor]
  ├─ idempotent_compose_final_video                [IdempotentExecutor + render_runtime]
  ├─ P04–P08 gates + publishability                [per work_dir JSON gates]
  └─ store.add_job / upload_status=ready_to_upload [DB/job store]
```

**Stateful concurrent hotspots:** reserve consume, idempotency claim, provider call (outside lock), artifact promote (`os.replace`), checkpoint write, gate JSON, upload status.

---

## 3. Authority map (singletons confirmed)

| Concern | Sole authority | Notes |
|---------|----------------|-------|
| Idempotent orchestration | `pipeline.idempotency.executor.IdempotentExecutor` | BUILD-03 |
| Idempotency records | `pipeline.idempotency.store.IdempotencyStore` | `IDEMPOTENCY.json` |
| Fingerprints | `pipeline.idempotency.fingerprint.compute_fingerprint` | includes `job_id` |
| Checkpoint | `pipeline.idempotency.checkpoint_store.CheckpointStore` | after success only |
| Resume | `pipeline.idempotency.resume_resolver.ResumeResolver` | |
| Reserve/consume | `pipeline.intelligence.reserve_queue` | BUILD-04G-H |
| Visual runtime | `visual_runtime.execute_visual_request` | wraps executor |
| Audio/TTS | `audio_runtime` / `tts_bridge` | wraps executor |
| Render | `render_bridge` / `render_runtime` | wraps executor |
| Publishability | `evaluate_publishability` | **out of H1 scope** |
| FFmpeg / RI | Phase-08 authorities | **out of H1 scope** |

**No second idempotency engine required for H1.** Prefer extending `IdempotencyStore.atomic_claim` / reserve locks.

`GenerationCache` is a **legacy nested cache**, not a competing global authority — but it is concurrent-unsafe (see findings).

---

## 4. Thread / process safety matrix

| Component | Lock type | Thread-safe | Process-safe | Classification |
|-----------|-----------|-------------|--------------|----------------|
| `IdempotencyStore._store_lock` | `threading.Lock` per path | **THREAD-SAFE** (same process) | **NOT SAFE** | DEF-001 |
| `atomic_claim` + `os.replace` | thread lock + atomic rename | THREAD-SAFE for claim | **NOT SAFE** (TOCTOU across processes) | DEF-001 |
| Provider `execute_fn` | runs **outside** claim lock | intentional | N/A | by design |
| `reserve_queue._lock_for` | `threading.Lock` | THREAD-SAFE | **NOT SAFE** | DEF-001 sibling |
| `reserve_queue` `os.replace` + fsync | atomic write | helps durability | not mutex | |
| `CheckpointStore` | none | **NOT SAFE** | **NOT SAFE** | P2 |
| `GenerationCache` | none | **NOT SAFE** | **NOT SAFE** | P2 |
| Gate JSON files | mostly single-writer per job | UNKNOWN under parallel gates | UNKNOWN | INFORMATIONAL |
| Job `work_dir` isolation | directory per job | SAFE if unique dirs | SAFE if unique dirs | |
| Upload / DB job row | depends on `store` impl | UNKNOWN (not deep-audited) | UNKNOWN | INFORMATIONAL |

**Do not treat thread-test PASS as process-safe PASS.**

---

## 5. Idempotency matrix

| Stage | Key | Provider inside lock? | Persist before provider? | Persist after success? |
|-------|-----|----------------------|--------------------------|------------------------|
| Claim | fingerprint | N/A | Claim record `IN_PROGRESS` **before** provider | |
| Script | fp(job,script,…) | No (outside) | Claim first | provenance + checkpoint |
| Visual | fp(job,visual,…) | No | Claim first | provenance + checkpoint |
| TTS/Audio | fp(job,audio,…) | No | Claim first | provenance + checkpoint |
| Subtitle | fp(job,subtitle,…) | No | Claim first | provenance + checkpoint |
| Render | fp(job,render,…) | No | Claim first | atomic promote + provenance |
| Reserve consume | queue file order | Yes (thread lock around read-modify-write) | N/A | write remaining queue |

**Fingerprint includes `job_id`** → cross-job collision requires identical job_id+stage+entity+inputs (misconfiguration), not random hash clash under normal unique work dirs.

---

## 6. Crash-recovery matrix

| Scenario | Expected current behavior | Duplicate paid risk | State risk |
|----------|---------------------------|---------------------|------------|
| A. Crash before lock/claim | No record | Low | None |
| B. Crash after claim (`IN_PROGRESS`) | Others see in-progress; after `stale_sec` (default 3600s) reclaim | **Medium** after stale reclaim (may re-call provider) | Stale lock ownership until timeout |
| C. Crash before provider (claimed) | Same as B | Medium after stale | |
| D. Crash during provider | `IN_PROGRESS` or exception→UNKNOWN/FAILED_* | Medium (provider may have side effects) | UNKNOWN path avoids blind duplicate (good) |
| E. Crash after provider success, before persist | Often UNKNOWN / incomplete ref | Medium if reclaim regenerates | Orphan artifact possible |
| F. Crash after persist, before downstream | Checkpoint/record may exist; resume can skip | Low if reuse validates | Downstream gates may be missing |
| G. Stale worker resumes after other completed | Should `reuse` if SUCCEEDED+valid artifact | Low if validation holds | Wrong reuse if invalid artifact accepted |

**False `ready_to_upload`:** Still gated by publishability/gates in `generate_video` — concurrency bugs more likely cause **duplicate cost** than silent publish, unless gate JSON corrupted (CheckpointStore/GenerationCache races).

---

## 7. DEF-AMP004-011 investigation

| Field | Evidence |
|-------|----------|
| Exact test | `scripts/test_build04a_visual_runtime.py::test_06_concurrent_duplicate` |
| Failure line | Assert all actions ∈ `{execute, reuse, duplicate_prevented}` |
| Reproduction | **3/15** unittest loops; **~15/40** custom stress — **not** rare enough to ignore |
| Observed mode | `provider_calls == 1` but actions `['failed','execute']`; store `metadata.error = "duplicate provider invocation"`; metrics `generation_started=1`, `retry_count=1`, final `SUCCEEDED` |
| Meaning | Test harness non-blocking lock detects a **second `provider_fn` entry** while first holder still holds the lock (test never releases). Combined with `retry_count`, points to **claim/reclaim vs in-flight execute** race under 2-thread same `work_dir` |
| Test-only? | **No** — failure mode exercises production `execute_visual_request` → `IdempotentExecutor` |
| Production affected? | **Yes for multi-threaded same work_dir**; single-threaded job workers may not hit it; multi-process covered by DEF-001 |
| Clean re-run proves stability? | **No** |

**H1 must treat DEF-AMP004-011 as an open P1**, not “maintenance flake.”

---

## 8. DEF-001 current status

| Field | Status |
|-------|--------|
| Original | AMP-001: multi-process idempotency/reserve lock thread-only, P2 |
| Phase-10 code | **Still true** — `store.py` / `reserve_queue.py` use `threading.Lock` only; no `msvcrt`/`fcntl`/portalocker |
| Production risk | Two OS processes, same idempotency path or shared channel reserve → both observe “not claimed” / both consume topic |
| Smallest extension point | `IdempotencyStore.atomic_claim` + `_write_unlocked` and `reserve_queue` consume/update: add **advisory file lock** around critical section; keep same JSON schema |
| Implement in this pre-audit? | **No** |

If deployment is multi-process workers on shared storage → elevate to **P1** for H1 scope.

---

## 9. Cross-job isolation result

| Resource | Isolation mechanism | Risk |
|----------|---------------------|------|
| `work_dir` | Per-job directory | Low if unique |
| `job_id` in fingerprint | Included in fp | Low |
| Idempotency store | Under `work_dir/idempotency` | Low across jobs; **high** if two workers share one work_dir |
| Artifacts / final mp4 | Under work_dir | Low across jobs |
| Gates / evidence | Under work_dir | Low |
| Reserve queue | **Shared** by `channel_id`+lang+format under `DATA_DIR` | **Cross-job by design** — must stay atomic |
| Upload status | Job store keyed by job id | Depends on DB integrity |

No audit evidence of cross-project fingerprint reuse when `job_id`/`work_dir` are unique.

---

## 10. Existing test results (no new tests)

| Suite / test | Result |
|--------------|--------|
| `test_build03_idempotency` (full) | Included in concurrency batch **PASS** |
| `test_amp003_task003` + `test_amp003_task003_concurrency` | **PASS** (batch) |
| `test_build04g_h1_idempotency_concurrency` (20 workers × 100 rounds) | **PASS** |
| `test_marathon_task002_reserve_atomicity` | **PASS** |
| Concurrent tests 04A/04B/04C/04D/04E (single run batch) | **PASS** (48 tests OK in combined run) |
| DEF-011 stress (this audit) | **FAIL intermittent** (see §7) |
| Multiprocessing stress | **No existing suite found** that spawns OS processes against `IdempotencyStore` |

Paid APIs: **0** (mock/local only).

---

## 11. P0 / P1 / P2 findings

| ID | Sev | Title |
|----|-----|-------|
| — | P0 | **None** (no mandatory gate bypass / false publishability architecture break found) |
| DEF-AMP004-011 | **P1** | Thread contention race: second `provider_fn` entry / `failed` under concurrent visual execute |
| DEF-001 | **P2** (P1 if multi-process workers) | No cross-process file lock on idempotency + reserve |
| H1-P2-CHECKPOINT | **P2** | `CheckpointStore` unlocked RMW |
| H1-P2-GENCACHE | **P2** | `GenerationCache` unlocked; legacy nested idempotency |
| H1-INFO-PROVIDER-OUTSIDE-LOCK | INFORMATIONAL | Provider outside claim lock is intentional; requires correct claim exclusivity |
| H1-INFO-STALE-RECLAIM | INFORMATIONAL | Default 3600s stale reclaim can re-bill after abandoned `IN_PROGRESS` |

---

## 12. Exact files that would need modification (implementation phase only)

| File | Why |
|------|-----|
| `pipeline/idempotency/store.py` | Process-safe advisory lock around claim/load/write; harden claim vs reclaim |
| `pipeline/idempotency/executor.py` | Ensure reclaim cannot run `execute_fn` while owner in-flight; clearer ownership |
| `pipeline/intelligence/reserve_queue.py` | Process-safe lock for consume/update |
| `pipeline/idempotency/checkpoint_store.py` | Thread/process-safe save |
| `pipeline/generation_cache.py` | Either lock or demote to non-authoritative under executor only |
| `scripts/test_build04a_visual_runtime.py` | Strengthen DEF-011 assertions **without weakening** (fix after fix) |
| New: process-level stress tests | Only in H1 implementation — not this pre-audit |

**Do not modify** publishability, ContinuityTracker, Artifact Verification, Audio Design, Localization, Creative Production, Rendering Integrity, or FFmpeg unless a **direct** reliability defect is proven in their locking (none found in this audit beyond shared work_dir JSON).

---

## 13. Minimal recommended implementation (for later H1 — not now)

1. **Extend** `IdempotencyStore` with cross-process advisory file lock (Windows `msvcrt.locking` / POSIX `fcntl`) around `atomic_claim` + `_write_unlocked` critical sections.  
2. **Same pattern** for `reserve_queue` consume/update.  
3. **Fix DEF-011:** make reclaim refuse while non-stale `IN_PROGRESS` owner alive; ensure failed-in-flight cannot open a second provider window; release/ownership heartbeats if needed.  
4. Lock or serialize `CheckpointStore._save`.  
5. Add **multiprocessing** stress tests (N processes, same work_dir / same reserve) — mock providers only.  
6. Keep BUILD-04G-H1 thread stress green; make DEF-011 reliably green (≥100/100).

**ARCHITECTURE-BLOCKED:** any proposal for a second global lock manager / second idempotency engine / new publishability path.

---

## 14. Explicit OUT OF SCOPE

- Code implementation in this pre-audit  
- New quality / publishability / FFmpeg / continuity / artifact / audio / localization / creative / RI engines  
- VLM/ASR, UI redesign, Phase-11, H2  
- Weakening existing tests  
- Paid APIs  

---

## 15. Acceptance criteria for H1 implementation

H1 implementation **PASS** requires:

1. [ ] DEF-AMP004-011: `test_06_concurrent_duplicate` stable (**≥100 consecutive PASS** or equivalent stress).  
2. [ ] Cross-process: two OS processes, same fingerprint → **≤1** mock provider call.  
3. [ ] Cross-process reserve: concurrent consume → **no duplicate topic consume**.  
4. [ ] Crash/reclaim: documented scenarios A–G covered by tests; no blind duplicate on UNKNOWN.  
5. [ ] Checkpoint concurrent writers do not corrupt `CHECKPOINTS.json`.  
6. [ ] Existing BUILD-03 / 04A–E concurrent / 04G-H1 / reserve atomicity suites still PASS.  
7. [ ] Phase-09/10 certification suites still PASS (no quality regression).  
8. [ ] Paid APIs = 0 in H1 tests.  
9. [ ] No new idempotency/publishability/FFmpeg authority.  
10. [ ] Report: `docs/marathon/production_hardening/H1_IMPLEMENTATION_REPORT.md`

---

## 16. Recommendation

```
GO
```

Proceed to a **bounded H1 implementation** that extends existing BUILD-03 / reserve locking only.

Do **not** start implementation in this turn.

---

## Final block

```
H1_PRE_AUDIT_STATUS: PASS
CHECKPOINT: AMP004-H1-PRE-AUDIT-PASS
STOP.
```
