# PHASE6 — Production Evidence Closure Audit

**Phase:** 6K — AUDIT / CERTIFICATION only  
**Date:** 2026-09-09  
**Customer context:** `c11_marathon_customer` / channel `4`  
**Predecessor:** Phase 6J PASS  

**Hard constraints honored:** no new engines; no Marathon; no YouTube upload; no new ML/providers; no gate weakening; no UNKNOWN→PASS; no fabricated PROVEN.

Companion deliverables:

- `PHASE6_REQUIREMENT_MATRIX.md`
- `PHASE6_AUTHORITY_MAP.md`
- `PHASE6_REAL_CERTIFICATION_MATRIX.md`

---

## STEP 0 — Codebase inventory (Phase 6A–6J + RCP + C05/BUILD)

| Slice | Role | Production code touch? | Cert result |
|-------|------|------------------------|-------------|
| 6A | faster-whisper, PySceneDetect, VMAF adapters | observation/adapters | PASS |
| 6B | CLIP/FAISS retrieval (HEURISTIC ≠ semantic) | `pipeline/retrieval` | PASS_WITH_LIMITATION |
| 6C | Frame evidence foundation | `pipeline/observation/frame_evidence` | PASS_WITH_LIMITATION |
| 6D | Real Gemini image/video observation | observe + semantic | PASS (LIVE) |
| 6E | Temporal normalize + VISUAL repair | temporal + repair_loop | PASS |
| 6F | Cross-beat entity consistency | cross_beat.py | PASS |
| 6G | Dialogue–visual alignment + adaptive pacing | alignment.py | PASS |
| 6H | Audio/speech observation | audio_evidence/observe.py | PASS |
| 6I | Acoustic features; identity UNKNOWN | acoustic.py | PASS_WITH_LIMITATION |
| 6J | Multimodal evidence projection | evidence_projection.py | PASS |
| RCP-02 | Pacing / dialogue hold (anti fixed-N) | story_visual_direction + plan | Historical fail → policy guard |
| RCP-03 | Semantic observation | semantic_coverage | REAL slice |
| RCP-04 | Multilingual / BN | localization | PASS_WITH_LIMITATION class |
| RCP-05 | (prior product RCP) | — | Inventory only |
| RCP-06A | Semantic UNKNOWN blocks publish | publishability | Regression OK in 6A–6J |
| RCP-06B | Duration / mid-dialogue trim protection | duration_budget + video_pipeline | Code present |
| RCP-06C | Continuity hard-block | ContinuityTracker | Authority sole |
| RCP-06D | VoiceIdentity contract | production_consistency | Contract only |
| RCP-06E | (series) | — | As prior |
| RCP-07 | TTS/blocker / E2E | runs under docs/marathon/runs | **FAILED** / publish FAIL |
| C05-S/V/Q/GA/GP/GX/MR | Story/visual/quality/materialization | preserved | Not re-authored |
| BUILD-03 | Idempotency | preserved | Slice artifacts present |
| BUILD-04F | Repair authority | preserved | VISUAL/AUDIO repair EXECUTED in 6E/6H |

**Authorities inspected (not modified):** AudioPlan, VoiceIdentity, SceneIntent, ContinuityTracker, Duration Contract, semantic_coverage, multimodal_consistency, Artifact Verification, Rendering Integrity, publishability.

---

## STEP 1–2 — Requirement matrix & evidence classes

See `PHASE6_REQUIREMENT_MATRIX.md`.

Promotion rules applied:

- HEURISTIC ↛ PROVIDER_VERIFIED  
- Code existence ↛ PROVEN  
- Unit tests ↛ real production certification  
- Prompt intent ↛ observed media truth  

---

## STEP 3 — Real media evidence audit

### Phase 6D–6J (slice cert media)

| Source | Assets | Observation | Publishability |
|--------|--------|-------------|----------------|
| 6D C11 frames (e.g. job2108 fallback PNG; video samples) | hashed under phase6d_evidence | Gemini PROVIDER_VERIFIED | Not claimed publishable from observation alone |
| 6E repair lineage | new asset hash + re-observe | PROVIDER_VERIFIED | Repair scoped VISUAL_ASSET |
| 6F–6G | reuse + LIVE Gemini | PASS/FAIL/UNKNOWN cases | UNKNOWN blocks |
| 6H–6I | edge-tts + faster-whisper | ASR DETERMINISTIC/HEURISTIC; acoustic UNKNOWN | Acoustic not PASS |
| 6J | reuse 6D/6E/6H | fusion projection | `never_directly_publishable: true` |

