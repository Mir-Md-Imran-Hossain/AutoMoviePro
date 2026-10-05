# AUTO MOVIE PRO — MATURE TOOL INTEGRATION & INDEPENDENT VALIDATION AUDIT

**Phase:** Pre-implementation architecture audit (T0)  
**Date:** 2026-09-11  
**Scope:** Evidence-first comparison of AMP production code vs mature open-source tools  
**Production code changed:** **none**  
**Packages installed:** **none**  
**Authority posture:** External tools = observers / specialist workers; AMP deterministic contracts = authority  

---

## 1. Executive Summary

AutoMovie Pro already has a **strong authority-layered production architecture**: BUILD-03 idempotency, BUILD-04F creative quality, BUILD-04G research, SceneIntent, ContinuityTracker, multimodal boundary, artifact verification, FFmpeg compose, duration contract, localization, and publishability AND-gates.

**Real-media marathon evidence (2026-09-10)** shows:

| Outcome | Evidence |
|---------|----------|
| End-to-end core path can complete | job2333 `FINAL_VERDICT=PASS_WITH_LIMITATION`, EXIT=0; job2332 salvage PUBLISHABLE + 6-lang LOCALIZED |
| Final render + localization | **PROVEN** (`final_short.mp4`, six language packages, curated `Output/Short/…`) |
| Montage brain (AMP-owned) | **PARTIALLY PROVEN** (checklist ok; stock-first; Agnes often UNKNOWN → i2v) |
| Semantic / Gemini observer | **UNRELIABLE** under quota (soft-continue flags required) |
| Agnes primary VIDEO path | **UNRELIABLE** (frequent UNKNOWN → fallback) |

**Core recommendation:** Do **not** replace AMP authorities with ShortGPT / MoneyPrinterTurbo / OpenMontage pipelines. Instead:

1. **Harden independent validators already wired** (Faster-Whisper, PySceneDetect, VMAF, CLIP/FAISS).
2. **Adopt concepts** (not full stacks) from ShortGPT editing JSON and MoneyPrinter material-matching.
3. **Never import AGPL OpenMontage** into core; keep as isolated reference.
4. **Defer** heavy GPU stacks (SAM2, Real-ESRGAN, Demucs, Remotion-as-authority, pyannote).
5. **Defer agent frameworks** until T4; if one is chosen later, prefer a **single** supervisor candidate that does **not** own quality/idempotency/render.

Optimize for: max real quality · min custom engineering · min duplicate logic · max observability · Windows maintainability.

---

## 2. Current AMP Production Architecture

```
Topic (BUILD-04G) → Research/FactPack → Script/TRS → Customer Approved Plan lock
    → SceneIntent + prompt_compiler → ContinuityTracker
    → Visual (Agnes VIDEO-primary → montage stock / i2v fallback)
    → TTS (Google → Edge → optional Piper) + subtitles
    → Observation (Whisper ASR, PySceneDetect, optional VMAF, Gemini semantic)
    → Artifact Verification → Creative Quality (04F) → Audience
    → Duration reconciliation → Publishability AND-gate
    → Localization (6 langs) → Curated Output export
    → FFmpeg remains final compose/remux authority
```

**Packaging surface:** `requirements.txt` / `requirements-dev.txt` (no root `pyproject.toml` / Dockerfile). Windows bootstrap via `START.bat` + `app/bootstrap_runtime.py`. Vendored FFmpeg under `ffmpeg-8.1.1-full_build/`.

**OpenMontage:** `third_party/OpenMontage/` + `ISOLATION_NOTICE.md` — **not imported** by `pipeline/` or `app/`.

---

## 3. Current Authority Map

