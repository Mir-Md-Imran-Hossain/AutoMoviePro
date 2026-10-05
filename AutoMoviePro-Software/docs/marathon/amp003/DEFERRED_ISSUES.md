# AMP-003 Deferred Issues

| ID | Task | Issue | Reason |
|----|------|-------|--------|
| DEF-AMP003-001 | TASK-001 | Cross-major schema migration adapter | Out of scope — major bump requires explicit migration task |
| DEF-AMP003-002 | TASK-001 | Process-level contract file locking | Deferred to TASK-003 idempotency scope |
| DEF-AMP003-004 | TASK-002 | Per-scene live contract wiring in TTS/visual loop | **PARTIAL T004-B** — scene gate; visual T004-C |
| DEF-T004-B-01 | T004-B | Auto-resume from VALIDATED_SCENES.json | T004-J |
| DEF-T004-B-02 | T004-B | segment_id explicit contract field | T004-E |
| DEF-AMP003-005 | TASK-002 | Global idempotency executor hardening | **RESOLVED TASK-003** |
| DEF-AMP003-006 | TASK-002 | Legacy script/render fallbacks in video_pipeline | TASK-004+ |
| DEF-AMP003-007 | TASK-003 | Cross-process file locking for idempotency store | TASK-004+ |
| DEF-AMP003-008 | TASK-003 | Live provider poll for UNKNOWN reconciliation | Future |
| DEF-T004-C1-01 | T004-C1 | Domain explicit segment_id on Scene | T004-E |
| DEF-T004-C1-02 | T004-C1 | Split TTS dialogue_id vs canonical UUID alignment | T004-E |
| DEF-T004-C1-03 | T004-C1 | Agnes Exception fallback bypass idempotency | **RESOLVED** — BYP-01 + BYP-02 removed |
| DEF-T004-C1-04 | T004-C1 | Image fallback bypasses visual_runtime | **PARTIAL C-3** — fallback semantic + multimodal boundary; full C-4 deferred |
| DEF-T004-C3-01 | T004-C3 | Production VLM/ASR semantic verification | Future — `evaluator_adapter.py` boundary only; HEURISTIC now |
| DEF-T004-C3-02 | T004-C3 | Product-plan PDF authoritative source | Not in repo — requirements from user spec + BUILD-04F docs |
| DEF-T004-C1-05 | T004-C1 | idx*10+i split fallback identity hack | T004-C C-2 |
| DEF-T004-C2B-01 | C2-2-B | BUILD-04A test_06 concurrent intermittent flake | Future maintenance |
