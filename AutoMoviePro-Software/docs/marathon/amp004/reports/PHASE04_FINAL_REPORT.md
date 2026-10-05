# PHASE-04 Final Report — Industrial Artifact Verification

**Checkpoint:** `AMP004-ARTIFACT-VERIFICATION-PASS`  
**Date:** 2026-08-31  
**Paid API calls:** 0

---

## 1. Implementation summary

Production observation boundary distinguishing INTENT / PROMPT / PROVIDER / OBSERVED / COMPOSITE.

### New package: `pipeline/artifact_verification/`
| Module | Role |
|--------|------|
| `contracts.py` | ArtifactObservation + PASS/FAIL/UNKNOWN + L0–L4 tiers |
| `media_probe.py` | ffprobe + silence/blank helpers (actual media) |
| `verifiers.py` | visual / audio / subtitle / **independent composite** |
| `semantic_boundary.py` | UNKNOWN ≠ PASS; contradiction → FAIL; no fake VLM |
| `gate.py` | ARTIFACT_GATE.json + observation persist + max verify cycles |
| `repair_bridge.py` | BUILD-04F minimal scopes; no regen on semantic UNKNOWN alone |
| `production.py` | `run_production_artifact_verification` |

### Production wiring
- `video_pipeline.py`: after MASTER_SHIP → **artifact verification** → creative → publishability (`require_artifact_gate=True`)
- `quality/bridge.py`: load ARTIFACT_GATE; missing gate → UNKNOWN when required

### Reused (not duplicated)
visual/audio/subtitle/render validators · multimodal/visual_semantic · BUILD-04F repair · existing provenance dirs

---

## 2. Production call graph (proven)

```
generate_video
  → SceneIntent + Continuity (P03)
  → Prompt → Generation
  → Observed artifacts (work_dir)
  → run_production_artifact_verification  [NEW — mandatory]
       → L0/L1 technical inspect
       → semantic boundary (UNKNOWN honest / FAIL on contradiction)
       → ARTIFACT_GATE.json + artifact_observations/
  → Multimodal/semantic (existing)
  → Repair (04F minimal scope if FAIL; cycle-capped)
  → Render
  → Final composite independent verify (Layer E)
  → Publishability AND (artifact FAIL/UNKNOWN → not publishable)
  → Publish
```

---

## 3. Honesty / UNKNOWN cases

| Case | Result |
|------|--------|
| File missing / corrupt / bad streams | FAIL → BLOCKED |
| Technical OK, no VLM/ASR observation | semantic=UNKNOWN (not PASS) |
| Unverified final composite | artifact gate UNKNOWN → block publish |
| Explicit contradiction evidence | FAIL → BLOCKED |
| High creative score + artifact FAIL | still not publishable |

**Limitation (documented, not faked):** Production L3/L4 VLM/ASR not implemented — semantic content of frames/speech remains UNKNOWN unless contradiction evidence is supplied. Technical Layer C/E verification is mandatory and real.

---

## 4. Tests

| Suite | Result |
|-------|--------|
| `test_amp004_phase04_artifact_verification.py` | **31/31 PASS** |
| Phase-02 + Phase-03 | 78 PASS (combined with P04) |
| BUILD-03/04C/04E/04F | 121 PASS |
| BUILD-04A/B/D | 72 PASS, 2 skip |
| BUILD-04G + G-H + AMP T001–T003 + C3/C2-E | 215 PASS |
| Import | `import_ok` |

---

## 5. Files changed

- `pipeline/artifact_verification/**` (NEW)
- `pipeline/video_pipeline.py`
- `pipeline/quality/bridge.py`
- `scripts/test_amp004_phase04_artifact_verification.py` (NEW)
- `docs/marathon/amp004/reports/PHASE04_*.md`
- state/registry/audit/deferred updates

---

## 6. Deferred

| ID | Note |
|----|------|
| DEF-AMP004-001 | Layer-D VLM/ASR still future (PHASE-06+) |
| Thumbnail fingerprint | still weak — out of scope |
| Fallback visual provenance | still weaker than Agnes path |

---

## 7. Acceptance

- [x] Observation contract  
- [x] Actual media inspection L0/L1  
- [x] Semantic UNKNOWN ≠ PASS  
- [x] Independent final composite verify  
- [x] Production path wired (not test-only)  
- [x] Publishability blocks FAIL/mandatory UNKNOWN  
- [x] Repair minimal + no unbounded loop  
- [x] No second quality/repair/idempotency/continuity engine  
- [x] PHASE-05 not started  

**phase_04_status = PASS**  
**checkpoint = AMP004-ARTIFACT-VERIFICATION-PASS**  
**next_phase = PHASE-05 / NOT_STARTED**

---

## STOP

Do **not** start PHASE-05 (script/narrative quality).
