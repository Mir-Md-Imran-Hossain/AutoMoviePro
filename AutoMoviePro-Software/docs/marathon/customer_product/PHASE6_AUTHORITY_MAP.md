# PHASE6 — Authority Map

**Date:** 2026-09-09  
**Audit type:** Forensic / no code changes  
**Scope:** Phase 6A–6J + RCP-02→07 + C05/BUILD authorities

---

## Single-authority domains

| Domain | Sole authority | Notes |
|--------|----------------|-------|
| Scene / semantic intent | `domain.scene_intent.SceneIntent` | Planning EXPECTED |
| Script plan | `domain.script.ScriptPlan` | |
| Visual bible | `pipeline.visual_intelligence.VisualBible` | |
| Story/visual direction | `pipeline.story_visual_direction` (C05-S) | DirectedVisualBeat |
| Continuity policy | `pipeline.visual_semantic.continuity.ContinuityTracker` | Observation layers cite only |
| Audio intent | `domain.scene.AudioPlan` | |
| Voice contract | `pipeline.production_consistency.VoiceIdentity` | Not acoustic verifier |
| Duration | `pipeline.duration_budget.resolve_duration_contract` | Short 60/120, Long 180/300 |
| Prompt compile | `pipeline.multimodal_consistency.prompt_compiler` | |
| Multimodal gate boundary | `pipeline.multimodal_consistency` | Evidence projection is not a second gate |
| Semantic certification | `pipeline.semantic_coverage` | |
| Artifact verification | `pipeline.artifact_verification` | |
| Rendering integrity | `pipeline.rendering_integrity` | |
| Quality / repair plan | `pipeline.quality` + BUILD-04F `plan_repair` | |
| Publishability | `pipeline.quality.publishability` | Fail-closed on semantic UNKNOWN/ABSENT |
| Idempotency | BUILD-03 `pipeline.idempotency` | |
| TTS generation | `pipeline.idempotency.tts_bridge` / `tts_google` | |
| Subtitle timing | `pipeline.idempotency.subtitle_bridge` (audio-duration authoritative) | |
| Visual observation evidence | `pipeline.observation.frame_evidence` | Not ContinuityTracker |
| Speech observation | `pipeline.observation.speech_timing` (faster-whisper) | |
| Audio evidence packaging | `pipeline.observation.audio_evidence` | |
| Acoustic features / identity UNKNOWN | `pipeline.observation.audio_evidence.acoustic` | Option A; no embedding |
| Retrieval | `pipeline.retrieval` | CLIP optional; HEURISTIC ≠ semantic |
| FFmpeg/media | `pipeline.compose` | |
| Evidence fusion projection | `pipeline.multimodal_consistency.evidence_projection` | Not publishability |

---

## Competing-authority scan

| Finding | Severity |
|---------|----------|
| No second ContinuityTracker / semantic gate / duration engine found in Phase 6 path | OK |
| OpenMontage AGPL production imports | **0** |
| Frame-evidence repair loop is VISUAL_ASSET; audio uses `plan_audio_design_repair` | OK (scoped) |
| Acoustic VoiceIdentity observation intentionally UNKNOWN (no second voice engine) | OK / LIMITED |

**Domains with 0 authorities for production observation:** acoustic speaker verification (capability absent → UNKNOWN, not a second authority).

**Domains with 2+ competing authorities:** none identified in Phase 6 observation stack.

---

## Authority chain (publish)

```
observation (6C–6J)
  → evidence_projection (6J; never_directly_publishable)
    → semantic_coverage
      → quality / BUILD-04F (on FAIL only)
        → publishability
          → publish / schedule
```

HARD RULE verified in code comments/tests: UNKNOWN does not become PASS/PUBLISHABLE via semantic_coverage / publishability.