### C11 marathon (mr_05d3459f7f87438b)

| Job | Type | Duration (probe) | Status | Approve | Publish |
|-----|------|------------------|--------|---------|---------|
| 2272 | long | **~8.85s** | COMPLETED | APPROVED | **FAIL** (`publish_validation_failed`) |
| 2273 | short | **~7.2s** | COMPLETED | APPROVED | **FAIL** |

Audio status in meta: **UNKNOWN**.  
Checkpoint: `C11-REAL-MARATHON-PASS-WITH-LIMITATION`.

### RCP-07

| Case | Status | Publish |
|------|--------|---------|
| RCP07-LONG (job 2295, mr_aa41a7a77b9e4c11) | **FAILED** | FAIL |
| RCP07-*-SHORT variants | FAIL / validation | FAIL |

**Genuinely proven on real media (narrow):** provider visual observation, location contradiction FAIL, temporal repair+reobserve, dialogue/visual timing slice, ASR coverage slice, UNKNOWN block, targeted repair without whole-video regen, fail-closed publishability *logic*.

**Not proven:** YouTube success; long≈180s / short≈60s actual masters; batch; full BN semantic publish path.

---

## STEP 4 — Visual requirement audit (per-dimension)

| Dimension | Can system OBSERVE? | Evidence | If no |
|-----------|---------------------|----------|-------|
| Character identity (labels) | Yes (provider subjects) | 6D Gemini | Biometric ID → UNKNOWN |
| Character continuity | Partial | 6F cross-beat | — |
| Location continuity | Yes | FAIL on contradiction | — |
| Environment | Partial | coverage dims | — |
| Object continuity | Partial | 6F entities | — |
| Explicit entities | Yes when expected | VisualCoverage | — |
| Relationships | Yes coarse | Gemini relations | — |
| Actions | Yes coarse | observed_actions | — |
| Camera | Weak | often NONE/UNKNOWN | UNKNOWN |
| Lighting | Weak | often NONE/UNKNOWN | UNKNOWN |
| Temporal consistency | Yes | 6E | — |
| Dialogue–visual correspondence | Yes | 6G | — |
| Adaptive pacing | Policy yes; full film limited | 6G | LIMITED |

**Do not group all visual requirements into one PASS.** Location contradiction is PROVEN; lighting is UNKNOWN/LIMITED.

---

## STEP 5 — Audio requirement audit

| Item | Result |
|------|--------|
| Actual audio observation | Yes (6H) |
| Speech segmentation | Yes (faster-whisper) |
| Dialogue coverage | Slice PROVEN |
| Transcript matching | LIMITED (no WER cert) |
| Timing | Slice PROVEN |
| Delivery integrity | LIMITED (loudness/ffprobe) |
| VoiceIdentity contract | PROVEN |
| Acoustic identity | **UNKNOWN** (`embedding_integrated: false`) |
| Cross-scene / localized voice continuity | Contract LIMITED; acoustic UNKNOWN |
| Emotion intent | IMPLEMENTED |
| Emotion observation | UNKNOWN |

**ACOUSTIC VOICE IDENTITY = UNKNOWN** preserved.

Classification: **OPTIONAL LIMITATION** (no approved acoustic verification technology in manifests; Option A chosen in 6I).  
Not a mandatory production gap *if* product accepts contract-only VoiceIdentity + UNKNOWN acoustic observation.  
Still **must not** be reported as PASS.

---

## STEP 6 — Multimodal audit

Beat-level connection (6J): intent + observed visual + observed audio + timing + continuity + entity/relationship projected → attach to `semantic_coverage` → publishability.

Verified flags in `evidence_projection.py`:

- `creates_publishability_gate: false`
- `never_directly_publishable: true`
- chain: `evidence_projection → semantic_coverage → publishability`
- No bypass found from projection → PUBLISHABLE

---

## STEP 7 — Semantic observation audit

| Mechanism | Class |
|-----------|-------|
| Gemini video/frame (6D–6G, semantic_coverage) | **PROVIDER_VERIFIED** |
| faster-whisper ASR text | DETERMINISTIC/HEURISTIC (not visual semantic) |
| ffprobe / duration / loudness | DETERMINISTIC media metrics — **not** semantic |
| CLIP/FAISS retrieval | **HEURISTIC**; `publishability_pass: false` |
| Keyword overlap alone | Not treated as semantic PASS |
| Missing provider | UNKNOWN (never invented PASS) |

