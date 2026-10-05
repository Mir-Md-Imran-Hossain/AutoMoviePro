# Open-Source Phase 6E — Pre-Audit Report

**Date:** 2026-09-09  
**Verdict:** **AUDIT PASS** (observation/normalization proceed; repair execution only via existing paths)

---

## Temporal comparison today

| Item | Location |
|------|----------|
| Comparison | `pipeline/observation/frame_evidence/temporal.py` → `compare_temporal_frames` |
| False FAIL risk | Naïve `_norm` string inequality on location (Phase 6D: `interior setting` ≠ `unspecified interior`) |
| Explicit contract | `visual_contract` / `continuity_constraints` flags (`require_location`, `explicit_camera`, etc.) |
| Continuity policy | `ContinuityTracker` + `_family_hits`, `_relationships_contradict`, `extract_explicit_*` |

**Safe extension:** add conservative semantic normalization **inside** frame_evidence before compare — not a new semantic model/gate.

---

## BUILD-04F + targeted regeneration

| Step | Path |
|------|------|
| Plan | `plan_semantic_beat_repair` → `VISUAL_ASSET`, `whole_video_regeneration=False` |
| Handoff | `repair_handoff_from_frame_evidence` |
| Runtime repair in production | `video_pipeline._observe_and_maybe_repair_semantic` → `build_dialogue_clip` (scene-local) |
| BUILD-03 image path | `idempotent_image_clip_via_build03` → `execute_visual_request` |
| Re-observe | `observe_semantic_coverage` / `observe_frame` |

**Repair execution safety:** Full `build_dialogue_clip` repair is production-capable but **expensive** (Agnes/stock/TTS stack). Phase 6E will:
1. Always prove handoff.
2. Attempt **beat-local** regeneration only via existing BUILD-03 image path when a lightweight provider is available.
3. If unsafe/unavailable → `execution: NOT_CERTIFIED` (no invented repair engine).

---

## Decision

- Normalize + contract-aware temporal: **implement** (extend only).
- Real FAIL → handoff: **implement/prove**.
- Real targeted regen + re-observe: **attempt via existing BUILD-03**; else NOT_CERTIFIED.
- No new engines.

**AUDIT PASS — proceed.**
