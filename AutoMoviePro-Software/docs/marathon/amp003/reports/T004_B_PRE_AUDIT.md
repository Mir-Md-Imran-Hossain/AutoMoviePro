# T004-B B-0 — Scene Contract Pre-Audit

**Marathon:** AMP-003 / TASK-004 / T004-B  
**Phase:** B-0 PRE-AUDIT  
**Date:** 2026-08-31  
**Code changes:** NONE

---

## 1. Current Scene Source

| Source | Location | Format |
|--------|----------|--------|
| Director plan | `niche_director.plan_niche_production` / `script_bridge` | `director_plan.json` → `plan["scenes"][]` |
| Resume | `video_pipeline.py` L126–136 | Existing `director_plan.json` reload |
| Hard fallback | `_fallback_history_plan` | dict with scenes[] |

**Production path:** `generate_video()` → `plan["scenes"]` list of legacy dicts.

---

## 2. Scene Transformation (Current)

| Step | Module | Runtime in Production? |
|------|--------|------------------------|
| `build_scene_contract` | `pipeline/scene_contract.py` | NO — offline only |
| `preflight_scene_contract` | `pipeline/scene_contract.py` | NO — offline only |
| `attach_contracts_to_plan` | `pipeline/scene_contract.py` | NO — only in `contract_wiring/stages.py` |
| `scene_from_legacy_contract` | `domain/adapters.py` | NO — only in BUILD-02 wiring |
| Dialogue sanitize | `video_pipeline.py` L499–558 | YES |
| Contract wiring gate | `production_bridge.assert_production_plan_wiring` | YES — offline trace, not Scene runtime |

**Gap:** Production scene loop (L572+) consumes raw dict without canonical Scene boundary.

---

## 3. Scene Storage

| Artifact | Path | Content |
|----------|------|---------|
| `director_plan.json` | `{work_dir}/director_plan.json` | Full plan + legacy scenes |
| `scene_contract` | Embedded in plan after attach (offline) | v0 contract dict |
| `contract_preflight` | Embedded per scene (offline) | PASS/FAIL/UNKNOWN |
| Resume meta | `resume_guard` markers | clip fingerprint per idx |

No `VALIDATED_SCENES.json` checkpoint exists yet.

---

## 4. Scene Consumers (Production)

| Consumer | File | Input Used |
|----------|------|------------|
| Scene loop | `video_pipeline.py` L572–795 | `scene["narration"]`, element, visual_prompt |
| TTS | `video_pipeline.py` L698+ | `narr` from scene dict |
| Visual | `build_dialogue_clip` | visual_prompt, element, narration |
| Localization | `localize_scene_clip` | english_narration, scene_idx |
| Quality gate | `evaluate_master_shippable` | scenes list |
| AV report | `_load_scene_av_summary` | idx, element |

All consumers use **legacy dict** — no canonical `Scene` instance.

---

## 5. Scene Identity (Current)

| Field | Legacy Dict | Canonical Scene (`domain/scene.py`) |
|-------|-------------|-------------------------------------|
| scene index | implicit loop `idx` | `scene_index`, `legacy_scene_id` |
| scene UUID | none | `id` (ContractBase) |
| dialogue | `narration` / `dialogue` | `metadata.dialogue`, `dialogue_id` |
| script link | none | `script_id` |
| element | `element` | `element` |
| claim | optional `claim_id` | `claim_id`, `primary_claim` |
| segment | none explicit | via dialogue_id / part_index downstream |

**Issue:** No stable UUID at production runtime; idx-only identity.

---

## 6. Scene Validation (Current)

| Validator | Where | Production |
|-----------|-------|------------|
| `preflight_scene_contract` | scene_contract.py | OFFLINE only |
| `plan_allows_generation` | scene_contract.py | OFFLINE only |
| `validate_instance(Scene)` | contract_wiring/core | OFFLINE only |
| Pydantic Scene model | domain/scene.py | Not invoked in production |
| Dialogue uniqueness | video_pipeline L499+ | YES — soft rewrite, not fail-closed |

---

## 7. Legacy Dict Usage

Production scene dict fields (typical):
- `narration`, `element`, `visual_prompt`, `exact_ai_video_prompt`
- `visual_query`, `keyword_triggers`, `claim_id`
- Optional: `shot`, `audio`, `subtitle`, `scene_contract` (if pre-attached offline)

Raw dict enters `build_dialogue_clip` without Pydantic validation.

---

## 8. Existing Adapters

| Adapter | File | Input → Output |
|---------|------|----------------|
| `scene_from_legacy_contract` | `domain/adapters.py` | scene_contract v0 dict → `Scene` |
| `attach_contracts_to_plan` | `pipeline/scene_contract.py` | legacy row → row + scene_contract |
| `wire_scenes_from_plan` | `contract_wiring/stages.py` | plan + Script → list[StageWireResult[Scene]] |

**Best reuse path:** `attach_contracts_to_plan` → `preflight` → `scene_from_legacy_contract` + audio/subtitle enrichment (from wire_scenes_from_plan).

---

## 9. Existing Tests

| Test | File | Coverage |
|------|------|----------|
| BUILD-01 | `scripts/test_build01_contracts.py` | scene_from_legacy_contract, attach_contracts |
| BUILD-02 | `scripts/test_build02_wiring.py` | wire_scenes_from_plan offline |
| TASK-002 | `scripts/test_amp003_task002.py` | contract wiring gate |

No dedicated production scene runtime boundary test exists.

---

## 10. Existing Bypass

| Bypass | Severity | Location |
|--------|----------|----------|
| Raw scene dict in production loop | P1 | video_pipeline.py L572+ |
| attach_contracts_to_plan not called at runtime | P1 | video_pipeline |
| preflight not enforced fail-closed | P1 | video_pipeline |
| Dialogue rewrite on failure (soft) | P2 | video_pipeline L514+ |

---

## 11. Exact Integration Point

**Insert boundary after:**
```python
assert_production_plan_wiring(...)  # L473–486
```

**Before:**
```python
scenes = list(plan.get("scenes") or [])  # L488
for idx, scene in enumerate(scenes):     # L572
```

**New flow:**
```
plan → attach_contracts_to_plan → preflight fail-closed
     → scene_from_legacy_contract (+ audio/subtitle plans)
     → validate Scene → persist checkpoint
     → handoff dict (validated only) → existing scene loop
```

---

## B-0 Acceptance

- [x] Production Scene call path identified
- [x] Scene creation point identified
- [x] Scene consumers identified
- [x] Canonical Scene model identified
- [x] Existing adapter identified
- [x] Legacy dict boundary identified
- [x] Identity fields identified
- [x] Downstream dependency identified
- [x] No code changes in B-0

**B-0 = PASS**
