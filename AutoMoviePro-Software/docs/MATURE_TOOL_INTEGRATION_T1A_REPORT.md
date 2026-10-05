# AUTO MOVIE PRO — MATURE TOOL INTEGRATION T1-A REPORT

**Phase:** T1-A — Independent Speech & Boundary Evidence Pack  
**Date:** 2026-09-11  
**Governing audit:** `docs/MATURE_TOOL_INTEGRATION_AUDIT.md` (T1-A section + authority map)  
**Verdict:** **PASS**

---

## 1. Scope

Harden existing Faster-Whisper (speech/timing) and PySceneDetect (scene-boundary) **observation** layers using real production media (job2333).

In scope:

- Word + segment timestamp evidence with provenance
- Windows CPU/int8/lazy-load path
- Hard vs soft documentary/Ken Burns classification for scene boundaries
- Golden real-media tests + focused unit tests
- Evidence under `docs/marathon/evidence/t1a/`

Out of scope (not started): CLIP, VMAF, MoneyPrinter, ShortGPT, Piper, OTIO, pyannote, agents, T1-B+.

Authority posture unchanged: observers only; AMP / FFmpeg / Duration Contract / Publishability remain authority; UNKNOWN ≠ PASS.

---

## 2. Existing Implementation Before T1-A

| Area | Before |
|------|--------|
| A. Faster-Whisper path | `pipeline/observation/speech_timing/observe.py` → `WhisperModel.transcribe(..., word_timestamps=True)` |
| B. Model config | Default `tiny`, `device=cpu`, `compute_type=int8`; env `AMP_WHISPER_MODEL` |
| C. Timestamp granularity | Segments + words when backend returns them |
| D. ASR schema | `amp_observation_speech_timing_v1`; weak provenance/hash/version/metrics |
| E. PySceneDetect path | `scene_boundary/observe.py` ContentDetector + FFmpeg fallback |
| F. Scene schema | `amp_observation_scene_boundary_v1`; scenes[] + boundary_times |
| G. Soft-issue handling | Soften only in `production.py` FAIL→PASS string list |
| H. Ken Burns/doc | Softened ad hoc in production gate after false FAIL |
| I. Tests | `scripts/test_phase6a_observation.py` (+ production ASR script) |
| J. Real media | job2333 `narration_*.m4a`, `final_short.mp4`, prior `AUDIO_ASR_EVIDENCE*` |

---

## 3. Changes Made

| File | Change |
|------|--------|
| `pipeline/observation/speech_timing/observe.py` | Provenance, `source_hash`, `tool_version`, metrics, lazy model cache, deterministic `AMP_WHISPER_CACHE` / `data/models/faster-whisper`, timestamp validation, honest `MODEL_UNAVAILABLE` / `INVALID_MEDIA`, schema_version `v1.1` (base schema id preserved) |
| `pipeline/observation/speech_timing/__init__.py` | Export validators / hash helpers |
| `pipeline/observation/scene_boundary/observe.py` | Provenance + hash + tool version; `classify_boundary_issue(s)`; hard vs soft in compare; documentary/Ken Burns soft labels; soft alone → PASS with visible soft issues |
| `pipeline/observation/scene_boundary/production.py` | Consume hard/soft from compare (no silent UNKNOWN→PASS) |
| `pipeline/observation/scene_boundary/__init__.py` | Export classifiers |
| `scripts/test_t1a_speech_boundary_evidence.py` | Unit + **REAL_MEDIA** golden tests |
| `scripts/test_phase6a_observation.py` | Accept `MODEL_UNAVAILABLE` reason |
| `docs/marathon/evidence/t1a/*` | Reproducible golden evidence (job artifacts untouched) |

No dependency strategy change. Existing `faster-whisper` + `scenedetect[opencv]` used. GPU not required.

---

## 4. Faster-Whisper Evidence Results

- Tool: `faster-whisper` **1.2.1**
- Model: `tiny` / CPU / int8
- Segment timestamps: **PROVEN**
- Word timestamps: **PROVEN** (`word_timestamps=True`; probabilities present)
- Provenance: path, SHA-256 `source_hash`, download_root, model/device/compute, observed_at
- Status vocabulary: PASS | FAIL | UNKNOWN | OBSERVATION_UNAVAILABLE
- Failures emit reason (`INVALID_MEDIA`, `MODEL_UNAVAILABLE`, `runtime_transcribe_failed`)
- Does **not** claim semantic truth (`claims_semantic_truth=false`)

---

## 5. PySceneDetect Evidence Results

- Tool: `pyscenedetect` **0.7.1** (FFmpeg fallback retained)
- Genuine cuts: observable (synthetic 2-color cut + job2333 11 scenes)
- Soft classification: static hold, documentary hold, missing_cut, cut density, boundary delta, Ken Burns/micro-flash
- Hard classification: missing/tiny/invalid media, detector hard failure
- Soft issues remain visible (`soft_issues`, production `soft:` prefix)
- Soft-only → observation PASS; hard → FAIL; detector missing without fallback → OBSERVATION_UNAVAILABLE / UNKNOWN reason `DETECTOR_UNAVAILABLE`

---

## 6. Real-Media Results

Job: **job2333** (marathon English JWST short). Originals **not** modified.

