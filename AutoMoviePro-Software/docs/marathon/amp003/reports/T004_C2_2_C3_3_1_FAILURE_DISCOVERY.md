# T004-C2-2-C-3-3-1 — Single Agnes Failure-Propagation Discovery

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2-C  
**Phase:** C2-2-C-3-3-1 (Discovery — CODE CHANGE = 0)  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-C-3-3-1-PASS  
**Authority:** Actual current code in `scene_builder.py` (inspected 2026-08-31)

---

## 1. Audit Scope

| In scope | Out of scope |
|----------|--------------|
| `_resolve_footage()` single Agnes branch L2172–2244 | Split path (`_build_split_dialogue_clip`) |
| `_resolve_single_agnes_beat_src()` L152–252 | Image fallback implementation change |
| BYP-02 L2211–2236 | BYP-02 removal (C2-2-E) |
| `build_dialogue_clip()` immediate consumer L460–503 | segment_id / revision architecture |
| `agnes_bridge.py` / `visual_runtime.py` (read-only) | C-4 image fallback hardening |

**Code changes this phase:** **0**

---

## 2. Current Single Path

```
build_dialogue_clip() L460
    ↓
_resolve_footage() L2127
    ↓ (if agnes_keys)
try:
    path, _result = _resolve_single_agnes_beat_src() L2182
        ↓
    idempotent_generate_agnes_beat_result()  [bridge]
        ↓
    classify_agnes_beat_outcome()
    if path is not None → return path L2210
except Exception:                           [BYP-02] L2211
    generate_agnes_dialogue_clip() L2212
    if valid → return path L2236
except Exception as exc:                    L2237 (BYP-02 inner failure only)
    agnes_err = exc
    ↓
if allow_image_fallback: build_image_video_fallback() L2248+
    ↓
pexels / still / make_color_clip L2324 → always returns Path
```

**Note:** `_agnes_beat_result` is **discarded** at L2182 — caller never inspects structured outcome.

---

## 3. SUCCESS

| Aspect | Actual behavior |
|--------|-----------------|
| Helper return | `(valid_path, result)` after `validate_visual_asset()` |
| `_resolve_footage` | `path is not None` → **immediate return** L2210 |
| BYP-02 | **NO** |
| Image fallback | **NO** |
| Provider | 1 invocation (first execute) or 0 (reconciled — N/A for fresh success) |
| Caller gets | Agnes `Path` |
| Job continues | Yes — mux + critic with real Agnes footage |

**C2-2-C-3-2 fix verified:** SUCCESS no longer falls through to image fallback.

---

## 4. REUSED

| Aspect | Actual behavior |
|--------|-----------------|
| Helper return | `(cached_path, result)` — same validation as SUCCESS |
| `_resolve_footage` | immediate return L2210 |
| BYP-02 | **NO** |
| Image fallback | **NO** |
| Provider | **0** additional invocations |
| Caller gets | Cached Agnes `Path` |
| Job continues | Yes |

---

## 5. FAILED_RETRYABLE

| Aspect | Actual behavior |
|--------|-----------------|
| Helper return | `(None, result)` L246–252 |
| Exception raised | **NO** (structured — no BYP-02) |
| `_resolve_footage` | try completes; `path` unset/None; **no return** in Agnes block |
| BYP-02 | **NO** |
| Direct `generate_agnes_dialogue_clip` from caller | **NO** |
| Bridge provider | May have invoked **once** inside `IdempotentExecutor` before failure |
| Image fallback | **YES** if `allow_image_fallback=True` L2248 |
| Caller gets | Fallback `Path` (image/stock/still/color) — **not None** |
| Job continues | Yes (production: `require_agnes=False` in `video_pipeline` L770) |
| Semantic preserved upstream | YES in store; **LOST** at `_resolve_footage` (discards `_result`) |

**Information loss:** FAILED_RETRYABLE indistinguishable from other `path=None` cases at caller level.

---

## 6. FAILED_FINAL

Same propagation as FAILED_RETRYABLE:

| Aspect | Actual behavior |
|--------|-----------------|
| Helper | `(None, result)` |
| BYP-02 | **NO** |
| Direct provider from caller | **NO** |
| Image fallback | **YES** (default production) |
| Caller | Fallback `Path` |
| Retry at caller | **NO** explicit retry; `build_dialogue_clip` may run `max_attempts=2` with **new** attempt prompt (outer loop L460), not same fingerprint blind retry |

---

## 7. UNKNOWN

| Aspect | Actual behavior |
|--------|-----------------|
| Helper | `(None, result)` L230–236; logs "no direct retry" |
| Bridge/runtime | UNKNOWN **persisted** in IdempotencyStore |
| BYP-02 | **NO** |
| Direct provider from caller | **NO** |
| Blind retry same fingerprint | **NO** (BUILD-03 gate in bridge) |
| Image fallback | **YES** if `allow_image_fallback=True` |
| Caller | Fallback `Path` |
| Job continues | Yes — **silent degradation** to non-Agnes footage |

