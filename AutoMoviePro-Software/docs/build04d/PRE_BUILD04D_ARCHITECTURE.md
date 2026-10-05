# BUILD-04D Pre-Build Architecture

## Existing render engine

Production final video assembly in `video_pipeline.generate_video`:

1. `concat_av_clips(clips, body, size)` — scene_builder / FFmpeg filter_complex
2. `mix_logo_safe(body, logo, branded)` — optional logo overlay
3. `_trim_reencode(src, final, max_seconds, size)` — final MP4

**Artifact:** `{work_dir}/final_{video_type}.mp4`

## Domain contracts (`domain/render.py`)

- `RenderJob`, `RenderManifest`, `RenderArtifact` — BUILD-02 wiring contracts
- BUILD-04D adds runtime layer: `RenderAssemblyManifest` + `RenderRequestSpec` in `pipeline/idempotency/`

## BUILD-04D integration

```
Scene clips + logo + config
        ↓
RenderAssemblyManifest
        ↓
RenderRequestSpec → fingerprint
        ↓
render_bridge.idempotent_compose_final_video
        ↓
render_runtime.execute_render_request
        ↓
BUILD-03 IdempotentExecutor
        ↓
FFmpeg engine (unchanged)
        ↓
validate → atomic promote → provenance → checkpoint
```

## Pilot entry

`video_pipeline.generate_video` compose phase → `idempotent_compose_final_video`

## Key rules implemented

- RULE 03: ffprobe/container validation, not file existence alone
- RULE 04: validate before checkpoint
- RULE 05: UNKNOWN → no blind rerender
- RULE 06: `.tmp.mp4` → validate → `os.replace` → final