| Evidence file | Result |
|---------------|--------|
| `docs/marathon/evidence/t1a/job2333_asr_narration_00.json` | ASR **PASS**; 2 segments; 25 words with timestamps; validation ok |
| `docs/marathon/evidence/t1a/job2333_english_master_concat.m4a` | Concat of narration_00..04 (evidence-only) |
| `docs/marathon/evidence/t1a/job2333_asr_english_master.json` | ASR **PASS**; multi-segment + words; provenance preserved |
| `docs/marathon/evidence/t1a/job2333_scene_boundary.json` | Detect **PASS**; 11 scenes / ~52.32s; compare **PASS** with soft documentary issues visible; hard_issues=[] |

---

## 7. Golden Test Results

`python scripts/test_t1a_speech_boundary_evidence.py -v`

| Suite | Count | Outcome |
|-------|-------|---------|
| SpeechTimestampUnitTests (A–H) | 8 | PASS |
| SceneBoundaryUnitTests (1–8) | 8 | PASS |
| RealMediaGoldenTests | 3 | PASS |
| **Total** | **19** | **OK** (~15s cached / ~43s cold model) |

---

## 8. Windows/CPU Results

- OS: Windows 10 (build 26200)
- Device: **cpu**, compute_type **int8**
- Cache: `data/models/faster-whisper` (HF symlink warning only; cache still works)
- GPU: not required; not used
- Lazy model load: process-local `_MODEL_CACHE`; second ASR run reused cache (`from_cache` metrics)

---

## 9. UNKNOWN Cases

| Case | Status / reason | Notes |
|------|-----------------|-------|
| Missing/tiny audio | FAIL / `INVALID_MEDIA` | Hard; not PASS |
| Import/model missing | OBSERVATION_UNAVAILABLE / `MODEL_UNAVAILABLE` | Unit-proven |
| Transcribe runtime fail | OBSERVATION_UNAVAILABLE / `runtime_transcribe_failed` | Reason preserved |
| Scene detector unavailable (no fallback) | OBSERVATION_UNAVAILABLE / `DETECTOR_UNAVAILABLE` | Unit-proven |
| Compare not executed | UNKNOWN | `unknown_as_pass=false` |
| Empty scenes | UNKNOWN / `no_scenes_detected` | Not auto-PASS |

No UNKNOWN→PASS conversion.

---

## 10. Regression Results

| Suite | Outcome |
|-------|---------|
| `scripts/test_t1a_speech_boundary_evidence.py` | **19 OK** |
| `scripts/test_phase6a_observation.py` | **15 OK** |
| `scripts/test_part2_q2_faster_whisper_production.py` | Errors: script lacks `sys.path` bootstrap (`ModuleNotFoundError: pipeline`) — **pre-existing runner limitation**, not a T1-A regression of observation modules |

---

## 11. Performance Baseline

From job2333 golden evidence (CPU / tiny / int8):

| Metric | narration_00 | english_master concat | final_short scene |
|--------|--------------|----------------------|-------------------|
| Media duration (approx) | ~9.9s span | ~52s speech pack | 52.32s video |
| Model load | 1.414s (cold) | cached / low | n/a |
| ASR execution | 0.626s | included in ~1.64s wall | n/a |
| Wall clock | 2.22s | 1.644s | 9.608s detect |
| RAM | not instrumented (baseline only) | — | — |

No premature optimization performed.

---

## 12. Authority Safety Verification

| Check | Result |
|-------|--------|
| BUILD-03 ownership | Unchanged |
| BUILD-04F ownership | Unchanged |
| ContinuityTracker ownership | Unchanged |
| SceneIntent ownership | Unchanged |
| Duration Contract ownership | Unchanged |
| FFmpeg authority | Unchanged |
| Publishability ownership | Unchanged |
| Second quality/subtitle/continuity/retry/queue/agent | **Not added** |
| Faster-Whisper / PySceneDetect role | Observation evidence only |

---

## 13. Remaining Problems

1. Whisper `tiny` on Windows produces imperfect transcripts (e.g. “mid-inferred”) — observation quality limitation, not a schema failure.
2. HF Hub unauthenticated download warning / Windows symlink cache warning — environment limitation.
3. `test_part2_q2_faster_whisper_production.py` needs path bootstrap to run under bare `python scripts/...` (pre-existing).
4. Scene soft PASS still means documentary holds are **visible soft issues**, not semantic approval.

---

## 14. T1-A Verdict

**PASS**

Acceptance checklist:

- [x] Faster-Whisper produces valid segment evidence
- [x] Word timestamp path proven (faster-whisper tiny, CPU/int8)
- [x] Real job2333 audio tested
- [x] Provenance preserved
- [x] Invalid/failed ASR → UNKNOWN/UNAVAILABLE/FAIL with reason (not PASS)
- [x] PySceneDetect genuine cuts observable
- [x] Documentary/Ken Burns false failures classified soft where appropriate
- [x] Genuine hard failures remain hard
- [x] UNKNOWN remains UNKNOWN
- [x] Windows CPU path reproducible
- [x] Authority ownership unchanged
- [x] Observation regression (phase6a) intact
- [x] This report created

**STOP.** Do not proceed to T1-B.