**Risk:** UNKNOWN treated same as generic failure at caller — no block/reconcile hook in `_resolve_footage`.

**Contradiction with ideal contract:** C2-2-B defined UNKNOWN should block/reconcile — **not implemented** at single caller yet.

---

## 8. IDENTITY_BLOCKED

| Aspect | Actual behavior |
|--------|-----------------|
| Bridge | `action=identity_blocked` — **no exception** (C2-2-B) |
| Helper | `(None, result)` L238–244 |
| Provider invocation | **0** |
| BYP-02 | **NO** (structured — no exception) |
| Image fallback | **YES** if `allow_image_fallback=True` |
| Caller | Fallback `Path` |
| Fail-closed | **NO** at caller — job may continue with image fallback |

**Contradiction with C2-2-B ideal:** Identity should fail-closed — caller currently **does not** fail closed.

**Legacy note:** If old code path raised `VisualIdentityError`, BYP-02 **would** fire — current result API prevents that for identity_blocked.

---

## 9. Exception Path (CASE G)

| Source | BYP-02? |
|--------|---------|
| Unexpected exception from `_resolve_single_agnes_beat_src` / bridge / runtime | **YES** L2211 |
| Exception inside BYP-02 `generate_agnes_dialogue_clip` | Caught by **second** except L2237; sets `agnes_err`; **no re-raise** |
| Structured FAILED/UNKNOWN/IDENTITY | **NO** — returns normally |

**BYP-02 trigger condition (exact):** Any `Exception` raised from the **try body** L2181–2210 (not from structured None path).

---

## 10. BYP-02 Exact Trigger

**Location:** `scene_builder.py` L2211–2236

```python
try:
    path, _agnes_beat_result = _resolve_single_agnes_beat_src(...)
    if path is not None:
        return path
except Exception:                    # ← BYP-02 entry
    path = generate_agnes_dialogue_clip(...)
    if path valid (>8000 bytes):
        return path
except Exception as exc:             # ← BYP-02 inner failures only
    agnes_err = exc
```

| Condition | BYP-02 fires? |
|-----------|---------------|
| SUCCESS | NO |
| REUSED | NO |
| FAILED_RETRYABLE | **NO** |
| FAILED_FINAL | **NO** |
| UNKNOWN | **NO** |
| IDENTITY_BLOCKED | **NO** |
| Invalid SUCCESS asset (validate fail) | **NO** |
| Bridge/runtime **Exception** | **YES** |
| Missing path without exception | **NO** |

**Structured vs Exception:** Only Python **Exception** from try body triggers BYP-02. Structured failures return `(None, result)` without raising.

---

## 11. Image Fallback Boundary

**Entry:** L2246+ (after Agnes block, when no early return)

| Precondition | Triggers fallback? |
|--------------|-------------------|
| Structured failure (`path=None`) | YES (if `allow_image_fallback=True`) |
| BYP-02 failure | YES |
| No agnes_keys | Skips Agnes block → YES |
| SUCCESS/REUSED | **NO** — early return prevents |

**Production default:** `video_pipeline` L770 `require_agnes=False`, `allow_image_fallback=True` → Agnes failure → image fallback → job continues.

**Assessment:**

| Question | Answer |
|----------|--------|
| Intended? | Historically yes — "never kill short over Agnes miss" |
| Dangerous for UNKNOWN/IDENTITY? | **YES** — semantic failure masked as alternate footage success |
| C-4 scope? | Image fallback hardening / policy |

**Code NOT modified this phase.**

---

## 12. Return Contract — `_resolve_footage()`

**Signature:** `-> Path` (never `Optional[Path]`)

| Outcome | Return value |
|---------|--------------|
| Agnes SUCCESS/REUSED | Agnes mp4 `Path` |
| Agnes failure + image fallback ok | `fb_out` image video `Path` |
| Stock/still ok | respective `Path` |
| All else | `fallback_{idx}_a{attempt}.mp4` color clip L2324–2326 |

**Never returns None.** Always some visual `Path` unless `RuntimeError` when `require_agnes=True` and `allow_image_fallback=False` L2278.

---

## 13. Caller Contract — `build_dialogue_clip()`

```python
video_src = _resolve_footage(...)   # always Path in normal production
_mux_scene(video_src=video_src, ...)
```

| `_resolve_footage` result | `build_dialogue_clip` behavior |
|---------------------------|--------------------------------|
| Agnes Path | Mux with Agnes source |
| Image fallback Path | Mux with fallback — **indistinguishable** at this layer |
| Color clip Path | Mux with color clip |

**Job continue:** Yes — loop proceeds to AV gates/critic. No check whether source was canonical Agnes.

---

