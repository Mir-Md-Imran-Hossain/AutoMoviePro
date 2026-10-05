# SUBTITLE_DATA_FLOW

```
Script (director_plan.json)
  ↓
Section / Scene (scene_id)
  ↓
Dialogue (dialogue_id, localized_text)
  ↓
Segment (segment_id, optional split)
  ↓
Localized Dialogue + Language
  ↓
Actual Audio (audio_fingerprint, audio_duration_sec)
  ↓
SubtitleRequestSpec
  ↓
compute_subtitle_fingerprint()
  ↓
IdempotentExecutor (claim → execute → validate → persist)
  ↓
subtitle_engine.generate_bound_cues() OR mock/provider
  ↓
SRT file + .meta.json sidecar
  ↓
validate_subtitle_asset()
  ↓
subtitle_provenance/
  ↓
checkpoint (BUILD-03)
  ↓
Render (subtitle_hash when applicable)
```

## Sidecar Meta
Each canonical SRT writes `{path}.srt.meta.json` with scene_id, dialogue_id, segment_id, language, text_hash, timing_model, fingerprint.

## Reuse Path
1. Idempotency store SUCCEEDED + valid artifact → reuse (0 provider calls)
2. Invalid SUCCEEDED → mark FAILED_RETRYABLE → regenerate
3. GenerationCache legacy key for atomic file commit