| Authority | Primary modules | Owns | External tool may… |
|-----------|-----------------|------|---------------------|
| BUILD-03 idempotency | `pipeline/idempotency/*` | Claim/reuse/checkpoint/retry | Observe only; never second store |
| BUILD-04F creative quality | `pipeline/quality/*`, repair bridges | Score + targeted repair | Feed evidence; not replace score |
| BUILD-04G research | `pipeline/intelligence/*` | Topic/dup/research | Supply sources; not own gate |
| SceneIntent | `domain/scene_intent.py`, `visual_semantic/scene_intent.py` | Semantic SoT | Validate; not rewrite silently |
| multimodal_consistency | `pipeline/multimodal_consistency/*` | Cross-modal boundary | Evidence adapters |
| ContinuityTracker | `pipeline/visual_semantic/continuity.py` | Continuity | Observe; no second tracker |
| av_quality_gates | `pipeline/av_quality_gates.py` | Technical AV cutoffs | Soft evidence only |
| prompt_compiler | `multimodal_consistency/prompt_compiler.py` | Canonical prompts | No parallel prompt engine |
| Artifact Verification | `pipeline/artifact_verification/*` | Media observation gate | Extend observers |
| FFmpeg | `pipeline/compose.py`, render bridges | Final render/compose | Workers may produce intermediates |
| Publishability | `pipeline/quality/publishability.py` | Ship AND-gate | Never fork |
| Duration contract | `pipeline/duration_budget.py` | Short/long budgets | OTIO may interchange only |
| Localization | `pipeline/localization.py` + consistency | Translate/TTS/remux | Caption helpers only |
| montage_brain | `pipeline/montage_brain/*` | Slot/stock discipline | Stock APIs as workers |
| Retrieval | `pipeline/retrieval/*` | Embed/index/rank | Real CLIP backend under AMP |
| Job/scheduler/config | `app/customer_job*`, `scheduler_service`, settings | Ops authority | No second queue/config |

**Anti-pattern already documented:** do not create duplicate continuity / publishability / generate / checkpoint engines (`OPEN_SOURCE_INTEGRATION_AUDIT.md`).

---

## 4. Existing Component Reliability Matrix