## 14. Retry Analysis

| Layer | Retry behavior |
|-------|----------------|
| BUILD-03 executor | Bounded retry for FAILED_RETRYABLE **inside bridge** |
| `_resolve_footage` | **No** retry on FAILED |
| UNKNOWN | **No** blind retry (bridge) |
| BYP-02 | One direct provider attempt on **exception only** |
| `build_dialogue_clip` outer loop | Up to 2 attempts (`max_av_retries`) with possibly revised prompt — **new** `_resolve_footage` call, not same-fingerprint blind retry |

---

## 15. Provider Invocation Analysis

| Outcome | Bridge provider | BYP-02 provider | Caller total (typical) |
|---------|-----------------|-----------------|------------------------|
| SUCCESS | 1 | 0 | 1 |
| REUSED | 0 | 0 | 0 |
| FAILED_RETRYABLE | 0–1 (failed attempt) | 0 | 0–1 |
| FAILED_FINAL | 0–1 | 0 | 0–1 |
| UNKNOWN | 0–1 (uncertain) | 0 | 0–1 |
| IDENTITY_BLOCKED | **0** | 0 | **0** |
| Exception | 0–1 | **0–1** | 0–2 |

**No NEW direct provider callsite** beyond BYP-02 and bridge-internal.

---

## 16. Information Loss

| Point | Loss |
|-------|------|
| L2182 `_agnes_beat_result` discarded | Full `VisualGenerationResult` / outcome enum lost |
| `path=None` convergence | FAILED, UNKNOWN, IDENTITY_BLOCKED, invalid SUCCESS all identical |
| `_resolve_footage` return | Caller cannot tell Agnes vs image fallback vs color clip |
| Job-level | Scene marked success if any Path muxed |

---

## 17. Direct Provider Audit

| Location | Line | Classification |
|----------|------|----------------|
| `agnes_bridge.py` | L209 | BRIDGE_INTERNAL |
| `scene_builder.py` | L1456 | PRODUCTION_BYPASS (BYP-01 split) |
| `scene_builder.py` | L2212 | PRODUCTION_BYPASS (BYP-02 single) |
| `media_assets.py` | L507 | Definition |
| `chernobyl_30_train.py` | L476 | DEV |
| `_smoke_agnes_clip.py` | L25 | DEV |

**NEW production callsite:** **NONE**

**BYP-01:** present | **BYP-02:** present L2211–2236

---

## 18. Test Matrix (for C2-2-C-3-3-2+)

| Scenario | provider_calls (caller) | BYP-02 | image_fallback | return type | outcome visible |
|----------|-------------------------|--------|----------------|-------------|-----------------|
| SUCCESS | 0–1 | NO | NO | Agnes Path | NO (discarded) |
| REUSED | 0 | NO | NO | Agnes Path | NO |
| FAILED_RETRYABLE | 0 | NO | YES* | fallback Path | NO |
| FAILED_FINAL | 0 | NO | YES* | fallback Path | NO |
| UNKNOWN | 0 | NO | YES* | fallback Path | NO |
| IDENTITY_BLOCKED | 0 | NO | YES* | fallback Path | NO |
| Exception in bridge | 0–1 | YES | maybe | Agnes or fallback | NO |
| Invalid SUCCESS asset | 0 | NO | YES* | fallback Path | NO |

\* when `allow_image_fallback=True` (production default)

---

## 19. Risks

| ID | Risk | Severity |
|----|------|----------|
| R1 | UNKNOWN → image fallback → job continues | P1 (policy) |
| R2 | IDENTITY_BLOCKED → image fallback — not fail-closed | P1 |
| R3 | Structured failure semantics discarded at L2182 | P1 |
| R4 | BYP-02 still bypasses idempotency on exception | P1 (known, C2-2-E) |
| R5 | Invalid SUCCESS → fallback without explicit failure signal | P2 |

---

## 20. Recommended Next Micro-Step

**C2-2-C-3-3-2:** Failure propagation hardening (minimal):

1. Preserve `_agnes_beat_result` / outcome in `_resolve_footage` decision logic
2. UNKNOWN → do **not** enter image fallback (block/reconcile path)
3. IDENTITY_BLOCKED → fail-closed (raise or explicit error return)
4. FAILED → controlled policy (no BYP-02, document fallback boundary)
5. Dedicated tests per test matrix §18

**Do NOT remove BYP-02** until C2-2-E.

---

## 21. Limitations

- Audit read-only — no runtime execution this phase
- `build_dialogue_clip` full critic loop not exhaustively traced
- Production env var overrides not enumerated

---

## 22. Final Verdict

**C2-2-C-3-3-1 = PASS**

All six structured outcomes + exception path mapped from **actual code**. BYP-02 trigger precisely identified. Image fallback boundary documented. Information loss points identified. Zero code changes.

**Next:** C2-2-C-3-3-2
