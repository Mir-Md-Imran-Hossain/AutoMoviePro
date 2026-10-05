# Open-Source Phase 6C — Implementation Report

**Date:** 2026-09-09  
**Verdict:** **PASS_WITH_LIMITATION**  
**REAL Marathon:** Not run  
**Paid API calls (this phase):** **0**  
**OpenMontage AGPL imports/copies:** **0**

---

## Exact files changed / added

### Added
| Path | Role |
|------|------|
| `pipeline/observation/frame_sampling/__init__.py` | Package export |
| `pipeline/observation/frame_sampling/sample.py` | Bounded frame sampler (compose FFmpeg only) |
| `pipeline/observation/frame_evidence/__init__.py` | Package export |
| `pipeline/observation/frame_evidence/contract.py` | Frame evidence schema |
| `pipeline/observation/frame_evidence/observe.py` | Frame observe (provider path + heuristic fixture) |
| `pipeline/observation/frame_evidence/temporal.py` | Bounded temporal evidence |
| `pipeline/observation/frame_evidence/coverage.py` | Beat coverage (C05-S vocabulary) |
| `pipeline/observation/frame_evidence/bridge.py` | Retrieval → observation lineage |
| `pipeline/observation/frame_evidence/repair_hook.py` | FAIL → BUILD-04F VISUAL_ASSET |
| `scripts/test_phase6c_frame_observation.py` | Focused tests |
| `docs/marathon/customer_product/OPEN_SOURCE_PHASE6C_PRE_AUDIT_REPORT.md` | Pre-audit |
| `docs/marathon/customer_product/OPEN_SOURCE_PHASE6C_IMPLEMENTATION_REPORT.md` | This report |
| `docs/marathon/customer_product/OPEN_SOURCE_PHASE6C_AUTHORITY_AUDIT.md` | Authority proof |

### Modified
| Path | Change |
|------|--------|
| `pipeline/observation/common.py` | Frame schemas + `STATUS_ABSENT` align |
| `pipeline/semantic_coverage.py` | `attach_frame_evidence_to_semantic_report`, ABSENT blocking in job gate |
| `pipeline/story_visual_direction.py` | `attach_frame_observation_evidence` + architecture flags |

---

## Authorities reused

- C05-S DirectedVisualBeat + FULL/PARTIAL/NONE/UNKNOWN coverage  
- ContinuityTracker (policy source only for explicit camera/lighting)  
- `pipeline/retrieval` provenance + customer isolation  
- `semantic_coverage` / RCP-03 Gemini video+frame path  
- Artifact Verification semantic boundary (UNKNOWN ≠ PASS)  
- BUILD-04F via `plan_semantic_beat_repair` → VISUAL_ASSET  
- BUILD-03 `IdempotentExecutor` untouched  
- `pipeline.compose.ffmpeg_bin` / `ffprobe_duration` only  

---

## Sampling behavior

| Media | Strategy |
|-------|----------|
| IMAGE | Single deterministic frame (file copy into cache) |
| Short video (≤4s) | begin / mid / end (≤3) |
| Longer video | Bounded uniform (≤7) |
| Beat windows | Prefer beat midpoints |
| Scene cuts | Optional Phase 6A boundaries |
| Cache | `content_hash` + sampling contract hash |
| Failure | UNKNOWN / OBSERVATION_UNAVAILABLE — never silent PASS |

Frames never treated as semantic PASS (`semantic_pass: false`).

---

## Observation behavior

- No API keys → UNKNOWN (mandatory expected → `mandatory_evidence: ABSENT`)  
- Heuristic caption fixture (tests only) → HEURISTIC, never `provider_verified`  
- Provider path reuses Gemini frame bytes pattern (not exercised; paid=0)  
- CLIP similarity never visual truth  

---

## Temporal behavior

Compares ordered frames only for Visual Contract / ContinuityTracker **explicit** requirements (relationship, location, lighting, camera). Insufficient frames or UNKNOWN observations → UNKNOWN. Day→night without intentional change → FAIL. No second ContinuityTracker.

---

## Coverage behavior

Maps frame observations onto C05-S dimensions. Retrieval scores are not coverage. Non-provider evidence cannot claim FULL as provider truth (capped).

---

## UNKNOWN / FAIL / PASS / ABSENT

| Status | Meaning in Phase 6C |
|--------|---------------------|
| PASS | Only when required evidence actually supports (provider or explicit temporal PASS) |
| FAIL | Critical contradiction / provider FAIL → may hand off repair |
| UNKNOWN | Observation unavailable / incomplete — **never** coerced to PASS |
| ABSENT | Missing mandatory frame evidence at semantic/publishability boundary — **blocking** |

---

## Repair handoff

- FAIL → `repair_handoff_from_frame_evidence` → `plan_semantic_beat_repair` → **VISUAL_ASSET** only  
- UNKNOWN → **no repair triggered**  
- No whole-video regeneration flag  

---

## Windows evidence

Unicode paths, spaces in paths, corrupted/missing media covered in focused tests on this Windows host.

---

## Dependency behavior

- No new mandatory deps  
- No torch force-install  
- CLIP reuse Phase 6B optional path  
- Hash embedder never reported as CLIP  

---

## Test / regression counts

| Suite | Result |
|-------|--------|
| Phase 6C focused | **26 OK** (covers acceptance criteria 1–32) |
| Phase 6A | 15 OK |
| Phase 6B | 16 OK |
| RCP-06A | 10 OK |
| RCP-06B | 15 OK |
| RCP-06C | 10 OK |
| RCP-06D | 12 OK |
| RCP-07 blocker | 9 OK |
| BUILD-03 | 14 OK |
| C05-S | 79 OK |
| C05-MR | 140 OK |

---

## Known limitations

1. Live provider-verified frame observation requires Google keys (not used this phase).  
2. Heuristic fixture is for contract tests only — not production certification.  
3. Video still samples frames via existing FFmpeg seek; no dense decode.  
4. Camera family contradiction depends on ContinuityTracker `_CAMERA_FAMILIES` word hits.  
5. URL-only retrieval candidates without local_path → UNKNOWN until download.  

---

## OpenMontage AGPL isolation proof

- New modules under `pipeline/observation/frame_*` only  
- Tests assert no `third_party.OpenMontage` imports  
- Architecture snapshot: `openmontage_agpl_imported: false`  
- Ideas only from documentary/frame concepts — no AGPL copy  

---

## Acceptance checklist

1–15: Satisfied under PASS_WITH_LIMITATION (limitation = no live paid provider observation in this phase; honest UNKNOWN path proven).

**HARD STOP — Phase 6D not started.**
