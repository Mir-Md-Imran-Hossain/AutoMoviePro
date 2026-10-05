# COMPLETE_SUBTITLE_CALLSITE_MATRIX

| Callsite | Caller | Scene | Dialogue | Segment | Language | Audio Dep | Format | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Render Dep | Scope | Status |
|----------|--------|-------|----------|---------|----------|-----------|--------|-------------|-------------|------------|------------|------------|------------|-------|--------|
| `write_srt` (bridge) | localization, scene_builder, video_pipeline | Y | Y | Y | Y | Y | SRT | Y | Y | Y | Y | Y | N* | PROD | COVERED |
| `write_srt` (legacy fallback) | tests, no work_dir | N | N | N | N | partial | SRT | N | N | partial | N | N | N | DEV/TEST | INTENTIONALLY_NON_PRODUCTION |
| `localize_scene_clip` | video_pipeline | Y | Y | N | Y | Y | SRT | Y | Y | Y | Y | Y | N | PROD | COVERED |
| `localize_master_clip` | localization export | Y | Y | N | Y | Y | SRT | Y | Y | Y | Y | Y | N | PROD | COVERED |
| `remux_replace_audio` burn-in | localization | Y | Y | N | Y | Y | SRT | Y | Y | Y | Y | Y | N | PROD | COVERED |
| `_mux_scene` sidecar | scene_builder | Y | Y | N | Y | Y | SRT | Y | Y | Y | Y | Y | N | PROD | COVERED |
| `english_master.srt` | video_pipeline | master | master-en | N | en | Y (TTS/Agnes) | SRT | Y | Y | Y | Y | Y | N | PROD | COVERED |
| `wire_subtitle_plan` | contract_wiring | Y | Y | N | en | planned | JSON plan | partial | N | Y | N | N | N | PROD | COVERED (plan only) |
| `proportional_cues` | subtitle_align, contract_wiring | Y | via plan | N | en | duration | internal | N | N | Y | N | N | N | PROD | COVERED (engine) |
| Render manifest subtitle_hash | render_bridge | aggregate | N | N | N | N | hash | Y | Y | Y | Y | Y | Y | PROD | COVERED |

*Sidecar SRT does not burn into final render by default; `subtitle_hash` in render manifest applies when subtitle asset participates in compose.
