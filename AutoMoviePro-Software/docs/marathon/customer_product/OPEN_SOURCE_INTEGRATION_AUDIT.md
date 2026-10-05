# Open-Source Production Stack Integration — AUDIT

**Date:** 2026-09-09  
**Scope:** Phases 1–5 (import + authority audit + capability matrices + build-vs-adopt)  
**Production code changed:** **none** (OpenMontage not wired into `pipeline/` / `app/`)  
**OpenMontage location:** `third_party/OpenMontage/` (isolated; see `ISOLATION_NOTICE.md`)  
**Upstream:** https://github.com/calesthio/OpenMontage  

---

## Executive verdict (audit only)

| Question | Answer |
|----------|--------|
| Is OpenMontage real code (not README vapor)? | **Yes** — substantial Python tools + Remotion TS + Backlot FastAPI + pytest |
| Can we vendor it into SaaS production as a library? | **Not by default** — **AGPL-3.0**; copyleft risk for network SaaS |
| Should we replace ContinuityTracker / BUILD-03 / FFmpeg / publishability? | **No** — KEEP_OURS (evidence below) |
| Highest-value next steps (post-audit)? | WRAP/ADAPT **observation** tools (WhisperX timing, PySceneDetect, VMAF, CLIP retrieval) behind AMP gates — not new authorities |
| Implementation (Phases 6–12)? | **DEFERRED** until this audit is accepted; no production wiring in this phase |

---

## PHASE 1 — OpenMontage import status

| Item | Evidence |
|------|----------|
| Cloned | `third_party/OpenMontage/` (~1984 files under tree) |
| Depth | `git clone --depth 1` |
| License file | `third_party/OpenMontage/LICENSE` → **GNU AGPL v3** |
| Production import | **None** — no `from tools.` / `from lib.` in AMP `pipeline/` or `app/` |
| Isolation notice | `third_party/OpenMontage/ISOLATION_NOTICE.md` |

### OpenMontage tree (verified on disk)

| Area | Path | What code actually does |
|------|------|-------------------------|
| Tool registry | `tools/tool_registry.py` | Discovers `BaseTool` subclasses; provider menu; Windows cp1252 scrubbing |
| Tool base | `tools/base_tool.py` | Subprocess contract, stability tiers (`EXPERIMENTAL`/`BETA`) |
| Analysis | `tools/analysis/` | `SceneDetect` (PySceneDetect+FFmpeg), `Transcriber` (faster-whisper/WhisperX), video analyzer, probes |
| Video / retrieval | `tools/video/` | Stock adapters (NASA/Archive/Pexels/…), `corpus_builder`, `clip_search`, compose/stitch, Remotion burn |
| Audio | `tools/audio/` | Mixer, `tts_selector`, provider TTS wrappers |
| Subtitle | `tools/subtitle/` | Cue generation / burn helpers |
| Lib core | `lib/checkpoint.py`, `pipeline_loader.py`, `scoring.py`, `corpus.py`, `slideshow_risk.py`, `delivery_promise.py`, `variation_checker.py` | Checkpoint governance, provider scoring, retrieval corpus, pre-compose risk |
| Pipelines | `pipeline_defs/*.yaml` (13) | Stage graphs incl. `documentary-montage.yaml`, `localization-dub.yaml` |
| Schemas | `schemas/` | JSON Schema for reviews, edit decisions, checkpoints |
| Remotion | `remotion-composer/` | Node/TS compositions (`Root.tsx`, Explainer, TalkingHead, captions) |
| Backlot | `backlot/server.py` | FastAPI live board / human gates |
| Skills | `skills/` | Agent markdown playbooks (not executable engines) |
| Tests | `tests/` | pytest coverage for tools, contracts, backlot, QA |

**Windows notes (from code):** `npx.cmd`, PATH resolution, hardlink→copy fallback, Unicode scrub for cp1252, `NUL` sinks — OpenMontage already considers Windows.

---

## PHASE 2 — AutoMovie Pro authority map (source-backed)

