# PHASE-05 Pre-Audit — Industrial Audio & Sound Design

**Date:** 2026-08-31  
**Checkpoint before:** `AMP004-ARTIFACT-VERIFICATION-PASS`  
**Production code changed during STEP-0:** `false`

**Note:** Frozen roadmap listed this work under PHASE-07; user checkpoint reassigns it as **PHASE-05 Audio & Sound Design**. Script-narrative work remains deferred.

---

## Production audio map (verified)

| Area | Status | Key paths |
|------|--------|-----------|
| Dialogue/TTS | EXISTS | `tts_bridge` → `audio_runtime` → Google/Edge |
| Split dialogue | EXISTS | `scene_builder._build_split_dialogue_clip` |
| Voice selection | EXISTS | `lang_config.resolve_locked_voice` |
| Emotion | WEAK | In `AudioRequestSpec` / fingerprint; not acoustic control |
| Pronunciation | ABSENT | Prompt hint only |
| Silence | PARTIAL | `dialogue_sync.pad_av_tail` + AV silence detectors |
| Ambience | **ABSENT** | No stem/plan engine |
| SFX | **ABSENT** | — |
| Music | **ABSENT** | — |
| Ducking | **ABSENT** | — |
| Mixing | MINIMAL | Mux/remux only — no multi-stem hierarchy |
| Subtitle sync | EXISTS | subtitle_bridge + bindings |
| Render audio | EXISTS | render_validation require_audio |
| Final audio verify | EXISTS | Phase-04 `verify_audio_artifact` + MASTER_SHIP |
| Repair/retry | EXISTS | `av_self_repair_agent` + BUILD-03 executor |
| Idempotency | EXISTS | BUILD-03 `AudioRequestSpec` fingerprint |

---

## Provider preflight today

| Provider | Preflight before call? | Gap |
|----------|------------------------|-----|
| Google TTS | Empty text, voice lock, keys/budget | No emotion/delivery/ambience/SFX contradiction preflight |
| Edge TTS | Empty text, voice map | Same |
| Subtitle | Structural | OK for identity |
| Render | validate before promote | No mix/duck policy |

---

## Contracts to EXTEND (not duplicate)

- `domain.scene.AudioPlan`
- `domain.scene_intent.AudioIntent`
- `pipeline.idempotency.audio_request.AudioRequestSpec`
- `pipeline.idempotency.audio_validation` / `av_quality_gates`
- Phase-04 artifact verification
- BUILD-04F repair scopes
- BUILD-03 fingerprint/idempotency

---

## Call graph today

```
generate_video → idempotent_synthesize_narration → execute_audio_request → TTS
  → scene mux → render → artifact verify → publishability
```

**Gap:** No canonical industrial AudioPlan (ambience/SFX/music/duck/mix) and no deterministic semantic audio preflight before provider.

---

## PHASE-05 IN SCOPE

| Work | Role |
|------|------|
| Extend AudioPlan / AudioIntent | Canonical sound-design fields |
| `pipeline/audio_design/` | Preflight, naturalness, mix/duck policy, loudness, gate, production |
| Wire `tts_bridge` | Preflight BEFORE provider |
| Wire `scene_runtime` / pipeline | Persist plan; AUDIO_DESIGN_GATE |
| Publishability | Invalid audio design blocks publish |
| Tests | `test_amp004_phase05_audio_sound_design.py` |

## OUT OF SCOPE

Full music library · paid SFX APIs · FFmpeg rewrite · VLM/ASR emotion proof · script engine rewrite · PHASE-06+

---

## STEP-0 acceptance

- [x] Audio paths mapped  
- [x] Absences documented (ambience/SFX/music/ducking)  
- [x] Extension points identified  

**→ Implement STEP-1…**
