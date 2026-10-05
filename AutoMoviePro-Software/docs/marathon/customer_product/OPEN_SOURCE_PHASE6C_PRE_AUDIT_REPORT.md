# Open-Source Phase 6C — Pre-Implementation Audit

**Date:** 2026-09-09  
**Scope:** Frame-level visual evidence & temporal observation foundation  
**Mode:** Read-only inspection of AutoMovie Pro + Phase 6A/6B + RCP-03/07 architecture  
**Verdict:** **AUDIT PASS** (reuse-ready) — implementation may proceed under stated guardrails

---

## 1. Components inspected

| # | Area | Primary paths |
|---|------|----------------|
| 1 | Phase 6B retrieval | `pipeline/retrieval/{bridge,retrieve,embedding,common,faiss_index,sources,reuse}.py` |
| 2 | C05-S DirectedVisualBeat | `pipeline/story_visual_direction.py` — `COVERAGE_FULL/PARTIAL/NONE/UNKNOWN` |
| 3 | C05-MR materialization | `pipeline/generation_payload.py` — `materialize_visual_beats` |
| 4 | Generated asset path | `pipeline/scene_builder.py`, `pipeline/video_pipeline.py` |
| 5 | RCP-03 semantic observation | `pipeline/semantic_coverage.py` → `av_sync_critic._critique_via_video_upload` / `_critique_via_frames` |
| 6 | Artifact Verification | `pipeline/artifact_verification/{semantic_boundary,contracts,gate}.py` |
| 7 | FFmpeg/ffprobe | `pipeline/compose.py`, `pipeline/ffmpeg_exec.py`, `pipeline/rendering_integrity/ffmpeg_boundary.py` |
| 8 | PySceneDetect (6A) | `pipeline/observation/scene_boundary/` |
| 9 | Semantic / multimodal gates | `semantic_coverage.py`, `multimodal_consistency/`, `quality/publishability.py` |
| 10 | ContinuityTracker | `pipeline/visual_semantic/continuity.py` |
| 11 | Evidence schemas | `pipeline/observation/common.py`, `pipeline/retrieval/common.py` |
| 12 | BUILD-04F repair | `quality/repair_planner.plan_repair`, `semantic_coverage.plan_semantic_beat_repair` → `VISUAL_ASSET` |
| 13 | Existing frame utils | `av_sync_critic._extract_frames`, `visual_qa.extract_evidence_frames`, `asset_compress` poster |

---

## 2. What will be reused

| Component | Reuse as |
|-----------|----------|
| `compose.ffmpeg_bin` / `ffprobe_duration` | Sole media extraction/probe boundary |
| `visual_qa.extract_evidence_frames` patterns + `_extract_frames` | Sampling mechanics inspiration; consolidate under observation adapter calling same FFmpeg boundary |
| `semantic_coverage.observe_semantic_coverage` | Provider-verified observation authority (Gemini video/frames) |
| `av_sync_critic` frame/video critique | Existing provider path — extend, do not fork |
| `story_visual_direction` coverage constants | Beat coverage vocabulary |
| `ContinuityTracker` explicit camera/lighting/location/relation extractors | Continuity **policy** source only |
| `plan_semantic_beat_repair` / `plan_repair` | FAIL → VISUAL_ASSET repair handoff |
| Phase 6B retrieval provenance | Lineage into frame evidence |
| Phase 6A scene_boundary | Optional cut timestamps for sampling |
| Observation `common.unavailable` pattern | Honest UNKNOWN/UNAVAILABLE envelopes |

---

## 3. Authorities to extend (not replace)

| Authority | Extension |
|-----------|-----------|
| `pipeline/observation/` | New `frame_sampling` + `frame_evidence` adapters (evidence only) |
| Phase 6B `retrieval/bridge` | Optional attach of frame-observation lineage |
| `semantic_coverage` | Optional consume structured frame evidence; **no new gate** |
| `story_visual_direction` | Optional attach helper (like Phase 6A/6B) |
| C05-MR units | Optional frame evidence refs on units |

---

## 4. New adapters required

| Adapter | Path | Why |
|---------|------|-----|
| Bounded frame sampler | `pipeline/observation/frame_sampling/` | Unify image/video/beat/scene-aware sampling with provenance; existing utils are scattered and not beat-bound |
| Frame evidence contract + observe | `pipeline/observation/frame_evidence/` | Canonical per-frame schema aligned to PASS/FAIL/UNKNOWN/ABSENT |
| Temporal compare | same package | Bounded frame-to-frame evidence vs Visual Contract; **not** a ContinuityTracker |
| Retrieval→observation bridge | same package | Traceability Phase 6B → frames → coverage |
| Repair evidence hook | same package | FAIL→BUILD-04F; UNKNOWN→no repair |

---

## 5. Duplicate-engine risks (must avoid)

| Risk | Mitigation |
|------|------------|
| Second FFmpeg runner | Call only `pipeline.compose` discovery/exec |
| Second ContinuityTracker | Temporal module emits evidence; ContinuityTracker remains policy authority |
| Second semantic gate | Only feed existing `semantic_coverage` / publishability ABSENT rules |
| Second repair engine | Only `plan_repair` / `plan_semantic_beat_repair` |
| Second quality engine | Observation-only adapters |
| OpenMontage AGPL `frame_sampler.py` | **Do not import**; ideas only |
| Hash/CLIP similarity as visual truth | Mark HEURISTIC; never `provider_verified` |
| Parallel `_extract_frames` drift | New sampler is canonical for Phase 6C; others remain as-is for legacy critics |

---

## 6. Exact integration points

1. **Sampling:** media path (retrieved or generated) → `frame_sampling.sample_frames` → cached by `content_hash` + sampling contract  
2. **Observation:** sampled frames → existing provider path when keys present; else UNKNOWN  
3. **Temporal:** ordered frame evidences + Visual Contract / ContinuityTracker **explicit** constraints → temporal evidence  
4. **Coverage:** DirectedVisualBeat expected dims × observed → FULL/PARTIAL/NONE/UNKNOWN  
5. **Bridge:** `retrieval selected` → sample → observe → coverage (customer/channel fail-closed)  
6. **Semantic:** optional attach; UNKNOWN/ABSENT still block publishability (RCP-06A)  
7. **Repair:** overall FAIL → BUILD-04F VISUAL_ASSET; UNKNOWN → no repair trigger  

---

## 7. Status vocabulary (no new statuses)

| Layer | Vocabulary |
|-------|------------|
| Frame / semantic observation | `PASS` / `FAIL` / `UNKNOWN` (+ `OBSERVATION_UNAVAILABLE` for tool failure) |
| Publishability missing evidence | `ABSENT` (existing) |
| C05-S coverage | `FULL` / `PARTIAL` / `NONE` / `UNKNOWN` |

Do **not** invent additional status enums.

---

## 8. AUDIT DECISION

**AUDIT PASS**

Rationale: All required authorities and extraction/observation paths already exist. Phase 6C needs AMP-owned observation adapters that consolidate sampling + contract + temporal/coverage evidence without creating engines.

**Guardrails for implementation:**
- paid API calls = 0 in this phase (tests use fixtures / no-key UNKNOWN path)
- no torch force-install; CLIP reuse Phase 6B rules
- no OpenMontage imports
- no gate weakening

Implementation may proceed.