| Component | Current Role | Authority | Real Evidence | Status | Observed Problems | Recommendation |
|-----------|--------------|-----------|---------------|--------|-------------------|----------------|
| Marathon cert runner | E2E orchestration | Cert harness | job2333 PASS_WITH_LIMITATION; many FAIL runs | PARTIALLY PROVEN | Provider quota, topic dup false-match | KEEP + STRENGTHEN |
| FFmpeg compose/remux | Final render | Sole render | final_short.mp4 job2325/2332/2333 | PROVEN | Probe edge cases | KEEP |
| Localization 6-lang | Dubbing packages | Localization | LOCALIZED en/bn/hi/ur/ta/ml | PROVEN | Scene-local flaky; master fallback | KEEP + STRENGTHEN |
| Duration contract | Budget/reconcile | Sole duration | DURATION_RECONCILIATION PASS | PROVEN | — | KEEP |
| BUILD-03 idempotency | Dedup/reuse | Sole | IDEMPOTENCY.json artifacts | PROVEN | UNKNOWN reconciliation | KEEP |
| ASR (faster-whisper) | Speech timing evidence | Observation | AUDIO_ASR_EVIDENCE_GATE PASS job2333 | PROVEN | Model download/CPU cost | KEEP + STRENGTHEN |
| Artifact / render / audio gates | Technical ship | Gates | ARTIFACT/RENDER/AUDIO PASS | PROVEN | — | KEEP |
| Publishability mechanics | Final AND | Sole | all_gates_pass when soft flags set | PARTIALLY PROVEN | Soft env can mask semantic FAIL | KEEP; tighten honesty |
| Creative quality 04F | Score/repair | Sole creative | PASS after near-miss fixes | PARTIALLY PROVEN | Heuristic dims; cache stale verdicts | KEEP + STRENGTHEN |
| Scene boundary (PySceneDetect) | Cut observation | Observation | Soften Ken Burns/missing_cut | PARTIALLY PROVEN | False FAIL on documentary holds | KEEP + STRENGTHEN |
| montage_brain | Stock-first slots | AMP montage | checklist ok job2332/2333 | PARTIALLY PROVEN | Weak without real stock hits | KEEP + STRENGTHEN |
| Retrieval CLIP/FAISS | Visual similarity | Observation | Tests + optional deps | PARTIALLY PROVEN | Hash embed ≠ semantic truth | KEEP + STRENGTHEN (real CLIP) |
| BUILD-04G research | Topic/research | Sole research | Runs complete; often LOCAL_FACTPACK | PARTIALLY PROVEN | Not external live web | KEEP + STRENGTHEN |
| Semantic coverage / Gemini | Semantic observe | Semantic gate | Soft-continue FAIL/UNKNOWN | UNRELIABLE | Quota/403/503 | KEEP authority; improve observers |
| Agnes VIDEO primary | Generative video | Provider worker | Frequent UNKNOWN | UNRELIABLE | Runtime UNKNOWN → i2v | KEEP adapter; diversify workers |
| Google TTS primary | TTS | Provider | Prefer Edge in cert | PARTIALLY PROVEN | Quota/skip flags | KEEP failover |
| Piper TTS | Offline fallback | Optional worker | Code path exists | UNPROVEN | Binary/model mgmt; BN quality unknown | DEFER production reliance |
| VMAF | Perceptual evidence | Observation | Adapter + tests | PARTIALLY PROVEN | Needs reference; libvmaf optional | KEEP + STRENGTHEN |
| Voice acoustic identity | Speaker proof | Claim | VOICE_ACOUSTIC_UNKNOWN | UNPROVEN | No pyannote | DEFER |
| Urdu RTL shaping | Locale proof | Localization | Explicit UNKNOWN cases | UNPROVEN | arabic-reshaper optional | KEEP + STRENGTHEN |
| OpenMontage | Reference AGPL | None in prod | Isolated third_party | UNPROVEN (intentional) | AGPL | REFERENCE ONLY |
| OTIO | Timeline interchange | None | Docs only | UNPROVEN | Not implemented | DEFER / concept |
| Customer product UX | Topic/approve UI | Product | Audits show gaps | PARTIALLY PROVEN | Engine > UX | Product track (out of tool scope) |

---

## 5. Mature Tool Comparison

