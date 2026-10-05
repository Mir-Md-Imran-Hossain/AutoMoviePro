# BUILD04E_FINAL_REPORT

## BUILD ID
BUILD-04E — Subtitle Runtime Integration

## BASELINE
BUILD-00R through BUILD-04D: PASS

## TIMING MODEL
`audio_relative` — cues span 0..audio_duration_sec

## IDENTITY STRATEGY
Job → Scene → Dialogue → Segment → Language + audio_fingerprint in SubtitleRequestSpec

## FINGERPRINT STRATEGY
BUILD-03 `compute_fingerprint(stage=subtitle)` over normalized semantic inputs

## IDEMPOTENCY STRATEGY
IdempotentExecutor + GenerationCache; invalid SUCCEEDED records rejected

## VALIDATION STRATEGY
Timestamp, overlap, binding, meta sidecar, scene margin, audio duration ceiling

## AUDIO ALIGNMENT STRATEGY
`audio_duration_sec` and `audio_fingerprint` in request; ffprobe on production paths

## LOCALIZATION STRATEGY
Per-language fingerprints; no cross-language reuse

## RECOVERY STRATEGY
Segment-level repair; UNKNOWN reconcile before retry; bounded attempts

## RENDER DEPENDENCY STRATEGY
`subtitle_hash` / `subtitle_asset_hash` in RenderAssemblyManifest

## TEST RESULTS
BUILD-04E: **40/40 PASS**

## REGRESSION
| Build | Status |
|-------|--------|
| BUILD-00R | PASS |
| BUILD-01 | PASS |
| BUILD-02 | PASS |
| BUILD-03 | PASS |
| BUILD-04A | PASS |
| BUILD-04B | PASS |
| BUILD-04B-H | PASS |
| BUILD-04C | PASS |
| BUILD-04D | PASS (33/35, 2 skipped) |
| BUILD-04E | PASS (40/40) |

## FILES ADDED
- pipeline/idempotency/subtitle_*.py (request, runtime, bridge, engine, validation, provenance, mock)
- scripts/test_build04e_subtitle_runtime.py
- docs/build04e/*

## FILES MODIFIED
- pipeline/localization.py — bridge routing + identity params
- pipeline/scene_builder.py — _mux_scene identity
- pipeline/video_pipeline.py — audio-based master SRT
- pipeline/idempotency/render_bridge.py — subtitle_path param
- pipeline/idempotency/result_validation.py — SRT min_bytes

## P0: 0 | P1: 0 | P2: 0 | UNRESOLVED: 0

## DEFERRED
- WhisperX alignment adapter (optional, existing stub)
- Cinematic subtitle styling (BUILD-04F+)

## NEXT BUILD
BUILD-04F
