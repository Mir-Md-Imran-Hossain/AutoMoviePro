# T004-C2-2-C-3-1 — Single Agnes Path Discovery

**Marathon:** AMP-003 / TASK-004 / T004-C / C2-2-C  
**Phase:** C2-2-C-3-1 (Discovery — NO CODE CHANGE)  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C2-2-C-3-1-PASS

---

## 1. Production call graph

```
video_pipeline.generate_video()
    ↓
build_dialogue_clip()                    scene_builder.py L152
    ↓
[single-beat gate]                         L220–262 NOT taken when audio ≤ chunk max
    ↓
_resolve_footage()                         scene_builder.py L2025
    ↓
idempotent_generate_agnes_beat()           L2079–2100 (LEGACY Path|None)
    ↓ (on Exception)
generate_agnes_dialogue_clip()             L2102–2117 (BYP-02)
    ↓
return path OR fall through
    ↓
build_image_video_fallback()               L2138+ (image fallback — C-4)
    ↓
stock / still / color fallback
    ↓
build_dialogue_clip: _mux_scene()          L387
    ↓
AV gates / critic / agent loop
    ↓
return target clip Path
```

---

## 2. Single-beat vs split detection

**Function:** `build_dialogue_clip()` L152

| Condition | Path |
|-----------|------|
| `spoken_est > AGNES_AUDIO_CHUNK_MAX + 0.35` AND `require_agnes` AND `agnes_keys` | **Split** → `_build_split_dialogue_clip()` (C2-2-C-2 migrated) |
| Otherwise | **Single** → `_resolve_footage()` in attempt loop L357 |

**C2-2-C-3 scope:** Single-beat branch only. Split path **NOT modified**.

---

## 3. Current single-path bridge call

**Function:** `_resolve_footage()` L2025–2216  
**Bridge block:** L2069–2134 (inside `if agnes_keys:`)

### Current code

```python
try:
    path = idempotent_generate_agnes_beat(      # LEGACY — Path|None
        work_dir=work,
        job_id=job_id or work.name,
        scene_id=idx,
        part_index=0,
        attempt=attempt,
        product_name=product_name or "gadget",
        element=element,
        visual_prompt=visual_prompt or visual_query,
        out_path=agnes_out,
        narration_hint=narration_hint,
        size=size,
        duration_hint=min(max(duration, AGNES_MIN_SECONDS), AGNES_AUDIO_CHUNK_MAX),
        override_prompt=override_prompt,
        niche=niche,
        use_catalog_image=_should_use_catalog(niche, product_name),
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
    )
except Exception:
    path = generate_agnes_dialogue_clip(...)   # BYP-02
    if path and path.exists() and path.stat().st_size > 8000:
        return path
except Exception as exc:                       # L2127 — catches BYP-02 inner failures only
    agnes_err = exc
    ...
```

### Output path pattern

`agnes_{idx:02d}_{element}{suffix}.mp4` where `suffix = ""` or `"_r{attempt}"`

---

## 4. Current result handling

| Bridge outcome | Current behavior |
|----------------|------------------|
| Returns valid `Path` | **`path` assigned but NO `return`** — falls through to image fallback L2138 |
| Returns `None` | Falls through to image fallback |
| Raises `VisualIdentityError` | BYP-02 fires → direct Agnes |
| Raises other `Exception` | BYP-02 fires → direct Agnes |
| BYP-02 success (>8000 bytes) | **Early `return path`** L2126 |
| BYP-02 failure | Falls through to image fallback |

### Critical discovery — missing success return

Bridge success does **not** early-return before image fallback. Only BYP-02 success returns explicitly.

**C2-2-C-3-2 implication:** Migration MUST add explicit early return on SUCCESS/REUSED (with validation) to restore intended single-beat behavior. This matches BYP-02's implicit contract (`exists` + `st_size > 8000`) plus split-path `validate_visual_asset()`.

---

## 5. BYP-02 location and semantics

| Item | Value |
|------|-------|
| Location | `scene_builder.py` L2101–2126 |
| Classification | **PRODUCTION_FALLBACK** |
| Trigger | Any `Exception` from bridge try body |
| Does NOT trigger on | Bridge `None` return |
| Removal phase | **C2-2-E** |
| Dead code | L2127–2134 second `except` — unreachable for try-body exceptions; catches BYP-02 inner failures |

---

## 6. Image fallback boundary

**Starts:** L2136 (after Agnes block, outside `if agnes_keys` inner try)

| Step | Function | Line |
|------|----------|------|
| 1 | `build_image_video_fallback()` | L2140–2164 |
| 2 | Pexels stock | L2175–2190 |
| 3 | Product still Ken-Burns | L2192–2212 |
| 4 | Color clip fallback | L2214–2216 |

**C2-2-C-3 scope:** Do NOT modify this block. Owned by C-4 for future hardening.

---

## 7. Identity propagation

### From production caller (`video_pipeline.py` L748–775)

| Field | Source |
|-------|--------|
| `job_id` | `work.name` |
| `dialogue_id` | `scene.get("dialogue_id")` |
| `canonical_scene_id` | `scene.get("canonical_scene_id")` |
| `script_id` | `scene.get("script_id")` or `plan.get("script_id")` |

