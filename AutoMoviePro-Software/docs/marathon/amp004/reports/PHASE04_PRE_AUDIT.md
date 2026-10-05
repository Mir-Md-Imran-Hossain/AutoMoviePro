# PHASE-04 Pre-Audit — Industrial Artifact Verification

**Date:** 2026-08-31  
**Checkpoint before:** `AMP004-PRODUCTION-CONTINUITY-PASS`  
**Production code changed during STEP-0:** `false`

---

## Artifact map (verified)

| Type | Created | Stored | Fingerprint | Provenance | Validation today | Media vs meta | UNKNOWN→PASS? | Invalid → render/publish? |
|------|---------|--------|-------------|------------|------------------|---------------|---------------|---------------------------|
| Video (scene) | scene_builder / agnes_bridge / fallback | work/scene_*.mp4 | visual FP (Agnes path) | visual_provenance | visual_validation L0 + AV gates L1 + multimodal L2 | Mixed | Semantic weak | Possible (best-attempt) |
| Image | media_assets / fallback | work/*.png | Weak / ad hoc | Ad hoc | validate_image_asset (not always called) | Mostly meta | No contract | Yes |
| Audio/TTS | tts_bridge → audio_runtime | narration_*.m4a | audio FP | audio_provenance | audio_validation L0 + AV L1 | Mixed | UNKNOWN blocked in bridge | Semantic miss possible |
| Subtitle | subtitle_bridge | *.srt + meta | subtitle FP | subtitle_provenance | subtitle_validation structural | Text only | UNKNOWN raises | Optional for publish |
| Final composite | render_bridge / legacy compose | final_*.mp4 | render FP | render_provenance | render_validation L0/L1 + MASTER_SHIP | Technical probe | UNKNOWN blocks bridge | Legacy path may skip render validator |
| Thumbnail | generate_thumbnail | thumbnail.jpg | None | None | Minimal | None | N/A | Non-blocking |
| Manifests/gates | various | work/*.json | Partial | quality_* provenance | result_validation / JSON | Meta | ABSENT non-blocking | Yes if ABSENT |

---

## Call graph (current)

```
generate_video
  → continuity (P03) + scenes
  → per-scene audio/visual idempotent generate + L0 validate
  → multimodal (Agnes) persist
  → render_bridge → validate_render_output
  → MASTER_SHIP_GATE
  → creative + publishability
  → ready_to_upload
```

**Gap:** No unified Layer C→D→E **observation contract**. `ARTIFACT_GATE.json` is optional → `ABSENT` → does not block. Final composite has technical checks but **no independent artifact-observation stage** that distinguishes INTENT/PROMPT/PROVIDER/OBSERVED/COMPOSITE. `visual_qa` exists but is **not** on the ship path.

---

## A–H answers

| Q | Finding |
|---|---------|
| Creates where? | Per-runtime bridges + scene_builder + render |
| Stored? | Job work_dir |
| Identified? | FP + dialogue/scene ids (strong on idempotent paths) |
| Provenance? | Per-modality provenance dirs (reuse — do not duplicate) |
| Validated? | L0 container + some L1 probe; L2 heuristic; no production L3 |
| Actual media? | Partial (ffprobe, AV gates, visual_qa unused in ship) |
| UNKNOWN→PASS? | Publishability blocks UNKNOWN **if present**; ABSENT ≠ UNKNOWN and does not block |
| Invalid → publish? | Possible when ARTIFACT dimension ABSENT / fallback paths |

---

## Phase-04 IN SCOPE

| Module | Role |
|--------|------|
| `pipeline/artifact_verification/` | NEW observation contract + verifiers + ARTIFACT_GATE + production entry |
| Reuse `visual_validation`, `audio_validation`, `subtitle_validation`, `render_validation`, `visual_qa` | L0/L1 — no duplicate engines |
| Reuse `multimodal_consistency` / `visual_semantic` | Semantic boundary — UNKNOWN ≠ PASS |
| Reuse BUILD-04F repair | Minimal scope mapping |
| `quality/bridge.py` + `publishability.py` | Load ARTIFACT_GATE; unverified final blocks |
| `video_pipeline.py` | Wire production verification before publishability |

## OUT OF SCOPE

Full VLM/ASR · SFX/music · new score/idempotency/continuity · FFmpeg rewrite · PHASE-05+

---

## STEP-0 acceptance

- [x] Artifact map complete  
- [x] Gaps vs A–E / L0–L4 documented  
- [x] Extend existing validators — do not fork  

**→ Implement STEP-1…**