| Tool | Primary Capability | Recommended Role | Integration Complexity | Custom Code | CPU/GPU | Windows | License Risk | Quality Benefit | Priority |
|------|--------------------|------------------|------------------------|-------------|---------|---------|--------------|-----------------|----------|
| Faster-Whisper | ASR timing | VALIDATOR (already) | LOW | LOW | CPU good; GPU optional | GOOD | LOW (MIT) | HIGH | **P0** |
| PySceneDetect | Scene cuts | VALIDATOR (already) | LOW | LOW | CPU | GOOD | LOW (BSD-3) | MEDIUM | **P0** |
| VMAF / libvmaf | Perceptual score | VALIDATOR (already) | MEDIUM | LOW | CPU/GPU | PARTIAL | LOW (BSD-ish via FFmpeg) | MEDIUM | **P1** |
| CLIP + FAISS | Retrieval embed | VALIDATOR/WORKER | MEDIUM | MEDIUM | GPU preferred | PARTIAL | LOW (Apache/MIT stack) | HIGH | **P1** |
| MoneyPrinterTurbo (concepts) | Material match, TTS/subtitle patterns | REFERENCE → ADAPTER ideas | LOW–MED | LOW | CPU | GOOD | LOW (MIT) | MEDIUM | **P1** |
| ShortGPT EditingEngine (JSON/EML) | Edit representation | REFERENCE → ADAPTER | MEDIUM | MEDIUM | CPU | GOOD | LOW (MIT) | MEDIUM | **P2** |
| OpenTimelineIO | Timeline interchange | ADAPTER (debug/export) | MEDIUM | MEDIUM | CPU | GOOD | LOW (Apache-2.0) | LOW–MED | **P2** |
| Piper | Offline TTS | WORKER fallback | MEDIUM | LOW | CPU | PARTIAL | MEDIUM (MIT→GPL fork drift) | LOW–MED | **P3** |
| Auto_Shorts_Generator | Hook/face/9:16 | OPTIONAL Shorts adapter | HIGH | HIGH | GPU rec. | UNKNOWN | UNKNOWN/review | MEDIUM Shorts-only | DEFER |
| shorts-generator | Whisper+captions | REFERENCE | MEDIUM | MEDIUM | CPU | UNKNOWN | Review | LOW | DEFER |
| OpenCV | Frame utilities | WORKER util | LOW | LOW | CPU | GOOD | LOW (Apache-2) | LOW | As-needed |
| pyannote | Diarization | VALIDATOR optional | HIGH | MEDIUM | GPU rec. | PARTIAL | MEDIUM (models gated) | MEDIUM | DEFER |
| SAM2 | Object track | FUTURE | HIGH | HIGH | GPU req. | PARTIAL | LOW–MED | UNKNOWN | DEFER |
| Real-ESRGAN | Upscale | OPTIONAL enhance | HIGH | MEDIUM | GPU req. | PARTIAL | LOW–MED | MEDIUM | DEFER |
| Demucs | Stem split | FUTURE audio | HIGH | MEDIUM | GPU rec. | PARTIAL | LOW–MED | LOW now | DEFER |
| Remotion | Motion graphics | OPTIONAL worker | HIGH | HIGH | Node+CPU/GPU | PARTIAL | MEDIUM (Remotion License) | MEDIUM | DEFER |
| OpenMontage | Agent montage suite | REFERENCE only | HIGH | HIGH | GPU preferred | GOOD in OM | **HIGH (AGPL-3)** | HIGH concepts | **REJECT import** |
| MS Agent Framework | Supervisor | Orchestration T4 | HIGH | HIGH | N/A | GOOD | LOW–MED | UNKNOWN | DEFER T4 |
| OpenAI Agents SDK | Handoffs | Orchestration T4 | MEDIUM | MEDIUM | N/A | GOOD | Vendor lock | LOW for AMP | DEFER / avoid as core |
| CrewAI | Role crews | Prototype only | MEDIUM | MEDIUM | N/A | GOOD | LOW–MED | LOW for AMP | REJECT as authority |

---

## 6. Tool-by-Tool Findings

### A. ShortGPT (MIT)

**Useful:** Editing Markup Language / JSON edit blocks; ContentTranslationEngine *ideas*; asset sourcing patterns.  
**Not useful as-is:** MoviePy-centric EditingEngine as AMP render replacement; whole ContentShortEngine pipeline (duplicates TRS/quality/idempotency).  
**Adapter boundary:** Translate AMP SceneIntent + duration contract → optional edit JSON for debugging / LLM-assisted edit suggestions → AMP still renders via FFmpeg.  
**Verdict:** Concept reuse **P2**; do not import renderer.

### B. MoneyPrinterTurbo (MIT)

**Useful:** Material retrieval ↔ script keyword matching; Edge vs Whisper subtitle provider switch; multi-TTS config patterns; WebUI/API separation ideas.  
**Not useful:** Replacing BUILD-04G / prompt_compiler / timeline / FFmpeg / publishability. MoviePy assembly as authority.  
**Adapter boundary:** Optional `material_match` worker feeding montage_brain slot queries; keep AMP ranking.  
**Verdict:** Highest practical **concept** source among “full short factories.”

### C. Auto_Shorts_Generator

Hook extraction, face tracking, 9:16 crop, blur BG — valuable for **Shorts-only** path. High coupling/GPU cost.  
**Verdict:** Optional Shorts adapter later; **not** long-form mandatory.

### D. shorts-generator (benpiper)

Whisper timing + vertical caption styles — overlaps AMP ASR + localization.  
**Verdict:** REFERENCE only; prefer AMP Faster-Whisper path.

### E. Faster-Whisper (MIT) — **already integrated**

