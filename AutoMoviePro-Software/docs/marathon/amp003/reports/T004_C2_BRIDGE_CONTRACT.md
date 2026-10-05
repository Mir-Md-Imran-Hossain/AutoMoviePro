# T004-C2 C2-1 — Agnes Bridge Boundary & Production Execution Contract

**Marathon:** AMP-003 / TASK-004 / T004-C  
**Phase:** C2-1  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-1-PASS  
**Code changes:** Minimal contract hardening only (partial identity fail-closed)

---

## 1. Current Gateway (C2-1-A)

Production Agnes visual generation-এর **একমাত্র canonical gateway**:

| Layer | Function | File |
|-------|----------|------|
| Production entry | `build_dialogue_clip()` | `pipeline/scene_builder.py` |
| Footage resolver | `_resolve_footage()` | single-beat Agnes |
| Split resolver | `_build_split_dialogue_clip()` | split Agnes |
| **Agnes gateway** | `idempotent_generate_agnes_beat()` | `pipeline/idempotency/agnes_bridge.py` |
| **Runtime** | `execute_visual_request()` | `pipeline/idempotency/visual_runtime.py` |
| **Executor** | `IdempotentExecutor.execute()` | `pipeline/idempotency/executor.py` |
| Provider (allowed inside bridge) | `generate_agnes_dialogue_clip()` | `pipeline/media_assets.py` |

**Production orchestration root:** `video_pipeline.py` → validated scene handoff → `build_dialogue_clip`.

দ্বিতীয় parallel gateway **তৈরি করা হয়নি** — existing BUILD-04A stack ব্যবহার করা হয়েছে।

---

## 2. Provider Boundary (C2-1-B)

### Invariant

```
Production orchestration
    ↓
idempotent_generate_agnes_beat  (gateway)
    ↓
execute_visual_request          (runtime)
    ↓
provider_fn closure             (bridge-internal)
    ↓
generate_agnes_dialogue_clip    (provider — ALLOWED here only)
```

### Bypass (NOT allowed — documented, fix in C2-2/C2-5)

| Location | Violation |
|----------|-----------|
| `scene_builder.py` L1242–1258 | Exception → direct provider (split) |
| `scene_builder.py` L1991–2007 | Exception → direct provider (single) |

Bridge-এর **ভিতরে** `provider_fn → generate_agnes_dialogue_clip` = **NOT bypass**.

---

## 3. Production Call Graph

```
video_pipeline (validated Scene handoff)
    ↓
build_dialogue_clip(idx, dialogue_id, canonical_scene_id, ...)
    ↓
┌─ single: _resolve_footage
│       ↓ try
│   idempotent_generate_agnes_beat → execute_visual_request → provider_fn
│       ↓ except  [C2-2 target]
│   generate_agnes_dialogue_clip  ← BYPASS
│
└─ split: _build_split_dialogue_clip
        ↓ per part
    idempotent_generate_agnes_beat(segment_id=seg-NN)
        ↓ except  [C2-2 target]
    generate_agnes_dialogue_clip  ← BYPASS
```

---

## 4. Identity Contract (C2-1-C)

C1 contract (`VisualRequestSpec` + `validate_visual_request_identity`) reuse করা হয়েছে।

### Production mandatory (gateway level)

| Field | Source | Mandatory |
|-------|--------|-----------|
| job_id | work.name / param | ✓ |
| scene_id (int) | scene_index / idx | ✓ |
| canonical_scene_id | T004-B handoff | ✓ (production) |
| dialogue_id | T004-B handoff UUID | ✓ (production) |
| script_id | handoff | optional metadata |
| segment_id | operational `seg-NN` (split only) | ✓ if part_index>0 |
| revision_id | caller (intentional regen) | optional |
| prompt / visual_prompt | scene | ✓ |
| provider | `"agnes"` hardcoded | ✓ |
| model | `"agnes-video-v2.0"` | ✓ |
| generation_mode | derived (image_url/catalog) | ✓ |
| size / duration_sec | params | ✓ |
| seed | N/A Agnes | absent (documented) |

### C2-1 hardening (minimal)

Partial identity (শুধু dialogue_id **অথবা** শুধু canonical_scene_id) → **BLOCK** (`VisualIdentityError`).

Fake domain `segment_id` invent করা হয় **না** — operational string `seg-{n:02d}` only (T004-E deferred)।

---

## 5. Error Contract (C2-1-D)

BUILD-03/04A mechanisms map:

| Outcome | Runtime return | State | Notes |
|---------|----------------|-------|-------|
| Success (first run) | `action=execute`, `success=True` | SUCCEEDED | |
| Cache hit | `action=reuse`, `success=True` | SUCCEEDED | provider calls=0 |
| Validation fail | `action=failed` | FAILED_RETRYABLE | invalid asset |
| Provider retryable | `action=failed` | FAILED_RETRYABLE | network etc. |
| Provider non-retryable | `action=failed` | FAILED_FINAL | rejection |
| UNKNOWN | `action=unknown` | UNKNOWN | TimeoutError class |
| Concurrent dup | `action=duplicate_prevented` | IN_PROGRESS | no blind exec |
| Identity fail | `VisualIdentityError` raised | — (pre-claim) | fail-closed |

**Input:** `VisualRequestSpec` + optional `provider_fn`  
**Output:** `VisualGenerationResult` or `None` (bridge on failure)  
**Exception:** gateway validation raises before claim; runtime maps provider exceptions via `retry_decision`

---

## 6. UNKNOWN Contract (C2-1-E)

