# Render Manifest Spec — BUILD-04D

## RenderAssemblyManifest

| Field | Purpose |
|-------|---------|
| manifest_version | Schema version (1.0.0) |
| render_template_version | compose-v1 |
| job_id | Work directory job scope |
| script_fingerprint | Links to script generation |
| scenes[] | Ordered scene inputs with asset hashes |
| logo_hash | Logo file content hash |
| intro_hash | Intro asset hash |
| subtitle_hash | Sidecar subtitle identity |
| output_config | size, max_seconds, fps, codecs |

## Scene entry

```json
{
  "scene_index": 0,
  "visual_asset_hash": "...",
  "audio_asset_hash": "",
  "subtitle_asset_hash": "",
  "start_sec": 0.0,
  "end_sec": 0.0,
  "duration_sec": 5.0
}
```

Built from clip files via `build_manifest_from_clips()`.

## Determinism

Sorted/normalized keys in `normalized()` output. No timestamps in semantic manifest.