---

## STEP 8 — Duration audit

| Contract | Value | Source |
|----------|-------|--------|
| Short target / max | 60 / 120 | `pipeline/duration_budget.py` |
| Long target / max | 180 / 300 | same |
| Sole silent duration authority | `pipeline.duration_budget` | No competing silent authority found |

Mid-dialogue trim protection: `video_pipeline.py` RCP-06B comment + `duration_budget` hard-trim guard.

**Original LONG ≈ 2–5 min / SHORT ≈ 1 min:**

- **Contractually supported:** YES  
- **Runtime certified on C11:** **NO** (masters ~7–9s while COMPLETED/APPROVED)  
→ Status: **contract GREEN, actualization RED**

---

## STEP 9 — Pacing audit

- Semantic hold policy in 6G; fixed-N switching rejected as authority  
- Hold-cap must not become timeline duration / truncate dialogue (RCP-02 permanent prevention)  
- Adaptive cues: dialogue boundary, action/entity/location/relationship/emotion/camera change *can* drive beat policy  
- Full long-form pacing on real 180s master: **not proven**

---

## STEP 10 — Continuity audit

- `ContinuityTracker` remains sole policy authority  
- Observation layers cite; do not replace  
- Explicit contradictions block; unspecified → prefer UNKNOWN over false hard FAIL (6E/6F normalize)

---

## STEP 11 — Repair audit

| Path | Evidence |
|------|----------|
| FAIL → repair → new asset → hash change → lineage → re-observe | 6E visual |
| AUDIO_ASSET repair | 6H |
| whole_video_regeneration | false in 6E–6J verdicts |
| BUILD-04F | remains repair plan authority |
| BUILD-03 | IDEMPOTENCY artifacts in repair_work |
| UNKNOWN → repair | blocked (`unknown_no_repair: true`) |

---

## STEP 12 — UNKNOWN audit

Searched bridges: semantic_coverage, multimodal_consistency/evidence_projection, publishability, observation common statuses, video_pipeline RCP-06A block.

**Unsafe UNKNOWN → PASS/READY/PUBLISHABLE/repair/success:** not found in these authorities.

Customer workspace/generation/publish: publishability still requires semantic PASS; UNKNOWN blocks.

---

## STEP 13 — False-success audit

| Claim | Reality |
|-------|---------|
| Generated | C11 COMPLETED files exist |
| Verified | Semantic/audio often incomplete; C11 audio_status UNKNOWN |
| Publishable | Not proven SUCCESS |
| Approved | C11 APPROVED despite under-duration |
| Published | FAIL |

**Generated ≠ Verified ≠ Publishable ≠ Approved ≠ Published** — architecture intent preserved for publishability UNKNOWN, but **COMPLETED/APPROVED at ~8s “long”** is a material false-success risk vs duration contract (**P1**).

RCP-07 FAILED correctly avoids false publish success.

---

## STEP 14 — Authority audit

See `PHASE6_AUTHORITY_MAP.md`.

- Competing authorities in Phase 6 stack: **0**  
- Acoustic verification authority: **0** (honest UNKNOWN)  
- Architecture conflict: **no** → not ARCHITECTURE_BLOCKED  

---

## STEP 15 — Customer journey

| Stage | Status |
|-------|--------|
| AUTH → ENTITLEMENT → CHANNEL → API | IMPLEMENTED (not re-proven in 6K) |
| TOPIC → RESEARCH → SCRIPT → TRS → PLAN | REAL on C11/RCP (LIMITED) |
| GENERATION | REAL; under-duration masters |
| OBSERVATION → QUALITY → REPAIR | REAL on Phase 6 slices |
| RENDER → PREVIEW | REAL artifacts; integrity LIMITED |
| APPROVAL | IMPLEMENTED; can APPROVE under-duration (gap) |
| PUBLISHABILITY | Fail-closed PROVEN in logic |
| PUBLISH → SCHEDULE | **FAILED** / not SUCCESS-proven |
| MONITOR → RECOVERY | monitor_ok seen; recovery not full-certified |

---

## STEP 16 — Multilingual

| Lang | Evidence |
|------|----------|
| EN | C11 / Phase 6 slices REAL |
| BN | RCP-04 class PASS_WITH_LIMITATION; semantic often UNKNOWN |

Config alone ≠ multilingual production PROVEN.

---

## STEP 17 — Long / short / batch

