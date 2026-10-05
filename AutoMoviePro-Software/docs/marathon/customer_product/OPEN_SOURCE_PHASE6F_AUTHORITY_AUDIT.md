# Open-Source Phase 6F — Authority Audit

**Date:** 2026-09-09  
**Verdict:** **PASS**

| Claim | Evidence |
|-------|----------|
| No second continuity engine | `cross_beat.py` sets `second_continuity_engine: false`; cites `ContinuityTracker`; architecture snapshot `cross_beat_is_not_second_continuity_engine` |
| No second semantic gate | `attach_frame_evidence_to_semantic_report` / `semantic_coverage` unchanged as cert authority |
| No second repair engine | Reuses `repair_handoff_from_frame_evidence` + `execute_targeted_visual_asset_repair_loop` (BUILD-04F / BUILD-03) |
| No second identity engine | `identity_certification_engine: false`; CLIP flagged `clip_similarity_is_not_identity_pass` |
| No second retrieval engine | Untouched |
| No second FFmpeg engine | Sampling/compose only via existing paths |
| BUILD-03 unchanged | Idempotency via `idempotent_image_clip_via_build03` |
| ContinuityTracker remains authority | Policy helpers reused via `normalize.classify_relationship_pair` → `_relationships_contradict` |
| BUILD-04F remains repair authority | FAIL → VISUAL_ASSET handoff |
| semantic_coverage remains gate | UNKNOWN blocks; UNKNOWN does not repair |
| UNKNOWN ≠ PASS / ≠ FAIL | Explicit flags; UNKNOWN path proven in `03_unknown.json` |
| HEURISTIC ≠ PROVIDER_VERIFIED | Distinguishing fields retained on entity state rows |
| OpenMontage AGPL imports/copies | **0** in `cross_beat.py` / normalize / repair_loop |
| Customer isolation | Cross-customer compare → FAIL |

**Windows:** Evidence under `docs/marathon/customer_product/phase6f_evidence/`  
**Paid API (session):** attempts **4** / successes **2** (mask `…syGE`); generation invocations **1**; initial two observes UNKNOWN then session retry PASS + prior LIVE 6D/6E reuse for multi-beat/negative.
