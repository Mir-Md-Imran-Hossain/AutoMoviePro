# T004-C2-2-C-1 — Canonical Agnes Result API Discovery

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2-C  
**Phase:** C2-2-C-1 (API Discovery — NO CODE CHANGE)  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-C-1-PASS

---

## 1. Prompt vs Actual Function Name

| Prompt-এ উল্লেখ | Actual codebase |
|----------------|-----------------|
| `idempotent_generate_agnes_dialogue_clip_result()` | **NOT FOUND** — এই নামে কোনো function নেই |
| C2-2-B equivalent | **`idempotent_generate_agnes_beat_result()`** — canonical result API |

**Verdict:** Migration target = `idempotent_generate_agnes_beat_result()` (`pipeline/idempotency/agnes_bridge.py`).

Legacy adapter = `idempotent_generate_agnes_beat()` (same file, L254–317).

---

## 2. Canonical Result API

### 2.1 Signature

```python
def idempotent_generate_agnes_beat_result(
    *,
    work_dir: Path,
    job_id: str,
    scene_id: int,
    part_index: int,
    attempt: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    out_path: Path,
    narration_hint: str = "",
    size: str = "1080x1920",
    duration_hint: float = 5.0,
    override_prompt: str = "",
    niche: str = "",
    image_url: str = "",
    use_catalog_image: bool = True,
    provider_fn=None,
    fallback_provider_fn=None,
    use_mock: bool = False,
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    production_identity: bool = False,
) -> VisualGenerationResult
```

**Source:** `pipeline/idempotency/agnes_bridge.py` L132–251

### 2.2 Return Type

`VisualGenerationResult` (`pipeline/idempotency/visual_runtime.py` L33–46):

| Field | Type | Meaning |
|-------|------|---------|
| `success` | `bool` | `True` iff `action in ("execute", "reuse")` (runtime layer) |
| `path` | `Optional[Path]` | Validated asset path; `None` if missing/invalid |
| `action` | `str` | `execute`, `reuse`, `failed`, `unknown`, `identity_blocked`, `reconciled`, `not_found`, … |
| `fingerprint` | `str` | Visual request fingerprint |
| `asset_id` | `str` | Derived from fingerprint + scene |
| `asset_hash` | `str` | Artifact hash from idempotency record |
| `generation_id` | `str` | From provenance / remote job store |
| `provider_invocations` | `int` | Actual provider calls this invocation |
| `metrics` | `dict[str, int]` | Executor metrics |
| `state` | `IdempotencyState` | BUILD-03 persisted state |
| `provenance_path` | `str` | Path to provenance JSON if loaded |
| `detail` | `str` | Identity/error detail (C2-2-B) |

### 2.3 Internal Flow

```
_build_agnes_spec()
    ↓
_validate_production_identity()  → VisualIdentityError caught → identity_blocked result
    ↓
execute_visual_request()        → IdempotentExecutor → provider_fn → validate → persist
    ↓
VisualGenerationResult (returned intact — no discard)
```

Provider default (when `provider_fn is None` and not `use_mock`):

```python
generate_agnes_dialogue_clip(...)  # BRIDGE_INTERNAL only
```

---

## 3. Outcome Classification

### 3.1 `AgnesBeatOutcome` Enum

**Source:** `agnes_bridge.py` L23–31

| Value | Meaning |
|-------|---------|
| `SUCCESS` | New validated generation |
| `REUSED` | Cache/idempotency reuse |
| `FAILED_RETRYABLE` | Definitive failure, retry may be allowed |
| `FAILED_FINAL` | Definitive failure, no retry |
| `UNKNOWN` | Provider state uncertain |
| `IDENTITY_BLOCKED` | Pre-execution identity fail |

### 3.2 `classify_agnes_beat_outcome(result: VisualGenerationResult) -> AgnesBeatOutcome`

**Source:** `agnes_bridge.py` L34–52

