# TASK-002 প্রতিবেদন — Pipeline Contract Wiring + Orchestration

**Marathon:** AMP-003  
**Task:** TASK-002  
**Checkpoint:** AMP003-T002-PASS  
**Verdict:** PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. উদ্দেশ্য

বর্তমান production pipeline-এ domain contracts এবং orchestration সঠিকভাবে connected কিনা — বাস্তব call graph, contract boundary, stage ordering, failure propagation, bypass audit এবং state traceability runtime evidence সহ verify করা।

---

## ২. Pre-Audit

| Area | ফাইল | Pre-Audit Status |
|------|------|------------------|
| Contract wiring core | `pipeline/contract_wiring/core.py` | VERIFIED |
| Per-stage wiring | `pipeline/contract_wiring/stages.py` | VERIFIED |
| Full trace | `pipeline/contract_wiring/trace.py` | VERIFIED (stage markers ছিল না) |
| Orchestrator bridge | `pipeline/contract_wiring/orchestrator_bridge.py` | PARTIAL (queue metadata only) |
| Production entry | `pipeline/video_pipeline.py` | **NOT_CONNECTED** (BUILD-02 bypass) |
| Queue orchestrator | `pipeline/orchestrator.py` | PARTIAL (`enrich_queue_payload` only) |
| BUILD-02 tests | `scripts/test_build02_wiring.py` | 17/17 PASS (offline wiring) |

---

## ৩. Production Call Graph

```
ENTRY: generate_video() — pipeline/video_pipeline.py
  ↓
[API keys / channel DNA / duplicate guard]
  ↓
[Intelligence gate] — pipeline/intelligence/bridge.py (optional topic/reserve)
  ↓
[Director plan] — idempotent_plan_niche_production → director_plan.json
  ↓
[Humanize / master lang] — pipeline/master_lang.py, content_humanizer.py
  ↓
★ CONTRACT WIRING GATE (post-fix) — production_bridge.assert_production_plan_wiring()
  │   topic → research → factpack → script → scene → visual/audio/subtitle
  │   → render → metadata → thumbnail → upload → publication
  ↓
[Per-scene loop] — TTS → build_dialogue_clip → localize_scene_clip
  ↓
[Compose] — idempotent_compose_final_video / concat_av_clips
  ↓
[Quality gates] — av_quality_gates, creative quality bridge
  ↓
[Metadata / thumbnail / package] — media_assets, package_export
  ↓
[Job store] — app.db.add_job → ready_to_upload
  ↓
FINAL ARTIFACT: final_{short|long}.mp4 + CONTRACT_WIRING_TRACE.json
```

**Parallel offline path:** `wire_pipeline_from_plan()` — BUILD-02 validation (test + queue pre-wire)

**Queue path:** `orchestrator.enqueue()` → `enrich_queue_payload()` (metadata only)

---

## ৪. Contract Boundary Audit

| Boundary | Input | Validation | Schema | Identity | Verdict |
|----------|-------|------------|--------|----------|---------|
| Topic | legacy dict | `validate_required_dict` | 1.0.0 | UUID | VERIFIED |
| Research | Topic instance | `validate_instance` | 1.0.0 | topic_id | VERIFIED |
| FactPack | legacy/build | adapter + validate | 1.0.0 | topic_id | VERIFIED |
| Script | plan + upstream | upstream + scenes key | 1.0.0 | topic_id | VERIFIED |
| Scene | scene_contract | attach_contracts_to_plan | 1.0.0 | script_id | VERIFIED |
| Visual/Audio/Subtitle | Scene | validate_instance | 1.0.0 | scene_id | VERIFIED |
| Render→Publication | fixture legacy | run_stage | 1.0.0 | job_id chain | VERIFIED |

**Gap (pre-fix):** `video_pipeline` plan dict সরাসরি scene loop-এ যেত — canonical wiring bypass — **P0**

---

## ৫. Orchestration Audit

**Canonical order (verified post-fix):**

`topic → research → factpack → script → scene → [visual→audio→subtitle]* → render → metadata → thumbnail → upload → publication`

`executed_stages` trace markers যোগ করা হয়েছে — runtime order verify — TEST-02, TEST-17 PASS

**Negative:** missing scenes → stops at `script` or `scene` — downstream render blocked — TEST-05, TEST-06 PASS

---

## ৬. Bypass Audit

| Bypass | Location | Severity | Status |
|--------|----------|----------|--------|
| video_pipeline skipped wiring | `generate_video()` | P0 | **FIXED** — `assert_production_plan_wiring` |
| Legacy script fallback | `_plan_niche_production_idempotent` | P2 | DOCUMENTED — idempotency bridge fail → legacy |
| Legacy render fallback | compose exception handler | P2 | DOCUMENTED — TASK-004 scope |
| enqueue metadata only | `orchestrator.enqueue` | INFO | Partial by design — full wire via `wire_plan_for_queue` |

Production path এখন `assert_production_plan_wiring` call করে — TEST-11 PASS

---

## ৭. Failure Propagation

| Case | Expected | Actual | Test |
|------|----------|--------|------|
| Invalid topic input | Stop at topic, no canonical | Stop + FAIL verdict | TEST-04, TEST-09 |
| Missing scenes | Stop before render | Stop at script/scene | TEST-05 |
| Empty plan | Stop at topic | Stop at topic | TEST-04 |
| assert_production invalid | RuntimeError | ProductionWiringError | TEST-08 |
| Input validation fail | Stage not executed | canonical=None | TEST-09 |

