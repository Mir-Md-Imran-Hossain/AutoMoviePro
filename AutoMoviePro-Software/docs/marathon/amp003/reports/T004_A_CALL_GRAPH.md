# T004-A — Production Call Graph Audit

**Marathon:** AMP-003 / TASK-004  
**Sub-task:** T004-A  
**Checkpoint:** AMP003-T004-A-PASS  
**Date:** 2026-08-31  
**Type:** PRE-AUDIT ONLY (no code changes)

---

## Executive Summary

Primary production entry: `pipeline/video_pipeline.py::generate_video()`.  
Secondary callers: `app/main.py`, `app/scheduler_service.py`, `pipeline/live_lab.py`.  
Queue path: `pipeline/orchestrator.py::enqueue()` — metadata enrichment only, does not execute pipeline.

**Coverage:** 100% of identified production callsites mapped (15 canonical stages + 3 auxiliary gates).

**Key gaps (for later sub-tasks):**
- Scene loop uses legacy `dict` — canonical `domain.Scene` not enforced at runtime (T004-B)
- Script/render legacy fallbacks bypass idempotency bridges (T004-H)
- Localization TTS without `work_dir` falls back to direct provider (T004-D/E)
- Engagement stage exists in BUILD-02 wiring only — not in live `generate_video` path

---

## Production Entry Points

| # | File | Function | Caller Context | Invokes |
|---|------|----------|----------------|---------|
| E1 | `app/main.py` | API handler ~L1276 | User-triggered generation | `generate_video()` |
| E2 | `app/scheduler_service.py` | scheduler ~L242, L329 | Scheduled production | `generate_video()` |
| E3 | `pipeline/live_lab.py` | live lab ~L539 | Dev/live lab | `generate_video()` |
| E4 | `pipeline/orchestrator.py` | `enqueue()` | Queue metadata | `enrich_queue_payload`, `enrich_payload_with_idempotency` — **no pipeline exec** |
| E5 | `pipeline/video_pipeline.py` | `generate_video()` | **Canonical production root** | Full pipeline below |

---

## Canonical Stage Call Graph

