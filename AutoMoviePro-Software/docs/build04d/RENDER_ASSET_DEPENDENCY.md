# Render Asset Dependency — BUILD-04D

Asset identity uses **content hash** (`hash_artifact`) not filename or mtime.

| Asset | Identity source |
|-------|-----------------|
| Scene clip | visual_asset_hash from clip file |
| Audio (embedded in clip) | audio_asset_hash when separate |
| Subtitle | subtitle_asset_hash |
| Logo | logo_hash |
| Intro | intro_hash |
| Script | script_fingerprint from provenance or director_plan hash |

Scene order and timing are part of manifest — reordering changes fingerprint.
