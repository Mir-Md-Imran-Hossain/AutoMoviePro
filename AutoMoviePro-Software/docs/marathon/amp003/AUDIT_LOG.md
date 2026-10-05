# AMP-003 Audit Log

## 2026-08-31 — TASK-001 Pre-Audit

**Scope:** `domain/` contracts, enums, adapters, registry, validation

**Findings:**
- Core `ContractBase` with UUID id, schema_version, extra=forbid — VERIFIED
- Registry missing Engagement, Render, JobAttempt, AppError — PARTIAL → fixed
- No explicit major-version compatibility check on deserialize — MISSING → fixed
- Legacy adapters (`topic_from_plan`, `fact_pack_from_legacy`, etc.) — VERIFIED
- BUILD-01 tests 18/18 PASS pre-change

**Actions:**
- Added `parse_schema_version`, `schema_versions_compatible`, `SchemaVersionMismatchError`
- Added `validate_contract_version`, `deserialize_contract`
- Extended `CONTRACT_REGISTRY` (+9 models)
- Created `scripts/test_amp003_task001.py` (35 tests)

**Result:** AMP003-T001-PASS

## 2026-08-31 — TASK-002 Pre-Audit + Fix

**Scope:** `video_pipeline.py`, `contract_wiring/*`, orchestrator queue

**Findings:**
- BUILD-02 wiring existed offline but `generate_video()` bypassed it — P0
- No `executed_stages` trace markers — P1
- No work-dir trace persistence — P1

**Actions:**
- Created `production_bridge.py` with fail-closed gate
- Hooked `assert_production_plan_wiring` into `video_pipeline.py`
- Added stage order markers to `trace.py`
- Created `scripts/test_amp003_task002.py` (21 tests)

**Result:** AMP003-T002-PASS

## 2026-08-31 — T004-A Pre-Audit (TASK-004)

**Scope:** Production call graph — `video_pipeline.py`, orchestrator, contract_wiring, idempotency bridges, scene_builder, localization, render, upload paths

**Findings:**
- Primary entry: `generate_video()` — 15/15 canonical stages mapped
- Contract wiring gate connected (TASK-002) — VERIFIED
- Scene loop uses legacy dict — canonical Scene not runtime-enforced — P1 → T004-B
- Script/render/audio/visual legacy fallbacks bypass idempotency — P1 → T004-H/C/D/F
- Localization partial idempotency (work_dir dependent) — P1 → T004-E
- Engagement stage offline only — P2 → TASK-011

**Actions:**
- Created `docs/marathon/amp003/reports/T004_A_CALL_GRAPH.md`
- Created `docs/marathon/amp003/reports/T004_A_REPORT.md`
- No code changes (audit only)

**Result:** AMP003-T004-A-PASS

## 2026-08-31 — T004-B Scene Contract Runtime Boundary

**Scope:** Production scene validation gate, canonical Scene adapter, identity integrity

**Findings:**
- Production loop consumed raw scene dict — P1 → FIXED
- attach_contracts_to_plan offline-only — P1 → FIXED via scene_runtime

**Actions:**
- Created `pipeline/scene_runtime.py` — fail-closed validation boundary
- Integrated `assert_production_scenes_validated` into `video_pipeline.py`
- 26 dedicated tests, full regression PASS

**Result:** AMP003-T004-B-PASS

## 2026-08-31 — T004-C C-0 Visual Pre-Audit

**Scope:** Production visual call graph — Agnes, split, image fallback, identity, validation, provenance

**Findings:**
- Production root: video_pipeline → build_dialogue_clip → _resolve_footage / _build_split_dialogue_clip
- Agnes partially wired via agnes_bridge → visual_runtime — P1 gaps on Exception fallback
- Image fallback bypasses visual_runtime entirely — P1 → C-4
- dialogue_id/segment_id not in VisualRequestSpec — P1 → C-1/C-2
- docs/build04a/ NOT_FOUND

**Actions:**
- Created `docs/marathon/amp003/reports/T004_C0_VISUAL_AUDIT.md`
- No code changes (audit only)

**Result:** AMP003-T004-C0-PASS

## 2026-08-31 — T004-C C-1 Visual Identity Hardening

**Scope:** VisualRequestSpec identity fields, fingerprint, fail-closed validation, provenance, idempotency compatibility