`pipeline/observation/speech_timing/observe.py`; `AUDIO_ASR_EVIDENCE*` **PASS** on job2333. Lazy/optional; UNKNOWN ≠ PASS.  
**Gap:** Ensure int8/CPU defaults documented; word-level timestamps for subtitle repair; Windows model cache path.  
**Verdict:** **P0 strengthen** as primary speech evidence.

### F. PySceneDetect (BSD-3) — **already integrated**

`pipeline/observation/scene_boundary/*`. Documentary Ken Burns causes false FAIL; soft issues added. Remains observation ≠ semantic truth.  
**Verdict:** **P0 strengthen** thresholds + soft taxonomy.

### G. VMAF — **adapter present**

`pipeline/observation/perceptual_quality/observe.py`. Proves perceptual similarity vs reference — **not** semantic correctness. Needs reference media + libvmaf in FFmpeg build.  
**Verdict:** **P1** enable in validation marathon when reference exists.

### H. CLIP + FAISS — **partial**

`pipeline/retrieval/*`; optional deps commented in `requirements.txt`. Hash embeddings must never be semantic PASS.  
**Verdict:** **P1** production CLIP backend (CPU open-clip or GPU) behind retrieval bridge; customer-isolated indexes.

### I. OpenTimelineIO (Apache-2.0)

Not implemented. Good for interchange/debug/export of edit decisions. Duration Contract remains authoritative.  
**Verdict:** **P2** optional export adapter after edit JSON exists.

### J. Piper

`pipeline/piper_tts_fallback.py` exists. Offline CPU TTS; model/binary management; Bengali quality **unknown** without real-media proof; license drift (archived MIT vs GPL forks) → **legal review** if bundling.  
**Verdict:** Keep optional; do not claim voice identity.

### K. pyannote

Useful for speaker/voice consistency evidence. HF model gates, GPU, Windows friction.  
**Verdict:** **DEFER** until voice-identity is a product blocker.

### L. OpenCV

Already via `scenedetect[opencv]`. Frame extract/crop utilities OK.  
**Verdict:** Utility only; never quality authority.

### M. SAM2 / N. Real-ESRGAN / O. Demucs

High GPU/runtime; not required for current marathon PASS path.  
**Verdict:** **DEFER**.

### P. Remotion

Present inside OpenMontage tree; Node dependency; Remotion License constraints. May produce motion-graphics intermediates; FFmpeg remains final.  
**Verdict:** **DEFER**; never AGPL+Remotion via OM import path.

### Q. OpenMontage (AGPL-3.0)

Real, sophisticated agent/tool/checkpoint/documentary suite. **AGPL network copyleft risk for SaaS.** Already isolated. Concepts (pre-compose validation, stock adapters, checkpoint honesty) already inspiring AMP montage_brain / observation — **without** importing code.  
**Verdict:** **REJECT in-process integration**; REFERENCE only; any future “external worker” needs **legal review**.

---

## 7. Recommended Independent Validation Stack

```
AMP Production Job
        │
        ▼
 ┌──────────────────────────────────────────────┐
 │ Independent Validation Sidecar (observe-only) │
 │  • Faster-Whisper → speech/timing evidence     │
 │  • PySceneDetect → boundary evidence           │
 │  • VMAF → perceptual evidence (if reference) │
 │  • CLIP/FAISS → retrieval similarity evidence│
 │  • FFprobe/FFmpeg → technical media evidence │
 │  • Optional OpenCV → frame metrics           │
 │  • Optional Gemini → semantic evidence       │
 │  • Optional pyannote → speaker evidence      │
 └──────────────────────────────────────────────┘
        │ normalized EvidencePacket
        │ (confidence, provenance, UNKNOWN≠PASS)
        ▼
 AMP Artifact Verification → BUILD-04F → Publishability
```

External tools **never** write publishability verdicts directly.

---

## 8. Recommended Integration Roadmap

