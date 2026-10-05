# Domain Audit Matrix — ৩০ Domain (PHASE-3)

প্রতিটি domain: A–P সংক্ষেপ। Evidence = verified codebase paths।  
**Production code changed:** `false`

---

## DOMAIN-01 Topic Intelligence

| Q | Answer |
|---|--------|
| A | `pipeline/intelligence/*`, `topic_scoring.py`, `channel_dna.py` |
| B | `generate_video` → `run_intelligence_gate` / reserve pick |
| C | Intelligence contracts + GateVerdict PASS/BLOCK |
| D | Duplicate/block list, fail-closed gate |
| E | Gate result + score evidence |
| F | Empty reserve, bad research, duplicate topic |
| G | Gate not PASS in production |
| H | Soft score for ranking |
| I | Live research provider flaky / MOCK mode |
| J | Re-pick topic / re-run research |
| K | Topic fingerprint + channel |
| L | Channel DNA / blocked list change |
| M | Research provenance modules |
| N | `test_build04g_*`, marathon research tests |
| O | `allow_duplicate` / resume plan can skip fresh gate |
| P | Full SEO honesty in all niches |

## DOMAIN-02 Research / Evidence / FactPack

| Q | Answer |
|---|--------|
| A | `fact_pack.py`, `intelligence/factpack_gate.py`, `domain/fact_pack.py` |
| B | Pre-director / script path |
| C | FactPack contract |
| D | Factpack gate |
| E | Claim vs evidence heuristic in 04F script evaluator |
| F | Unsupported claim, empty pack |
| G | Required evidence missing (when gate on) |
| H | Weak evidence → repair script |
| I | Web truthfulness |
| J | Regenerate factpack / script section |
| K | Factpack fingerprint |
| L | Topic change |
| M | Provenance in intelligence |
| N | `test_api_budget_factpack.py`, 04G tests |
| O | Plan resume may reuse old notes |
| P | Live citation verification |

## DOMAIN-03 Script / Narrative / Retention

| Q | Answer |
|---|--------|
| A | `niche_director`, script idempotency 04C, `retention_architecture.py`, 04F `evaluate_script_quality` |
| B | Plan build → scenes narrations |
| C | Script/Scene contracts |
| D | Director prompts + uniqueness |
| E | Hook/retention/structure scores (text) |
| F | Weak hook, robotic text, hallucination |
| G | CRITICAL script issues → REGENERATE |
| H | Soft pacing/naturalness |
| I | Audience retention prediction |
| J | SCRIPT / SCRIPT_SECTION |
| K | Script request fingerprint |
| L | Topic/factpack change |
| M | Script provenance |
| N | `test_build04c_*`, 04F |
| O | Resume accepted scenes |
| P | Pre-visual “visual impossibility” detector incomplete |

## DOMAIN-04 Scene Planning / SceneIntent

| Q | Answer |
|---|--------|
| A | `domain/scene.py`, `domain/scene_intent.py`, builders |
| B | `assert_production_scenes_validated` |
| C | Scene + SceneIntent |
| D | Preflight scene_contract |
| E | Intent fingerprint |
| F | Missing dialogue_id, bad duration |
| G | SceneValidationError |
| H | Soft visual emphasis |
| I | Incomplete entity inference |
| J | Scene / VisualPlan |
| K | scene identity fingerprint |
| L | Dialogue revision |
| M | VALIDATED_SCENES.json |
| N | T004-B tests |
| O | Legacy plan without gate = blocked in prod path |
| P | Full entity graph always populated নয় |

## DOMAIN-05 Visual Prompt Engineering

| Q | Answer |
|---|--------|
| A | `prompt_engineering.py`, `prompt_hardening.py`, `multimodal_consistency/prompt_compiler.py` |
| B | scene handoff + Agnes spec prompt |
| C | CompiledPrompt sections |
| D | Negative constraints, forbidden in positive |
| E | prompt_validator contradiction |
| F | Prompt vs intent mismatch |
| G | CRITICAL prompt contradiction |
| H | Style soft warnings |
| I | Provider silent mutation |
| J | Recompile prompt / regenerate visual |
| K | intent_fingerprint |
| L | Intent field change |
| M | Compiled sections in metadata (partial) |
| N | C3 multimodal tests |
| O | override_prompt paths |
| P | Provider-specific transform audit incomplete |

