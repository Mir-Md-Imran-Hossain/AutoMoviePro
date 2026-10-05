# Complete Render Callsite Matrix — BUILD-04D

| Callsite | Caller | Job | Script | Visual | Audio | Subtitle | Logo | Intro | Config | Renderer | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Recovery | Status |
|----------|--------|-----|--------|--------|-------|----------|------|-------|--------|----------|-------------|-------------|------------|------------|------------|----------|--------|
| `render_bridge.idempotent_compose_final_video` | video_pipeline | Yes | fp | clip hashes | embedded | — | hash | — | size/fps | ffmpeg | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `render_runtime.execute_render_request` | bridge, tests | Yes | Yes | Yes | Yes | optional | Yes | optional | Yes | mock/ffmpeg | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `concat_av_clips` direct | legacy fallback | — | — | — | — | — | — | — | — | ffmpeg | No | No | partial | No | No | — | **COVERED** (fallback) |
| `localization.try_compose_from_scene_local` | localization | Yes | — | per-scene | per-scene | burned | — | — | — | ffmpeg | No | No | partial | No | No | — | **DOCUMENTED_NON_PRODUCTION** |
| `scene_builder` split concat | split path | Yes | — | parts | parts | — | — | — | — | ffmpeg | No | No | partial | No | No | — | **BLOCKED** (scene-level) |
| Dev `generate_video` scripts | scripts/* | via pipeline | — | — | — | — | — | — | — | — | via pilot | — | — | — | — | — | **DOCUMENTED_NON_PRODUCTION** |

Production final assembly path is **COVERED** via render bridge.
