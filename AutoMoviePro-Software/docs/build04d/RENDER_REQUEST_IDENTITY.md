# Render Request Identity — BUILD-04D

## RenderRequestSpec

Wraps `RenderAssemblyManifest` + provider/model.

Fingerprint inputs include full normalized manifest:

- job_id, script_fingerprint
- scenes[]: index, visual/audio/subtitle hashes, timing
- logo_hash, intro_hash, subtitle_hash
- output_config: size, max_seconds, fps, codecs

Excluded: timestamp, attempt number, execution UUID.

## Entity ID

`render-{job_id}`

## Stage

`render` (BUILD-03 fingerprint stage)
