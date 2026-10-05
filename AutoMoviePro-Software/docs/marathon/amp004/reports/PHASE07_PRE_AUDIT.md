# PHASE-07 Pre-Audit — Industrial Creative Production & Retention

**Date:** 2026-09-03  
**Checkpoint before:** `AMP004-LOCALIZATION-SUBTITLE-TEXT-PASS`  
**Production code changed during STEP-0:** `false`

**Roadmap note:** Frozen AMP004 listed visual quality as PHASE-06 and script-narrative as PHASE-05. User PHASE-07 is **creative production, storytelling, retention, and generation-time prevention**. Visual CV/VLM remains deferred. Do not start PHASE-08 (VFX/FFmpeg).

---

## 1. Production call graph (verified)

```
app.main / scheduler_service
  → video_pipeline.generate_video
      → intelligence.bridge.run_intelligence_gate          (topic/research)
      → idempotency.script_bridge.idempotent_plan_niche_production
          → niche_director.plan_niche_production           (LLM script)
      → content_humanizer.humanize_plan
      → contract_wiring.production_bridge.assert_production_plan_wiring
      → scene_runtime.assert_production_scenes_validated
          → scene_contract.preflight_scene_contract
          → continuity_runtime.apply_production_continuity  (P03 ContinuityTracker)
          → audio_design.production.apply_production_audio_design (P05)
      → per-scene TTS (tts_bridge) + visual (scene_builder / agnes_bridge)
      → render_bridge.idempotent_compose_final_video
      → av_quality_gates.evaluate_master_shippable
      → artifact_verification.production.run_production_artifact_verification (P04)
      → audio_design.production.run_production_audio_design_gate
      → localization_consistency.production.run_production_localization_gate (P06)
      → quality.bridge.run_creative_quality_gate            (BUILD-04F scores)
      → quality.bridge.run_publishability_gate
      → media_assets.generate_thumbnail
      → package_export.export_upload_package
```

**Canonical entry:** `pipeline/video_pipeline.py` → `generate_video`.

---

## 2. Area map

| Area | Status | Canonical path | Notes |
|------|--------|----------------|-------|
| Topic / research / factpack | EXISTS | `pipeline/intelligence/*` | Parallel `fact_pack.py` — do not recreate |
| Script generation | EXISTS | `script_bridge` → `niche_director` | Parallel `ai_providers.generate_script_bundle` — do not recreate |
| Script quality (post) | EXISTS | `quality/evaluators.evaluate_script_quality` | BUILD-04F authority — **extend, do not replace** |
| Hook contract | WEAK | generic-opener list in evaluators | No first-section purpose contract; no clickbait/unsupported-claim block pre-gen |
| Retention | WEAK | `retention_architecture.py` | Blueprint exists; **not production-wired** |
| SceneIntent | EXISTS | `domain/scene_intent.py` | Semantic authority. Missing explicit `purpose` / narrative_role / shot purpose |
| Scene purpose | ABSENT | scenes generated from narration + shot text | “WHY does this scene exist?” not required |
| ContinuityTracker | EXISTS | `visual_semantic/continuity.py` + `continuity_runtime` | Production-wired P03 — **sole continuity authority** |
| Action atomicity | WEAK | TemporalAction + continuity impossible-action | No HOLD vs DESCRIBE vs TRANSFORM split; smartphone/camera via `entity_grounding.infer_phone_camera_entities` |
| Entity/attribute ownership | PARTIAL | SemanticEntity + EntityRelation | Phone-camera heuristic exists; not a general ownership preflight |
| Metaphor / figurative | ABSENT | — | Risk of literalizing “camera powerhouse”, “heart of the city” |
| Camera / shot plan | WEAK | `domain.scene.ShotPlan` (camera as free text) | No shot_type/purpose; no unmotivated-cut policy |
| Prompt compiler | EXISTS | `multimodal_consistency.prompt_compiler` | Canonical. Duplicates: `prompt_engineering`, `scene_contract.compile_prompt_from_contract` — **do not add a third** |
| Negative constraints | PARTIAL | SceneIntent.negative_constraints + phone DSLR list | Not systematically generated from purpose/metaphor/ownership |
| Emotion / pacing | PARTIAL | AudioIntent / AudioPlan (P05) | Dialogue pause/emphasis plan not scene-purpose-bound |
| SFX / music | EXISTS | AudioPlan (P05) | Creative sync (door close → SFX; mood mismatch) not planned here |
| Transitions / VFX | WEAK | continuity narrative_change; text effects P06 | No purposeful cut vs zoom/flash policy — deep VFX is PHASE-09 |
| Thumbnail / title | WEAK | `media_assets.generate_thumbnail` | Non-blocking; no title↔script consistency gate |
| Preflight before provider | PARTIAL | scene_contract, audio, loc, multimodal | **Script LLM and visual gen lack creative-purpose preflight** |
| Artifact verification | EXISTS | P04 | Observe actual media — reuse |
| Multimodal | EXISTS | `multimodal_consistency` | Reuse |
| Repair | EXISTS | BUILD-04F `repair_planner` | Reuse; map creative issues to SCRIPT/SCENE/VISUAL_PLAN/RENDER |
| Idempotency | EXISTS | BUILD-03 | Reuse; prompt/intent change already invalidates visual FP |
| Publishability | EXISTS | AND dimensions P02–P06 | Creative **score** is 04F; no CREATIVE_PRODUCTION_GATE |