| Stage | Name | Action |
|-------|------|--------|
| **T0** | Audit only | **This document** — no installs, no wiring |
| **T1** | Independent validation | Harden Whisper/SceneDetect/VMAF/CLIP evidence packages; validation marathon |
| **T2** | Specialist adapters | Material-match worker; edit-JSON export; OTIO export; Piper hardening if needed |
| **T3** | Selective replacement | Only if real-media proves AMP worker worse (e.g., specific stock matcher) — still behind AMP authority |
| **T4** | Supervisor/orchestration | At most one agent framework as diagnostic supervisor; AMP engines remain authoritative |

Do not skip stages.

---

## 9. Immediate Integration Candidates (max 5)

### 1) Faster-Whisper evidence hardening — **P0**
- **Why:** Already PROVEN; highest ROI for subtitle/timing truth.  
- **Part:** Word timestamps → localization_consistency repair hints.  
- **Boundary:** Observation → ASR evidence JSON only.  
- **Benefit:** Fewer false subtitle PASS/FAIL.  
- **Effort:** LOW. **Risks:** CPU/RAM on Windows.

### 2) PySceneDetect soft-taxonomy + calibration — **P0**
- **Why:** Documentary false FAIL cascades to audience.  
- **Part:** Soft issue catalog; confidence.  
- **Boundary:** Observation gate only.  
- **Benefit:** Honest PASS with soft labels.  
- **Effort:** LOW. **Risks:** Over-softening.

### 3) Real CLIP + FAISS production backend — **P1**
- **Why:** Stock-first montage quality without Agnes.  
- **Part:** `pipeline/retrieval/embedding.py` real model path.  
- **Boundary:** Retrieval evidence; hash fallback marked non-semantic.  
- **Benefit:** Better stock hits.  
- **Effort:** MEDIUM. **Risks:** Torch size on Windows.

### 4) VMAF in validation marathon — **P1**
- **Why:** Technical perceptual proof between encode variants.  
- **Part:** Existing perceptual observe adapter.  
- **Boundary:** Evidence only when reference exists.  
- **Benefit:** Encode regression detection.  
- **Effort:** LOW–MED. **Risks:** libvmaf not in all FFmpeg builds.

### 5) MoneyPrinter-style material_match adapter (concept) — **P1/T2**
- **Why:** Improves script↔stock alignment with low authority risk.  
- **Part:** Keyword/query builder feeding montage_brain.  
- **Boundary:** Worker returns candidates; AMP ranks/selects.  
- **Benefit:** Fewer off-topic stills.  
- **Effort:** MEDIUM. **Risks:** Accidental MoviePy/deps creep — forbid.

---

## 10. Deferred Candidates

| Candidate | Why wait |
|-----------|----------|
| ShortGPT full EditingEngine | MoviePy authority risk; concept-first |
| OTIO | Needs edit JSON first |
| Piper as primary TTS | BN quality unproven; license drift |
| pyannote | GPU/HF gates; not blocking ship |
| Auto_Shorts_Generator / shorts-generator | Shorts-only; overlap ASR |
| SAM2 / Real-ESRGAN / Demucs | Resource-heavy; no marathon gap proof |
| Remotion | Node + license; OM entanglement |
| Agent frameworks (all) | T4 only; duplicate orchestration risk |

---

## 11. Reject / Do-Not-Integrate Candidates

| Candidate | Why |
|-----------|-----|
| OpenMontage as library | **AGPL-3.0** SaaS copyleft risk; duplicates checkpoint/tool registry |
| MoneyPrinterTurbo / ShortGPT as full pipeline | Duplicate research/quality/render/job authorities |
| CrewAI / any agent as quality or publishability engine | Authority collision |
| Second FFmpeg/MoviePy render authority | Breaks AMP compose contract |
| Second idempotency/queue/config/health engine | Operational fragmentation |
| Hash embeddings as semantic PASS | False certification |

---

## 12. Licensing & Dependency Risk

> Not legal advice — items marked for **legal review**.

