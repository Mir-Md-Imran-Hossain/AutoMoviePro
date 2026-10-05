# T004-C1 C1-0 — Visual Contract Discovery

**Marathon:** AMP-003 / TASK-004 / T004-C  
**Phase:** C1-0 CONTRACT DISCOVERY  
**Date:** 2026-08-31  
**Code changes:** 0

---

## 1. Contract Inventory

| Contract | File | Key identity fields |
|----------|------|---------------------|
| Scene | `domain/scene.py` | `id` (UUID), `scene_index`, `dialogue_id`, `script_id`, `legacy_scene_id` |
| VisualPlan | `domain/scene.py` | `scene_id` (UUID str), `dialogue_id`, `prompt_hash` |
| Dialogue | `domain/script.py` | `id` (UUID), `script_id`, `scene_id` (UUID), `element`, `text` |
| Script | `domain/script.py` | `id`, `topic_id`, `sections[]` |
| VisualRequestSpec | `pipeline/idempotency/visual_request.py` | `job_id`, `scene_id` (int), `visual_plan_id`, provider/model/mode/prompt/seed |
| AudioRequestSpec (reference) | `pipeline/idempotency/audio_request.py` | `dialogue_id`, `part_index`, `segment_id` — **pattern to mirror** |

---

## 2. Identity Source Map

| Field | Current source | Status |
|-------|----------------|--------|
| **job_id** | `work.name` / `video_pipeline` work dir | VERIFIED — scene_builder L1951, agnes_bridge param |
| **scene_id (int)** | Loop index `idx` in `build_dialogue_clip` | VERIFIED — legacy runtime index |
| **canonical_scene_id (UUID)** | T004-B `scene_to_handoff_dict` → `canonical_scene_id` | **AVAILABLE but NOT propagated to visual** |
| **dialogue_id (UUID)** | T004-B handoff `dialogue_id` from Script section | **AVAILABLE but NOT propagated to visual** |
| **script_id** | T004-B handoff `script_id` | AVAILABLE — not used in visual |
| **scene_index** | T004-B handoff `scene_index` | AVAILABLE — matches int idx |
| **dialogue_id (split TTS)** | `scene_builder` hardcoded `f"split-{idx:02d}"` | PRODUCTION string — **not canonical UUID** |
| **segment_id (split)** | `scene_builder` `f"seg-{i+1:02d}"` | PRODUCTION string — used in TTS only |
| **part_index** | Split loop variable `i` / `part_index` param in agnes_bridge | VERIFIED in agnes_bridge |
| **visual_plan_id** | `element` or `f"p{part_index}"` in agnes_bridge | VERIFIED |
| **revision_id** | ScriptRequestSpec pattern only | **MISSING_SOURCE in visual** |
| **prompt** | `override_prompt` / `visual_prompt` / compiled contract | VERIFIED |
| **provider** | Hardcoded `"agnes"` in agnes_bridge | VERIFIED |
| **model** | Hardcoded `"agnes-video-v2.0"` | VERIFIED |
| **generation_mode** | Derived from image_url / catalog in agnes_bridge | VERIFIED |
| **resolution** | `size` param `"1080x1920"` etc. | VERIFIED |
| **duration** | `duration_hint` / `duration_sec` | VERIFIED |
| **aspect_ratio** | Derived from size split `WxH` | IMPLICIT in `size` — no separate field |
| **seed** | VisualRequestSpec optional field | **MISSING_SOURCE for Agnes** — media_assets has no seed param |

---

## 3. VisualRequestSpec vs Domain Scene

| Domain Scene | VisualRequestSpec | Gap |
|--------------|-------------------|-----|
| `id` (UUID) | `scene_id` (int) only | Canonical UUID not in visual spec |
| `dialogue_id` | absent | P1 gap |
| `visual_plan.dialogue_id` | absent | Not wired |
| N/A segment in Scene model | absent | Split uses ad-hoc strings in scene_builder — **DEFER explicit domain segment to T004-E** |

---

## 4. Production Callsites

| Callsite | File | Identity passed today |
|----------|------|----------------------|
| `_resolve_footage` | scene_builder L1949 | job_id, scene_id=idx, part_index=0 |
| `_build_split` agnes | scene_builder L1206 | job_id, scene_id=idx, part_index=i |
| `_resolve_footage` split fallback | scene_builder L1261 | **scene_id=idx*10+i** — identity hack (C-2 scope) |
| `execute_visual_request` | visual_runtime | spec fields only |
| BUILD-04A tests | test_build04a | job_id, scene_id=1, no dialogue_id |

---

## 5. Fingerprint Today

```
compute_fingerprint(
  job_id, stage="visual",
  entity_id=f"scene-{scene_id:02d}-{visual_plan_id}",
  provider, model,
  inputs=normalized_inputs()  # no dialogue_id, no segment_id, no revision_id
)
```

**Audio fingerprint (reference pattern):**
```
entity_id=f"scene-{scene_id:02d}-{dialogue_id}{-segment_suffix}"
inputs include dialogue_id, segment_id, part_index
```

---

## 6. Revision Semantics (BUILD-04C reference)

- `ScriptRequestSpec.revision_id` — empty = base identity; non-empty = new generation scope
- `force_regenerate` on IdempotentExecutor — requires caller to change identity (revision_id)
- Retry = same fingerprint (attempt excluded via normalize skip)

---

## 7. Seed Policy Discovery

| Provider | Seed support |
|----------|--------------|
| Agnes (`generate_agnes_dialogue_clip`) | **NO** — no seed parameter in API wrapper |
| Mock visual provider | YES — optional seed in mock |
| Image fallback (`fallback_image_video`) | YES — `character_base_seed` + beat index — **separate path, C-4 scope** |

**Conclusion:** Agnes path — document as **provider limitation**; do not inject fake seed.

---

## 8. Segment Identity Decision (C1-1)

- **Domain Scene** has no `segment_id` field → **DEFERRED to T004-E**
- **Production split path** already uses operational strings:
  - `segment_id=f"seg-{i+1:02d}"` (TTS)
  - `part_index=i+1` (agnes_bridge)
- **C1 action:** Include `part_index` + optional `segment_id` in VisualRequestSpec fingerprint (mirroring AudioRequestSpec), sourced from scene_builder when available — **not inventing domain segment model**

---

## 9. Missing Identity Summary

| Gap | Severity | C1 action |
|-----|----------|-----------|
| dialogue_id not in VisualRequestSpec | P1 | Add + fingerprint |
| canonical_scene_id not propagated | P1 | Add + validate production |
| segment_id/part_index not in visual fingerprint | P1 | Add (operational strings) |
| revision_id absent | P1 | Add (mirror script) |
| idx*10+i hack | P1 | **DOCUMENT for C-2** — not fix in C1 |
| Agnes seed | P2 | Document limitation |
| domain segment_id | P2 | DEFER T004-E |

---

## C1-0 Acceptance

- [x] Scene contract inspected
- [x] VisualRequestSpec inspected
- [x] Dialogue contract inspected
- [x] VisualPlan inspected
- [x] Existing fingerprint inspected
- [x] Actual callsites inspected
- [x] Identity source mapped
- [x] Missing identity documented
- [x] No code change

**C1-0 = PASS**  
**Checkpoint = AMP003-T004-C1-0-PASS**