**Changes:**
- `visual_request.py` — dialogue_id, canonical_scene_id, segment_id, revision_id, validate/build helpers
- `agnes_bridge.py` — production identity propagation + split segment guard
- `visual_provenance.py` — identity metadata
- `visual_runtime.py` — legacy key uses entity_id
- `scene_builder.py` / `video_pipeline.py` — identity propagation from validated handoff

**Tests:**
- `scripts/test_amp003_task004_c1_visual_identity.py` — 21/21 PASS
- `scripts/test_build04a_visual_runtime.py` — 18/18 PASS (regression)
- `scripts/test_amp003_task004_b_identity.py` — 6/6 PASS

**Deferred:** domain segment_id (T004-E), Agnes Exception bypass (C-2), image fallback (C-4), idx*10+i hack (C-2)

**Result:** AMP003-T004-C1-PASS — STOP (C-2 NOT STARTED)

## 2026-08-31 — T004-C C2-0 Agnes Callsite Forensic Audit

**Scope:** Repository-wide Agnes callsite mapping — no code changes

**Findings:**
- Production root: video_pipeline → build_dialogue_clip → _resolve_footage / _build_split_dialogue_clip
- Canonical path: idempotent_generate_agnes_beat → execute_visual_request → provider_fn
- **P1 bypass:** scene_builder L1242 (split) + L1991 (single) — Exception → direct generate_agnes_dialogue_clip
- Bridge-internal provider_fn (agnes_bridge L96) — ALLOWED
- Dev scripts: _smoke_agnes_clip, chernobyl_30_train — direct calls, DEV_ONLY
- request_agnes_clip — DEAD_CODE (0 callers)

**Deliverable:** `docs/marathon/amp003/reports/T004_C2_AGNES_CALLSITE_AUDIT.md`

**Result:** AMP003-T004-C2-0-PASS

## 2026-08-31 — T004-C C2-1 Bridge Boundary Contract

**Scope:** Gateway/boundary contract definition + boundary tests — NO bypass removal

**Changes:**
- `agnes_bridge.py` — partial identity fail-closed (dialogue_id + canonical_scene_id together)
- `scripts/test_amp003_task004_c2_boundary.py` — NEW 18 tests

**Contract doc:** `docs/marathon/amp003/reports/T004_C2_BRIDGE_CONTRACT.md`

**Bypasses:** BYP-01/BYP-02 documented → C2-2/C2-5 (not fixed in C2-1)

**Tests:** boundary 18/18; BUILD-04A 18/18; C1 21/21; T004-B 6/6; BUILD-03 14/14

**Result:** AMP003-T004-C2-1-PASS — STOP (C2-2 NOT STARTED)

## 2026-08-31 — T004-C C2-2-A Pre-Fix Read

**Scope:** BYP-01/BYP-02 current behavior audit — NO code changes

**Verified:**
- BYP-01: scene_builder L1242–1258 split path exception → direct Agnes
- BYP-02: scene_builder L1991–2007 single path exception → direct Agnes
- Bridge returns None on runtime fail (no bypass); exception triggers bypass
- BYP-02 L2017 second except is unreachable dead code
- Runtime UNKNOWN/retry semantics exist in executor (BUILD-03)

**Deliverable:** `docs/marathon/amp003/reports/T004_C2_2_PRE_FIX.md`

**Result:** AMP003-T004-C2-2-A-PASS

## 2026-08-31 — T004-C C2-2-B Failure Semantics Contract

**Scope:** Canonical Agnes failure outcomes — bypasses NOT removed

**Changes:**
- `agnes_bridge.py` — `AgnesBeatOutcome`, `classify_agnes_beat_outcome()`, `idempotent_generate_agnes_beat_result()`
- `visual_runtime.py` — `VisualGenerationResult.detail` field
- `scripts/test_amp003_task004_c2_failure_contract.py` — NEW 15 tests

**Doc:** `docs/marathon/amp003/reports/T004_C2_FAILURE_CONTRACT.md`

**Tests:** failure contract 15/15; boundary 18/18; C1 21/21; BUILD-03 14/14; BUILD-04A 17/18 (test_06 intermittent)

**Result:** AMP003-T004-C2-2-B-PASS — STOP (C2-2-C NOT STARTED)

