# SUBTITLE_RUNTIME_INTEGRATION

## Entry Point
```python
from pipeline.idempotency.subtitle_bridge import idempotent_write_srt

idempotent_write_srt(
    text, audio_path, srt_path,
    work_dir=work,
    job_id=work.name,
    scene_id=str(idx),
    dialogue_id=f"scene-{idx:02d}",
    language="en",
)
```

## Production Routing
`localization.write_srt` routes to bridge when `work_dir` is set. Legacy path retained for unit tests without work_dir.

## Engine
`subtitle_engine.generate_bound_cues` — proportional word-chunk timing with identity fields in meta.

## Tests
`scripts/test_build04e_subtitle_runtime.py` — 40 cases E01-E38+