| Authority | Primary paths | Owns | Duplicate risk |
|-----------|---------------|------|----------------|
| BUILD-03 idempotency | `pipeline/idempotency/{executor,store,checkpoint_store,fs_lock,tts_bridge}.py` | Claim/reuse/validate/persist | Do **not** replace with OM checkpoint |
| BUILD-04F repair | `pipeline/quality/{orchestrator,repair_planner,repair_runtime}.py` + `*_repair_bridge.py` | Plan/execute repair scopes | Bridges must remain into this core |
| BUILD-04G topic/dup | `pipeline/intelligence/{duplicate,gate,orchestrator}.py`, `app/customer_trs_workflow.py` | Topic duplicate gates | Keep |
| SceneIntent | `domain/scene_intent.py`, `pipeline/visual_semantic/scene_intent.py` | Intent contract + fingerprint | Keep |
| C05-S visual beats | `pipeline/story_visual_direction.py` (`DirectedVisualBeat`) | Dialogue→visual beat decomposition | No symbol named `DialogueVisualBeat` |
| ContinuityTracker | `pipeline/visual_semantic/continuity.py`, `continuity_runtime.py` | Continuity validate/block | Keep; OM has no equivalent product continuity engine |
| AudioPlan / VoiceIdentity | `domain/scene.py`, `pipeline/audio_design/plan_builder.py`, `pipeline/production_consistency.py` | Audio contract + voice lock | Keep |
| LocalizationContract | `pipeline/localization_consistency/contract.py` | Locale contract | Keep |
| Localization runtime | `pipeline/localization.py` | Translate/TTS/SRT/remux | Keep FFmpeg remux authority |
| Artifact verification | `pipeline/artifact_verification/` | Visual/audio/subtitle/composite verify | Keep |
| Multimodal consistency | `pipeline/multimodal_consistency/` | Cross-modal gate | Keep |
| Rendering integrity | `pipeline/rendering_integrity/` | Preflight/post-render gate | Keep |
| FFmpeg | `pipeline/compose.py`, `ffmpeg_exec.py`, `rendering_integrity/ffmpeg_boundary.py` | Resolve/run/probe | Keep; do not adopt MoviePy/Remotion as render authority |
| Publishability | `pipeline/quality/publishability.py` | Final ship gate (UNKNOWN≠PASS) | Keep |
| Semantic coverage | `pipeline/semantic_coverage.py` | Observe + job gate | Keep as **final semantic authority** |
| Duration | `pipeline/duration_budget.py` | Short/Long contracts | Keep |
| Provider routers | `llm_router.py`, `api_keys.py`, `purpose_caps.py`, `google_api_gate.py`, `tts_*`, `provider_error_class.py` | Routing, circuit, TTS failover | Preserve RCP-07 TTS logic |
| Customer plan / gen | `app/customer_production_plan.py`, `customer_generation_orchestrator.py` | Plan + admit + start gen | Keep |
| Job state / scheduler | `app/customer_job.py`, `scheduler_service.py`, `customer_job_automation.py` | State + queue | Keep |
| Observability | `pipeline/live_activity.py`, `app/customer_marathon_observability.py` | Stream + ledger | Keep |

Anti-duplication: multiple `detect_duplicate_engines` guards in customer modules — any OpenMontage wiring must not create a second continuity/publishability/generate path.

---

## PHASE 3 — OpenMontage capability matrix

Decision vocabulary: **REPLACE | ADAPT | WRAP | KEEP_OURS | REJECT | DEFER**

### OM-01 Tool registry / BaseTool
| Field | Value |
|-------|--------|
| Path | `tools/tool_registry.py`, `tools/base_tool.py` |
| Purpose | Discover/ rank tools; stability envelopes |
| Deps | Python stdlib + tool packages |
| License | AGPL-3.0 |
| Windows | Explicit cp1252 / npx.cmd handling |
| GPU | N/A |
| AMP equivalent | `purpose_caps`, `llm_router`, `google_api_gate`, channel readiness |
| Quality | Mature for agent CLIs; different product shape than AMP SaaS |
| Authority conflict | Would fork provider routing |
| Risk | High (AGPL + architecture mismatch) |
| **Decision** | **REJECT** as in-process registry; **DEFER** concept study only |

### OM-02 Checkpoint / pipeline loader
| Field | Value |
|-------|--------|
| Path | `lib/checkpoint.py`, `lib/pipeline_loader.py`, `pipeline_defs/*.yaml` |
| Purpose | Stage gates, approvals, YAML pipelines |
| AMP equivalent | BUILD-03 idempotency + customer job automation |
| Conflict | Second checkpoint authority |
| **Decision** | **KEEP_OURS** (BUILD-03); **REJECT** OM checkpoint as authority |

