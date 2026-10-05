# Open-Source Phase 6G — Pre-Audit Report

**Date:** 2026-09-09  
**Verdict:** **AUDIT PASS** — no new duration / pacing / audio authority required

---

## Canonical timing

| Concept | Location |
|---------|----------|
| Dialogue timing | `DialogueSegment.start_sec/end_sec` (`story_visual_direction.py`); from `script_plan_to_dialogue_segments` |
| Audio timing | Measured `ffprobe_duration` (`compose.py`); AudioPlan is plan target only |
| Visual timing | `DirectedVisualBeat.duration_sec` + `scene["visual_timing"]` (`trs_facade.py`) |
| Visual hold | `decide_visual_hold_policy()` — **asset hold budget**, not timeline truncation |
| Duration authority | `pipeline.duration_budget.resolve_duration_contract` |
| Coverage vocabulary | C05-S `FULL/PARTIAL/NONE/UNKNOWN` (`coverage.py`) |

---

## Silent dialogue drop risks (already guarded)

- `materialize_visual_beats` blocks missing `dialogue_id`/`beat_id`
- `assert_generation_alignment_preflight` blocks binding defects
- RCP-02: hold must not truncate dialogue timeline; `customer_plan_adapter` keeps dialogue IDs

Missing visual coverage → existing `PRODUCTION_INCOMPLETE:*` / `dialogue_without_visual_intent` / `required_coverage_none` — reuse, do not invent new vocabulary.

---

## Safe extension

`pipeline/observation/frame_evidence/alignment.py`

Evidence-only:

- dialogue / visual timeline projection
- temporal coverage FULL/PARTIAL/NONE/UNKNOWN
- semantic alignment vs provider observation
- adaptive hold **recommendation** via existing `decide_visual_hold_policy`
- no-silent-drop invariant check
- handoff to existing BUILD-04F on FAIL

**Does not** override Duration Contract, AudioPlan clock, or C05-S beat authority.

---

## Decision

Implement 6G as alignment/evidence layer only. **STOP** if tempted to create a second pacing engine — not required.