| Mode | Real evidence |
|------|---------------|
| Single short slice observation | PROVEN (6D–6J) |
| Single short E2E ~60s + publish | **NOT PROVEN** |
| Long ~180s E2E | **NOT PROVEN** (C11 “long” ~8.85s) |
| Multilingual BN E2E | LIMITED |
| Batch | **NOT PROVEN** (do not extrapolate) |

---

## STEP 18 — Open-source audit

| Check | Result |
|-------|--------|
| OpenMontage production imports in `pipeline/` | **0** (comments/isolation only; tree under `third_party/OpenMontage` not imported) |
| AGPL copied into production path | **0** claimed; isolation maintained |
| faster-whisper | **Used** in 6A/6H/6I cert |
| PySceneDetect / VMAF | Adapters 6A; production usage as configured |
| CLIP/FAISS | Optional; often unavailable → HEURISTIC retrieval only |

No new dependencies added in 6K.

---

## STEP 19 — Performance / cost (review only)

| Signal | Note |
|--------|------|
| Phase 6D–6G paid Gemini | Controlled LIVE counts; key masks in evidence |
| 6H–6J | Prefer reuse + local ASR; 0 Google on 6J cert |
| Repair | Targeted asset; whole-video false |
| Risk | Under-duration COMPLETED may hide need for more generation/repair cycles when duration gate is enforced |

No performance architecture changes in this audit.

---

## STEP 20 — Production-grade scorecard

| Domain | Color |
|--------|-------|
| Observation architecture (6A–6J) | GREEN / YELLOW |
| Provider visual semantic (slice) | GREEN |
| Audio ASR coverage (slice) | YELLOW |
| Acoustic identity | GRAY |
| Duration contract | GREEN |
| Duration actualization | RED |
| Publish fail-closed | GREEN |
| Publish success / YouTube | RED |
| Continuity authority | GREEN |
| Repair targeted | GREEN |
| Multilingual BN | YELLOW |
| Batch | RED |
| OpenMontage isolation | GREEN |

---

## STEP 21 — Gap severity summary

- **P0:** Unsafe UNKNOWN→PUBLISHABLE — **not found**  
- **P1:** Duration actualization vs COMPLETED/APPROVED; publish SUCCESS unproven; long/short runtime certification missing  
- **P2:** BN semantic; camera/lighting observation weakness  
- **P3:** Acoustic identity / emotion observation OPTIONAL UNKNOWN  

No fixes implemented in this phase.

---

## STEP 22 — Next-phase decision

| Option | Fit? |
|--------|------|
| A READY_FOR_REAL_FULL_CERTIFICATION | **No** — material P1 gaps |
| B READY_WITH_LIMITATIONS | Observation stack yes; **full product claim no** |
| C BLOCKED | **Yes for full production-requirement satisfaction** |
| D ARCHITECTURE_BLOCKED | **No** — single authorities intact |

**FINAL VERDICT: BLOCKED**

Rationale: Original AutoMovie Pro production requirements for **runtime duration (short≈60 / long≈180–300)** and **successful publish path** are not satisfied by available real evidence. Phase 6 observation/evidence foundation is otherwise strong and architecture-clean, but cannot certify product readiness.

**Observation-stack sub-status (informational):** READY_WITH_LIMITATIONS (6I acoustic UNKNOWN optional; camera/lighting weak; BN limited).

### NEXT RECOMMENDED PHASE

**`DURATION_ACTUALIZATION_AND_SHORT_E2E_PUBLISH_CERT`**

Smallest evidence-derived next phase (not “Phase 6K implementation”, not a new ML engine):

1. Enforce / prove actual media duration against `pipeline.duration_budget` before COMPLETED/APPROVED.  
2. Produce one REAL short master near target 60s (≤120) with dialogue coverage + mid-dialogue trim protection.  
3. Drive publishability with real observation evidence; prove publish path (or honest FAIL with root cause) — **no YouTube upload required until validation passes**.  
4. Keep acoustic VoiceIdentity as UNKNOWN optional limitation.  
5. Do not add observation engines; wire existing 6A–6J evidence into the customer job path where gaps remain.

Defer long-form 180s and batch until short E2E duration+publishability is GREEN.

---

## HARD STOP

- No production code changes in Phase 6K.  
- No next implementation phase started.  
- No full Marathon / no YouTube upload.  
- No new ML dependencies or providers.  
- Gates not weakened; UNKNOWN not converted to PASS.  
- Certification not fabricated.

**Phase 6K audit complete.**