---

## 3. Duplicates — DO NOT recreate

| System | Keep |
|--------|------|
| SceneIntent | semantic source |
| ContinuityTracker | continuity |
| prompt_compiler | prompts |
| AudioPlan / audio_design | audio |
| LocalizationContract | localization |
| artifact_verification | observe actual artifacts |
| multimodal_consistency | cross-modal |
| BUILD-03 IdempotentExecutor | cache/fingerprint |
| BUILD-04F quality/evaluators + repair_planner | quality scores + repair |
| publishability.evaluate_publishability | publish AND |
| retention_architecture | extend/wire, not replace |
| entity_grounding.infer_phone_camera_entities | extend |

---

## 4. Provider calls without creative preflight

| Site | Gap |
|------|-----|
| `script_runtime.execute_script_request` → `niche_director` | No topic/identity/purpose preflight; no hook/purpose check before visual spend |
| `continuity_runtime` → compile → Agnes/visual | Continuity + prompt contradiction only; no scene-purpose / metaphor / shot-purpose |
| `video_pipeline` TTS fallback `synthesize_narration` | P05 preflight on primary path; fallback still a bypass (document; do not rewrite TTS engine) |
| Thumbnail Pollinations | Optional paid path; consistency not checked |

Deterministic information currently left to the provider: scene purpose, shot reason, attribute-vs-transform, metaphor visualization policy, retention role, title honesty.

---

## 5. Identity / fingerprint / provenance

| Strong | Weak |
|--------|------|
| Script/visual/audio fingerprints (BUILD-03) | Hook/retention not first-class persisted contracts |
| SceneIntent fingerprint in handoff | Fingerprint omits purpose / shot_purpose / negatives |
| CONTINUITY_STATE, AUDIO/LOCALIZATION/ARTIFACT gates | No CREATIVE_PRODUCTION_GATE.json |

---

## 6. EXTEND (implementation intent — not done in STEP-0)

- **NEW package** `pipeline/creative_production/` — plan + deterministic preflight + gate (same pattern as `audio_design` / `localization_consistency`)
- **EXTEND** SceneIntent + ShotPlan + prompt_compiler sections (purpose, ownership, figurative policy, shot purpose)
- **WIRE** scene_runtime (after continuity + audio), script_runtime (before provider), video_pipeline + publishability
- **REUSE** ContinuityTracker, AudioPlan, LocalizationContract, P04, 04F, BUILD-03
- **WIRE** existing `retention_architecture.attach_retention_to_plan`

## OUT OF SCOPE (document only)

- Full CV/VLM physical-world understanding (DEF-AMP004-009)
- New prompt engine / new quality score / new repair / new idempotency
- PHASE-08+ FFmpeg Filtergraph / cinematic VFX library
- Paid thumbnail/LLM calls in tests

---

## 7. Honesty policy

Physical plausibility without CV → **HEURISTIC / UNKNOWN**, never silent PASS.  
Linguistic “engaging” without human eval → **HEURISTIC**.  
UNKNOWN mandatory → **not publishable**.