```
generate_video(channel, video_type, topic, work_dir)
│
├─[INIT] load_api_bundle, apply_niche_to_channel, duplicate guard (product_registry)
│
├─[RESUME] find_resumable_work / director_plan.json load
│
├─ STAGE: TOPIC + RESEARCH (pre-director intelligence gate)
│   Caller: generate_video L141–184
│   Callee: intelligence.bridge.pick_topic_from_reserve
│           intelligence.bridge.run_intelligence_gate
│           intelligence.gate.evaluate_gate_result / block_if_not_pass
│   Input: channel dict, topic str, work Path
│   Output: intelligence_gate_passed bool, enriched research_notes
│   Contract: intelligence/contracts.py (ChannelProfile, Candidate)
│   Idempotency: intelligence/research_runtime.py (cached research)
│   Validation: gate.py fail-closed (require_fail_closed)
│   Fallback: trending_search (L200–222) if fail_closed=false — DEV ONLY
│   Bypass: PARTIAL — legacy topic pick when gate disabled
│   Status: VERIFIED (production fail-closed)
│
├─ STAGE: SCRIPT (director plan)
│   Caller: _plan_niche_production_idempotent → generate_video L226+
│   Callee: idempotency.script_bridge.idempotent_plan_niche_production
│           → script_runtime.execute_script_request
│           → niche_director.plan_niche_production (engine)
│   Input: niche, topic, keys, max_seconds, research_notes
│   Output: director plan dict (scenes[], title, description, tags)
│   Contract: domain.Script (offline via contract_wiring wire_script)
│   Idempotency: BUILD-04C script_bridge + IdempotentExecutor
│   Validation: script_validation, content_humanizer (optional)
│   Fallback: plan_niche_production direct on bridge Exception (L27–29)
│   Bypass: YES — legacy fallback on any bridge error
│   Status: PARTIAL
│
├─ STAGE: CONTRACT WIRING GATE (plan-level, offline validation)
│   Caller: generate_video L473–486
│   Callee: contract_wiring.production_bridge.assert_production_plan_wiring
│           → wire_pipeline_from_plan (all domain stages)
│           → detect_orphans, persist CONTRACT_WIRING_TRACE.json
│   Input: plan dict, job_id=work.name
│   Output: PipelineTrace (fail-closed on error)
│   Contract: domain.* (Topic→Engagement chain offline)
│   Idempotency: N/A (validation only)
│   Validation: run_stage per stage, stage_order_valid
│   Fallback: none — raises ProductionWiringError
│   Bypass: none in production path
│   Status: VERIFIED (TASK-002)
│
├─ STAGE: SCENE (per-scene loop — legacy dict runtime)
│   Caller: generate_video L572–795 (for idx, scene in scenes)
│   Callee: build_dialogue_clip (scene_builder.py)
│   Input: scene dict from plan (narration, element, visual_prompt, ...)
│   Output: scene_XX_element.mp4 clip Path
│   Contract: domain.Scene — **offline only** (wire_scenes_from_plan in BUILD-02)
│             scene_contract.build_scene_contract — used in wiring, not enforced in loop
│   Idempotency: resume_guard clip_fingerprint / should_reuse_existing_clip
│   Validation: av_quality_gates, av_self_repair_agent (on reuse)
│   Fallback: dialogue rewrite inline (L514–554), agent regen
│   Bypass: YES — unvalidated scene dict enters build_dialogue_clip
│   Status: GAP → T004-B
│
│   ├─ STAGE: AUDIO (English TTS per scene)
│   │   Caller: generate_video L698–731
│   │   Callee: idempotency.tts_bridge.idempotent_synthesize_narration
│   │           → audio_runtime.execute_audio_request
│   │           OR synthesize_narration direct (fallback L716)
│   │   Input: narration str, scene idx, google keys
│   │   Output: narration_XX.m4a Path
│   │   Contract: domain.AudioPlan (offline)
│   │   Idempotency: BUILD-04B tts_bridge
│   │   Validation: audio_validation, sidecar match
│   │   Fallback: synthesize_narration direct on bridge Exception
│   │   Bypass: YES — legacy TTS fallback
│   │   Status: PARTIAL → T004-D
│   │
│   └─ STAGE: VISUAL (within build_dialogue_clip)
│       Caller: scene_builder.build_dialogue_clip
│       Callee: idempotency.agnes_bridge.idempotent_generate_agnes_beat
│               → visual_runtime.execute_visual_request
│               OR media_assets.generate_agnes_dialogue_clip (fallback L1224)
│               OR fallback_image_video.build_image_video_fallback
│       Input: visual_prompt, element, product_name, agnes keys
│       Output: agnes_XX_element.mp4 / scene clip
│       Contract: domain.VisualPlan (offline)
│       Idempotency: BUILD-04A agnes_bridge → visual_runtime
│       Validation: visual_validation, av_quality_gates
│       Fallback: image Ken-Burns, stock, pexels
│       Bypass: YES — direct generate_agnes_dialogue_clip on bridge fail
│       Status: PARTIAL → T004-C
│
├─ STAGE: LOCALIZATION (per-scene + master)
│   Caller: generate_video L645–663 (reuse path), L768–789 (new clip)
│           generate_video L1034–1059 (master localize)
│   Callee: localization.localize_scene_clip
│           localization.localize_master_clip
│   Input: scene clip, english_narration, languages[], google keys
│   Output: SCENE_LOCAL/{idx}/{lang}/video.mp4, LOCALIZED/
│   Contract: domain.Localization (offline)
│   Idempotency: tts_reuse.reuse_or_synthesize_tts → tts_bridge when work_dir set
│   Validation: detect_subtitle_coverage, remux gates
│   Fallback: edge_tts direct when no work_dir in reuse_or_synthesize_tts
│   Bypass: PARTIAL — translate_text direct, edge_tts without idempotency if no work_dir
│   Status: PARTIAL → T004-E
│
├─ STAGE: SUBTITLE (English master SRT)
│   Caller: generate_video L892–912
│   Callee: localization.write_srt(work_dir=work)
│           → idempotency.subtitle_bridge.idempotent_write_srt
│           → subtitle_runtime.execute_subtitle_request
│   Input: en_narr text, audio path, srt path
│   Output: english_master.srt
│   Contract: domain.SubtitlePlan/Cue (offline)
│   Idempotency: BUILD-04E subtitle_bridge (when work_dir provided)
│   Validation: subtitle_validation
│   Fallback: write_srt legacy proportional split (no work_dir)
│   Bypass: PARTIAL — legacy path if work_dir omitted
│   Status: VERIFIED in generate_video (work_dir always passed)
│
├─ STAGE: RENDER (final compose)
│   Caller: generate_video L817–835
│   Callee: idempotency.render_bridge.idempotent_compose_final_video
│           → render_runtime.execute_render_request
│           OR scene_builder.concat_av_clips + mix_logo_safe + _trim_reencode
│   Input: clips[], logo, video_type, size, max_seconds
│   Output: final_{short|long}.mp4
│   Contract: domain.RenderJob/RenderArtifact (offline)
│   Idempotency: BUILD-04D render_bridge
│   Validation: render_validation, _has_audio check
│   Fallback: legacy concat+logo+trim on bridge Exception (L829–835)
│   Bypass: YES — legacy compose fallback
│   Status: PARTIAL → T004-F
│
├─ STAGE: QUALITY (technical + creative gates)
│   Caller: generate_video L852–941
│   Callee: av_quality_gates.evaluate_master_shippable
│           quality.bridge.run_creative_quality_gate (BUILD-04F)
│           quality.bridge.run_publishability_gate
│   Input: final mp4, plan, scenes
│   Output: MASTER_SHIP_GATE.json, quality_report.json, PUBLISHABILITY_GATE.json
│   Contract: domain.ValidationResult (quality/contracts.py)
│   Idempotency: quality/fingerprint.py (evaluation cache)
│   Validation: fail-closed — raises on unshippable
│   Fallback: none — exceptions propagate
│   Bypass: none
│   Status: VERIFIED
│
├─ STAGE: METADATA
│   Caller: generate_video L943–946
│   Callee: plan.get(title/description/tags) — inline
│   Input: plan dict fields
│   Output: title, description, tags strings
│   Contract: domain.VideoMetadata (offline wire_metadata)
│   Idempotency: N/A
│   Validation: contract wiring gate (offline)
│   Fallback: default title template
│   Bypass: none significant
│   Status: VERIFIED (derived from validated plan)
│
├─ STAGE: THUMBNAIL
│   Caller: generate_video L965–979
│   Callee: media_assets.generate_thumbnail
│   Input: title, topic, pollinations/google keys
│   Output: thumbnail.jpg
│   Contract: domain.ThumbnailAsset (offline wire_thumbnail)
│   Idempotency: generation_cache (partial)
│   Validation: file existence check
│   Fallback: skip on Exception (non-blocking)
│   Bypass: direct provider call — no idempotency bridge
│   Status: PARTIAL (non-blocking)
│
├─ STAGE: UPLOAD (package preparation)
│   Caller: generate_video L981–1002
│   Callee: package_export.export_upload_package
│           app.db.add_job / update_job
│   Input: final video, metadata, thumbnail
│   Output: UPLOAD_PACKAGE/, job record upload_status=ready_to_upload
│   Contract: domain.UploadJob (offline wire_upload_job)
│   Idempotency: N/A
│   Validation: publishability gate must pass first
│   Fallback: package skip on Exception (non-blocking)
│   Bypass: none on happy path
│   Status: VERIFIED (gated by quality)
│
├─ STAGE: PUBLICATION
│   Caller: generate_video L1014–1029, L1097–1119
│   Callee: settings.dry_run_publish check, PUBLISH_STATUS.txt
│           LicenseClient.sync_job (optional)
│   Input: job record, dry_run flag
│   Output: publication state marker, remote sync
│   Contract: domain.Publication (offline wire_publication)
│   Idempotency: N/A
│   Validation: dry_run enforced via settings
│   Fallback: sync_job failure logged only
│   Bypass: none
│   Status: VERIFIED (dry-run default)
│
└─ STAGE: ENGAGEMENT
    Caller: **NOT IN generate_video production path**
    Callee: contract_wiring wire_comment (offline trace only, include_engagement=False)
    Input: N/A live
    Output: N/A live
    Contract: domain.Comment/EngagementAction (BUILD-02 offline)
    Status: NOT_CONNECTED — deferred TASK-011
```

