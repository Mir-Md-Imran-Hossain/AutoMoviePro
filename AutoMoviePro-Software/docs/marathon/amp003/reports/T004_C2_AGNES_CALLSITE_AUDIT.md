# T004-C2 C2-0 — Agnes Callsite Forensic Audit

**Marathon:** AMP-003 / TASK-004 / T004-C  
**Phase:** C2-0 AGNES CALLSITE FORENSIC AUDIT  
**Date:** 2026-08-31  
**Code changes:** 0  
**Prior checkpoint:** AMP003-T004-C1-PASS

---

## 1. Audit Scope

Repository-wide search for:

| Pattern | Hits (code) |
|---------|-------------|
| `generate_agnes_dialogue_clip` | 5 Python files (excl. docs) |
| `idempotent_generate_agnes_beat` | 3 Python files |
| `execute_visual_request` | 4 Python files |
| `agnes_bridge` | 2 Python files |
| `build_dialogue_clip` | 6 Python call sites |
| `_resolve_footage` | internal scene_builder only |
| `_build_split_dialogue_clip` | internal scene_builder only |
| `request_agnes_clip` | 1 definition, **0 callers** (DEAD_CODE) |
| `_agnes_video` | media_assets internal only |

---

## 2. Production Root Call Graph

```
video_pipeline.py (L748)
    ↓
build_dialogue_clip()                    [PRODUCTION entry]
    ↓
    ├─ spoken_est > chunk max?
    │       ↓ YES
    │   _build_split_dialogue_clip()     [PRODUCTION split path]
    │       ↓ per part i, attempt
    │   idempotent_generate_agnes_beat() [CANONICAL bridge]
    │       OR
    │   generate_agnes_dialogue_clip()  [P1 BYPASS — Exception fallback L1242]
    │       ↓ on miss
    │   _resolve_footage(idx*10+i, agnes_api="")  [image/stock — NOT Agnes, C-4 scope]
    │
    └─ single beat
            ↓ attempt loop L240
        _resolve_footage()                 [PRODUCTION single path]
            ↓
        idempotent_generate_agnes_beat()   [CANONICAL bridge L1969]
            OR
        generate_agnes_dialogue_clip()     [P1 BYPASS — Exception fallback L1991]
            ↓ on fail
        build_image_video_fallback()       [image — C-4 scope, NOT Agnes]
```

**Canonical runtime chain (when bridge succeeds):**

```
idempotent_generate_agnes_beat (agnes_bridge.py)
    → VisualRequestSpec + identity validation
    → execute_visual_request (visual_runtime.py)
    → IdempotentExecutor claim/execute/reuse
    → provider_fn → generate_agnes_dialogue_clip (bridge-internal ONLY)
    → validate_visual_asset
    → save_visual_provenance
    → checkpoint
```

---

## 3. Complete Callsite Registry

### 3.1 `generate_agnes_dialogue_clip` — Provider Definition

| Location | Line | Class | Notes |
|----------|------|-------|-------|
| `pipeline/media_assets.py` | L507 | **PROVIDER DEF** | Actual Agnes API wrapper; calls `_agnes_video` |

### 3.2 Production Bridge Path (CANONICAL)

| Location | Line | Class | Path |
|----------|------|-------|------|
| `pipeline/idempotency/agnes_bridge.py` | L96–111 | **BRIDGE INTERNAL** | `provider_fn` closure — **ALLOWED** (inside bridge → visual_runtime) |
| `pipeline/idempotency/agnes_bridge.py` | L115 | **BRIDGE → RUNTIME** | `execute_visual_request` |
| `pipeline/scene_builder.py` | L1969–1990 | **PRODUCTION** | Single-beat: `_resolve_footage` → bridge |
| `pipeline/scene_builder.py` | L1219–1241 | **PRODUCTION** | Split: `_build_split_dialogue_clip` → bridge |

### 3.3 Production Direct Provider Bypass (P1 GAP)

