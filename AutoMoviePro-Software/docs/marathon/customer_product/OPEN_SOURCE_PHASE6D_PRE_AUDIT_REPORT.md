# Open-Source Phase 6D — Pre-Audit Report

**Date:** 2026-09-09  
**Verdict:** **AUDIT PASS** — existing Phase 6C + RCP-03 paths sufficient; **no new production engine required**

---

## Entry points (exact)

| Concern | Entry point |
|---------|-------------|
| Frame sampling | `pipeline.observation.frame_sampling.sample_frames` |
| Frame observation | `pipeline.observation.frame_evidence.observe_frame` / `observe_frames` |
| Temporal | `pipeline.observation.frame_evidence.compare_temporal_frames` |
| Coverage | `pipeline.observation.frame_evidence.beat_frame_coverage` (C05-S vocab) |
| Retrieval lineage | `pipeline.observation.frame_evidence.bridge_retrieval_to_frame_observation` |
| Semantic observation (RCP-03) | `pipeline.semantic_coverage.observe_semantic_coverage` → `av_sync_critic` video/frames |
| Semantic gate | `pipeline.semantic_coverage.evaluate_job_semantic_gate` + publishability ABSENT rules |
| Repair handoff | `pipeline.observation.frame_evidence.repair_handoff_from_frame_evidence` → `plan_semantic_beat_repair` → BUILD-04F `VISUAL_ASSET` |
| FFmpeg | `pipeline.compose.ffmpeg_bin` / `ffprobe_duration` only |
| Continuity policy | `pipeline.visual_semantic.continuity.ContinuityTracker` |

---

## Provider configuration

| Item | Status |
|------|--------|
| `.env` Google keys | Present (`GOOGLE_API_KEY_1`…`_19`) via `load_api_bundle()['google_keys']` |
| Circuit | OPEN=false at audit time |
| Healthy keys | Counted via `filter_usable_keys` (non-zero) |
| CLIP | `RETRIEVAL_UNAVAILABLE` (no torch) — not forced |
| FAISS | Available (CPU) |
| FFmpeg | Bundled `ffmpeg-8.1.1` |

**Secrets:** never logged; only masks / counts in reports.

---

## Safe real media (customer-scoped)

| Asset | Path | Role |
|-------|------|------|
| IMAGE | `data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png` | Real image cert |
| VIDEO | `data/customer_generation_work/c11_marathon_customer/job2108/scene_00_beat.mp4` | Real video / temporal (~7.2s) |
| NEGATIVE | Same outdoor/space-style beat media with **hospital interior** required | Mismatch |

Customer: `c11_marathon_customer` / channel isolation tests use distinct customer_id.

---

## Paid call budget (planned)

| Step | Calls |
|------|-------|
| Real IMAGE observe | ≤1 key × ≤2 models (stop on first success) |
| Real VIDEO observe (2 frames for temporal) | ≤2 successful observes |
| Negative observe | ≤1 |
| UNKNOWN path | 0 (empty keys) |
| **Expected upper bound** | **≤6 attempts / ≤4 successes** |
| Marathon / C11 full / upload | **0** |

---

## Production vs test-only

| Production | Test-only |
|------------|-----------|
| frame_sampling / frame_evidence / semantic_coverage / repair_handoff | Heuristic fixture (`allow_heuristic_fixture`) — **forbidden as PASS** in 6D |
| compose FFmpeg | lavfi-generated media only if C11 media missing |
| BUILD-04F handoff evidence | No invented repair execution |

---

## Decision

- Existing path **sufficient** → no new implementation engines.
- Live provider path **available** → attempt minimum real observation certification.
- If provider fails mid-run → record UNKNOWN/ENVIRONMENT_LIMITED; **do not fabricate PASS**.

**AUDIT PASS — proceed to certification slice.**