## 2026-08-31 — T004-C C2-2-C-2 Split Caller Migration

**Scope:** Split path Agnes caller → canonical result API (BYP-01 NOT removed)

**Changes:**
- `scene_builder.py` — `_resolve_split_agnes_beat_src()` helper; split loop uses `idempotent_generate_agnes_beat_result()`
- `scripts/test_amp003_task004_c2_c2_split_migration.py` — NEW 18 tests

**Doc:** `docs/marathon/amp003/reports/T004_C2_2_C2_SPLIT_MIGRATION.md`

**Direct provider audit:** BYP-01 L1352 (unchanged); bridge-internal L209; BYP-02 L2102; no NEW production bypass

**Tests:** split migration 18/18; failure contract 15/15; boundary 18/18; C1 21/21; B identity 6/6; BUILD-03 14/14; BUILD-04A 18/18 (this run; test_06 known FLAKY deferred)

**Result:** AMP003-T004-C2-2-C-2-PASS — STOP (C2-2-C-3 NOT STARTED)

## 2026-08-31 — T004-C C2-2-C-3-1 Single Path Discovery

**Scope:** Full single-beat Agnes path discovery — NO code change

**Findings:**
- Single path: `build_dialogue_clip` → `_resolve_footage` → legacy `idempotent_generate_agnes_beat`
- BYP-02 at L2101–2126 (unchanged)
- Image fallback L2138+ (unchanged)
- Identity: job_id, dialogue_id, canonical_scene_id, script_id passed; segment_id/revision_id not passed
- **Gap:** bridge success does not early-return — falls through to image fallback

**Doc:** `docs/marathon/amp003/reports/T004_C2_2_C3_DISCOVERY.md`

**Result:** AMP003-T004-C2-2-C-3-1-PASS — STOP (C2-2-C-3-2 NOT STARTED)

## 2026-08-31 — T004-C C2-2-C-3-2 Single SUCCESS/REUSE Return

**Scope:** Single-beat `_resolve_footage` canonical result API + explicit SUCCESS/REUSE return

**Changes:**
- `scene_builder.py` — `_resolve_single_agnes_beat_src()`; `_resolve_footage()` early return on valid path
- `scripts/test_amp003_task004_c2_c3_single_success.py` — NEW 16 tests

**Fix:** Bridge success no longer falls through to image fallback

**BYP-02:** L2211 unchanged (C2-2-E)

**Doc:** `docs/marathon/amp003/reports/T004_C2_2_C3_2_SUCCESS_RETURN.md`

**Tests:** single success 16/16; split 18/18; failure contract 15/15; boundary 18/18; C1 21/21; B identity 6/6; BUILD-03 14/14; BUILD-04A 18/18

**Result:** AMP003-T004-C2-2-C-3-2-PASS — STOP (C2-2-C-3-3 NOT STARTED)

## 2026-08-31 — T004-C C2-2-C-3-3-1 Single Failure Propagation Discovery

**Scope:** Read-only audit of single-beat failure propagation — CODE CHANGE = 0

**Findings:**
- Structured FAILED/UNKNOWN/IDENTITY → `(None, result)` — no BYP-02
- BYP-02 fires only on Exception from try body L2181–2210
- All structured failures fall through to image fallback (production default)
- `_agnes_beat_result` discarded — information loss at L2182
- UNKNOWN/IDENTITY not fail-closed at caller (gap vs C2-2-B ideal)

**Doc:** `docs/marathon/amp003/reports/T004_C2_2_C3_3_1_FAILURE_DISCOVERY.md`

**Result:** AMP003-T004-C2-2-C-3-3-1-PASS — STOP (C2-2-C-3-3-2 NOT STARTED)

## 2026-08-31 — T004-C C2-SINGLE-FAILURE-PROPAGATION / C2-C3-FP

**Scope:** Single-beat Agnes failure propagation hardening — SUCCESS/REUSED/FAILED/UNKNOWN/IDENTITY/EXCEPTION

**Changes:**
- `scene_builder.py` — `AgnesOutcomeError`; outcome-aware `_resolve_footage()` boundary; BYP-02 REMOVED
- `agnes_bridge.py` — `try_reconcile_agnes_beat_unknown()`
- `scripts/test_amp003_task004_c2_single_failure_propagation.py` — NEW 20 tests
- `scripts/test_amp003_task004_c2_c3_single_success.py` — TEST-14/15 updated (UNKNOWN/IDENTITY fail-closed)