| License | Tools | Risk note |
|---------|-------|-----------|
| MIT | Faster-Whisper, ShortGPT, MoneyPrinterTurbo | Generally permissive |
| BSD-3 | PySceneDetect | Permissive |
| Apache-2.0 | OpenTimelineIO, many ML libs | Permissive |
| AGPL-3.0 | OpenMontage | **High** — network copyleft; keep isolated; legal review before any process boundary sharing |
| Remotion License | Remotion | Commercial terms; review before bundling |
| Piper | MIT archived / GPL forks | Confirm exact binary/model license before shipping |
| pyannote models | HF gated + agreements | Compliance process needed |
| Stock APIs | Pexels/etc. | Content license ≠ code license |

---

## 13. Windows Production Risk

| Area | Assessment |
|------|------------|
| FFmpeg portable | GOOD (vendored + bootstrap) |
| Faster-Whisper / CTranslate2 | GOOD–PARTIAL (first model download, RAM) |
| Torch + CLIP | PARTIAL (large wheels, path length) |
| PySceneDetect+OpenCV | GOOD (already in requirements) |
| Node/Remotion | PARTIAL (npx.cmd, AGPL OM path) |
| File locking | GOOD (`msvcrt` path in idempotency) |
| Unicode cp1252 | Watch console logging (OM notes) |

Prefer CPU int8 Whisper and optional CLIP over GPU-mandatory stacks for current AMP Windows SaaS packaging.

---

## 14. Resource Requirements

| Component | CPU | RAM | GPU | Disk | Runtime |
|-----------|-----|-----|-----|------|---------|
| Faster-Whisper small/int8 | Medium | 2–4 GB | Optional | ~1–3 GB models | Seconds–minutes / job |
| PySceneDetect | Low–Med | Low | None | Low | Seconds |
| VMAF | High | Med | Optional | Low | Minutes if full |
| CLIP + FAISS | High | 4–8 GB+ | Recommended | Models + index | Seconds–minutes |
| Piper | Low | Low | None | Voice models | Realtime-ish |
| pyannote/SAM2/ESRGAN/Demucs | High | High | Recommended/Required | Large | Minutes+ |

---

## 15. Proposed Adapter Architecture

```
AMP Adapter (thin)
  inputs: SceneIntent / audio path / video path / queries
  calls: external tool (subprocess or optional import)
  outputs: EvidencePacket {
      tool, version, method,
      status: PASS|FAIL|UNKNOWN,
      confidence,
      provenance (hashes, model id),
      metrics,
      claims_semantic_truth: false
  }
  never: mutate publishability, duration contract, ContinuityTracker, BUILD-03 store
```

Pattern matches existing bridges: `pipeline/retrieval/bridge.py`, observation modules, `*_repair_bridge.py` feeding BUILD-04F.

---

## 16. Independent Validation Marathon Design

**Goal:** Prove six-language **core production** (no YouTube publish).

**Matrix:**

| Axis | Values |
|------|--------|
| Format | long-form, short-form |
| Languages | en, bn, hi, ur, ta, ml |

**Per job capture (mandatory artifacts):**

- research / fact_pack  
- script + approval  
- dialogue + AudioPlan  
- TTS audio + provenance  
- visual assets + route (Agnes/stock/i2v)  
- montage slots / retrieval evidence  
- Whisper ASR evidence  
- PySceneDetect boundary evidence  
- optional VMAF  
- semantic evidence (or honest UNKNOWN)  
- subtitle timing  
- duration reconciliation  
- FFprobe metadata  
- quality gates + repair events  
- LOCALIZED packages  
- publishability decision  

**Publish:** OUT OF SCOPE.

**Pass rule:** Technical + localization + duration PASS; semantic UNKNOWN allowed only if labeled (not silent PASS).

---

## 17. Failure Taxonomy