| Condition | Outcome |
|-----------|---------|
| `action == "identity_blocked"` | `IDENTITY_BLOCKED` |
| `success` + `action == "reuse"` | `REUSED` |
| `success` + `action in ("execute", "reconciled")` | `SUCCESS` |
| `state == UNKNOWN` or `action == "unknown"` | `UNKNOWN` |
| `state == FAILED_FINAL` | `FAILED_FINAL` |
| `state == FAILED_RETRYABLE` or `action == "failed"` | `FAILED_RETRYABLE` |
| `action == "duplicate_prevented"` + `state == UNKNOWN` | `UNKNOWN` |
| `not success` (fallback) | `FAILED_RETRYABLE` |
| else | `SUCCESS` |

**Caller pattern (recommended):**

```python
result = idempotent_generate_agnes_beat_result(...)
outcome = classify_agnes_beat_outcome(result)
```

---

## 4. Semantic Behavior by Outcome

### 4.1 SUCCESS

| Aspect | Behavior |
|--------|----------|
| Trigger | `success=True`, `action=execute` (or `reconciled`) |
| Path | `result.path` exists and is file |
| Provider | ≥1 invocation on first execute; 0 on reconciled from local artifact |
| Provenance | Written via `save_visual_provenance()` |
| Checkpoint | IdempotencyStore → `SUCCEEDED` |
| Caller | Continue with validated path |

### 4.2 REUSED

| Aspect | Behavior |
|--------|----------|
| Trigger | `success=True`, `action=reuse` |
| Path | Prior artifact path |
| Provider | `provider_invocations == 0` |
| Fingerprint | Same as prior success |
| Caller | Continue with cached path |

### 4.3 FAILED (RETRYABLE / FINAL)

| Aspect | Behavior |
|--------|----------|
| Trigger | `action=failed`, `success=False` |
| State | `FAILED_RETRYABLE` or `FAILED_FINAL` |
| Path | Typically `None` |
| Provider | May have been invoked |
| Caller | Controlled failure — **not** silent success |

Sub-distinction (BUILD-03):

- Provider rejection → often `FAILED_FINAL`
- Invalid asset post-generation → often `FAILED_RETRYABLE`

### 4.4 UNKNOWN

| Aspect | Behavior |
|--------|----------|
| Trigger | Provider timeout/response lost; `MockBehavior.UNKNOWN` |
| State | `IdempotencyState.UNKNOWN` persisted in store |
| Action | `"unknown"` |
| Retry same fingerprint | **No blind provider call** (executor returns unknown) |
| Reconciliation | `reconcile_visual_unknown()` available (`visual_runtime.py` L189–227) |
| Caller | Block/reconcile — **must NOT** call `generate_agnes_dialogue_clip()` directly |

Evidence: `test_amp003_task004_c2_failure_contract.py` TEST-05, TEST-07.

### 4.5 IDENTITY_BLOCKED

| Aspect | Behavior |
|--------|----------|
| Trigger | Missing/partial production identity before provider |
| Action | `"identity_blocked"` |
| State | `FAILED_FINAL` |
| Provider | **0 invocations** |
| Detail | Error string in `result.detail` |
| Legacy API | Re-raises `VisualIdentityError` |
| Caller | Fail closed — no provider, no retry |

Partial identity example: `dialogue_id` set but `canonical_scene_id` empty → blocked.

Split path: missing `segment_id` when `part_index > 0` → blocked.

---

## 5. Legacy Adapter

### 5.1 `idempotent_generate_agnes_beat() -> Optional[Path]`

**Source:** `agnes_bridge.py` L254–317

| Result outcome | Legacy return |
|----------------|---------------|
| SUCCESS / REUSED (valid path) | `Path` |
| FAILED / UNKNOWN | `None` (**ambiguous**) |
| IDENTITY_BLOCKED | raises `VisualIdentityError` |

**Must remain** for backward compatibility (C2-2-C-7).

---

## 6. Supporting Runtime APIs

| API | Location | Purpose |
|-----|----------|---------|
| `execute_visual_request()` | `visual_runtime.py` | Core BUILD-04A runtime |
| `reconcile_visual_unknown()` | `visual_runtime.py` L189 | UNKNOWN reconciliation |
| `validate_visual_asset()` | `visual_validation.py` L98 | Asset validation (reuse in C2-2-C-4) |
| `load_visual_provenance()` | `visual_provenance.py` | Provenance read |
| `IdempotentExecutor` | `executor.py` | BUILD-03 execution + UNKNOWN gate |