Downstream silently continue করে না — VERIFIED

---

## ৮. State/Checkpoint Traceability

- `CONTRACT_WIRING_TRACE.json` per work_dir — job_id, executed_stages, stage pass/fail
- Global trace: `DATA_DIR/contract_traces/{job_id}.json`
- Identity chain: topic_id → factpack → script — TEST-14 PASS
- Orphan detection: `detect_orphans()` — TEST-15 PASS
- Resume reload: `load_work_trace()` — TEST-16 PASS

---

## ৯. Gap Matrix

| ID | Area | Expected | Actual (pre-fix) | Severity | Fix | Test | Status |
|----|------|----------|------------------|----------|-----|------|--------|
| G-001 | Production wiring | Plan wired before scenes | Dict bypass | P0 | production_bridge + video_pipeline hook | TEST-11, TEST-19 | FIXED |
| G-002 | Stage order evidence | Trace markers | None | P1 | executed_stages in trace.py | TEST-02, TEST-17 | FIXED |
| G-003 | Work-dir trace | Persist per job | Global only | P1 | persist_work_trace | TEST-03, TEST-16 | FIXED |
| G-004 | Per-scene runtime wire | Contract per TTS/visual | Dict scenes | P2 | Deferred TASK-004 | — | DEFERRED |
| G-005 | Full idempotency | TASK-003 scope | Partial bridges | INFO | DOCUMENT ONLY | — | DEFERRED |

---

## ১০. Root Cause

BUILD-02 contract wiring layer তৈরি হয়েছিল কিন্তু `generate_video()` production entry point-এ integrate করা হয়নি — শুধু offline tests এবং queue metadata enrichment ছিল।

---

## ১১. Surgical Fix

1. **`pipeline/contract_wiring/production_bridge.py`** (নতুন)
   - `validate_production_plan_wiring()`, `assert_production_plan_wiring()`
   - `stage_order_valid()`, `persist_work_trace()`, `load_work_trace()`
   - Orphan detection integration

2. **`pipeline/contract_wiring/trace.py`**
   - `executed_stages` markers per stage

3. **`pipeline/video_pipeline.py`**
   - Post-plan `assert_production_plan_wiring()` fail-closed gate

4. **`pipeline/contract_wiring/__init__.py`**
   - Export production bridge APIs

---

## ১২. পরিবর্তিত ফাইল

- `pipeline/contract_wiring/production_bridge.py` (নতুন)
- `pipeline/contract_wiring/trace.py`
- `pipeline/contract_wiring/__init__.py`
- `pipeline/video_pipeline.py`
- `scripts/test_amp003_task002.py` (নতুন)

---

## ১৩. Dedicated Test

**`scripts/test_amp003_task002.py` — 21/21 PASS**

| Test | Coverage |
|------|----------|
| TEST-01–03 | Valid pipeline, order, persistence |
| TEST-04–08 | Negative / invalid / assert raises |
| TEST-09–10 | Failure propagation |
| TEST-11–13 | Bypass audit |
| TEST-14–16 | Identity, orphan, resume |
| TEST-17–19 | Runtime orchestration |
| TEST-20–21 | Contract boundaries |

---

## ১৪. Regression

| Suite | Result |
|-------|--------|
| TASK-002 dedicated | 21/21 PASS |
| BUILD-02 wiring | 17/17 PASS |
| TASK-001 | 35/35 PASS |
| BUILD-01 | 18/18 PASS |
| BUILD-00R | 5/5 PASS |

---

## ১৫. Runtime Evidence

- `wire_sample_history_pipeline()` — full chain PASS, 13+ stages executed
- `CONTRACT_WIRING_TRACE.json` written to work_dir with `executed_stages`
- `video_pipeline.py` source contains `assert_production_plan_wiring` — production hook verified
- Invalid plan raises `ProductionWiringError` — TEST-08
- Stage order: topic index < research < script < render — TEST-17

---

## ১৬. Limitations

1. **Per-scene runtime** — scene loop এখনও dict-based; canonical Scene contract প্রতি TTS/visual call-এ re-wired নয় (TASK-004)
2. **Render/upload in wiring trace** — fixture data দিয়ে contract validation; actual file paths পরে generate হয়
3. **Legacy fallbacks** — script/render bridge fail হলে legacy path এখনও exists (documented P2)
4. **TASK-003 idempotency** — implement করা হয়নি (per scope lock)

---

## ১৭. Deferred Issues

| ID | Item | Target Task |
|----|------|-------------|
| DEF-AMP003-004 | Per-scene live contract wiring | TASK-004 |
| DEF-AMP003-005 | Global idempotency executor hardening | TASK-003 |
| DEF-AMP003-006 | Remove legacy compose/script fallbacks | TASK-004+ |

---

## ১৮. Final Verdict

**TASK-002 = PASS**

Pre-audit complete, production call graph verified, contract boundaries connected via production bridge, orchestration order verified, negative tests PASS, failure propagation verified, bypass audit complete (P0 fixed), dedicated tests 21/21, regression PASS, evidence recorded.

**Checkpoint:** AMP003-T002-PASS  
**TASK-003:** NOT_STARTED

---

*AMP-003 TASK-002 execution complete. STOP.*