## DOMAIN-06 Visual Generation

| Q | Answer |
|---|--------|
| A | `agnes_bridge`, `media_assets.generate_agnes_dialogue_clip`, fallbacks |
| B | scene_builder → bridge only |
| C | VisualRequestSpec |
| D | Identity validation |
| E | Technical container + optional semantic gate |
| F | Provider fail, UNKNOWN, identity block |
| G | IDENTITY_BLOCKED, FAILED_FINAL, semantic_blocked (strict) |
| H | Retryable failures |
| I | Provider content quality |
| J | VISUAL_ASSET scene-scoped |
| K | Visual fingerprint |
| L | Prompt/dialogue/revision |
| M | visual_provenance |
| N | 04A + C1/C2/C3 |
| O | `skip_semantic_validation` metadata |
| P | Always-on Layer-D |

## DOMAIN-07 Visual Artifact Verification

| Q | Answer |
|---|--------|
| A | `visual_validation.py`, `visual_qa.py`, semantic fixtures |
| B | Post-generation bridge / optional QA |
| C | validate_visual_asset tuple |
| D | Min size / ftyp |
| E | Motion/black frames; heuristic objects |
| F | Empty/corrupt/static/black |
| G | Technical invalid, static when motion required |
| H | Soft composition |
| I | Subject match without VLM → UNKNOWN |
| J | Regenerate visual |
| K | Artifact hash |
| L | New provider bytes |
| M | QA JSON evidence frames |
| N | `test_visual_qa.py`, 04A |
| O | QA not always mandatory on every beat |
| P | Object-level CV |

## DOMAIN-08 Continuity

| Q | Answer |
|---|--------|
| A | `visual_semantic/continuity.py` |
| B | Multimodal/semantic gate when ContinuityTracker passed |
| C | ContinuityState |
| D | continuity_expected flags |
| E | Location/posture/character checks |
| F | Unexplained wardrobe/location drift |
| G | HIGH continuity break (strict) |
| H | Narrative change allowed |
| I | Lighting/camera-style drift |
| J | Scene visual repair |
| K | Prior state in tracker |
| L | Scene order change |
| M | Prior descriptions list |
| N | C3 tests |
| O | Tracker optional |
| P | Persistent cross-job continuity store |

## DOMAIN-09 Dialogue / TTS

| Q | Answer |
|---|--------|
| A | `tts_google.py`, `audio_runtime`, human_speech_engine, edge fallback |
| B | Scene audio build |
| C | AudioRequestSpec / AudioPlan |
| D | Language/voice keys |
| E | Duration/gates; dialogue_id match (C3) |
| F | Wrong language, cutoff, silence |
| G | Hard AV gates (cutoff, pace) |
| H | Soft emotion tags |
| I | Pronunciation correctness |
| J | AUDIO_ASSET |
| K | Audio fingerprint |
| L | Dialogue text change |
| M | audio_provenance |
| N | 04B tests |
| O | Edge fallback paths |
| P | ASR re-transcription verify |

## DOMAIN-10 Emotion / Voice Performance

| Q | Answer |
|---|--------|
| A | Emotion tags in quality audio evaluator; AudioIntent |
| B | Soft in 04F |
| C | emotion fields |
| D | Limited |
| E | Tag vs narration heuristic |
| F | Emotion mismatch |
| G | Rarely hard |
| H | Soft |
| I | True prosody |
| J | Audio regen |
| K | Voice profile id |
| L | Emotion intent change |
| M | Partial |
| N | 04F |
| O | Easy soft-pass |
| P | Prosody model |

## DOMAIN-11 SFX

| Q | Answer |
|---|--------|
| A | **Near-absent** (niche text mentions only) |
| B | Not production pipeline |
| C | None |
| D–O | N/A / GAP |
| P | **P1 gap** — no SFX contract |