### OM-03 Documentary / real-footage retrieval
| Field | Value |
|-------|--------|
| Path | `pipeline_defs/documentary-montage.yaml`, `tools/video/stock_sources/*`, `direct_clip_search.py`, `corpus_builder.py`, `clip_search.py`, `lib/corpus.py` |
| Purpose | Multi-source stock/archival retrieve + CLIP corpus rank |
| Deps | requests, torch/transformers (CLIP), ffmpeg, filelock |
| GPU | Preferred for CLIP; CPU possible (slow) |
| AMP equivalent | Pexels/Pollinations keys + Agnes generative path — **weak** real-footage montage |
| Quality | Stronger retrieval breadth than AMP today |
| Conflict | Must not bypass SceneIntent / semantic_coverage |
| Risk | AGPL if vendored; API key/ToS per stock source |
| **Decision** | **WRAP** (preferred: reimplement adapters under AMP license **or** out-of-process AGPL worker) — **ADAPT** concepts; **not REPLACE** semantic authority |

### OM-04 Provider scoring
| Field | Value |
|-------|--------|
| Path | `lib/scoring.py` (`ProviderScore`, weighted explain) |
| Purpose | Multi-factor provider choice |
| AMP equivalent | `purpose_caps`, sticky keys, TTS diagnostics, readiness |
| **Decision** | **ADAPT** scoring ideas into AMP routers; **REJECT** AGPL module import |

### OM-05 Slideshow / variation / delivery promise
| Field | Value |
|-------|--------|
| Path | `lib/slideshow_risk.py`, `variation_checker.py`, `delivery_promise.py` |
| Purpose | Pre-compose risk of static slideshow; variation checks |
| AMP equivalent | Partial via AV critic / semantic / creative gates |
| **Decision** | **ADAPT** as **observation inputs** to existing gates (WRAP metrics); **KEEP_OURS** final gate |

### OM-06 SceneDetect (PySceneDetect wrapper)
| Field | Value |
|-------|--------|
| Path | `tools/analysis/scene_detect.py` |
| Purpose | Cut/scene boundaries |
| Deps | `scenedetect[opencv]` + FFmpeg fallback |
| AMP equivalent | No dedicated scene-boundary observer |
| **Decision** | **WRAP** PySceneDetect directly under AMP (Apache/BSD-friendly tool), inspired by OM wrapper — **not** vendor OM file |

### OM-07 Transcriber (WhisperX / faster-whisper)
| Field | Value |
|-------|--------|
| Path | `tools/analysis/transcriber.py` |
| Purpose | Word-level timing / diarization hooks |
| AMP equivalent | Subtitle timing largely TTS-derived SRT (`localization.write_srt`) — weak ASR observation |
| **Decision** | **WRAP** WhisperX/faster-whisper as observation backend for subtitle/timing gates |

### OM-08 Reference video analysis
| Field | Value |
|-------|--------|
| Path | `tools/analysis/video_analyzer.py`, `video_understand.py`, downloader/transcript tools |
| Purpose | Reference intelligence |
| AMP equivalent | Partial critic / semantic paths |
| **Decision** | **DEFER** (heavy yt-dlp/GPU; product niche) |

### OM-09 Remotion composer
| Field | Value |
|-------|--------|
| Path | `remotion-composer/` |
| Purpose | Programmatic motion graphics / caption burn |
| Deps | Node, Remotion |
| AMP equivalent | FFmpeg subtitle burn + Agnes video |
| Conflict | Must not replace FFmpeg render authority |
| **Decision** | **WRAP** optional motion-graphics adapter only; **KEEP_OURS** FFmpeg |

### OM-10 HyperFrames / multi-runtime compose
| Field | Value |
|-------|--------|
| Path | `tools/video/video_compose.py`, `hyperframes_compose.py` |
| Purpose | Remotion|HyperFrames|FFmpeg locked routing |
| **Decision** | **REJECT** as AMP compose authority; study blockers only |

### OM-11 Localization-dub pipeline YAML
| Field | Value |
|-------|--------|
| Path | `pipeline_defs/localization-dub.yaml` |
| AMP equivalent | `pipeline/localization.py` + LocalizationContract |
| **Decision** | **KEEP_OURS**; **REJECT** OM pipeline as authority |

### OM-12 TTS selector / Piper / multi-TTS
| Field | Value |
|-------|--------|
| Path | `tools/audio/tts_selector.py`, provider TTS tools |
| AMP equivalent | `tts_google` + Edge fallback + RCP-07 failover |
| **Decision** | **KEEP_OURS** Google routing; **WRAP** Piper as **additional** offline fallback behind existing Edge/Google policy |

### OM-13 Backlot UI
| Field | Value |
|-------|--------|
| Path | `backlot/` |
| Purpose | Human approval board |
| AMP equivalent | Customer TRS / approval UX |
| **Decision** | **REJECT** (product UX already owned) |

