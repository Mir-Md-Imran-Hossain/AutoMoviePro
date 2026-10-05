# T004-C2-2 C2-2-A — Pre-Fix Implementation Read (Exception Fallback)

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2  
**Phase:** C2-2-A READ CURRENT IMPLEMENTATION  
**Date:** 2026-08-31  
**Code changes:** 0  
**Prior checkpoint:** AMP003-T004-C2-1-PASS

---

## 1. Inspection Scope

| File | Purpose |
|------|---------|
| `pipeline/scene_builder.py` | Production caller + BYP-01/BYP-02 |
| `pipeline/idempotency/agnes_bridge.py` | Canonical gateway |
| `pipeline/idempotency/visual_runtime.py` | Runtime orchestration |
| `pipeline/idempotency/executor.py` | Claim/execute/UNKNOWN/retry |
| `pipeline/idempotency/store.py` | Idempotency persistence |

C2-0 callsites **re-verified** — line numbers unchanged.

---

## 2. BYP-01 — Split Dialogue Path

**Location:** `scene_builder.py` L1218–1258  
**Function:** `_build_split_dialogue_clip()`  
**Loop:** per split part `i`, attempt `attempt`

### Current code flow

```
try:
    src = idempotent_generate_agnes_beat(...)   # L1221–1241
except Exception:                                # L1242 — catches ALL exceptions
    src = generate_agnes_dialogue_clip(...)     # L1243–1258 — DIRECT BYPASS
```

### Trigger conditions

| Event | BYP-01 fires? | Next step |
|-------|---------------|-----------|
| Bridge raises `VisualIdentityError` | **YES** | Direct Agnes |
| Bridge raises any other `Exception` | **YES** | Direct Agnes |
| Bridge returns `None` (runtime fail) | **NO** | L1259 `if not src` → image fallback via `_resolve_footage` (C-4, `agnes_api=""`) |
| Bridge returns valid `Path` | **NO** | Continue split mux |

### Current return behavior

- Bypass success → `src` set; continues part pipeline
- Bypass failure → `src` None/missing → L1259–1302 image Ken-Burns fallback (`_resolve_footage`, no Agnes keys)
- **No** idempotency record, **no** provenance, **no** checkpoint on bypass path

### Caller behavior after bypass failure

`_build_split_dialogue_clip` does **not** abort scene — image fallback per part (C-4 scope, out of C2-2).

---

## 3. BYP-02 — Single-Beat Path

**Location:** `scene_builder.py` L1968–2016  
**Function:** `_resolve_footage()`

### Current code flow

```
try:
    path = idempotent_generate_agnes_beat(...)   # L1971–1990
except Exception:                                 # L1991
    path = generate_agnes_dialogue_clip(...)      # L1992–2007 — DIRECT BYPASS
    if path valid (>8000 bytes):
        return path                               # L2008–2016 early return
except Exception as exc:                          # L2017 — UNREACHABLE (dead code)
    agnes_err = exc
```

### Syntax note (verified: file parses)

Two sibling `except Exception` on same `try` — second handler (L2017) is **unreachable** for exceptions from the `try` body (first handler catches all `Exception`). Exceptions raised **inside** the first `except` block (during direct Agnes) **propagate uncaught** to outer scope.

### Trigger conditions

| Event | BYP-02 fires? | Next step |
|-------|---------------|-----------|
| Bridge raises any `Exception` | **YES** | Direct Agnes; early return if valid file |
| Bridge returns `None` | **NO** | Falls through to L2026+ image fallback |
| Bridge returns valid `Path` | **NO** | Used downstream in `_resolve_footage` |

### Current return behavior

- Bypass success (file >8000) → **immediate return** `path` — bypasses validation/provenance/checkpoint
- Bypass fail → `path` may be None → L2026 `build_image_video_fallback` (C-4)
- Runtime `None` (no exception) → image fallback, **not** direct Agnes

---

## 4. Bridge Layer (`agnes_bridge.py`)

### Gateway function

`idempotent_generate_agnes_beat()` — **canonical production gateway**

### Internal flow

1. Build `VisualRequestSpec`
2. Production identity validation (fail-closed if partial/missing)
3. Wrap `generate_agnes_dialogue_clip` in `provider_fn` (ALLOWED — bridge-internal)
4. `execute_visual_request()` → `IdempotentExecutor`

### Return contract (current limitation)

| Runtime outcome | Bridge returns | Raises? |
|-----------------|----------------|---------|
| Success (`execute`/`reuse`) | `Path` | No |
| Failure (`failed`/`unknown`) | **`None`** | No |
| Identity validation fail | — | **`VisualIdentityError`** |
| Partial identity | — | **`VisualIdentityError`** |

