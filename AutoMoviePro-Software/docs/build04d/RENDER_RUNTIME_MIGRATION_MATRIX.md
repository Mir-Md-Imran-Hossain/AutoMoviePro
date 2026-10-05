# Render Runtime Migration Matrix — BUILD-04D

| Callsite | Renderer | Job | Script | Visual | Audio | Subtitle | Logo | Intro | Manifest | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Recovery | Retry | Prod | Tests | Status |
|----------|----------|-----|--------|--------|-------|----------|------|-------|----------|-------------|-------------|------------|------------|------------|----------|-------|------|-------|--------|
| video_pipeline final compose | ffmpeg | Yes | Yes | Yes | Yes | — | Yes | — | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | D01–D35 | **PASSED** |
| render_bridge | ffmpeg/mock | Yes | Yes | Yes | Yes | opt | Yes | opt | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | D01–D35 | **PASSED** |
| localization scene concat | ffmpeg | Yes | — | Yes | Yes | burned | — | — | No | No | No | partial | No | No | — | — | partial | — | **BLOCKED** |
| legacy compose fallback | ffmpeg | Yes | partial | Yes | Yes | — | Yes | — | No | No | No | partial | No | No | manual | — | Yes | — | **BLOCKED** |