### OM-14 Reviewer skills + final_review schema
| Field | Value |
|-------|--------|
| Path | `skills/meta/reviewer.md`, `schemas/artifacts/*review*` |
| AMP equivalent | publishability + artifact + semantic + AV critic |
| **Decision** | **ADAPT** schema ideas as evidence structs; **KEEP_OURS** gates |

### OM-15 Avatar / talking-head / many gen-video providers
| Field | Value |
|-------|--------|
| Path | `tools/video/*_video.py`, `tools/avatar/` |
| **Decision** | **DEFER** / **REJECT** for core AMP path (provider sprawl; Agnes remains video authority) |

---

## PHASE 4 — External open-source tools matrix

| ID | Tool | Typical license* | Purpose | AMP equivalent | Win/GPU | Decision |
|----|------|------------------|---------|----------------|---------|----------|
| EXT-01 | OpenTimelineIO | Apache-2.0 | Timeline interchange | Director plan / scene list (not OTIO) | Win OK / no GPU | **WRAP** export/import adapter later |
| EXT-02 | PySceneDetect | BSD-3 | Scene/cut detect | None dedicated | Win OK / CPU | **WRAP** as boundary observer |
| EXT-03 | WhisperX | BSD-ish + model terms | Word timing / align | TTS-timed SRT | Win+GPU preferred | **WRAP** observation |
| EXT-04 | pyannote.audio | MIT + model ToS | Speaker diarization | VoiceIdentity is lock not diarization | GPU heavy | **WRAP** observation only |
| EXT-05 | CLIP (OpenAI/openclip) | MIT | Visual-text embed | Semantic via Gemini critic | GPU preferred | **WRAP** retrieval/index |
| EXT-06 | FAISS | MIT | Vector search | None | CPU/GPU | **WRAP** with CLIP |
| EXT-07 | SAM 2 | Apache-2.0 | Segment/track | ContinuityTracker (symbolic) | GPU | **DEFER** then WRAP continuity **evidence** |
| EXT-08 | OpenCV | Apache-2.0 | CV primitives | Minimal direct use | Win OK | **WRAP** utilities (non-authority) |
| EXT-09 | VMAF (libvmaf) | BSD-2-Clause-like | Perceptual quality | Rendering integrity (technical) | CPU | **WRAP** into rendering_integrity observation |
| EXT-10 | Real-ESRGAN | BSD-3 | Upscale/restore | FFmpeg scale | GPU | **DEFER** targeted enhance |
| EXT-11 | Demucs | MIT | Stem separation | AudioPlan mix (no stems) | GPU | **DEFER** |
| EXT-12 | Piper TTS | GPL/MIT historically — verify pin | Offline TTS | Edge-TTS fallback | CPU | **WRAP** behind TTS fallback chain |
| EXT-13 | Remotion | Remotion license (commercial terms for some uses) | Motion graphics | FFmpeg burn | Node | **WRAP** optional; not render authority |
| EXT-14 | MoviePy | MIT | Editing DSL | compose/ffmpeg | Win OK | **REJECT** as authority; optional util only |
| EXT-15 | faster-whisper | MIT | ASR | None | CPU/GPU | **WRAP** (lighter WhisperX peer) |
| EXT-16 | Silero VAD | MIT | Speech activity | None | CPU | **DEFER**/WRAP for audio gates |

\*Confirm exact SPDX at install pin time; model weights often have separate terms.

---

## PHASE 5 — Build vs buy/adopt (AMP components)

| AMP area | Keep ours because… | Adopt external because… |
|----------|---------------------|-------------------------|
| Idempotency BUILD-03 | Job-scoped claim/reuse proven in SaaS | OM checkpoint is AGPL + different model |
| ContinuityTracker | Product continuity rules + hard-block RCP-06C | SAM2/CLIP only add **evidence**, not policy |
| Semantic coverage | Fail-closed UNKNOWN≠PASS; Gemini video observe | CLIP helps retrieval, not final PASS |
| Publishability | Mandatory gate chain | No OSS replacement |
| FFmpeg compose | Existing Windows authority | MoviePy/Remotion must not become second compose engines |
| Localization + BN remux | Canonical SCENE_LOCAL path (RCP-07 fixed) | WhisperX improves **timing observation** of spoken audio |
| TTS Google routing | RCP-07 multi-key 429/403/503 | Piper/Edge as fallbacks only |
| Topic duplicate BUILD-04G | Product gate | FAISS/CLIP could strengthen similarity later |
| Agnes video gen | Paid product path | Stock retrieval complements, doesn’t replace |
| Subtitle write_srt | Deterministic from narration | WhisperX for **observed** timing vs planned |
| AV critic / repair | BUILD-04F bridges | VMAF/slideshow_risk as extra signals |
| Customer orchestrator | Isolation + entitlements | None |

