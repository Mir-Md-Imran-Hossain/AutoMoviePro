# T004-C2-2-B — Agnes Failure / UNKNOWN Semantics Contract

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2  
**Phase:** C2-2-B  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-B-PASS

---

## 1. বর্তমান bridge behavior (pre/post C2-2-B)

### Legacy API (`idempotent_generate_agnes_beat`)

- Success → `Path`
- Runtime failure → **`None`** (ambiguous)
- Identity failure → **`VisualIdentityError`** (exception)

### Canonical API (C2-2-B — **NEW**)

- `idempotent_generate_agnes_beat_result()` → **`VisualGenerationResult`** সব path-এ
- Identity failure → structured result (`action=identity_blocked`), legacy adapter re-raises

**BYP-01/BYP-02 untouched** — scene_builder exception bypass এখনও intact (C2-2-D/E)।

---

## 2. VisualGenerationResult analysis

```python
VisualGenerationResult(
    success: bool,
    path: Optional[Path],
    action: str,              # execute|reuse|failed|unknown|identity_blocked|...
    fingerprint: str,
    state: IdempotencyState,
    provider_invocations: int,
    provenance_path: str,
    detail: str,              # C2-2-B: identity/error detail
)
```

**কোথায় তৈরি:** `visual_runtime.execute_visual_request()`, `reconcile_visual_unknown()`

**কোথায় হারিয়ে যেত:** `idempotent_generate_agnes_beat()` শুধু `Path|None` return করত — **result discard**

---

## 3. Result data flow

```
provider_fn / mock
    ↓
execute_visual_request()
    ↓
VisualGenerationResult (full)
    ↓
idempotent_generate_agnes_beat_result()  ← canonical (NEW)
    ↓
classify_agnes_beat_outcome()
    ↓
idempotent_generate_agnes_beat()  ← legacy Path|None adapter
    ↓
scene_builder (still bypass on exception — C2-2-D/E)
```

---

## 4. SUCCESS semantics

- `success=True` + `action=execute` (or `reconciled`)
- Validated asset exists
- Provenance + checkpoint written

---

## 5. REUSED semantics

- `success=True` + `action=reuse`
- Provider invocations = 0
- Same fingerprint as prior success

---

## 6. FAILED semantics

| Subclass | State | action |
|----------|-------|--------|
| FAILED_RETRYABLE | FAILED_RETRYABLE | failed |
| FAILED_FINAL | FAILED_FINAL | failed |

Provider rejection → FAILED_FINAL; invalid asset → FAILED_RETRYABLE.

---

## 7. UNKNOWN semantics

- Provider execution uncertainty (timeout/response lost)
- `state=UNKNOWN`, `action=unknown`
- **Persisted** in IdempotencyStore
- Retry same fingerprint → **no blind provider call** (verified TEST-07)
- **No** direct Agnes fallback through result API

---

## 8. Identity failure semantics

- Category: **`IDENTITY_BLOCKED`** (non-retryable, pre-execution)
- `action=identity_blocked`, `state=FAILED_FINAL`
- **No provider invocation**
- Production identity error → **never** direct Agnes retry
- Legacy API: re-raises `VisualIdentityError` (C1 backward compat)

---

## 9. None behavior (resolved)

| Situation | Legacy `None` | Canonical outcome |
|-----------|---------------|-------------------|
| Runtime failed | None | FAILED_* |
| UNKNOWN | None | UNKNOWN |
| Identity (legacy) | exception | IDENTITY_BLOCKED |
| Success | Path | SUCCESS / REUSED |

**None ≠ SUCCESS** — verified TEST-13/14  
**None ≠ implicit UNKNOWN** — must inspect result via `_result` API

---

## 10. Retry behavior

- Same fingerprint, retryable failure → BUILD-03 bounded retry inside executor
- UNKNOWN → no blind retry
- Identity blocked → no retry (pre-provider)
- Intentional revision → new fingerprint (unchanged C1)

---

## 11. Caller behavior (current)

| Caller | Consumes | On failure |
|--------|----------|------------|
| scene_builder split | legacy Path | None → image fallback; **Exception → BYP-01** |
| scene_builder single | legacy Path | None → image fallback; **Exception → BYP-02** |

---

## 12. Future bypass-removal (C2-2-C/D/E)

Callers will use `idempotent_generate_agnes_beat_result()` + `classify_agnes_beat_outcome()`:

| Outcome | Action |
|---------|--------|
| SUCCESS/REUSED | continue |
| FAILED | controlled failure |
| UNKNOWN | block/reconcile |
| IDENTITY_BLOCKED | fail-closed |

**Never** `except → generate_agnes_dialogue_clip()`

---

## 13. Test evidence

**File:** `scripts/test_amp003_task004_c2_failure_contract.py`

| Test | Result |
|------|--------|
| TEST-01 SUCCESS | PASS |
| TEST-02 REUSED | PASS |
| TEST-03 FAILED | PASS |
| TEST-04 IDENTITY_BLOCKED | PASS |
| TEST-05 UNKNOWN | PASS |
| TEST-06 UNKNOWN persisted | PASS |
| TEST-07 no blind retry | PASS |
| TEST-08 identity explicit | PASS |
| TEST-09 runtime non-success | PASS |
| TEST-10 fingerprint | PASS |
| TEST-11 path | PASS |
| TEST-12 provenance | PASS |
| TEST-13 None not success | PASS |
| TEST-14 None semantics | PASS |
| TEST-15 reuse | PASS |

**Total: 15/15 PASS**

---

## 14. Regression evidence

| Suite | Result |
|-------|--------|
| `test_amp003_task004_c2_failure_contract.py` | 15/15 PASS |
| `test_amp003_task004_c2_boundary.py` | 18/18 PASS |
| `test_amp003_task004_c1_visual_identity.py` | 21/21 PASS |
| `test_build03_idempotency.py` | 14/14 PASS |
| `test_build04a_visual_runtime.py` | 17/18 stable; test_06 concurrent **intermittent flake** (3/5 runs PASS, isolated always PASS) — pre-existing |

BUILD-00R, BUILD-01, BUILD-02, BUILD-04B+ : **NOT_AVAILABLE** in repo scripts/

---

## 15. Limitations

- Legacy API still returns `None` on failure — C2-2-C will refine caller contract
- BYP-01/BYP-02 still active on bridge **exception** path
- BUILD-04A test_06 timing-sensitive under load

---

## 16. Deferred items

| Item | Task |
|------|------|
| BYP-01 removal | C2-2-D |
| BYP-02 removal | C2-2-E |
| Caller migration to result API | C2-2-C |
| Image fallback on Agnes fail | C-4 |
| Domain segment_id | T004-E |
| BUILD-04A test_06 flake hardening | Future maintenance |

---

## 17. Final verdict

**C2-2-B STATUS: PASS**  
**Checkpoint: AMP003-T004-C2-2-B-PASS**

Canonical failure semantics defined via `AgnesBeatOutcome` + `idempotent_generate_agnes_beat_result()`. UNKNOWN safe. Identity blocked. No new parallel architecture. Bypasses untouched. P0=0, no new P1.

**STOP — C2-2-C NOT STARTED**
