# T004-C3 — Multimodal Consistency + Prompt Grounding

**Checkpoint:** `AMP003-T004-C3-PASS`  
**তারিখ:** ২০২৬-০৮-৩১  
**স্ট্যাটাস:** PASS

---

## ১. পণ্য উদ্দেশ্য

AutoMovie Pro-এর শিল্প-মানের (industrial-grade) **multimodal consistency boundary** প্রতিষ্ঠার লক্ষ্য ছিল — কেবল technically valid ভিডিও নয়, বরং:

- Script, Dialogue, Visual, Audio, Subtitle, Localization
- Character, Objects, Actions, Temporal order, Scene continuity, Prompts, Facts

সবগুলো **একই intended reality** বর্ণনা ও সংরক্ষণ করে।

---

## ২. গবেষণা-ভিত্তিক প্রকৌশল নীতি

| নীতি | বাস্তবায়ন |
|-------|-----------|
| Prompt উৎস সত্য নয় | `SceneIntent` canonical semantic source |
| এক সত্য → দুই দিক | Generation + Validation একই intent থেকে |
| প্রতিযোগী quality system নয় | BUILD-04F reuse via `quality_bridge.py` |
| Heuristic ≠ Vision | `HEURISTIC`, `OFFLINE_TEST_ONLY`, `PROVIDER_VERIFIED` লেবেল |
| Fail-closed critical mismatch | Layer-wise `BLOCKED`, score দিয়ে critical bypass নয় |

**Engineering hardening (অতিরিক্ত):**
- Prompt positive section থেকে `FORBIDDEN`/`NEGATIVE_CONSTRAINTS` আলাদা
- Identity mismatch সবসময় block (heuristic mode-এও)
- `revision_id` fallback provenance-এ

---

## ৩. স্থাপত্য (Architecture)

```
Canonical Scene / Dialogue
        ↓
   SceneIntent (domain/scene_intent.py)
        ↓
   ┌────────────────┴────────────────┐
   ↓                                 ↓
Prompt Compiler              Semantic Validators
(multimodal_consistency/     (visual_semantic/ +
 prompt_compiler.py)         multimodal_consistency/)
   ↓                                 ↓
Provider Prompt              IndustrialValidationReport
                                   ↓
                            BUILD-04F Repair (quality_bridge)
```

**Production call graph:**

```
video_pipeline
  → scene_runtime.assert_production_scenes_validated
      → build_canonical_scene → SceneIntent compile (handoff)
  → scene_builder
      → idempotent_generate_agnes_beat_result (agnes_bridge)
          → execute_visual_request (BRIDGE_INTERNAL)
          → multimodal_gate_for_spec (post-success)
  → render (downstream)
```

**Direct provider audit:** `scene_builder.py`-এ `generate_agnes_dialogue_clip` সরাসরি import নেই — শুধু `agnes_bridge.py` BRIDGE_INTERNAL।

---

## ৪. Canonical Scene Semantics

`domain/scene_intent.py` — একমাত্র semantic contract (duplicate Scene model নেই):

- `SemanticEntity`, `EntityRelation` — entity grounding
- `TemporalAction` — action order
- `AudioIntent`, `SubtitleIntent`, `LocalizationIntent` — cross-modal intent
- `SceneIntent` — scene_id, dialogue_id, revision_id, actions, forbidden, continuity

Builder: `pipeline/visual_semantic/scene_intent.py` — dialogue/visual plan থেকে derive।

---

## ৫. Entity / Attribute / Relation Grounding

`pipeline/multimodal_consistency/entity_grounding.py`

**উদাহরণ (mobile phone camera):**

```
MOBILE_PHONE_01
  └── CAMERA_MODULE_01 (part_of, parent_id)
```

Detect:
- Entity substitution
- Component → separate object (`component_as_separate_object`)
- Attribute misbinding (`*_entity` wrong owner)
- Relation confusion

`infer_phone_camera_entities()` — narration থেকে heuristic inference (লেবেল: HEURISTIC)।

---

## ৬. Action / Temporal / Continuity

| Layer | Module | Detect |
|-------|--------|--------|
| Action | `visual_semantic/validators.py` | wrong/conflicting/simultaneous action |
| Temporal | validators + timeline | impossible order, duration mismatch |
| Continuity | `visual_semantic/continuity.py` | unexplained location/posture/character change |