| Category | Examples from AMP marathon |
|----------|----------------------------|
| generation failure | Agnes UNKNOWN, i2v miss |
| provider failure | Groq 429 payload, Cerebras 402 |
| quota failure | Google 429/403 suspended keys |
| semantic failure | SEMANTIC_COVERAGE FAIL/UNKNOWN |
| timing failure | ASR mismatch, subtitle drift |
| duration failure | contract miss / UNKNOWN duration |
| audio failure | TTS preflight, Edge fallback |
| localization failure | scene_localize_incomplete |
| rendering failure | FFmpeg/render integrity |
| continuity failure | ContinuityTracker block |
| artifact failure | ARTIFACT_GATE |
| configuration failure | missing keys, AMP flags |
| orchestration failure | cert topic dup false-match |
| infrastructure failure | Event loop closed, disk, RAM |

---

## 18. Final Recommendation

**Integrate first (validators):** Faster-Whisper hardening, PySceneDetect calibration, real CLIP/FAISS, VMAF-in-validation.

**Remain AMP-owned:** BUILD-03, BUILD-04F, BUILD-04G, SceneIntent, ContinuityTracker, prompt_compiler, FFmpeg, publishability, duration, localization authority, montage_brain contracts.

**Validators only:** Whisper, SceneDetect, VMAF, CLIP similarity, FFprobe, optional Gemini/pyannote.

**Defer:** Piper primacy, OTIO, Shorts face-crop suites, SAM2/ESRGAN/Demucs, Remotion, all agent frameworks.

**Never duplicate:** Second quality engine, idempotency, continuity, publishability, FFmpeg authority, queue/scheduler/config/health/job engines; **never AGPL-import OpenMontage**.

---

## A. TOP 5 TO INTEGRATE

1. Faster-Whisper evidence depth (word timestamps)  
2. PySceneDetect documentary calibration  
3. Production CLIP + FAISS (non-hash)  
4. VMAF in independent validation marathon  
5. Material-match specialist adapter (MoneyPrinter concepts)

## B. TOP 5 TO KEEP AMP-OWNED

1. BUILD-03 idempotency  
2. BUILD-04F creative quality + repair  
3. FFmpeg compose/remux  
4. Publishability AND-gate  
5. ContinuityTracker + SceneIntent + duration contract  

## C. TOP 5 TO DEFER

1. pyannote  
2. SAM2 / Real-ESRGAN / Demucs  
3. Remotion motion graphics  
4. OTIO (until edit JSON exists)  
5. Agent supervisor frameworks (T4)

## D. TOP 5 TO REJECT / AVOID

1. OpenMontage AGPL in-process import  
2. ShortGPT/MoneyPrinter as full pipeline replacement  
3. MoviePy as render authority  
4. CrewAI/Agents as quality or publishability authority  
5. Hash embeddings certified as semantic PASS  

## E. FIRST REAL IMPLEMENTATION PHASE

**Name:** T1-A — Independent Speech & Boundary Evidence Pack  

**Scope (small, testable):**

1. Assert Faster-Whisper produces segment+word timestamps into existing ASR evidence schema.  
2. Golden tests on job2333 English master audio.  
3. PySceneDetect soft-issue unit tests for Ken Burns / missing_cut.  
4. No new authorities; no new deps beyond already-listed optional packages.  
5. Report: PASS/UNKNOWN rates on one short + one localized BN remux.

**Stop condition:** Evidence pack reproducible on Windows without changing publishability ownership.

---

## Appendix — Evidence anchors

- Marathon PASS_WITH_LIMITATION: `docs/marathon/runs/mr_core_engine_20260910T172555Z_6b20087d/`  
- Salvage PASS: `docs/marathon/runs/LIVE_MARATHON_JOB2332_SALVAGE_PASS.md`  
- Prior OSS audit: `docs/marathon/customer_product/OPEN_SOURCE_INTEGRATION_AUDIT.md`  
- OpenMontage isolation: `third_party/OpenMontage/ISOLATION_NOTICE.md`  
- Deps: `requirements.txt` (faster-whisper, scenedetect[opencv], optional CLIP/FAISS comments)

**End of T0 audit. No production code modified.**
