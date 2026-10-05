# TTS Runtime Coverage — BUILD-04B-H

## Canonical lifecycle

```
AudioRequestSpec
    ↓ fingerprint (compute_audio_fingerprint)
    ↓ IdempotentExecutor (claim / reuse)
    ↓ provider (google | edge_tts | mock)
    ↓ validate_audio_asset
    ↓ save_audio_provenance
    ↓ checkpoint (BUILD-03 store)
    ↓ asset path
```

## Wrapped paths (BUILD-04B-H)

| Path | Entry | Status |
|------|-------|--------|
| Main scene TTS | `video_pipeline` → `idempotent_synthesize_narration` | COVERED (BUILD-04B) |
| Localization per-scene | `localize_scene_clip` → `reuse_or_synthesize_tts(work_dir=…)` | COVERED |
| Localization master | `localize_master_clip` → bridge + idempotent kwargs | COVERED |
| Split dialogue | `scene_builder` → `idempotent_synthesize_narration` + segment_id | COVERED |
| Cutoff repair | `scene_builder._repair_cutoff_with_complete_tts` | COVERED |
| Edge fallback | `idempotent_edge_tts` | COVERED |
| Reuse/synth unified | `idempotent_reuse_or_synthesize_tts` | COVERED |

## Identity fields in fingerprint

- job_id, entity_id (scene + dialogue + segment)
- dialogue_text, language, provider, model
- voice_id, voice_profile, emotion, speaking_speed
- part_index, segment_id, audio_plan_version

Excluded: timestamp, attempt number, random execution ID.

## Coverage verdict

**ONE CANONICAL TTS RUNTIME PATH** for production pipeline execution. Provider-specific engines remain behind the bridge.
