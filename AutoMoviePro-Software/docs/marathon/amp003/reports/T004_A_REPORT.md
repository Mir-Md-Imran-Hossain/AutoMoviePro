# T004-A প্রতিবেদন — Production Call-Graph Audit

**Marathon:** AMP-003 / TASK-004  
**Sub-task:** T004-A  
**Checkpoint:** AMP003-T004-A-PASS  
**Verdict:** PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. উদ্দেশ্য

বর্তমান production video pipeline-এর বাস্তব call graph audit — কোন stage কোথা থেকে call হয়, কোন contract/idempotency bridge ব্যবহার হয়, কোথায় legacy bypass আছে — 100% callsite mapping।

**এই sub-task-এ কোনো code change করা হয়নি।**

---

## ২. Pre-Audit

| Area | Status |
|------|--------|
| Baseline AMP003-T003-PASS | VERIFIED |
| `video_pipeline.py` | Primary production root |
| `contract_wiring/` | Offline gate connected (TASK-002) |
| `idempotency/*_bridge.py` | Partial production coverage |
| BUILD-04A–04F runtimes | Exist, partially wired |

---

## ৩. Production Entry Points

| Entry | File | Notes |
|-------|------|-------|
| API | `app/main.py` | User generation |
| Scheduler | `app/scheduler_service.py` | Scheduled jobs |
| Live lab | `pipeline/live_lab.py` | Dev testing |
| Queue | `pipeline/orchestrator.py` | Metadata only — no exec |

---

## ৪. Call Graph Summary

Primary flow: `generate_video()` → intelligence gate → script (idempotent) → contract wiring gate → per-scene loop (TTS + visual via scene_builder) → render → quality gates → metadata/thumbnail/upload package → publication marker.

বিস্তারিত: `T004_A_CALL_GRAPH.md`

---

## ৫. Stage Coverage Matrix

| Stage | Mapped | Runtime Contract | Idempotency | Status |
|-------|--------|------------------|-------------|--------|
| Topic | ✓ | intelligence | research cache | VERIFIED |
| Research | ✓ | intelligence | research cache | VERIFIED |
| FactPack | ✓ | offline wiring | factpack_bridge (intel) | PARTIAL |
| Script | ✓ | offline + bridge | script_bridge | PARTIAL (fallback) |
| Scene | ✓ | offline only | resume_guard | GAP |
| Visual | ✓ | offline + bridge | agnes_bridge | PARTIAL |
| Audio | ✓ | offline + bridge | tts_bridge | PARTIAL |
| Localization | ✓ | offline | tts when work_dir | PARTIAL |
| Subtitle | ✓ | offline + bridge | subtitle_bridge | VERIFIED |
| Render | ✓ | offline + bridge | render_bridge | PARTIAL |
| Metadata | ✓ | plan fields | N/A | VERIFIED |
| Thumbnail | ✓ | offline | none | P2 |
| Upload | ✓ | package_export | N/A | VERIFIED |
| Publication | ✓ | dry_run + sync | N/A | VERIFIED |
| Engagement | ✓ | offline only | N/A | NOT_CONNECTED |

**Coverage: 15/15 stages mapped (100%)**

---

## ৬. Root Causes (Pre-implementation)

| ID | Issue | Severity |
|----|-------|----------|
| RC-A01 | Scene loop bypasses canonical Scene contract | P1 |
| RC-A02 | Script/render/audio legacy fallbacks | P1 |
| RC-A03 | Visual Agnes direct call on bridge fail | P1 |
| RC-A04 | No runtime failure propagation gate | P1 |
| RC-A05 | No fingerprint dependency invalidation | P1 |

---

## ৭. Surgical Plan (Next Sub-tasks)

| Sub-task | Target |
|----------|--------|
| T004-B | Scene contract runtime boundary |
| T004-C | Visual production path enforcement |
| T004-D | Audio/TTS production coverage |
| T004-E | Localization + subtitle binding |
| T004-F | Render contract enforcement |
| T004-G | Failure propagation |
| T004-H | Legacy fallback fail-closed |
| T004-I | Cross-stage dependency validation |
| T004-J | End-to-end contract trace |
| T004-K | Production bypass audit |
| T004-L | Final integration + regression |

---

## ৮. Tests

T004-A = audit only — dedicated test N/A.  
Baseline regression not re-run (no code changes).

---

## ৯. Evidence

- Report: `docs/marathon/amp003/reports/T004_A_CALL_GRAPH.md`
- 100% production callsite mapped
- 12 gaps identified for subsequent sub-tasks

---

## ১০. Final Verdict

**T004-A = PASS**  
**Checkpoint = AMP003-T004-A-PASS**  
**Next = T004-B (NOT_STARTED until this session continues)**

---

**STOP — T004-B implementation এই command-এ শুরু করা হয়নি (T004-A audit complete only).**