| Location | Line | Class | Trigger | Idempotency |
|----------|------|-------|---------|-------------|
| `pipeline/scene_builder.py` | L1242–1258 | **PRODUCTION BYPASS** | `except Exception` after bridge fail | **NONE** |
| `pipeline/scene_builder.py` | L1991–2007 | **PRODUCTION BYPASS** | `except Exception` after bridge fail | **NONE** |

**C-0/C-1 confirmed finding:** bridge exception → direct `generate_agnes_dialogue_clip()` → idempotency bypass.

### 3.4 Test / Dev / Legacy Callers

| Location | Line | Class | Notes |
|----------|------|-------|-------|
| `scripts/test_amp003_task004_c1_visual_identity.py` | L225 | **TEST_ONLY** | `use_mock=True`; identity guard test only |
| `scripts/_smoke_agnes_clip.py` | L25 | **DEV_ONLY** | Manual smoke test; direct provider |
| `scripts/chernobyl_30_train.py` | L476 | **DEV_ONLY** | Training script; direct provider + retry loop |
| `scripts/marathon_av_100.py` | L230 | **DEV_ONLY** | Calls `build_dialogue_clip` → inherits production paths |
| `scripts/image_fallback_train.py` | L405 | **DEV_ONLY** | Calls `build_dialogue_clip`; forces image fallback mode |
| `scripts/resume_agnes_short.py` | L45 | **DEV_ONLY** | Calls `build_dialogue_clip` |
| `scripts/rebuild_agnes_short.py` | L82 | **DEV_ONLY** | Calls `build_dialogue_clip` |
| `scripts/verify_av_critic.py` | L86 | **DEV_ONLY** | Calls `build_dialogue_clip` |
| `pipeline/ai_providers.py` | L196 | **DEAD_CODE** | `request_agnes_clip` — no callers found |

### 3.5 Related Agnes API (Out of C2 Dialogue Scope)

| Location | Line | Class | Notes |
|----------|------|-------|-------|
| `pipeline/media_assets.py` | L388 | **LEGACY/OTHER** | `generate_intro_video` → `_agnes_free_or_paid` — intro, not dialogue beat |
| `pipeline/media_assets.py` | L799 | **PROVIDER INTERNAL** | `_agnes_video` — HTTP poll implementation |

---

## 4. Path Classification

### 4.1 Single-Beat Production Path

| Step | Function | File | Line | Bridge? |
|------|----------|------|------|---------|
| Entry | `build_dialogue_clip` | scene_builder | L41 | — |
| Footage | `_resolve_footage` | scene_builder | L1896 | — |
| Primary | `idempotent_generate_agnes_beat` | scene_builder | L1969 | ✓ |
| Fallback | `generate_agnes_dialogue_clip` | scene_builder | L1991 | ✗ BYPASS |
| Post-fail | `build_image_video_fallback` | scene_builder | L2030 | N/A (not Agnes) |

**Identity (post C-1):** `dialogue_id`, `canonical_scene_id`, `script_id` propagated from `video_pipeline` validated handoff.

**Retry:** `build_dialogue_clip` loop L240–809; `attempt` passed to `_resolve_footage`; stale file unlink L1963 when attempt>1.

**Repair:** `_repair_cutoff_with_complete_tts` L1535 — TTS-only, **no Agnes regen** (by design).

### 4.2 Split-Dialogue Production Path

| Step | Function | File | Line | Bridge? |
|------|----------|------|------|---------|
| Entry | `_build_split_dialogue_clip` | scene_builder | L981 | — |
| Per-part | `idempotent_generate_agnes_beat` | scene_builder | L1219 | ✓ |
| Fallback | `generate_agnes_dialogue_clip` | scene_builder | L1242 | ✗ BYPASS |
| Miss fallback | `_resolve_footage(idx*10+i)` | scene_builder | L1280 | image/stock only |

**Identity:** `part_index=i+1`, `segment_id=seg-{i+1:02d}`, canonical dialogue/scene from handoff.

**Known hack (C-1 deferred):** `idx*10+i` used only for image fallback `_resolve_footage` call — **NOT Agnes path**.

### 4.3 Retry Path

