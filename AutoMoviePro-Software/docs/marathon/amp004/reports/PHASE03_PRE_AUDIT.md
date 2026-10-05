# PHASE-03 Pre-Audit — Production Continuity

**তারিখ:** ২০২৬-০৮-৩১  
**Checkpoint before:** `AMP004-QUALITY-GATE-FOUNDATION-PASS`  
**Production code changed during STEP-0:** `false`

---

## A–H answers (verified)

| Q | Finding |
|---|---------|
| A. Scene N state created | `assert_production_scenes_validated` → canonical Scene + handoff dict; SceneIntent builder available but continuity state **not** written job-wide |
| B. Scene N+1 created | `video_pipeline` loop `for idx, scene in enumerate(scenes)` — independent per scene |
| C. Previous state → next? | **NO** in production. ContinuityTracker only if caller passes it to multimodal/visual gates (optional) |
| D. Constraints → prompt compiler? | **Weak** — `CONTINUITY: str(continuity_refs)` only; no structured REQUIRED/FORBIDDEN from prior scene |
| E. Visual/audio/subtitle share continuity? | Identity via dialogue_id/scene_id (T004-B); continuity **state** not shared |
| F. Optional or mandatory? | **Optional** — tracker not auto-invoked |
| G. Continuity failure ignorable? | **YES** — post-gen only when tracker passed; production loop skips tracker |
| H. Reach publication? | Continuity break alone does not block publishability (Phase-02 multimodal AND unrelated) |

---

## Gaps (PHASE-03)

1. No pre-generation continuity constraints  
2. ContinuityTracker not in production scene loop  
3. Prompt compiler CONTINUITY section unstructured / empty often  
4. No persist for recovery (`CONTINUITY_STATE.json` absent)  
5. Impossible action combos only partially in visual_semantic validators (post-gen heuristic)  

---

## IN SCOPE files

| File | Role |
|------|------|
| `pipeline/visual_semantic/continuity.py` | Extend ContinuityTracker (sole authority) |
| `pipeline/visual_semantic/continuity_runtime.py` | NEW production apply/persist wiring |
| `pipeline/multimodal_consistency/prompt_compiler.py` | Structured CONTINUITY/CAMERA/LIGHTING sections |
| `pipeline/multimodal_consistency/prompt_validator.py` | Continuity contradiction checks |
| `pipeline/video_pipeline.py` / `scene_runtime.py` | Call apply continuity after validation |
| `scripts/test_amp004_phase03_continuity.py` | Behavioral suite |

## OUT OF SCOPE

VLM/ASR · Layer-D CV · SFX/music · new score systems · FFmpeg redesign · PHASE-04+

---

## STEP-0 acceptance

- [x] Production gap confirmed: prevention missing  
- [x] Single ContinuityTracker authority preserved  
- [x] No code change in STEP-0  

**→ Implement STEP-1…**
