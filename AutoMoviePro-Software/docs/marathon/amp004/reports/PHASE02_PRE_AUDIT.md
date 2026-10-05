# PHASE-02 Pre-Audit (STEP-0)

**তারিখ:** ২০২৬-০৮-৩১  
**Checkpoint before:** `AMP004-ARCHITECTURE-FREEZE`  
**Production code changed during STEP-0:** `false`

---

## ১. State verification

| Field | Value |
|-------|-------|
| `architecture_freeze` | true |
| `phase_02_status` | NOT_STARTED |
| `checkpoint` | AMP004-ARCHITECTURE-FREEZE |
| `next_checkpoint` | AMP004-QUALITY-GATE-FOUNDATION |

---

## ২. Actual production call graph (verified)

```
generate_video()                          # video_pipeline.py
  → intelligence gate (fail-closed)
  → director plan
  → assert_production_plan_wiring
  → assert_production_scenes_validated
  → scene_builder → agnes_bridge (per beat)
       → execute_visual_request
       → multimodal_gate_for_spec (post-success; may semantic_blocked)
  → compose / final
  → evaluate_master_shippable → MASTER_SHIP_GATE.json
  → run_creative_quality_gate → CREATIVE_QUALITY_GATE.json
  → run_publishability_gate → PUBLISHABILITY_GATE.json
  → if not publishable: raise RuntimeError
  → store job upload_status=ready_to_upload
```

---

## ৩. Current publishability decision path

`pipeline/quality/bridge.py` → `run_publishability_gate`  
`pipeline/quality/publishability.py` → `evaluate_publishability`

Inputs today:
- `technical_pass` (MASTER_SHIP_GATE)
- `creative_report` (CREATIVE_QUALITY_GATE / quality_report)
- subtitle_structural_pass (default True)
- provenance_complete (default True)

**Multimodal status: NOT an input.**

---

## ৪. Current multimodal decision path

`agnes_bridge.idempotent_generate_agnes_beat_result`  
→ `multimodal_gate_for_spec`  
→ on BLOCKED (strict/fixture/identity): `action=semantic_blocked`, beat fails  

Result is **scene-local**. No job-level `MULTIMODAL_QUALITY_GATE.json`.  
No read in `run_publishability_gate`.

---

## ৫. Bypass paths (verified)

| Path | Location | Risk |
|------|----------|------|
| `spec.metadata["skip_semantic_validation"]` | agnes_bridge | Production can skip multimodal if set |
| Heuristic advisory (non-strict) | agnes_bridge | Soft — identity still blocks |
| No job-level multimodal AND | publishability | **P0 gap** — BLOCKED lost after scene stage |

No `force_publish` / `disable_quality_gate` symbols found in production grep.

---

## ৬. Exact gaps (PHASE-02)

1. multimodal BLOCKED ↛ publishability BLOCKED  
2. Production `skip_semantic_validation` not rejected  
3. No persisted multimodal aggregate for publish gate  
4. Mandatory UNKNOWN multimodal not evaluated at publish  

---

## ৭. Files to modify (IN SCOPE)

| File | Change |
|------|--------|
| `pipeline/quality/publishability.py` | AND multimodal (+ optional artifact/render status) |
| `pipeline/quality/bridge.py` | Load multimodal aggregate into publishability |
| `pipeline/quality/multimodal_aggregate.py` | **NEW** — persist/load/aggregate (thin) |
| `pipeline/idempotency/agnes_bridge.py` | Persist multimodal; reject production skip |
| `scripts/test_amp004_phase02_quality_gate.py` | **NEW** suite |
| `docs/marathon/amp004/reports/*` | Audit/report |
| `docs/marathon/amp004/AMP004_STATE.json` etc. | State |

---

## ৮. OUT OF SCOPE

ContinuityTracker wiring · VLM/ASR · Layer-D CV · SFX/music · localization redesign · FFmpeg redesign · PHASE-03+ · second quality score · second idempotency

---

## STEP-0 acceptance

- [x] Call path mapped  
- [x] Gaps identified  
- [x] No production behavior change in STEP-0  

**→ Continue STEP-1 documentation + STEP-2/3 implementation.**