## DOMAIN-12 Music / Background Audio

| Same as 11 | **P1 gap** |

## DOMAIN-13 Audio Mixing / Loudness / Ducking

| A | Minimal ffmpeg mux; no loudness standard pipeline |
| P | **P1** LUFS/ducking |

## DOMAIN-14 Audio ↔ Visual Sync

| A | `av_quality_gates` duration/desync; dialogue_sync |
| B | Scene + master |
| G | av_desync_length hard |
| P | Frame-accurate lip sync N/A |

## DOMAIN-15 Dialogue ↔ Visual Semantic

| A | C3 cross_modal + 04F evaluate_scene_visual_alignment |
| B | Bridge post-success (partial) + final 04F |
| G | Contradiction CRITICAL when strict/fixture |
| P | Production always-on Layer-D |

## DOMAIN-16 Localization

| A | `localization.py`, C3 localization_semantic |
| B | Localized export path |
| G | localization_text hard gate |
| P | Live semantic drift detector weak |

## DOMAIN-17 Subtitle Timing / Meaning

| A | 04E subtitle runtime, subtitle_align, C3 timeline |
| G | subtitle_timing hard |
| P | Reading-speed UX incomplete |

## DOMAIN-18 On-screen Text / Typography

| A | Limited burn_title / drawtext paths |
| P | **P2** typography contract |

## DOMAIN-19 VFX / Transitions

| A | Motion/fallback zoom-ish ffmpeg; not purposeful VFX system |
| P | **P2** purposeful-effects-only policy |

## DOMAIN-20 FFmpeg Filtergraph / Mapping

| A | `compose.py`, `scene_builder` concat filter_complex, `ffmpeg_exec.py` |
| B | Compose + scene mux |
| F | Wrong -map, freeze, black tail |
| G | Master ship black_tail / freeze |
| N | `test_ffmpeg_exec.py`, black_tail tests |
| P | Formal filtergraph schema |

## DOMAIN-21 Rendering / Encoding

| A | 04D render runtime + x264 args |
| G | Invalid container / encode fail |
| P | Bitrate ladder policy |

## DOMAIN-22 Final Media Integrity

| A | Master ship + publishability |
| G | Not publishable if technical fail |
| P | Full master semantic pass |

## DOMAIN-23 Temporal Continuity

| A | TemporalAction + validators + timeline |
| P | Physics-level reasoning absent (honest) |

## DOMAIN-24 Cross-modal Consistency

| A | multimodal_consistency + 04F cross_modal |
| O | Heuristic advisory unless strict |
| P | Wire BLOCKED → publishability always |

## DOMAIN-25 Creative Quality / Retention

| A | BUILD-04F canonical |
| B | End of `generate_video` |
| G | BLOCKED/UNKNOWN not publishable |
| P | None for authority — keep single |

## DOMAIN-26 Targeted Repair

| A | repair_planner/runtime + semantic/multimodal bridges |
| J | RepairScope enum |
| P | Full dependency-aware auto orchestration |

## DOMAIN-27 Idempotency / Cache Invalidation

| A | BUILD-03 + quality/invalidation.py |
| K | Fingerprints |
| P | Cross-process lock deferred |

## DOMAIN-28 Provenance / Traceability

| A | *_provenance.py modules + traces |
| P | Unified provenance dashboard |

## DOMAIN-29 Cost Control

| A | api_budget, provider_budget, playbook skip critic |
| P | Tiered Level-0…4 enforcement matrix |

## DOMAIN-30 Final Publishability Gate

| A | `quality/publishability.py` + MASTER_SHIP |
| G | UNKNOWN→not publishable |
| P | Explicit ARTIFACT layer input |

---

## PHASE-3 acceptance

- [x] ৩০ domain A–P covered (সংক্ষেপ matrix)  
- [x] Gaps labeled P0/P1/P2 candidates  
- [x] No code change  

**→ PHASE-3 PASS.**