**Direct bypass audit:**
- BYP-02 (single path): REMOVED
- BYP-01 (split path L1464): REMAINS — deferred C2-2-E

**Doc:** `T004_C2_SINGLE_AGNES_FAILURE_PROPAGATION.md`, `T004_C2_2_C3_FAILURE_PROPAGATION_REPORT.md`

**Tests:** failure propagation 20/20; single success 16/16; split 18/18; failure contract 15/15; boundary 18/18; C1 21/21; B 6/6; BUILD-03 14/14; BUILD-04A 18/18 (test_06 PASS); TASK-001 35/35; TASK-002 21/21; TASK-003 20/20

**Result:** AMP003-T004-C2-SINGLE-FAILURE-PROPAGATION-PASS / AMP003-T004-C2-C3-FP-PASS — STOP (next C2-2-E, user command required)

## 2026-08-31 — T004-C C2-2-E Split BYP-01 Elimination

**Scope:** Remove split-path Exception → direct `generate_agnes_dialogue_clip()` bypass (BYP-01)

**Changes:**
- `scene_builder.py` — BYP-01 removed from `_build_split_dialogue_clip()`; Exception → log + image fallback
- Removed unused `generate_agnes_dialogue_clip` import from scene_builder
- `scripts/test_amp003_task004_c2_e_split_bypass_elimination.py` — NEW 13 tests
- Updated split migration + single failure propagation test mock targets

**Direct bypass audit:**
- BYP-01: **REMOVED**
- BYP-02: **REMOVED** (prior)
- Production Agnes calls in scene_builder: **ZERO**
- Only BRIDGE_INTERNAL in agnes_bridge.py

**Doc:** `T004_C2_E_SPLIT_BYPASS_ELIMINATION.md`

**Tests:** C2-E 13/13; split migration 18/18; single failure 20/20; full regression PASS

**Result:** AMP003-T004-C2-E-PASS — STOP (next C2-2-D, user command required)

## 2026-08-31 — T004-C C-3 Visual Semantic Consistency

**Scope:** SceneIntent contract, semantic validation boundary, continuity, fallback quality, BUILD-04F repair integration

**New modules:** `domain/scene_intent.py`, `pipeline/visual_semantic/*`

**Integration:** `agnes_bridge.py` post-success heuristic semantic gate (strict mode via metadata)

**Tests:** C3 25/25; C2 regressions PASS; BUILD-04F 42/42; BUILD-04A test_06 flake FAIL (known)

**Doc:** `T004_C3_VISUAL_SEMANTIC_CONSISTENCY.md`

**Result:** AMP003-T004-C3-PASS — STOP (next C-4, user command required)

## 2026-08-31 — T004-C3 Multimodal Consistency + Prompt Grounding (Expanded)

**Scope:** Entity grounding, prompt compiler, cross-modal validation, timeline, localization semantics, industrial validation layers, BUILD-04F quality bridge, production wiring

**New modules:** `pipeline/multimodal_consistency/*` (boundary, entity_grounding, prompt_compiler, prompt_validator, cross_modal, timeline, localization_semantic, evaluator_adapter, quality_bridge, industrial_status)

**Extended:** `domain/scene_intent.py` (SemanticEntity, EntityRelation, AudioIntent, SubtitleIntent, LocalizationIntent)

**Production wiring:**
- `agnes_bridge.py` → `multimodal_gate_for_spec` (identity mismatch always blocks; strict/fixture full block)
- `scene_runtime.py` → SceneIntent prompt compile in validated handoff

**Architecture preserved:** Canonical Scene → SceneIntent → Prompt Compiler → Provider; no duplicate Scene model; no new provider bypass; C2-E BYP-01/02 preserved

**Tests:** multimodal 41/41; visual_semantic 25/25; BUILD-03..04G-H1 PASS; AMP C2/B regression PASS

**Known flake:** BUILD-04A test_06 — intermittent (this run PASS)

**Doc:** `T004_C3_MULTIMODAL_CONSISTENCY.md` (বাংলা)

**Result:** AMP003-T004-C3-PASS — STOP (T004 complete নয়; next C-4)
