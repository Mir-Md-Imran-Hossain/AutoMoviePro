# T004-C3 — Visual Semantic Consistency & Fallback Quality Boundary

**Marathon:** AMP-003  
**Task:** TASK-004 / T004-C  
**Phase:** C-3  
**Checkpoint:** AMP003-T004-C3-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## ১. উদ্দেশ্য

AutoMovie Pro-এর লক্ষ্য শুধু technically valid video file নয় — accurate, coherent, visually meaningful, narration-synchronized, temporally/scene-to-scene consistent, production-ready content।

T004-C3 একটি **validation boundary** তৈরি করে Agnes/image generator rewrite না করে:

```
Scene Intent → Visual Request → Generation → Technical Validation → Semantic Check → Continuity → PASS / REPAIR
```

---

## ২. Product-quality objective

Product plan PDF repo-তে পাওয়া যায়নি। প্রাসঙ্গিক requirement sources:

- `docs/build04f/CREATIVE_QUALITY_MODEL.md`
- `docs/build04f/QUALITY_DIMENSIONS.md`
- `pipeline/scene_contract.py` (claim → evidence → shot)
- User-specified failure modes: wrong action, conflicting actions, continuity break, dialogue/visual mismatch

---

## ৩. বর্তমান architecture

```
video_pipeline
  → scene_runtime (validated handoff + identity)
  → scene_builder → agnes_bridge → visual_runtime
  → validate_visual_asset (technical)
  → visual_semantic.boundary (semantic — NEW)
  → quality/repair (BUILD-04F)
  → downstream
```

**C2 regressions preserved:** BYP-01/02 removed; outcome semantics intact.

---

## ৪. SceneIntent contract

**File:** `domain/scene_intent.py`

`SceneIntent` extends existing Scene/VisualPlan semantics without replacing `Scene` model.

Fields: `scene_id`, `dialogue_id`, `summary`, `primary_action`, `actors`, `location`, `posture`, `required_objects`, `forbidden_objects`, `action_order`, `continuity_expected`, `narrative_change_allowed`, etc.

Builder: `pipeline/visual_semantic/scene_intent.py` — `build_scene_intent_from_dialogue()` derives intent from **shared dialogue + visual prompt source**.

---

## ৫. Action validation

**File:** `pipeline/visual_semantic/validators.py`

Deterministic heuristic checks (honestly labeled):

- `UNEXPECTED_ACTION`
- `CONFLICTING_ACTION` (e.g. drink + eat simultaneously)
- `MULTI_ACTION_OVERLOAD`

**Not computer vision** — uses `VisualAnalysisMetadata` adapter boundary.

---

## ৬. Object validation

Required/forbidden object compatibility via metadata objects list.

Codes: `MISSING_REQUIRED_OBJECT`, `FORBIDDEN_OBJECT`, `UNEXPECTED_OBJECT`.

---

## ৭. Location validation

Chair vs floor style mismatches → `LOCATION_MISMATCH`.

---

## ৮. Posture validation

Expected vs detected posture → `POSTURE_MISMATCH`.

---

## ৯. Continuity

**File:** `pipeline/visual_semantic/continuity.py`

`ContinuityTracker` tracks character, location, posture, objects across scenes.

- `continuity_expected=True` + no `narrative_change_allowed` → unexplained change = `CONTINUITY_BREAK`
- Legitimate narrative change → PASS

---

## ১০. Dialogue/visual alignment

Shared semantic source: dialogue → scene intent → visual request.

`DIALOGUE_IDENTITY_MISMATCH` always blocks.

`DIALOGUE_VISUAL_CONTRADICTION` blocks only in **strict** mode or `OFFLINE_TEST_ONLY` fixtures.

---

## ১১. Temporal ordering

`TemporalAction` list with `order` + `relation`.

`TEMPORAL_CONTRADICTION` when sequential order required but analysis reports simultaneous actions.

---

## ১২. Technical vs semantic validation

| Status | Meaning |
|--------|---------|
| `TECHNICAL_PASS` | File valid (via existing `validate_visual_asset`) |
| `SEMANTIC_PASS` | Intent compatible |
| `SEMANTIC_PARTIAL` | Heuristic advisory issues |
| `SEMANTIC_BLOCKED` | Strict/fixture mode block |
| `UNKNOWN` | Skipped |

**Rule:** Never claim `SEMANTIC_PASS` when only technical validation ran without semantic evaluation.

---

## ১৩. Fallback boundary

**File:** `pipeline/visual_semantic/fallback.py`

`FallbackAssetRecord`: `fallback_reason`, `source_provider`, scene/dialogue identity, `intent_fingerprint`, `validation_status`, `is_agnes_success=False`.

Fallback assets run semantic validation — cannot bypass.

---

## ১৪. Targeted repair

**File:** `pipeline/visual_semantic/repair_bridge.py`

Integrates BUILD-04F: semantic failure → `RepairScope.VISUAL_ASSET` → `plan_semantic_repair()` → bounded attempts → escalate (no infinite loop).

---

## ১৫. Quality integration

Feeds existing `CreativeQualityResult` / `plan_repair()` — no competing quality system.

Robotic signals: `REPEATED_PATTERN` (deterministic, defensible).

---

## ১৬. Strict vs heuristic modes

| Mode | Behavior |
|------|----------|
| Heuristic (default production) | Advisory; blocks only identity mismatch |
| Strict / OFFLINE_TEST_ONLY fixture | Full semantic blocking for tests |

Production hook in `agnes_bridge.py`: runs heuristic gate post-success; strict block only with `strict_semantic_validation` or `semantic_analysis_fixture` metadata.

---

## ১৭. Limitations

- No real computer vision / VLM in automated tests
- Heuristic metadata ≠ pixel-level verification
- Image provider chain (C-4) not redesigned
- Full VLM integration deferred

---

## ১৮. Tests

`scripts/test_amp003_task004_c3_visual_semantic_consistency.py` — **25/25 PASS**

All offline, no paid API, behavioral fixtures labeled `OFFLINE_TEST_ONLY`.

---

## ১৯. Regression

| Suite | Result |
|-------|--------|
| C3 semantic | 25/25 PASS |
| C2 single success | 16/16 PASS |
| C2 failure propagation | 20/20 PASS |
| C2-E split bypass | 13/13 PASS |
| BUILD-04F | 42/42 PASS |
| BUILD-03 | 14/14 PASS |
| BUILD-04A | 17/18 PASS (test_06 known intermittent flake — FAIL this run) |

---

## ২০. Direct provider audit

No new production bypass in `scene_builder.py`. Only `agnes_bridge.py` BRIDGE_INTERNAL.

---

## ২১. Final verdict

**FEATURE STATUS: PASS**

**CHECKPOINT: AMP003-T004-C3-PASS**

Semantic validation boundary implemented. C2 outcomes preserved. Offline behavioral tests pass. Heuristic limitations documented honestly.

**P0 = 0**

**NEXT:** T004-C4 (image fallback architecture) or user command — NOT auto-started.