**Gap:** Runtime failure returns `None` silently — caller cannot distinguish UNKNOWN vs failed vs validation-without-exception without inspecting store.

`VisualGenerationResult` exists in `visual_runtime.py` but **not exposed** by bridge.

---

## 5. Runtime Layer (`visual_runtime.py` + `executor.py`)

### Success path

```
claim → execute_fn (provider) → validate → persist (provenance) → checkpoint → SUCCEEDED
```

### Failure mapping (BUILD-03)

| Condition | `action` | `IdempotencyState` |
|-----------|----------|-------------------|
| Reuse hit | `reuse` | SUCCEEDED |
| Provider timeout/lost | `unknown` | **UNKNOWN** |
| Retryable error | `failed` | FAILED_RETRYABLE |
| Non-retryable | `failed` | FAILED_FINAL |
| Validation fail | `failed` | FAILED_RETRYABLE |
| Concurrent dup | `duplicate_prevented` | IN_PROGRESS |

### UNKNOWN behavior (runtime — correct)

- Store persists `UNKNOWN`
- Retry same fingerprint → `action=unknown` or `duplicate_prevented` — **no blind provider call** (verified C2-1 TEST-13)
- `reconcile_visual_unknown()` available

**Problem:** BYP-01/BYP-02 **circumvent** this by catching bridge exceptions and calling provider directly.

---

## 6. Exception vs None — Two Failure Channels

| Channel | Bridge | Caller (scene_builder) | Idempotency |
|---------|--------|------------------------|-------------|
| **A: Exception** | Raises before/during gateway | BYP → direct Agnes | **BYPASS** |
| **B: None return** | Runtime failed safely | Image fallback (C-4) | Preserved in store |

C2-2 must close channel **A**. Channel **B** is separate (caller treats None as miss — image fallback deferred to C-4).

---

## 7. Desired Behavior (C2-2 Target)

```
Bridge exception OR runtime failure
    ↓
NO direct generate_agnes_dialogue_clip from scene_builder
    ↓
Controlled outcome:
    - propagate structured failure / None with logged state
    - UNKNOWN persisted → reconcile or block
    - retryable → BUILD-03 policy inside runtime only
    ↓
Image fallback ONLY via existing C-4 path (NOT as Agnes bypass substitute)
```

### Per bypass

| ID | Remove | Replace with |
|----|--------|--------------|
| BYP-01 L1242–1258 | `except → direct Agnes` | Accept bridge result; no direct call |
| BYP-02 L1991–2007 | `except → direct Agnes` | Accept bridge result; no direct call |

---

## 8. Downstream Caller Impact

### Split path (`_build_split_dialogue_clip`)

- After fix: bridge exception → must not call Agnes; `src` stays unset → existing image fallback path (unchanged — C-4)
- Identity errors (`VisualIdentityError`) → should **fail-closed**, not bypass

### Single path (`_resolve_footage`)

- After fix: no early return from bypass; failed Agnes → existing image/stock fallback chain (L2026+)
- `agnes_err` tracking (L2017 dead code) → needs cleanup in C2-2-E

---

## 9. C2-2 Sub-Phase Plan (Reference)

| Phase | Action |
|-------|--------|
| C2-2-B | Failure semantics map (reuse BUILD-03) |
| C2-2-C | Safe return contract (expose result or typed failure) |
| C2-2-D | Remove BYP-01 + split tests |
| C2-2-E | Remove BYP-02 + single tests |
| C2-2-F | UNKNOWN safety tests |
| C2-2-G | Retry safety tests |
| C2-2-H | Forensic rescan (production direct = 0) |

---

## 10. Out of Scope (Explicit)

- Image fallback (`build_image_video_fallback`, `_resolve_footage` with `agnes_api=""`) → **C-4**
- Domain `segment_id` → **T004-E**
- Agnes provider rewrite → **not in scope**

---

## C2-2-A Acceptance

- [x] BYP-01 identified and verified (L1242–1258)
- [x] BYP-02 identified and verified (L1991–2007)
- [x] Current exception behavior documented
- [x] Current return behavior documented (`None` vs exception)
- [x] Caller behavior documented
- [x] Desired behavior documented
- [x] No code changes

---

## C2-2-A Verdict

**PASS**  
**Checkpoint:** `AMP003-T004-C2-2-A-PASS`

**Next:** C2-2-B — Define Failure Semantics (no implementation until B complete)
