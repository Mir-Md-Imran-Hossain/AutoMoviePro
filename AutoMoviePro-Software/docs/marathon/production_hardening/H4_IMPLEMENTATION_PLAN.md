# H4 Implementation Plan — Real Production Workflow QA + Hardening

**Baseline:** `AMP004-H4-PRE-AUDIT-PASS`  
**Date:** 2026-09-03  

## Finding map

| Finding | Sev | Workflow | Authority | Root Cause | Minimal Fix | Tests |
|---------|-----|----------|-----------|------------|-------------|-------|
| DEF-H4-001 | P2 | Multilingual package | `generate_video` + publishability | `ready_to_upload` set before `localize_master_clip` | Move packaging before ready; multilingual fail-closed on package failure | H4 focused |
| DEF-H4-002 | P2 | E2E soft handoff | `e2e_industrial.runner` | Soft handoff unlabeled vs production | Explicit `allow_soft_handoff`; evidence flag; never skip publishability | H4 + P09 |
| DEF-H4-003 | P2 | VLM/ASR | Artifact Verification | Deferred depth | **DEFER** | — |
| DEF-H4-004 | P2 | Long-form/batch | Ops | Not certified | **DEFER** + classify in report | — |
| DEF-H4-005 | P3 | Prompt dual | LEGACY | Merge later | **DEFER** | — |
| DEF-H4-006 | P3 | TTS adapter | tts_bridge | Disciplined in H3 | **CLOSED as N/A** (H3) / monitor | H3 |

## Scope
- ready_to_upload boundary vs localization packaging
- Soft-handoff containment/documentation in offline E2E
- Focused H4 workflow tests (offline/mock)
- Regressions H1–H3 + P02–P10

## Out of scope
H5, Phase-11, VLM/ASR, WorkflowEngine2, paid APIs, batch load infra, long-form certification claims.

## Authority map
Unchanged: generate_video, SceneIntent, ContinuityTracker, BUILD-03, BUILD-04F, audio, localization, AV, render_bridge, ffmpeg_exec, RI, publishability, H2 config.

## Acceptance
ready_to_upload only after publishability AND (if multilingual) successful localize packages; failure injects never upload; soft handoff explicit; paid APIs=0.

## Rollback
Revert `video_pipeline` order + runner flag; keep H1/H2/H3 intact.
