# SUBTITLE_RUNTIME_MIGRATION_MATRIX

| Callsite | Job | Scene | Dialogue | Segment | Language | Audio | Subtitle | Timing | FP | Idem | Val | Prov | CP | Render | Recovery | Scope | Tests | Status |
|----------|-----|-------|----------|---------|----------|-------|----------|--------|----|----|-----|------|----|----|----------|-------|-------|--------|
| write_srt bridge | Y | Y | Y | Y | Y | Y | Y | audio_rel | Y | Y | Y | Y | Y | N* | Y | PROD | E01-E38 | PASSED |
| localize_scene_clip | Y | Y | Y | N | Y | Y | Y | audio_rel | Y | Y | Y | Y | Y | N | Y | PROD | E24 | PASSED |
| localize_master | Y | Y | Y | N | Y | Y | Y | audio_rel | Y | Y | Y | Y | Y | N | Y | PROD | E24 | PASSED |
| _mux_scene | Y | Y | Y | N | Y | Y | Y | audio_rel | Y | Y | Y | Y | Y | N | Y | PROD | E22 | PASSED |
| english_master.srt | Y | master | master-en | N | en | Y | Y | audio_rel | Y | Y | Y | Y | Y | N | Y | PROD | E06 | PASSED |
| render subtitle_hash | Y | agg | N | N | N | N | hash | N/A | Y | Y | Y | Y | Y | Y | Y | PROD | E35 | PASSED |
| write_srt legacy | N | N | N | N | N | partial | Y | audio_rel | N | N | partial | N | N | N | N | TEST | — | INTENTIONALLY_NON_PRODUCTION |

*Sidecar-only; render hash when subtitle_path passed to compose.