---

## Auxiliary Production Modules

| Module | Role | Connected to generate_video |
|--------|------|----------------------------|
| `pipeline/contract_wiring/` | Offline plan validation + trace | YES — gate L473 |
| `pipeline/idempotency/` | Runtime idempotent execution | PARTIAL — script/visual/audio/render/subtitle |
| `pipeline/intelligence/` | Topic research + gate | YES — pre-director |
| `pipeline/scene_builder.py` | Scene clip assembly | YES — per-scene loop |
| `pipeline/scene_contract.py` | Scene preflight v0 | OFFLINE ONLY (wiring) |
| `pipeline/localization.py` | Multi-lang TTS + subtitle burn | YES — optional |
| `pipeline/media_assets.py` | Agnes + thumbnail | YES — via scene_builder |
| `pipeline/quality/` | Creative + publishability gates | YES — post-render |
| `pipeline/package_export.py` | Upload package | YES — post-quality |
| `pipeline/resume_guard.py` | Scene resume/reuse | YES — scene loop |
| `pipeline/product_registry.py` | Duplicate product lock | YES — pre/post plan |

---

## Idempotency Bridge Matrix (Production)

| Stage | Bridge | Runtime Used in generate_video | Legacy Fallback |
|-------|--------|-------------------------------|-----------------|
| Script | `script_bridge.idempotent_plan_niche_production` | YES | `plan_niche_production` |
| Visual/Agnes | `agnes_bridge.idempotent_generate_agnes_beat` | YES (scene_builder) | `generate_agnes_dialogue_clip` |
| Audio/TTS | `tts_bridge.idempotent_synthesize_narration` | YES | `synthesize_narration` |
| Audio (loc) | `tts_bridge.idempotent_reuse_or_synthesize_tts` | YES when work_dir passed | direct edge/google |
| Subtitle | `subtitle_bridge.idempotent_write_srt` | YES (work_dir passed) | proportional write_srt |
| Render | `render_bridge.idempotent_compose_final_video` | YES | concat_av_clips legacy |
| FactPack | `factpack_bridge` | NO — inside intelligence only | N/A |
| Thumbnail | none | direct generate_thumbnail | N/A |