### Special hunt list (user-requested)

| Capability | AMP today | External | Recommendation |
|------------|-----------|----------|----------------|
| Duplicate scene detection | BUILD-04G text/topic; clip hash heuristics | CLIP+FAISS | WRAP index later |
| Asset retrieval | Pexels/Pollinations | OM stock adapters / CLIP corpus | WRAP adapters (relicense-safe rewrite) |
| Visual semantic search | Gemini critic | CLIP+FAISS | WRAP |
| Timeline representation | director_plan JSON | OpenTimelineIO | WRAP export |
| Scene boundary | Implicit by dialogue beats | PySceneDetect | WRAP observer |
| Word-level subtitle | TTS duration heuristics | WhisperX | WRAP observer |
| Speaker observation | VoiceIdentity lock | pyannote | WRAP (not replace VoiceIdentity) |
| Video quality | rendering_integrity + ffprobe | VMAF | WRAP |
| Restoration | Limited | Real-ESRGAN | DEFER |
| Audio separation | Limited | Demucs | DEFER |
| Real footage | Weak | OM documentary retrieval | WRAP/ADAPT |
| Provider scoring | purpose_caps / readiness | OM `scoring.py` concepts | ADAPT |
| Reference analysis | Partial | OM video_analyzer | DEFER |
| Montage editing | Scene concat | OM documentary pipeline | ADAPT concepts only |
| Motion graphics | FFmpeg | Remotion | WRAP optional |
| Post-render inspection | artifact + publishability | OM final_review | ADAPT fields |

---

## Proposed post-audit priority (may change with evidence)

Aligned with user P1–P14, **reordered by AGPL/risk**:

| Priority | Item | Audit-backed decision |
|----------|------|------------------------|
| P1 | WhisperX / faster-whisper timing observation | WRAP |
| P2 | PySceneDetect boundary observation | WRAP |
| P3 | VMAF into rendering_integrity | WRAP |
| P4 | CLIP+FAISS retrieval index (AMP-owned code) | WRAP |
| P5 | Stock/real-footage adapters (AMP rewrite; OM as reference) | ADAPT/WRAP |
| P6 | Piper behind TTS fallback (preserve Google failover) | WRAP |
| P7 | OpenTimelineIO export | WRAP |
| P8 | Slideshow-risk / variation metrics as gate **inputs** | ADAPT |
| P9 | Provider scoring dimensions into routers | ADAPT |
| P10 | pyannote speaker observation | WRAP |
| P11 | Remotion optional motion adapter | WRAP |
| P12 | Real-ESRGAN | DEFER |
| P13 | Demucs | DEFER |
| P14 | SAM 2 continuity evidence | DEFER |
| — | In-process OpenMontage AGPL import | **REJECT** until legal WRAP-as-service |

---

## Legal / dependency risks

1. **AGPL-3.0 OpenMontage:** linking or shipping OM code inside the SaaS process likely triggers AGPL obligations. Default: **no in-process import**; optional separate AGPL worker with clear network boundary + counsel review.  
2. **Remotion:** separate commercial/license considerations for some deployments.  
3. **Model ToS:** WhisperX/pyannote/CLIP weights ≠ repo license.  
4. **Torch stack:** heavy Windows install; keep optional extras, CPU fallbacks required for WRAP tools.

---

## What this phase did **not** do

- No production `import` of OpenMontage  
- No authority replacement  
- No gate weaken  
- No REAL SHORT re-cert for OSS stack  
- No `OPEN_SOURCE_INTEGRATION_FINAL_REPORT.md` (that belongs after Phases 6–12)

---

## Next gate (Phase 6+)

Only after product accepts this audit:

1. Implement WRAP adapters under `pipeline/observation/` (or similar) that emit evidence JSON.  
2. Feed evidence into **existing** semantic / rendering / subtitle / publishability contracts.  
3. Focused tests + RCP-06/07 regressions per tool.  
4. Isolated comparison tests before any REPLACE (none recommended now).  
5. REAL SHORT with `deterministic_fixtures=false` only after green regressions.

---

## HARD STOP (audit phase)

**Audit complete. Implementation not started.**  
Report path: `docs/marathon/customer_product/OPEN_SOURCE_INTEGRATION_AUDIT.md`