### Runtime behavior (verified)

1. Provider raises timeout-class error → executor sets `UNKNOWN` in store
2. Second call with same fingerprint → `action=unknown` or `duplicate_prevented` — **NOT blind retry**
3. `reconcile_visual_unknown()` available for local artifact recovery

### Bridge exception gap (C2-2 target)

`scene_builder` `except Exception` → direct provider call = **violates UNKNOWN rule** at orchestration layer.

Runtime UNKNOWN handling **preserved** — C2-2-এ orchestration bypass remove করতে হবে।

---

## 7. Validation Contract (C2-1-F)

Lifecycle (via `execute_visual_request`):

```
fingerprint → IdempotentExecutor.claim
    → _execute (provider)
    → validate_visual_asset (MP4 container, min size)
    → save_visual_provenance
    → checkpoint (CheckpointStore)
    → SUCCEEDED
```

Invalid output (`MockBehavior.INVALID_ASSET`) → `failed`, **NOT** promoted to success.

Validation engine rewrite করা হয় **নি** — `visual_validation.py` unchanged.

---

## 8. Provenance Contract (C2-1-G)

`save_visual_provenance` persists:

- `input_hash` = request fingerprint
- `provider`, `model`, `prompt_hash`
- metadata: `scene_id`, `canonical_scene_id`, `dialogue_id`, `segment_id`, `part_index`, `revision_id`, `entity_id`, `generation_mode`
- seed: empty for Agnes (provider limitation)

Request fingerprint == provenance `input_hash` — **verified TEST-10**.

---

## 9. Checkpoint Contract

`IdempotentExecutor.execute()` success path:

- `CheckpointStore.save_checkpoint()` after validated persist
- stage=`visual`, `input_hash`=fingerprint, `output_hash`=artifact hash

Verified TEST-11.

States: NOT_STARTED → IN_PROGRESS (claim) → SUCCEEDED | FAILED_* | UNKNOWN

---

## 10. Current Bypasses (C2-1-H)

| ID | Location | Current behavior | Why unsafe |
|----|----------|----------------|------------|
| BYP-01 | split L1242 | bridge except → direct Agnes | No idempotency, no provenance, no UNKNOWN |
| BYP-02 | single L1991 | bridge except → direct Agnes | Same |

### Desired (C2-2)

```
bridge/runtime failure
    ↓
controlled retry / UNKNOWN / failed
    ↓
NO direct generate_agnes_dialogue_clip from scene_builder
```

---

## 11. C2-2 Implementation Requirement

1. Remove both `except Exception: generate_agnes_dialogue_clip` blocks
2. Propagate `VisualGenerationResult` / failure state to caller
3. UNKNOWN → reconcile or block job — no blind Agnes retry
4. Image fallback remains separate (C-4) — not used as Agnes bypass substitute

---

## 12. Deferred segment_id Dependency

- Domain `Scene.segment_id` → **T004-E**
- C2 operational binding: `seg-{i+1:02d}` string from scene_builder
- Gateway blocks split part without `segment_id` when `part_index>0`
- No fake canonical UUID segment invented

---

## 13. Test Evidence

**File:** `scripts/test_amp003_task004_c2_boundary.py`

| Test | Description | Result |
|------|-------------|--------|
| TEST-01 | valid gateway accepts | PASS |
| TEST-02 | identity reaches gateway/provenance | PASS |
| TEST-03 | missing scene identity BLOCK | PASS |
| TEST-04 | missing dialogue identity BLOCK | PASS |
| TEST-05 | revision preserved | PASS |
| TEST-06 | fingerprint unchanged to runtime | PASS |
| TEST-07 | provider inside runtime | PASS |
| TEST-08 | valid passes validation | PASS |
| TEST-09 | invalid not success | PASS |
| TEST-10 | provenance fingerprint match | PASS |
| TEST-11 | checkpoint written | PASS |
| TEST-12 | UNKNOWN preserved | PASS |
| TEST-13 | UNKNOWN no blind retry | PASS |
| TEST-14 | reuse zero provider calls | PASS |
| TEST-15 | meaningful change new FP | PASS |
| TEST-16 | no fake domain segment_id | PASS |
| TEST-17 | bridge boundary explicit | PASS |
| TEST-18 | deterministic contract | PASS |

**Total: 18/18 PASS**

---

## 14. Regression

| Suite | Result |
|-------|--------|
| `test_amp003_task004_c2_boundary.py` | 18/18 PASS |
| `test_build04a_visual_runtime.py` | 18/18 PASS (isolated) |
| `test_amp003_task004_c1_visual_identity.py` | 21/21 PASS |
| `test_amp003_task004_b_identity.py` | 6/6 PASS |
| `test_build03_idempotency.py` | 14/14 PASS |

---

## 15. Limitations

- C2-0 bypasses still present (by design — C2-2 scope)
- Agnes seed unsupported — metadata absent
- `idx*10+i` split image fallback identity hack — C2-4/C-4
- Bridge returns `None` on failure — caller must handle (C2-2 improve)

---

## 16. Final Verdict

**C2-1 STATUS: PASS**  
**Checkpoint: AMP003-T004-C2-1-PASS**

Canonical gateway identified. Provider boundary documented. Identity/error/UNKNOWN/validation/provenance/checkpoint contracts verified. Bypasses identified and assigned to C2-2/C2-5. No new bypass introduced. P0=0, P1=0 (known bypasses documented as C2-2 work).

**STOP — C2-2 NOT STARTED**
