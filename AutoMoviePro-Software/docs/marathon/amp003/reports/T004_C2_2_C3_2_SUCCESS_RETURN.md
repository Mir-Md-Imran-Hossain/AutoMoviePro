# T004-C2-2-C-3-2 — Single Agnes SUCCESS/REUSE Return Hardening

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2-C  
**Phase:** C2-2-C-3-2  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-C-3-2-PASS

---

## 1. C2-2-C-3-1 discovery

Single path: `build_dialogue_clip` → `_resolve_footage` → legacy bridge.

**Bug confirmed:** bridge success → `path` assigned → **no return** → image fallback.

Report: `docs/marathon/amp003/reports/T004_C2_2_C3_DISCOVERY.md`

---

## 2. Existing success fall-through bug

Pre-migration `_resolve_footage()`:

- `idempotent_generate_agnes_beat()` success → variable set
- No early return
- Execution continued to `build_image_video_fallback()` L2248+

Only BYP-02 success path returned explicitly (L2126 equivalent).

---

## 3. Canonical result API

**New helper:** `_resolve_single_agnes_beat_src()` (`scene_builder.py`)

- Calls `idempotent_generate_agnes_beat_result()`
- Classifies via `classify_agnes_beat_outcome()`
- `part_index=0` (single beat)
- No fabricated `segment_id` / `revision_id`

**`_resolve_footage()` migration:**

```python
path, _ = _resolve_single_agnes_beat_src(...)
if path is not None:
    return path   # ← fixes fall-through bug
```

---

## 4. SUCCESS handling

- `outcome == SUCCESS`
- `validate_visual_asset(path, mode="video")` passes
- **Immediate `return path`** before image fallback

---

## 5. REUSED handling

- Same validation as SUCCESS
- Cached asset returned
- Provider invocations = 0 on reuse
- No image fallback

---

## 6. Asset validation

Uses existing `validate_visual_asset()` from `visual_validation.py`.

Invalid/missing asset on SUCCESS-marked result → `None` → controlled fall-through (not false success).

---

## 7. Explicit return

Valid SUCCESS/REUSED now **must not** reach:

- `build_image_video_fallback()`
- stock/still/color chain

Verified by tests TEST-02, TEST-04.

---

## 8. Image fallback boundary

Block at L2248+ **NOT MODIFIED**.

Only change: valid Agnes path returns before that boundary.

---

## 9. BYP-02 status

**BYP-02 STILL PRESENT** at `scene_builder.py` L2211–2226.

- Fires on unexpected `Exception` from canonical path
- Structured outcomes do not trigger BYP-02
- Removal reserved for **C2-2-E**

---

## 10. Identity propagation

Preserved unchanged:

| Field | Value |
|-------|-------|
| `job_id` | `job_id or work.name` |
| `dialogue_id` | caller param |
| `canonical_scene_id` | caller param |
| `script_id` | caller param |
| `part_index` | `0` |

---

## 11. Provenance

`load_visual_provenance(work_dir, fingerprint)` — verified TEST-11.

---

## 12. Checkpoint

`CheckpointStore` + `IdempotencyStore SUCCEEDED` — verified TEST-12.

---

## 13. Dedicated tests

**Suite:** `scripts/test_amp003_task004_c2_c3_single_success.py`

| Result | Count |
|--------|-------|
| PASS | **16/16** |

Exercises actual `_resolve_footage()` with mock bridge provider.

---

## 14. Regression

| Suite | Result |
|-------|--------|
| `test_amp003_task004_c2_c3_single_success.py` | 16/16 PASS |
| `test_amp003_task004_c2_c2_split_migration.py` | 18/18 PASS |
| `test_amp003_task004_c2_failure_contract.py` | 15/15 PASS |
| `test_amp003_task004_c2_boundary.py` | 18/18 PASS |
| `test_amp003_task004_c1_visual_identity.py` | 21/21 PASS |
| `test_amp003_task004_b_identity.py` | 6/6 PASS |
| `test_build03_idempotency.py` | 14/14 PASS |
| `test_build04a_visual_runtime.py` | 18/18 PASS (this run) |

---

## 15. Known flake

`BUILD-04A test_06_concurrent_duplicate` — **PASS** this run.

Status: **FLAKY (deferred)** DEF-T004-C2B-01 — not modified.

---

## 16. Limitations

- FAILED/UNKNOWN/IDENTITY full caller propagation → C2-2-C-3-3+
- BYP-02 exception bypass still active
- `segment_id` / `revision_id` not wired in single path (T004-E)
- Legacy `idempotent_generate_agnes_beat()` adapter unchanged

---

## 17. Final verdict

**C2-2-C-3-2 = PASS**

Single-beat canonical result API migrated. SUCCESS/REUSED return validated Path before image fallback. Fall-through bug fixed. BYP-02 and image fallback untouched.

**P0 = 0 | New P1 = 0**

**Next:** C2-2-C-3-3
