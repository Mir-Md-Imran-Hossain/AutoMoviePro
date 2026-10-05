# Open-Source Phase 6C — Authority Audit

**Date:** 2026-09-09  
**Purpose:** Prove Phase 6C did not create duplicate engines or weaken fail-closed policy.

---

## Proof matrix

| Claim | Evidence |
|-------|----------|
| No new quality engine | Adapters under `pipeline/observation/frame_*` only emit evidence; quality remains `pipeline/quality/*` |
| No new semantic gate | `attach_frame_evidence_to_semantic_report` extends existing `semantic_coverage`; `creates_semantic_gate: false`; job gate still `evaluate_job_semantic_gate` |
| No new continuity engine | `compare_temporal_frames` sets `second_continuity_engine: false`; ContinuityTracker path unchanged as policy authority |
| No new repair engine | `repair_handoff_from_frame_evidence` calls existing `plan_semantic_beat_repair` / BUILD-04F; `second_repair_engine: false` |
| No new FFmpeg engine | Sampler uses `pipeline.compose.ffmpeg_bin` / `ffprobe_duration`; `reuses_compose_ffmpeg: true`, `creates_ffmpeg_engine: false` |
| No BUILD-03 replacement | No edits to `pipeline/idempotency/executor.py` or store claim semantics; tests still import `IdempotentExecutor` |
| No OpenMontage AGPL import/copy | Source scan of new files; architecture `openmontage_agpl_imported: false` |
| No customer isolation bypass | Bridge calls `assert_customer_scoped_asset_reuse`; cross-customer → FAIL blocked |
| UNKNOWN ≠ PASS | Observe/sampling/semantic attach refuse PASS promotion; tests `test_24`, `test_25`, `test_08` |
| ABSENT blocks certification | `mandatory_frame_evidence=ABSENT` forces non-PASS + blocking gate |
| FAIL repair only | `test_26` triggers VISUAL_ASSET; `test_27` UNKNOWN does not |
| Retrieval not semantic PASS | `clip_similarity_is_not_visual_truth`, `retrieval_score_is_not_coverage` |
| HEURISTIC ≠ PROVIDER_VERIFIED | Fixture observe sets `heuristic=True`, `provider_verified=False` |

---

## Existing authorities preserved

| Authority | Status |
|-----------|--------|
| C05-S / DirectedVisualBeat | Preserved (input + coverage vocab) |
| SceneIntent / Visual Contract | Preserved |
| ContinuityTracker | Preserved |
| `pipeline/retrieval/` | Preserved |
| Artifact Verification | Preserved |
| semantic_coverage / multimodal | Extended only |
| BUILD-04F | Preserved (handoff target) |
| BUILD-03 | Preserved |
| FFmpeg/render boundary (`compose`) | Preserved |

---

## Architecture snapshot flags (C05-S)

- `frame_evidence_is_not_continuity_authority: true`  
- `frame_evidence_is_not_semantic_gate: true`  
- `frame_evidence_is_not_ffmpeg_engine: true`  
- `openmontage_agpl_imported: false`  

---

## Verdict

**Authority integrity: PASS**

Phase 6C adds observation adapters and lineage only.
