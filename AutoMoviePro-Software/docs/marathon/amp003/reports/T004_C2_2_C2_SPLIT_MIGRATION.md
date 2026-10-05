# T004-C2-2-C-2 — Split Agnes Caller Canonical Result API Migration

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2-C  
**Phase:** C2-2-C-2  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-C-2-PASS

---

## 1. বর্তমান split caller (pre/post)

### Pre (C2-2-C-2 আগে)

```python
try:
    src = idempotent_generate_agnes_beat(...)  # Path|None
except Exception:
    src = generate_agnes_dialogue_clip(...)    # BYP-01
```

### Post (C2-2-C-2)

```python
try:
    src, _agnes_beat_result = _resolve_split_agnes_beat_src(...)
except Exception:
    src = generate_agnes_dialogue_clip(...)    # BYP-01 — unchanged
```

**Location:** `pipeline/scene_builder.py` — `_build_split_dialogue_clip()` inner loop (~L1320+)

---

## 2. C2-2-C-1 API discovery reference

| Item | Actual |
|------|--------|
| Canonical API | `idempotent_generate_agnes_beat_result()` |
| Outcome helper | `classify_agnes_beat_outcome(result)` |
| Outcome enum | `AgnesBeatOutcome` |
| Prompt alias `idempotent_generate_agnes_dialogue_clip_result()` | **NOT FOUND** |

Report: `docs/marathon/amp003/reports/T004_C2_2_C_API_DISCOVERY.md`

---

## 3. Legacy API limitation

`idempotent_generate_agnes_beat()` → `Path|None`:
- SUCCESS/REUSED → Path (indistinguishable)
- FAILED/UNKNOWN → None (ambiguous)
- IDENTITY → Exception (BYP-01 trigger risk)

---

## 4. Canonical result API

নতুন helper: **`_resolve_split_agnes_beat_src()`**

- Calls `idempotent_generate_agnes_beat_result()` with C1 identity
- Classifies via `classify_agnes_beat_outcome()`
- Validates asset via `validate_visual_asset()`
- Returns `(Optional[Path], VisualGenerationResult)`

---

## 5. SUCCESS handling

- `outcome == SUCCESS`
- `result.path` exists + `validate_visual_asset()` passes
- Split assembly continues with validated path

---

## 6. REUSED handling

- `outcome == REUSED`
- Same validation as SUCCESS
- Provider invocations = 0 on reuse
- No regeneration

---

## 7. FAILED_RETRYABLE handling

- Explicit non-success → `src = None`
- **No new** direct `generate_agnes_dialogue_clip()` call
- Logged: `Split Agnes failed ... outcome=FAILED_RETRYABLE`
- Existing image fallback block (L1369+) may activate — **unchanged**

---

## 8. FAILED_FINAL handling

- Explicit non-success → `src = None`
- Not interpreted as success
- No new provider call

---

## 9. UNKNOWN handling

- `src = None`
- **No** direct Agnes call
- **No** blind retry (BUILD-03 gate preserved)
- UNKNOWN persisted in IdempotencyStore
- Logged with fingerprint prefix

---

## 10. IDENTITY_BLOCKED handling

- Pre-execution fail-closed
- Provider invocation = 0
- `src = None`, detail logged
- Does not raise through result path (no BYP-01 trigger for structured identity block)

---

## 11. Identity propagation

Preserved from C1 (unchanged args):

| Field | Split value |
|-------|-------------|
| `job_id` | `job_id or work.name` |
| `dialogue_id` | caller param |
| `canonical_scene_id` | caller param |
| `script_id` | caller param |
| `segment_id` | `f"seg-{i+1:02d}"` |
| `revision_id` | bridge default `""` (not in split signature) |

**Deferred:** `idx*10+i` in image fallback `_resolve_footage` call — existing hack, not redesigned (C2-4).

---

## 12. Asset handling

`result.success` alone insufficient — uses `validate_visual_asset(path, mode="video")`.

Invalid SUCCESS-marked asset → controlled `None` return.

---

## 13. Provenance

`load_visual_provenance(work_dir, result.fingerprint)` — verified in tests.

Metadata includes: `dialogue_id`, `canonical_scene_id`, `segment_id`, `revision_id`.

---

## 14. Checkpoint

`CheckpointStore(work_dir/checkpoints).latest_for_job(job_id)` — verified.

`IdempotencyStore` record → `SUCCEEDED` on success.

---

## 15. BYP-01 remaining status

**BYP-01 STILL PRESENT** at `scene_builder.py` L1352–1367.

- Fires only on **unexpected Exception** from `_resolve_split_agnes_beat_src`
- Structured FAILED/UNKNOWN/IDENTITY do **not** trigger bypass
- Removal reserved for **C2-2-D**

---

## 16. Image fallback explicitly deferred

Block at L1369+ (`if not src or not src.exists()`) — **NOT MODIFIED**.

Ken-Burns / `_resolve_footage` — owned by C-4 scope for future hardening.

---

## 17. Test evidence

**Suite:** `scripts/test_amp003_task004_c2_c2_split_migration.py`

| Result | Count |
|--------|-------|
| PASS | **18/18** |

---

## 18. Regression evidence

| Suite | Result |
|-------|--------|
| `test_amp003_task004_c2_c2_split_migration.py` | 18/18 PASS |
| `test_amp003_task004_c2_failure_contract.py` | 15/15 PASS |
| `test_amp003_task004_c2_boundary.py` | 18/18 PASS |
| `test_amp003_task004_c1_visual_identity.py` | 21/21 PASS |
| `test_amp003_task004_b_identity.py` | 6/6 PASS |
| `test_build03_idempotency.py` | 14/14 PASS |
| `test_build04a_visual_runtime.py` | 18/18 PASS (this run) |

---

## 19. Known BUILD-04A flake

`test_06_concurrent_duplicate` — **PASS** this run.

Known intermittent full-suite flake (DEF-T004-C2B-01) — not fixed in this phase.

Status: **FLAKY (deferred)** — single run PASS recorded.

---

## 20. Limitations

- Single-path caller (BYP-02) not migrated — C2-2-C-3
- BYP-01 exception bypass still active
- UNKNOWN → `src=None` may still hit existing image fallback (pre-existing behavior)
- `revision_id` not wired in split function signature

---

## 21. Final verdict

**C2-2-C-2 = PASS**

Split production caller migrated to canonical result API with explicit outcome handling. Identity preserved. Asset validation preserved. No new direct provider bypass. BYP-01 and image fallback untouched.

**P0 = 0 | New P1 = 0**

**Next:** C2-2-C-3 (single path migration)
