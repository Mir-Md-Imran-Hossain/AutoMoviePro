# PRE_BUILD04E_ARCHITECTURE

## Baseline
BUILD-00R through BUILD-04D PASS. BUILD-03 idempotency executor is canonical for all generation stages.

## Existing Subtitle Engine (preserved)
| Component | Path | Role |
|-----------|------|------|
| Proportional alignment | `pipeline/subtitle_align.py` | `proportional_cues`, `cues_to_srt`, `validate_cues` |
| SRT writer (legacy) | `pipeline/localization.py` | `write_srt()` — word-chunk proportional timing |
| Scene mux SRT | `pipeline/scene_builder.py` | `_mux_scene` sidecar `.srt` |
| Localization | `pipeline/localization.py` | per-scene/per-lang SRT + burn-in |
| Master SRT | `pipeline/video_pipeline.py` | `english_master.srt` sidecar |
| Contract wiring | `pipeline/contract_wiring/stages.py` | `wire_subtitle_plan` |
| Domain | `domain/scene.py` | `SubtitleCue`, `SubtitlePlan` |

## Root Cause (Dialogue-A over Dialogue-B)
1. Legacy `write_srt` had **no dialogue_id/scene_id binding** — index-only timing
2. **No fingerprint/idempotency** — stale SRT reuse possible
3. Master SRT used **final video duration** instead of **audio duration**
4. No validation of dialogue/scene/language identity before checkpoint

## BUILD-04E Extension
```
Existing engine (write_srt / proportional_cues)
        ↓
subtitle_bridge.idempotent_write_srt
        ↓
subtitle_runtime.execute_subtitle_request
        ↓
BUILD-03 IdempotentExecutor
        ↓
validation → provenance → checkpoint
```

## New Modules
- `pipeline/idempotency/subtitle_request.py` — SubtitleRequestSpec + fingerprint
- `pipeline/idempotency/subtitle_engine.py` — bound cue generation
- `pipeline/idempotency/subtitle_bridge.py` — production entry
- `pipeline/idempotency/subtitle_runtime.py` — executor integration
- `pipeline/idempotency/subtitle_validation.py` — timing + identity validation
- `pipeline/idempotency/subtitle_provenance.py` — trace records
- `pipeline/idempotency/mock_subtitle_provider.py` — offline tests
