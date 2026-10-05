# SUBTITLE_RENDER_DEPENDENCY

RenderAssemblyManifest includes:
- `subtitle_hash` — aggregate sidecar hash
- `RenderSceneInput.subtitle_asset_hash` — per-scene when applicable

`build_manifest_from_clips(subtitle_path=...)` feeds hash into render fingerprint.

Subtitle change → render fingerprint change → stale render detected.

Subtitle change does NOT regenerate script/visual/audio upstream.