### Into bridge call (`_resolve_footage` L2081–2099)

| Field | Passed | Notes |
|-------|--------|-------|
| `job_id` | ✓ `job_id or work.name` | |
| `dialogue_id` | ✓ | |
| `canonical_scene_id` | ✓ | |
| `script_id` | ✓ | |
| `segment_id` | **NOT passed** | bridge default `""`; single-beat uses `part_index=0` |
| `revision_id` | **NOT passed** | bridge default `""` |
| `production_identity` | **NOT passed** | auto-detected when dialogue_id + canonical_scene_id both set |

**No `idx * 10 + i` in single path** (that hack exists only in split image-fallback `_resolve_footage` call L1390).

---

## 8. Existing validation

| Layer | Validation |
|-------|------------|
| Bridge/runtime | `validate_visual_asset()` inside `execute_visual_request()` |
| BYP-02 return | `path.exists()` + `st_size > 8000` |
| Bridge legacy return | `path.is_file()` check inside `idempotent_generate_agnes_beat()` |
| Single path post-bridge | **None** (no caller-side validation before return — and no return on bridge success) |

**C2-2-C-3-2:** Reuse `validate_visual_asset(path, mode="video")` per split-path pattern (`_resolve_split_agnes_beat_src`).

---

## 9. Retry behavior

| Scope | Behavior |
|-------|----------|
| `build_dialogue_clip` | `max_attempts = 1 + min(1, max_av_retries)` — L351 |
| `_resolve_footage` | Receives `attempt`; stale `agnes_out` unlinked when `attempt > 1` L2073 |
| Runtime FAILED_RETRYABLE | BUILD-03 executor bounded retry — inside bridge |
| Caller | No explicit FAILED_RETRYABLE handling today |

---

## 10. Downstream assembly (post `_resolve_footage`)

```python
video_src = _resolve_footage(...)           # L359
_mux_scene(video_src=video_src, ...)        # L387
# AV gates, critic, agent repair loop
return target                               # final scene clip
```

**Preservation requirement:** `_resolve_footage` must continue returning `Path` on success — same contract for `build_dialogue_clip`.

---

## 11. Split vs single pattern comparison

| Aspect | Split (C2-2-C-2) | Single (C2-2-C-3 target) |
|--------|------------------|--------------------------|
| Helper | `_resolve_split_agnes_beat_src()` | **Needs** `_resolve_single_agnes_beat_src()` or equivalent |
| API | `idempotent_generate_agnes_beat_result()` | Same |
| Return to caller | `(Optional[Path], VisualGenerationResult)` | Should produce `Optional[Path]` for `_resolve_footage` return |
| `part_index` | `i + 1` | `0` |
| `segment_id` | `f"seg-{i+1:02d}"` | Not passed (default "") |
| Success return | Used in split loop | **Missing today** — must add in migration |
| Failure → image | `if not src` in split loop | Fall through in `_resolve_footage` |

---

## 12. Canonical API reference (C2-2-C-1)

| API | Location |
|-----|----------|
| `idempotent_generate_agnes_beat_result()` | `agnes_bridge.py` L132 |
| `classify_agnes_beat_outcome()` | `agnes_bridge.py` L34 |
| `AgnesBeatOutcome` | `agnes_bridge.py` L23 |
| `VisualGenerationResult` | `visual_runtime.py` L33 |
| Legacy adapter | `idempotent_generate_agnes_beat()` — remain for compat |

---

## 13. Direct provider inventory (baseline)

| Location | Classification |
|----------|----------------|
| `agnes_bridge.py` L207–221 | BRIDGE_INTERNAL |
| `scene_builder.py` L1353 | BYP-01 (split — unchanged) |
| `scene_builder.py` L2102 | **BYP-02** (single) |
| `scripts/chernobyl_30_train.py` | DEV |
| `scripts/_smoke_agnes_clip.py` | DEV |

---

## 14. C2-2-C-3-2 migration plan (for next phase)

1. Add `_resolve_single_agnes_beat_src()` — mirror split helper semantics, single-specific params
2. Replace L2079–2100 canonical call with helper inside try block
3. On SUCCESS/REUSED + validated path → **`return path`** (fixes missing return)
4. On FAILED/UNKNOWN/IDENTITY → `path = None`, fall through (no direct Agnes)
5. Preserve BYP-02 except block unchanged
6. Do NOT modify image fallback L2138+

---

## 15. C2-2-C-3-1 verdict

| Criterion | Status |
|-----------|--------|
| Full single path traced | **PASS** |
| Bridge call documented | **PASS** |
| Result handling documented | **PASS** |
| BYP-02 located | **PASS** L2101–2126 |
| Image fallback boundary | **PASS** L2136+ |
| Identity propagation | **PASS** |
| Validation gap identified | **PASS** |
| Code changed | **NONE** |

**Checkpoint:** `AMP003-T004-C2-2-C-3-1-PASS`

**Next:** C2-2-C-3-2 — Canonical result API migration

**Blockers:** None for discovery. Migration must address missing bridge-success return.
