# PHASE-08 Pre-Audit — Industrial VFX + FFmpeg + Rendering Integrity

**Date:** 2026-09-03  
**Checkpoint before:** `AMP004-CREATIVE-PRODUCTION-QUALITY-PASS`  
**Production code changed during STEP-0:** `false`

**Roadmap note:** Frozen AMP004 listed VFX/FFmpeg under PHASE-09. User assigns this as **PHASE-08**. Do not start PHASE-09 (E2E industrial QA).

---

## 1. Production render call graph (verified)

```
generate_video
  → scene clips (scene_builder.build_dialogue_clip)
  → idempotent_compose_final_video          [BUILD-04D canonical]
      → build_manifest_from_clips
      → execute_render_request
          → provider: concat_av_clips + mix_logo_safe + _trim_reencode
          → validate_render_output (ffprobe)
          → atomic promote + provenance
  → evaluate_master_shippable
  → run_production_artifact_verification    [P04 Layer-E]
  → audio / localization / creative gates
  → publishability
```

**Canonical render entry to EXTEND:** `pipeline/idempotency/render_bridge.py::idempotent_compose_final_video`  
**Canonical executor:** `execute_render_request` (BUILD-04D)  
**Structured FFmpeg helper (promote):** `pipeline/ffmpeg_exec.py` (currently test-heavy; become documented boundary)

---

## 2. Authority map (summary)

| Area | Status | Classification | Path |
|------|--------|----------------|------|
| Final compose | EXISTS | ACTIVE | render_bridge → render_runtime |
| FFmpeg bin/probe | EXISTS | ACTIVE | compose.ffmpeg_bin / ffprobe_* |
| Structured FFmpeg run | EXISTS | UNUSED→PROMOTE | ffmpeg_exec.run_ffmpeg |
| Scene mux/concat | EXISTS | ACTIVE | scene_builder |
| Legacy compose helpers | EXISTS | LEGACY | compose.concat_clips / overlay_logo |
| MoviePy | ABSENT | — | none in production |
| Timeline semantic | WEAK | ACTIVE | multimodal_consistency.timeline |
| Timeline for render | WEAK | gap | no intentional gap/overlap contract |
| Filtergraph contract | ABSENT | gap | string filter_complex in scene_builder |
| VFX purpose | WEAK | ACTIVE policy | creative_production.transitions; deep VFX absent |
| Typography | PARTIAL | ACTIVE | scene_builder master_mux_vf + P06 TextPlan |
| Subtitle burn | ACTIVE | localization.remux_replace_audio | P06 authority |
| Codec profile | ACTIVE | system_profile.ffmpeg_x264_args | |
| Render validation | ACTIVE | render_validation.validate_render_output | |
| Artifact observe | ACTIVE | P04 | Layer-E |
| Rendering integrity gate | ABSENT | — | not on publishability |
| Temp / retry | ACTIVE | render_runtime temp + IdempotentExecutor | |

### Duplicates — do NOT recreate

| Keep | Do not fork |
|------|-------------|
| idempotent_compose_final_video | new compose engine |
| execute_render_request | second idempotency |
| validate_render_output + P04 | second media verifier pretending to replace P04 |
| creative_production.transitions | second transition engine |
| localization_consistency / P06 text | second text/localization engine |
| publishability.evaluate_publishability | second publish gate |

---

## 3. Gaps for Phase-08

1. No RenderIntegrityContract (timeline intentionality, VFX directives, filtergraph nodes, explicit stream maps)
2. No preflight before expensive compose for timeline/VFX/geometry
3. No RENDERING_INTEGRITY_GATE on publishability (distinct from ship `render_status`)
4. ffmpeg_exec not production-wired as provenance capture
5. Accidental vs intentional overlap/gap not classified
6. VFX without purpose not blocked at render boundary
7. Return code alone can be treated as success without integrity gate wrap

## 4. EXTEND plan (post STEP-0)

- NEW `pipeline/rendering_integrity/` (same pattern as audio_design / creative_production)
- Wire preflight into `idempotent_compose_final_video` before `execute_render_request`
- Wire `run_production_rendering_gate` in `video_pipeline` after final exists + P04-compatible observe
- Add `rendering_integrity_status` AND dimension to publishability
- Reuse BUILD-04D, P04 probe, ffmpeg_exec, creative transitions, P06 glyph/safe-area helpers

## OUT OF SCOPE

- Full cinematic VFX library rewrite
- MoviePy adoption
- Deleting legacy compose.py helpers
- Regenerating AI assets to fix deterministic filtergraph errors
- PHASE-09 E2E