---

## Search Term Callsite Index

| Search Term | Primary Production Location |
|-------------|----------------------------|
| `generate_video` | video_pipeline.py:51; app/main.py; scheduler_service.py |
| `plan_niche_production` | niche_director.py; script_bridge fallback; video_pipeline L29 |
| `generate_agnes_dialogue_clip` | media_assets.py; agnes_bridge provider_fn; scene_builder L1224 |
| `synthesize_narration` | tts_google.py; video_pipeline L716 fallback; tts_reuse L195 |
| `write_srt` | localization.py:447; subtitle_bridge when work_dir set |
| `concat` / render | render_bridge; scene_builder.concat_av_clips fallback |
| `upload` | package_export; app.db job store |
| `publication` | dry_run_publish; PUBLISH_STATUS.txt; LicenseClient.sync |

---

## Gap Severity (T004-A Findings)

| ID | Stage | Gap | Severity | Target Sub-task |
|----|-------|-----|----------|-----------------|
| GAP-A01 | Script | Legacy fallback bypasses idempotency | P1 | T004-H |
| GAP-A02 | Scene | Runtime uses dict, not canonical Scene | P1 | T004-B |
| GAP-A03 | Visual | Direct Agnes call on bridge fail | P1 | T004-C |
| GAP-A04 | Audio | Direct synthesize_narration fallback | P1 | T004-D |
| GAP-A05 | Render | Legacy concat on bridge fail | P1 | T004-F |
| GAP-A06 | Localization | translate/edge_tts without idempotency path | P1 | T004-E |
| GAP-A07 | Failure | No explicit stage failure propagation gate | P1 | T004-G |
| GAP-A08 | Dependency | No runtime fingerprint invalidation chain | P1 | T004-I |
| GAP-A09 | E2E | No offline deterministic full trace test | P1 | T004-J |
| GAP-A10 | Bypass | Multiple production fallbacks undocumented/gated | P1 | T004-K |
| GAP-A11 | Thumbnail | No idempotency bridge | P2 | defer |
| GAP-A12 | Engagement | Not connected to production | P2 | TASK-011 |

---

## Acceptance

- [x] 100% production callsites mapped
- [x] All 15 canonical stages documented
- [x] Entry points identified
- [x] Idempotency bridge matrix complete
- [x] Gaps classified with severity

**T004-A = PASS**  
**Checkpoint = AMP003-T004-A-PASS**