---

## 7. Current scene_builder Callers (Pre-Migration)

### 7.1 Split Path — BYP-01 Area (~L1218–1258)

**Function:** `_build_split_dialogue_clip` inner loop

**Current:**

```python
try:
    src = idempotent_generate_agnes_beat(...)   # LEGACY Path|None
except Exception:
    src = generate_agnes_dialogue_clip(...)   # BYP-01 direct fallback
```

**Identity passed:** `dialogue_id`, `canonical_scene_id`, `script_id`, `segment_id=f"seg-{i+1:02d}"`

**Post-bridge:** L1259 — `if not src or not src.exists()` → image fallback (out of C2-2-C scope)

### 7.2 Single Path — BYP-02 Area (~L1968–2007)

**Function:** `_resolve_footage`

**Current:**

```python
try:
    path = idempotent_generate_agnes_beat(...)   # LEGACY Path|None
except Exception:
    path = generate_agnes_dialogue_clip(...)     # BYP-02 direct fallback
```

**Identity passed:** `dialogue_id`, `canonical_scene_id`, `script_id` (no segment_id — part_index=0)

**Note:** L2017 `except Exception` is **dead code** (nested inside BYP-02 try that already catches).

### 7.3 Information Loss Today

| Semantic | Legacy caller sees |
|----------|-------------------|
| SUCCESS | `Path` |
| REUSED | `Path` (indistinguishable from SUCCESS) |
| FAILED | `None` |
| UNKNOWN | `None` (same as FAILED) |
| IDENTITY_BLOCKED | Exception (may trigger BYP-01/02) |

**Migration goal (C2-2-C-2/3):** Use `idempotent_generate_agnes_beat_result()` + `classify_agnes_beat_outcome()` so caller has explicit outcome before bypass/image-fallback logic.

---

## 8. Migration Design Notes (For C2-2-C-2 onward)

### 8.1 Expected Caller Handling

| Outcome | Action |
|---------|--------|
| SUCCESS | Validate asset → continue |
| REUSED | Validate asset → continue |
| FAILED_* | Controlled failure |
| UNKNOWN | Block/reconcile — no direct Agnes |
| IDENTITY_BLOCKED | Fail closed |

### 8.2 Asset Validation (C2-2-C-4)

Do **not** trust `result.success` alone. Reuse:

- `validate_visual_asset(path, mode="video")`
- `result.path.is_file()`
- fingerprint match via `compute_visual_fingerprint(spec)`
- provenance via `load_visual_provenance(work_dir, fingerprint)`

### 8.3 BYP-01 / BYP-02

**Remain in place** during C2-2-C. Removal deferred to C2-2-D / C2-2-E.

After migration, bypass should only fire on **unexpected exceptions**, not on structured FAILED/UNKNOWN/IDENTITY outcomes.

### 8.4 Image Fallback

Existing at L1259+ (split) and L2026+ (single). **Do not modify** in C2-2-C.

---

## 9. Direct Provider Call Inventory (Baseline)

| Location | Classification |
|----------|----------------|
| `agnes_bridge.py` L207–221 | BRIDGE_INTERNAL |
| `scene_builder.py` L1243–1258 | PRODUCTION_FALLBACK (BYP-01) |
| `scene_builder.py` L1992–2007 | PRODUCTION_FALLBACK (BYP-02) |
| `scene_builder.py` L36 import | IMPORT (used by bypass) |

No `idempotent_generate_agnes_dialogue_clip_result` anywhere in codebase.

---

## 10. C2-2-C-1 Verdict

| Criterion | Status |
|-----------|--------|
| Actual result API identified | **PASS** — `idempotent_generate_agnes_beat_result()` |
| Prompt alias checked | **PASS** — `idempotent_generate_agnes_dialogue_clip_result()` does not exist |
| Parameters documented | **PASS** |
| Return type documented | **PASS** |
| Outcome semantics documented | **PASS** |
| scene_builder callers located | **PASS** — split L1218, single L1968 |
| Code changed | **NONE** (as required) |

**Checkpoint:** `AMP003-T004-C2-2-C-1-PASS`

**Next:** C2-2-C-2 — Split path migration
