# Complete TTS Callsite Matrix — BUILD-04B-H

Status values: **COVERED** | **INTENTIONALLY_NON_GENERATING** | **BLOCKED**

| Callsite | Caller | Provider | Language | Voice | Emotion | Speed | AudioRequestSpec | Fingerprint | Idempotency | Validation | Provenance | Checkpoint | Retry | Recovery | Status |
|----------|--------|----------|----------|-------|---------|-------|------------------|-------------|-------------|------------|------------|------------|-------|----------|--------|
| `tts_bridge.idempotent_reuse_or_synthesize_tts` | localization, tts_reuse, internal | google / edge_tts | spec.language | resolved voice | neutral default | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `tts_bridge.idempotent_synthesize_narration` | video_pipeline, scene_builder | google | hint | Charon chain | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `tts_bridge.idempotent_edge_tts` | tts_bridge fallback, tts_google | edge_tts | hint | edge voice | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `video_pipeline` scene TTS | orchestrator | google | en | Charon | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `localization.localize_scene_clip` | video pipeline | google | per-lang | MASTER_VOICE | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `localization.localize_master_clip` | master export | google / edge | per-lang | voice chain | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `localization` voice-retry `synthesize_narration` | master TTS fallback | google | per-lang | alt voice | neutral | 1.0 | Yes (kwargs) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `scene_builder` split `CHERNOBYL_RE_TTS_PARTS` | split dialogue | google | SOURCE_LANG | Charon | neutral | 1.0 | Yes + segment_id | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `scene_builder._repair_cutoff_with_complete_tts` | cutoff repair | google | en | default | neutral | 1.0 | Yes + segment_id | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `tts_reuse.reuse_or_synthesize_tts` (work_dir set) | localization | google / edge | hint | sidecar | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `tts_google.synthesize_narration` edge branch (idempotency_work_dir) | google failure | edge_tts | hint | edge | neutral | 1.0 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **COVERED** |
| `embedded_audio.should_skip_english_tts_generation` | bridge | — | en | — | — | — | Yes | Yes | skip | validate ref | Yes | Yes | — | reuse ref | **INTENTIONALLY_NON_GENERATING** |
| `tts_reuse.find_reusable_tts` sidecar hit | bridge pre-check | — | lang | voice | — | — | Yes | Yes | skip gen | validate | register | Yes | — | sidecar | **INTENTIONALLY_NON_GENERATING** |
| `tts_reuse.reuse_or_synthesize_tts` (no work_dir) | legacy callers | google / edge | hint | sidecar | neutral | 1.0 | No | No | No | partial | No | No | partial | legacy | **BLOCKED** |
| `tts_google.synthesize_narration` (no idempotency_work_dir) | legacy fallback | google / edge | hint | default | neutral | 1.0 | No | No | No | partial | No | No | partial | legacy | **BLOCKED** |
| `av_self_repair_agent` agent TTS | repair agent | google / edge | lang | Charon | neutral | paced | No | No | No | size check | No | No | manual | repair | **BLOCKED** |
| `scripts/marathon_av_100.py` | dev script | google | en | default | — | — | No | No | No | — | No | No | — | — | **BLOCKED** |
| `scripts/chernobyl_30_train.py` | dev script | google | en | default | — | — | No | No | No | — | No | No | — | — | **BLOCKED** |
| `scripts/rebuild_*.py` | dev script | google | en | default | — | — | No | No | No | — | No | No | — | — | **BLOCKED** |
| `edge_tts_fallback.synthesize_edge_tts` direct | legacy only | edge_tts | hint | edge | — | — | No | No | No | minimal | No | No | — | — | **BLOCKED** |

## Production pipeline coverage

All production video-pipeline TTS paths (video_pipeline, localization with work_dir, scene_builder split/cutoff, canonical bridge) are **COVERED**.

Remaining **BLOCKED** callsites are legacy paths without `work_dir`, repair-agent utilities, or offline dev scripts — not invoked by the main orchestrated job path when `work_dir` is supplied.

## UNKNOWN policy

Primary provider **UNKNOWN** → `RuntimeError("TTS UNKNOWN — reconciliation required before fallback")` — no blind edge_tts invocation.
