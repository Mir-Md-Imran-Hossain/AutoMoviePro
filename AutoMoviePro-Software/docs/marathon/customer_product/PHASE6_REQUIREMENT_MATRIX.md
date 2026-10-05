# PHASE6 — Requirement Matrix

**Date:** 2026-09-09  
**Audit:** Phase 6K Production Evidence Closure (forensic; no code changes)  
**Rule:** PROVEN ≠ code existence ≠ unit tests ≠ generation success alone

Status vocabulary: `IMPLEMENTED` | `PROVEN` | `LIMITED` | `UNKNOWN` | `FAILED` | `NOT_IMPLEMENTED`

Evidence class: `DETERMINISTIC` | `HEURISTIC` | `PROVIDER_VERIFIED` | `HUMAN_REVIEW` | `UNKNOWN`

---

## Matrix (46 requirements)

| # | Requirement | Authority | Implementation | Evidence | Class | Status | Limitation | Exact file/report | Real cert |
|---|-------------|-----------|----------------|----------|-------|--------|------------|-------------------|-----------|
| 1 | natural script | ScriptPlan / TRS | Customer script path + C11 REAL prep | C11 research/script REAL | DETERMINISTIC (structure) | LIMITED | Naturalness not scored by provider | `C11_CERTIFICATION.json` | LIMITED |
| 2 | natural dialogue | ScriptPlan + AudioPlan | Dialogue lines in plan; ASR observes speech | 6G/6H coverage | HEURISTIC (naturalness) / PROVIDER_VERIFIED (ASR text) | LIMITED | Naturalness = UNKNOWN acoustically | phase6g/h evidence | LIMITED |
| 3 | character consistency | ContinuityTracker | Tracker + 6F cross-beat | Adjacent beat PASS/FAIL | PROVIDER_VERIFIED (when Gemini observes subjects) | LIMITED | Face/identity biometric not proven | 6F LIVE | LIMITED |
| 4 | character identity | ContinuityTracker + VoiceIdentity (contract) | Continuity + 6D subjects | Subject labels from Gemini | PROVIDER_VERIFIED (labels) | LIMITED | Acoustic speaker ID UNKNOWN | 6D/6I | LIMITED |
| 5 | location consistency | ContinuityTracker | Explicit location contradiction FAIL | Hospital vs spacecraft FAIL | PROVIDER_VERIFIED | PROVEN (contradiction path) | Unspecified attrs → no false hard fail | 6D/6E/6J negative | PROVEN |
| 6 | environment continuity | ContinuityTracker + 6F | Environment dimension in coverage | PARTIAL/FULL dims | PROVIDER_VERIFIED / UNKNOWN | LIMITED | Often PARTIAL | 6D coverage dims | LIMITED |
| 7 | object continuity | ContinuityTracker + 6F | Entity state projection | Cross-beat compare | PROVIDER_VERIFIED when entities observed | LIMITED | Sparse object grounding on short clips | 6F | LIMITED |
| 8 | explicit object grounding | SceneIntent / VisualCoverage | Expected entities → observe | NONE/PARTIAL/FULL | PROVIDER_VERIFIED | LIMITED | Slice-proven; not full marathon | 6D–6F | LIMITED |
| 9 | relationship grounding | SceneIntent + observe | relationship dimension | Gemini relations | PROVIDER_VERIFIED | LIMITED | Vocabulary narrow | 6D | LIMITED |
| 10 | action correctness | SceneIntent + observe | action dimension | observed_actions | PROVIDER_VERIFIED | LIMITED | Coarse action labels | 6D | LIMITED |
| 11 | camera continuity | ContinuityTracker | camera expected vs observed | Often UNKNOWN/NONE | UNKNOWN / PROVIDER_VERIFIED | LIMITED | Weak observation coverage | 6D dims | LIMITED |
| 12 | lighting continuity | ContinuityTracker | lighting dimension | Often UNKNOWN/NONE | UNKNOWN | UNKNOWN | Rarely PROVIDER_VERIFIED | 6D dims | UNKNOWN |
| 13 | temporal visual consistency | 6E temporal normalize | Adjacent frame normalize + ContinuityTracker | 6E PASS + repair | PROVIDER_VERIFIED | PROVEN (slice) | Not full-length film | OPEN_SOURCE_PHASE6E_* | PROVEN |
| 14 | dialogue/visual semantic alignment | 6G alignment | Timelines FULL/PARTIAL/NONE/UNKNOWN | 6G LIVE 4 dlg / 3 beats | PROVIDER_VERIFIED + DETERMINISTIC timing | PROVEN (slice) | Not full customer render marathon | phase6g_evidence | PROVEN |
| 15 | dialogue/audio coverage | 6H audio observe | ASR segments vs dialogue plan | 6H positive/negative | DETERMINISTIC + ASR | PROVEN (slice) | edge-tts fixtures ≠ Google TTS marathon | phase6h_evidence | PROVEN |
| 16 | no silent dialogue drop | 6G + subtitle/duration | Hold must not truncate dialogue | RCP-02 policy + 6G | DETERMINISTIC | PROVEN (policy+slice) | Full E2E silent-drop hunt not re-run in 6K | alignment.py; RCP-02 notes | PROVEN |
| 17 | transcript correctness | faster-whisper (6A/6H) | ASR text vs dialogue | Match/mismatch cases | HEURISTIC (WER not certified) | LIMITED | No formal WER gate | phase6h | LIMITED |
| 18 | subtitle timing | subtitle_bridge | Audio-duration authoritative | RCP/BUILD tests | DETERMINISTIC | IMPLEMENTED | Real subtitle QA on BN limited | subtitle_bridge | LIMITED |
| 19 | voice identity contract | VoiceIdentity (RCP-06D) | Contract fields on plan | Contract present | DETERMINISTIC | PROVEN (contract) | Not acoustic | production_consistency.py | PROVEN |
| 20 | acoustic voice identity | 6I acoustic | Features only; embedding=false | VOICE_IDENTITY_OBSERVATION=UNKNOWN | UNKNOWN | UNKNOWN | **OPTIONAL LIMITATION** (no approved embedding tech) | phase6i; acoustic.py | UNKNOWN |
| 21 | cross-scene voice continuity | VoiceIdentity + 6I | Contract continuity; acoustic UNKNOWN | Heuristic voice-hint only | HEURISTIC / UNKNOWN | LIMITED | Acoustic UNKNOWN across scenes | 6I | LIMITED |
| 22 | localized voice continuity | localization + VoiceIdentity | BN/EN voice contract | RCP-04 limited | DETERMINISTIC (contract) | LIMITED | BN semantic often UNKNOWN | RCP-04 class | LIMITED |
| 23 | emotion intent | AudioPlan / SceneIntent | Intent fields | Intent exists | DETERMINISTIC | IMPLEMENTED | Observation separate | AudioPlan | IMPLEMENTED |
| 24 | actual emotion observation | 6I | Explicitly not false-mismatch; emotion UNKNOWN | emotion_not_false_mismatch | UNKNOWN | UNKNOWN | Not claimed PASS | 6I verdict | UNKNOWN |
| 25 | audio delivery integrity | 6H/6I + ffprobe/loudness | Delivery NORMAL/… | 6I delivery NORMAL | DETERMINISTIC / HEURISTIC | LIMITED | Not full mix QA | 6H/6I | LIMITED |
| 26 | visual pacing | 6G decide_visual_hold_policy | Semantic hold; reject fixed-N | 6G tests + LIVE | DETERMINISTIC + PROVIDER_VERIFIED cues | LIMITED | Full timeline marathon not re-proven | alignment.py | LIMITED |
| 27 | adaptive visual changes | 6G | Beat change on dialogue/action/entity/loc/rel/emotion/camera cues | Policy + cert | DETERMINISTIC | LIMITED | Cue → beat proven in slice; not long-form | 6G | LIMITED |
| 28 | no fixed-N visual switching | story_visual_direction + 6G | Explicit reject fixed-N authority | Code + tests | DETERMINISTIC | PROVEN (anti-regression) | RCP-02 failure permanently guarded in policy | alignment.py L441 | PROVEN |
| 29 | duration contract | duration_budget | short 60/120; long 180/300 | Code defaults | DETERMINISTIC | PROVEN (contract numbers) | Runtime media ≠ contract | duration_budget.py | PROVEN (numbers only) |
| 30 | long-form duration | duration_budget + pipeline | Target 180 / max 300 | C11 long **~8.85s** COMPLETED | DETERMINISTIC (probe) | **FAILED** (runtime) | Contract supported; actual duration not certified | C11_CERTIFICATION.json job2272 | **FAILED** |
| 31 | short-form duration | duration_budget + pipeline | Target 60 / max 120 | C11 short **~7.2s** COMPLETED | DETERMINISTIC (probe) | **FAILED** (runtime vs target) | Under-duration COMPLETED = material gap | job2273 | **FAILED** |
| 32 | multilingual production | localization_consistency | EN/BN paths | RCP-04 PASS_WITH_LIMITATION | MIXED | LIMITED | BN semantic UNKNOWN common | RCP-04 / localization | LIMITED |
| 33 | semantic observation | semantic_coverage | Gemini video/frame | 6D–6G LIVE | PROVIDER_VERIFIED | PROVEN (slice) | Keyword≠semantic (guarded) | semantic_coverage.py | PROVEN |
| 34 | provider-verified observation | frame_evidence + semantic | provider_verified flags | 6D evidence | PROVIDER_VERIFIED | PROVEN (slice) | CLIP retrieval ≠ this | phase6d | PROVEN |
| 35 | UNKNOWN propagation | semantic + publishability + observation | UNKNOWN blocks; no repair | 6F–6J unknown cases | DETERMINISTIC | PROVEN | — | publishability.py; 6J verdict | PROVEN |
| 36 | targeted visual repair | BUILD-04F + frame repair_loop | VISUAL_ASSET; hash change; re-observe | 6E EXECUTED | DETERMINISTIC + PROVIDER_VERIFIED | PROVEN (slice) | — | phase6e | PROVEN |
| 37 | targeted audio repair | plan_audio_design_repair | AUDIO_ASSET | 6H EXECUTED | DETERMINISTIC | PROVEN (slice) | edge-tts path | phase6h | PROVEN |
| 38 | re-observation | repair → observe | After hash change | 6E re-observe PASS | PROVIDER_VERIFIED | PROVEN (slice) | — | 6E lineage | PROVEN |
| 39 | whole-video regeneration avoidance | BUILD-04F | whole_video_regeneration=false | 6E–6J verdicts | DETERMINISTIC | PROVEN (slice) | — | phase6*_evidence/06_verdict | PROVEN |
| 40 | artifact verification | artifact_verification | Observe actual media | Pipeline integration | DETERMINISTIC | IMPLEMENTED | Not re-certified end-to-end in 6K | artifact_verification | LIMITED |
| 41 | render verification | rendering_integrity | VMAF/ffprobe paths | 6A adapters; pipeline | DETERMINISTIC / UNKNOWN ref | LIMITED | No-ref → UNKNOWN (correct) | rendering_integrity | LIMITED |
| 42 | publishability fail-closed | publishability | ABSENT/UNKNOWN/FAIL block | Code + slice | DETERMINISTIC | PROVEN | Publish *success* not proven | publishability.py | PROVEN (fail-closed) |
| 43 | customer isolation | workspaces + FAISS + bridges | Isolation checks | Code flags / tests | DETERMINISTIC | IMPLEMENTED | Full adversarial isolation marathon not in 6K | frame_evidence/bridge; faiss | LIMITED |
| 44 | idempotency | BUILD-03 | IDEMPOTENCY.json in repair work | Present in 6E–6J work | DETERMINISTIC | PROVEN (slice artifacts) | — | repair_work/idempotency | PROVEN |
| 45 | provenance | visual_provenance / lineage | Hash lineage files | 6E/6J | DETERMINISTIC | PROVEN (slice) | — | visual_provenance/*.json | PROVEN |
| 46 | secret redaction | api_keys / paid_api logs | key_masks in paid JSON | 6D–6J 00_paid_api | DETERMINISTIC | PROVEN (logs) | Continuous ops audit out of scope | 00_paid_api.json | PROVEN |

---

## Scorecard colors (certification only; no numeric score)

| Color | Meaning | Requirements (examples) |
|-------|---------|-------------------------|
| GREEN | Proven on real evidence | 5, 13–16, 19, 28, 29 (contract), 33–39, 42 (fail-closed), 44–46 |
| YELLOW | Implemented limited/partial | 1–4, 6–12, 17–18, 21–23, 25–27, 32, 40–41, 43 |
| BLUE | Heuristic only | Transcript naturalness; CLIP retrieval; voice-hint mismatch |
| GRAY | UNKNOWN | 12 (lighting often), 20, 24 |
| RED | Failed / not certified | 30, 31 (runtime duration); YouTube publish success; RCP-07 E2E |

---

## Gap severity

| ID | Gap | Severity |
|----|-----|----------|
| G1 | C11/RCP jobs COMPLETED with ~7–9s media vs short≥60 / long≥180 contract | **P1** (core correctness; risk of false COMPLETED) |
| G2 | YouTube / publish SUCCESS never proven (publish_validation_failed / RCP-07 FAIL) | **P1** |
| G3 | Long-form real duration + dialogue coverage not certified | **P1** |
| G4 | BN multilingual semantic often UNKNOWN | **P2** |
| G5 | Camera/lighting observation weak | **P2** |
| G6 | Acoustic VoiceIdentity UNKNOWN (no approved embedding) | **P3** OPTIONAL LIMITATION |
| G7 | Emotion acoustic observation UNKNOWN | **P3** |
| G8 | CLIP often unavailable (retrieval HEURISTIC) | **P3** |
| G9 | Unsafe UNKNOWN→PASS in publishability / semantic | **Not found** (P0 clear) |

**P0 false-success note:** No code path found converting UNKNOWN→PUBLISHABLE. Separate issue: jobs marked COMPLETED while far under duration target — treat as **P1 duration actualization / gate** (not semantic UNKNOWN bypass).