`continuity_expected` + `narrative_change_allowed` — deliberate change allowed।

---

## ৭. Prompt Compiler + Contradiction

`prompt_compiler.py` — structured sections:
SUBJECT_ENTITIES, ATTRIBUTES, RELATIONSHIPS, ACTION, TEMPORAL_ORDER, ENVIRONMENT, ...

`prompt_validator.py` — canonical vs provider prompt:
- Forbidden in positive → BLOCK
- Posture/device contradiction → BLOCK
- Required object missing from compiled prompt → BLOCK/HIGH

---

## ৮. Cross-Modal Validation

| Boundary | Module |
|----------|--------|
| Audio ↔ Dialogue identity | `cross_modal.py` |
| Visual ↔ Dialogue | `cross_modal.py` + visual_semantic |
| Subtitle timing | `timeline.py` |
| Localization semantics | `localization_semantic.py` |

Status labels: `PASS`, `PARTIAL`, `BLOCKED`, `UNKNOWN`, `VERIFIED` (future provider)।

---

## ৯. Fallback + Repair

- `visual_semantic/fallback.py` — fallback ≠ Agnes SUCCESS; semantic gate mandatory
- `multimodal_consistency/quality_bridge.py` — BUILD-04F `CreativeQualityResult`
- Targeted repair: `VISUAL_ASSET` scope only; budget via `DEFAULT_MAX_SCENE_REPAIRS`

---

## ১০. Future Multimodal Evaluator

`evaluator_adapter.py`:
- `MultimodalEvaluator` ABC
- `OfflineFixtureEvaluator` — OFFLINE_TEST_ONLY
- `HeuristicEvaluator` — prompt-derived, not CV

---

## ১১. Industrial Validation Layers

`industrial_status.py`:

1. TECHNICAL_VALIDATION
2. SEMANTIC_VALIDATION
3. CROSS_MODAL_VALIDATION
4. CONTINUITY_VALIDATION
5. LOCALIZATION_VALIDATION
6. PROMPT_VALIDATION

Final: যেকোনো layer `BLOCKED` → overall `BLOCKED`।

---

## ১২. সীমাবদ্ধতা

- Production-এ semantic analysis = **HEURISTIC** (prompt/description-derived)
- Full VLM/ASR verification = future adapter; falsely labeled নয়
- Product-plan PDF repo-তে পাওয়া যায়নি — requirements user spec + existing BUILD-04F docs থেকে

---

## ১৩. পরীক্ষা (Tests)

| Suite | Result |
|-------|--------|
| `test_amp003_task004_c3_multimodal_consistency.py` | **41/41 PASS** |
| `test_amp003_task004_c3_visual_semantic_consistency.py` | **25/25 PASS** |
| BUILD-03 through BUILD-04G-H1 | PASS |
| AMP-003 TASK-001–003, T004-B, C1, C2 | PASS |

**Known flake:** BUILD-04A `test_06` — intermittent (prior sessions); this run 18/18 PASS.

---

## ১৪. Regression Summary

```
BUILD-03: 14/14
BUILD-04A: 18/18
BUILD-04B: 21/21 + hardening 19/19
BUILD-04C: 25/25
BUILD-04D: 33/33 (2 skipped)
BUILD-04E: 40/40
BUILD-04F: 42/42
BUILD-04G: 58/58 + hardening 21/21 + H1 6/6
AMP-003 C3 multimodal: 41/41
AMP-003 C3 visual: 25/25
C2 suites: PASS (preserved)
```

---

## ১৫. Production Wiring Changes

| File | Change |
|------|--------|
| `pipeline/multimodal_consistency/` | New package — boundary, compiler, validators |
| `pipeline/scene_runtime.py` | SceneIntent prompt compile in handoff |
| `pipeline/idempotency/agnes_bridge.py` | `multimodal_gate_for_spec` post-success |
| `domain/scene_intent.py` | Extended semantic fields |
| `pipeline/visual_semantic/scene_intent.py` | Entity inference, cross-modal intents |

---

## ১৬. Verdict

**T004-C3-PASS**

- Canonical semantic source established ✓
- No duplicate Scene model ✓
- No new production provider bypass ✓
- C2-E behavior preserved ✓
- 40+ behavioral scenarios PASS ✓
- Regression PASS ✓

**STOP** — T004-D/E/TASK-005 শুরু হয়নি।