| Context | Mechanism | Fingerprint impact |
|---------|-----------|-------------------|
| Single-beat AV critic | `max_av_retries` loop; revised prompt | Same identity unless revision_id set |
| Split part | `attempt` loop L1211 | attempt excluded from fingerprint (BUILD-03) |
| Bridge internal | IdempotentExecutor retry policy | Same fingerprint on retry |

### 4.4 Repair Path

| Repair | Agnes involved? | Notes |
|--------|-----------------|-------|
| Cutoff TTS repair | **NO** | `_repair_cutoff_with_complete_tts` |
| Critic prompt revision | **YES** (via _resolve_footage retry) | May hit bridge or bypass |
| Image Ken-Burns fallback | **NO** (Agnes skipped) | C-4 scope |

---

## 5. `execute_visual_request` Callsites

| Location | Class | Provider |
|----------|-------|----------|
| `agnes_bridge.py` L115 | **PRODUCTION** | Agnes via provider_fn |
| `test_build04a_visual_runtime.py` | TEST_ONLY | Mock |
| `test_amp003_task004_c1_visual_identity.py` | TEST_ONLY | Mock |

**No direct `execute_visual_request` from `video_pipeline.py`.**

---

## 6. Production Bypass Summary

| Invariant | Current State |
|-----------|---------------|
| INVARIANT-C2-01: All production Agnes via canonical boundary | **VIOLATED** — 2 Exception fallback sites |
| Production direct `generate_agnes_dialogue_clip` outside bridge | **2 active bypasses** in scene_builder |
| Bridge-internal provider_fn | **COMPLIANT** — agnes_bridge only |
| Dev script direct calls | **OUT OF PRODUCTION SCOPE** — documented |

**Production bypass count (must → 0 in C2-5):** **2**

---

## 7. Identity Propagation Status (Baseline for C2-1+)

| Field | Single path | Split path | Bridge | Provenance |
|-------|-------------|------------|--------|------------|
| job_id | ✓ | ✓ | ✓ | ✓ |
| scene_id (int) | ✓ | ✓ | ✓ | ✓ |
| canonical_scene_id | ✓ (if handoff) | ✓ | ✓ validated | ✓ |
| dialogue_id | ✓ | ✓ | ✓ validated | ✓ |
| segment_id | N/A | ✓ seg-NN | ✓ required if part>0 | ✓ |
| revision_id | optional | optional | ✓ | ✓ |
| prompt | ✓ | ✓ per-part | ✓ | ✓ (hash) |
| provider/model | agnes / v2.0 | same | hardcoded | ✓ |
| seed | N/A (Agnes) | N/A | not set | absent |

**Gap:** Exception bypass paths do **not** inherit idempotency/provenance even when identity is present.

---

## 8. P1 Findings for C2 Implementation

| ID | Finding | Target Phase |
|----|---------|--------------|
| C2-P1-01 | Exception fallback L1242 bypasses idempotency (split) | C2-2 |
| C2-P1-02 | Exception fallback L1991 bypasses idempotency (single) | C2-2 |
| C2-P1-03 | UNKNOWN state not surfaced to caller on bypass | C2-2, C2-6 |
| C2-P1-04 | Split image fallback uses idx*10+i (not Agnes) | Document → C-4/C2-4 |

---

## 9. Deferred (Not C2-0 Action)

| Item | Reason | Task |
|------|--------|------|
| Image fallback wiring | C-4 scope | T004-C C-4 |
| Domain segment_id | T004-E | T004-E |
| Intro `generate_intro_video` Agnes | Not dialogue beat path | Out of C2 |
| Dev script direct calls | Not production runtime | Document only |

---

## C2-0 Acceptance Checklist

- [x] সব Agnes callsite mapped
- [x] সব production callsite identified
- [x] direct provider calls identified (2 bypass + 1 bridge-internal allowed)
- [x] fallback paths identified (Exception bypass + image/stock)
- [x] single-beat path mapped
- [x] split path mapped
- [x] retry path mapped
- [x] repair path mapped
- [x] no code changes

---

## C2-0 Verdict

**PASS**  
**Checkpoint:** `AMP003-T004-C2-0-PASS`

**Next:** C2-1 Bridge Boundary Audit (no implementation until C2-1 scope)
