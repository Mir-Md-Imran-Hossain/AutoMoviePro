# T004-C C-0 — Visual Production Pre-Audit

**Marathon:** AMP-003 / TASK-004 / T004-C  
**Phase:** C-0 PRE-AUDIT  
**Checkpoint:** AMP003-T004-C0-PASS  
**Date:** 2026-08-31  
**Code changes:** 0

---

## Executive Summary

Production visual root: `video_pipeline.generate_video()` → `build_dialogue_clip()` → `_resolve_footage()` / `_build_split_dialogue_clip()`.

BUILD-04A idempotency layer (`agnes_bridge` → `visual_runtime`) **partially wired** for Agnes beats. Image fallback, stock paths, and bridge-failure fallbacks **bypass** canonical visual runtime.

**docs/build04a/** — **NOT_FOUND** (BUILD-04A tests live in `scripts/test_build04a_visual_runtime.py` only).

---

## 1. Production Entry Point

| # | Caller | Callee | Class |
|---|--------|--------|-------|
| P1 | `video_pipeline.py` L748 | `build_dialogue_clip()` | **PRODUCTION** |
| P2 | `build_dialogue_clip()` L242 | `_resolve_footage()` | **PRODUCTION** |
| P3 | `build_dialogue_clip()` L121 | `_build_split_dialogue_clip()` | **PRODUCTION** (long audio > chunk) |
| P4 | `scene_builder.py` L822 | `build_image_video_fallback()` | **PRODUCTION** (cutoff persist) |

No direct `execute_visual_request` call from `video_pipeline.py` — visual path is entirely via `scene_builder`.

---

## 2. Agnes Primary Path

```
build_dialogue_clip / _build_split_dialogue_clip
    ↓
idempotent_generate_agnes_beat (agnes_bridge.py)
    ↓
VisualRequestSpec (provider=agnes, model=agnes-video-v2.0)
    ↓
execute_visual_request (visual_runtime.py)
    ↓
IdempotentExecutor: claim → execute_fn → validate → persist → checkpoint
    ↓
provider_fn → generate_agnes_dialogue_clip (media_assets.py)
```

### Call sites (agnes_bridge)

| File | Function | Lines | Class |
|------|----------|-------|-------|
| `scene_builder.py` | `_resolve_footage` | L1947–1965 | PRODUCTION |
| `scene_builder.py` | `_build_split_dialogue_clip` | L1204–1222 | PRODUCTION |

### Legacy bypass on bridge Exception

| File | Lines | Fallback | Class |
|------|-------|----------|-------|
| `scene_builder.py` | L1966–1982 | `generate_agnes_dialogue_clip` direct | **LEGACY PRODUCTION BYPASS** |
| `scene_builder.py` | L1223–1239 | `generate_agnes_dialogue_clip` direct | **LEGACY PRODUCTION BYPASS** |

---

## 3. Split Dialogue Path

**Trigger:** `build_dialogue_clip()` L110 — narration > `AGNES_AUDIO_CHUNK_MAX + 0.35`

```
_build_split_dialogue_clip()
    ↓
plan_agnes_segments() — segment planning
    ↓
per part i: idempotent_generate_agnes_beat(part_index=i)
    OR generate_agnes_dialogue_clip fallback
    ↓
on Agnes miss: _resolve_footage(idx=idx*10+i, require_agnes=False)  ← identity hack
    ↓
_mux_scene per part → concat parts
```

**Identity gap:** Split fallback uses `scene_id=idx*10+i` in `_resolve_footage`, not canonical `segment_id`. TTS split uses `dialogue_id=f"split-{idx:02d}"`, `segment_id=f"seg-{i+1:02d}"` (L1065–1083) but **not propagated to VisualRequestSpec**.

---

## 4. Image Fallback Path

```
_resolve_footage (Agnes fail / no keys)
    ↓
build_image_video_fallback (fallback_image_video.py L850)
    ↓
FallbackPipelineService — Pollinations/Google image + Ken Burns FFmpeg
    ↓
NO visual_runtime / NO idempotency bridge / NO visual_provenance
```

Additional image fallback call sites:

| Location | Lines | Class |
|----------|-------|-------|
| `_build_split_dialogue_clip` Agnes miss | L1261–1283 via `_resolve_footage` | PRODUCTION |
| `build_dialogue_clip` cutoff persist | L822–831 | PRODUCTION |
| `localization.py` | L251 `extend_image_master_for_audio` | PRODUCTION (out of T004-C scope — DOCUMENT) |

**Stock/Pexels path:** `_resolve_footage` L2033+ — category stock video — **no idempotency bridge**.

---

## 5. Identity Path

### VisualRequestSpec (`visual_request.py`)

| Field | Present | Used in fingerprint |
|-------|---------|---------------------|
| job_id | ✓ | ✓ |
| scene_id | ✓ | ✓ |
| visual_plan_id | ✓ (element or p{N}) | ✓ |
| dialogue_id | **NO** | **NO** |
| segment_id | **NO** | **NO** |
| prompt / visual_prompt | ✓ | ✓ |
| seed | ✓ optional | ✓ (if set) |
| provider / model | ✓ | ✓ |
| generation_mode | ✓ | ✓ |
| size / duration_sec | ✓ | ✓ |
| revision_id | **NO** | **NO** |

`entity_id` = `scene-{scene_id:02d}-{visual_plan_id}`

### T004-B validated scene handoff

`video_pipeline` passes validated scene dict with `canonical_scene_id`, `dialogue_id` — **NOT consumed by scene_builder / agnes_bridge**.

### scene_builder mux identity

`_mux_scene`: `dialogue_id=f"scene-{idx:02d}"` (L279) — hardcoded, not from canonical Scene.

---

## 6. Validation Path

| Layer | Module | Production |
|-------|--------|------------|
| MP4 container | `visual_validation.validate_video_asset` | YES — via visual_runtime |
| Image format | `visual_validation.validate_image_asset` | YES — if mode=image |
| Min bytes | 8000 video / 1000 image | YES |
| ffprobe duration/dimensions | **NOT in visual_validation** | GAP |
| Post-mux AV gates | `av_quality_gates`, `diagnose_clip` | YES — after visual, separate layer |

Image fallback output: validated only by file size + mux gates — **not visual_validation.py**.

---

## 7. Provenance Path

| Asset source | Provenance saved? | Location |
|--------------|-------------------|----------|
| Agnes via visual_runtime | YES | `{work}/visual_provenance/{fp[:24]}.json` |
| Agnes direct bypass | **NO** | — |
| Image fallback | **NO** | fallback writes meta in work dir only |
| Stock video | **NO** | — |

Provenance fields (when saved): job_id, provider, model, prompt_hash, scene_id, visual_plan_id, seed, generation_id — **no secrets**.

---

## 8. Fingerprint Path

- `compute_visual_fingerprint(spec)` → BUILD-03 `compute_fingerprint(stage=visual)`
- Legacy parallel key: `GenerationCache.make_generation_key` in `_legacy_key()`
- `generation_bridge.idempotent_generation_request` — alternate fingerprint — **NOT used in production** (DEAD_CODE for prod path)

---

## 9. Seed Handling

| Path | Seed behavior |
|------|---------------|
| `VisualRequestSpec.seed` | Optional; passed to mock provider only |
| `agnes_bridge` | **Does not set seed** on spec |
| `generate_agnes_dialogue_clip` | **No seed parameter** — Agnes API path |
| `fallback_image_video` | `character_base_seed()` + beat index; persisted in fallback meta |
| Provenance | `requested_seed` / `actual_seed` from spec (often None for Agnes) |

**Gap:** Agnes path has no real seed capture; fallback has local seed lineage not linked to visual fingerprint.

---

## 10. Checkpoint / Retry / UNKNOWN

| Mechanism | Agnes via bridge | Direct bypass | Image fallback |
|-----------|------------------|---------------|----------------|
| IdempotencyStore claim | ✓ | ✗ | ✗ |
| Checkpoint (IdempotentExecutor) | ✓ | ✗ | ✗ |
| UNKNOWN reconcile | `reconcile_visual_unknown` | ✗ | ✗ |
| Retry (FAILED_RETRYABLE) | via executor | uncontrolled | uncontrolled |

Attempt counter in `_resolve_footage`: `attempt` param changes output filename suffix — **may change identity** vs fingerprint (visual_plan_id uses element not attempt).

---

## 11. Concurrency / Cache

- BUILD-04A: `execute_visual_request` uses IdempotentExecutor (thread lock)
- BUILD-04A test: concurrent duplicate — max 1 provider call
- `GenerationCache` inside `_execute` — legacy cache layer parallel to idempotency store
- Image fallback: **no concurrent protection**

---

## 12. Targeted Regeneration

- BUILD-04F: `quality/repair_planner.py` — `RepairScope.VISUAL_ASSET`, `VISUAL_PLAN`
- `quality/repair_runtime.execute_repair_request` — idempotent repair tracking
- **Not wired** to re-invoke `agnes_bridge` in production scene_builder loop
- Scene regen via `max_av_retries` + attempt suffix — partial, not repair-planner driven

---

## 13. Direct Provider Calls (Production)

| Call | File | Class | Idempotency |
|------|------|-------|-------------|
| `generate_agnes_dialogue_clip` | scene_builder (fallback) | LEGACY PRODUCTION | ✗ |
| `build_image_video_fallback` | scene_builder | PRODUCTION | ✗ |
| Pexels/stock in `_resolve_footage` | scene_builder | PRODUCTION | ✗ |
| `generate_product_still` | imported scene_builder | UNCLEAR/dead in hot path | ✗ |

### TEST_ONLY / DEV_ONLY direct calls

| Call | File | Class |
|------|------|-------|
| `generate_agnes_dialogue_clip` | `scripts/_smoke_agnes_clip.py` | DEV_ONLY |
| `generate_agnes_dialogue_clip` | `scripts/chernobyl_30_train.py` | DEV_ONLY |

---

## 14. Existing Tests Mapped

| Test file | Scope | Tests |
|-----------|-------|-------|
| `scripts/test_build04a_visual_runtime.py` | visual_runtime mock | 18 |
| `scripts/test_amp003_task003.py` | global idempotency | includes bypass doc |
| `scripts/test_amp003_task004_b_*.py` | scene boundary | 26 (T004-B) |

**No dedicated T004-C tests yet.**

---

## 15. BUILD-04A Module Inventory

| Module | Role |
|--------|------|
| `visual_request.py` | VisualRequestSpec + fingerprint |
| `visual_runtime.py` | Canonical execute path |
| `agnes_bridge.py` | Agnes → visual_runtime wrapper |
| `visual_validation.py` | Asset validation |
| `visual_provenance.py` | Provenance persistence |
| `mock_visual_provider.py` | Offline test provider |
| `generation_bridge.py` | Alternate bridge — **unused in production** |

---

## 16. Gap Severity (C-0 Findings)

| ID | Gap | Severity | Target Phase |
|----|-----|----------|--------------|
| GAP-C01 | Agnes bridge Exception → direct provider | P1 | C-2 |
| GAP-C02 | Image fallback bypasses visual_runtime | P1 | C-4 |
| GAP-C03 | dialogue_id/segment_id not in VisualRequestSpec | P1 | C-1/C-2 |
| GAP-C04 | T004-B canonical IDs not propagated to visual | P1 | C-2 |
| GAP-C05 | Split path scene_id hack (idx*10+i) | P1 | C-2 |
| GAP-C06 | Seed not captured for Agnes path | P2 | C-3 |
| GAP-C07 | Image fallback no provenance/idempotency | P1 | C-4/C-6 |
| GAP-C08 | Stock video path untracked | P2 | C-10 |
| GAP-C09 | Repair planner not wired to visual regen | P1 | C-8 |
| GAP-C10 | generation_bridge unused | INFO | — |

---

## C-0 Acceptance Checklist

- [x] production visual root found
- [x] Agnes path mapped
- [x] image fallback mapped
- [x] split path mapped
- [x] identity path mapped
- [x] validation path mapped
- [x] provenance path mapped
- [x] direct provider calls mapped
- [x] fallback paths mapped
- [x] existing tests mapped
- [x] no code changes

**C-0 = PASS**  
**Checkpoint = AMP003-T004-C0-PASS**

---

## Next Phase

**C-1** — Visual Request Contract Audit (`VisualRequestSpec` fingerprint + identity fields)

**STOP — C-1 not started in this command.**
