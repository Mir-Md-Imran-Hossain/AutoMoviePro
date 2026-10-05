# Open-Source Phase 6H — Pre-Audit Report

**Date:** 2026-09-09  
**Verdict:** **AUDIT PASS** — no new TTS / audio / VoiceIdentity / ASR / subtitle / quality / repair / FFmpeg engine required

---

## Canonical authorities

| Concept | Location |
|---------|----------|
| Audio intent | `domain.scene.AudioPlan` + `audio_design` |
| Voice contract | `pipeline.production_consistency.VoiceIdentity` (RCP-06D) — **not** acoustic verification |
| TTS | `idempotency.tts_bridge` / `tts_google` |
| ASR observation | `pipeline.observation.speech_timing.observe_speech_timing` (faster-whisper, optional) |
| Duration | `duration_budget.resolve_duration_contract` |
| Subtitle timing | `subtitle_bridge` (audio-duration authoritative) |
| Audio quality | `av_quality_gates` + `audio_design.loudness` (no broadcast LUFS claim) |
| Artifact boundary | `idempotency.audio_validation` + `compose.ffprobe_duration` |
| Dialogue timeline | Phase 6G `frame_evidence.alignment` |
| Audio repair | **YES** — `RepairScope.AUDIO_ASSET` via `audio_design.repair_bridge.plan_audio_design_repair` + `av_self_repair_agent` |

---

## Gaps (honest)

- VoiceIdentity continuity is **contract/heuristic**, not acoustic speaker verification → observation must record `VOICE_IDENTITY_OBSERVATION=UNKNOWN` unless a real verifier exists (it does not).
- Technical metadata / TTS success ≠ semantic PASS.
- Frame-evidence repair loop remains VISUAL_ASSET-only; audio FAIL must use audio repair bridge, not invent a new loop.

---

## Safe extension

`pipeline/observation/audio_evidence/`

Evidence packaging only:

- artifact probe via existing ffprobe/validation
- speech segments via Phase 6A `observe_speech_timing`
- dialogue coverage FULL/PARTIAL/NONE/UNKNOWN
- transcript alignment (conservative)
- VoiceIdentity **contract** binding + UNKNOWN acoustic verification
- timeline join with Phase 6G
- FAIL → existing `plan_audio_design_repair` handoff (AUDIO_ASSET)
- UNKNOWN → no repair

faster-whisper remains observation-only (`authority=observation_only`).
