# Open-Source Integration — Phase 6A Report

**Date:** 2026-09-09  
**Scope:** Observation adapters only — faster-whisper, PySceneDetect, VMAF/libvmaf  
**OpenMontage AGPL code imported:** **No**  
**REAL Marathon:** **Not run** (per phase rules)  
**Production authority replaced:** **No**  
**Duplicate authority created:** **No**

---

## Selected ASR tool and why

| Candidate | Installed in env | Weight | Word timestamps | CPU | Windows |
|-----------|------------------|--------|-----------------|-----|---------|
| **faster-whisper** | **Yes** (1.2.1) | Lighter | Yes (`word_timestamps=True`) | int8 CPU | Proven |
| WhisperX | No | Heavier (align + diarize stack) | Yes | GPU preferred | Not present |

**Selection: faster-whisper**

Reasons (code/env evidence):
1. Already importable on this Windows production machine.
2. CPU fallback via `device=cpu`, `compute_type=int8` — GPU not mandatory.
3. Optional: missing import → `OBSERVATION_UNAVAILABLE` (startup never imports ASR at module load time beyond lazy call).
4. WhisperX deferred; speaker diarization explicitly marked `UNAVAILABLE` (pyannote later).

Planned subtitle timing is **never** treated as actual PASS (`planned_as_actual_pass: false`).

---

## PySceneDetect integration

| Item | Detail |
|------|--------|
| Package | `pipeline/observation/scene_boundary/` |
| Primary tool | `scenedetect` ContentDetector |
| Fallback | FFmpeg `select='gt(scene,0.4)'` when PySceneDetect missing |
| Wired to | `story_visual_direction.attach_scene_boundary_evidence` (evidence only) |
| Does **not** replace | Director Plan, `DirectedVisualBeat` (C05-S), ContinuityTracker |
| Final gate | **Not created** (`creates_final_gate: false`) |

Evidence includes: scenes, boundary times, planned-vs-actual deltas, unexpected cut density, excessive static hold.

---

## VMAF integration

| Item | Detail |
|------|--------|
| Package | `pipeline/observation/perceptual_quality/` |
| Mechanism | Existing FFmpeg binary + `libvmaf` filter (present in bundled ffmpeg-8.1.1) |
| Wired to | `rendering_integrity.observe.observe_rendered_output` → `perceptual_quality` field |
| No reference | status **UNKNOWN** (`vmaf_reference_unavailable`) |
| Does **not** | Create a new render engine; replace compose/FFmpeg authority |

---

## Architecture

```
pipeline/observation/
  common.py
  speech_timing/     → localization_consistency.subtitle_rules.attach_speech_timing_observation
                     → localization_consistency.production.apply_production_localization(audio_path=…)
  scene_boundary/    → story_visual_direction.attach_scene_boundary_evidence
  perceptual_quality/→ rendering_integrity.observe.observe_rendered_output
```

External tools never publish / repair / approve / publishability-PASS / idempotency-claim / continuity-own.

---

## Evidence schemas

| Schema | Key fields |
|--------|------------|
| `amp_observation_speech_timing_v1` | transcript, words[], segments[], speakers[], status, tool |
| `amp_observation_scene_boundary_v1` | scenes[], boundary_times_sec, scene_count |
| `amp_observation_perceptual_quality_v1` | vmaf, metrics, reference_path / UNKNOWN if absent |

Comparison payloads:
- `planned_vs_observed` (speech)
- `planned_vs_observed` (beats vs cuts)

---

## Dependency / Windows impact

| Tool | Required at startup? | Notes |
|------|----------------------|-------|
| faster-whisper | No (lazy) | HF model download on first use (`tiny`); symlink warning on Windows OK |
| scenedetect | No (lazy; FFmpeg fallback) | Installed for this env during Phase 6A tests |
| libvmaf | Via existing ffmpeg | Filter confirmed present |

Startup does not hard-fail if optional packages are absent.

---

## CPU / GPU behavior

| Adapter | Default | GPU |
|---------|---------|-----|
| Speech | CPU int8 | Optional later |
| Scene | CPU (OpenCV / FFmpeg) | N/A |
| VMAF | CPU via ffmpeg | N/A |

---

## Existing authority integration

| Authority | Change |
|-----------|--------|
| Localization / subtitle rules | Evidence attach + optional `audio_path` on `apply_production_localization` |
| Rendering integrity observe | Attach VMAF block; missing ref → UNKNOWN |
| C05-S story_visual_direction | Evidence helper only; snapshot flags `scene_boundary_is_not_continuity_authority` |
| AudioPlan / VoiceIdentity / ContinuityTracker / BUILD-03 / publishability | **Unchanged as authorities** |

---

## Tests

`python -m scripts.test_phase6a_observation -v` → **15/15 OK**

Covers: unit/contract, Windows paths with spaces, unavailable tool, malformed planned cues, UNKNOWN (no VMAF ref), deterministic fixture media via ffmpeg lavfi, authority wiring.

---

## Regressions run

| Suite | Result |
|-------|--------|
| RCP-06A semantic | OK (10) |
| RCP-06B duration | OK (15) |
| RCP-06C continuity | OK (10) |
| RCP-06D voice | OK (12) |
| RCP-07 blocker fix | OK (9) |
| voice_lock | OK |
| BUILD-03 idempotency | OK (14) |
| BUILD-04D render | OK (35, skipped=2) |
| BUILD-04E subtitle | OK (40) — after mock FAILURE retryable wording (DEF-H3-007) |
| C05-S story visual | OK (79) |
| BUILD-00R imports | OK (5) |
| Phase 6A observation | OK (15) |

**BUILD-04E note:** Initial run failed e23/e30 because mock `FAILURE` raised an unlabeled `RuntimeError`, classified UNKNOWN under DEF-H3-007, blocking reclaim. Fix: mock message includes `temporary` → RETRYABLE. H3 production classify_error policy unchanged. Phase 6A adapters were not the cause.

Fixtures/MOCK in unit tests are **not** counted as production certification.

---

## Limitations

1. Speaker diarization not claimed (faster-whisper path).  
2. VMAF without reference stays UNKNOWN — no synthetic reference invented.  
3. Live VMAF identical-file run may return UNAVAILABLE on some filter/path edge cases; unavailable is explicit.  
4. Speech model download depends on HuggingFace hub on first CPU run.  
5. Scene FFmpeg fallback is coarser than PySceneDetect ContentDetector.  
6. No REAL SHORT / Marathon in this phase.  
7. Full C01–C10 / Phase02–10 matrix not exhaustively re-executed (targeted RCP/BUILD/C05-S + Phase6A focused suite).
8. Mock FAILURE wording adjusted for DEF-H3-007 compatibility; production unlabeled→UNKNOWN policy unchanged.

---

## Replacement / duplicate check

| Question | Answer |
|----------|--------|
| Production code replacement of authorities? | **No** |
| Duplicate ContinuityTracker / publishability / FFmpeg engine? | **No** |
| OpenMontage AGPL copy? | **No** |

---

## HARD STOP (Phase 6A)

Integration + regression proof complete. REAL production deferred to a later phase.
