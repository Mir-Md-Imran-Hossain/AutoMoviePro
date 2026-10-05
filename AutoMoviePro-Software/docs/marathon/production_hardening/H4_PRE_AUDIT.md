# H4 Pre-Audit — Real Production Workflow QA

**Date:** 2026-09-03  
**Mode:** READ-ONLY (no source/test changes; no paid APIs; no H4 implementation)  
**Baseline checkpoints:**  
- H1: `H1-PRODUCTION-RELIABILITY-PASS`  
- H2: `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION`  
- H3: `AMP004-H3-PERFORMANCE-COST-PASS-WITH-LIMITATION`  
- Phase-10: `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS` / `AMP004-PHASE10-PASS`  
**Audit checkpoint:** `AMP004-H4-PRE-AUDIT-PASS`

---

## 1. Executive Summary

The canonical production call graph from `generate_video` through gates to `ready_to_upload` is **connected and fail-closed**. Offline industrial E2E (mock render + real gates) completes **PASS** with `UPLOAD_STATUS.json` only when publishability says publishable. Six failure injections produce **FAIL_DETECTED** and **no** `ready_to_upload`. Phase-09 + Phase-10 suites **97/97 PASS**. FFMPEG/FFPROBE available on this host.

**No P0/P1 workflow disconnect or publishability bypass found.** Remaining gaps are **P2/P3**: post-ready localization packaging order, E2E soft handoff when full SceneIntent enrichment absent, deferred VLM/ASR semantics, long-form/batch scale not fully certified, known H2/H3 limitations.

**Recommendation:** `H4_PRE_AUDIT_GO_WITH_LIMITATIONS`.

---

## 2. Baseline

| Item | Evidence |
|------|----------|
| H1 | Lock identity / process-safe claim — retained |
| H2 | dry_run + local-login fail-closed + AMP_SKIP blocked — smoke OK this audit |
| H3 | Usage ledger `COST_NOT_DETERMINABLE`; TTS fallback discipline — retained |
| Phase-10 | Real lavfi E2E + certification — report PASS |
| Deferred | DEF-H2-007; DEF-H3-008/009/010; DEF-AMP004-001 (VLM/ASR partial); DEF-AMP004-005/006 |
| Paid APIs this audit | **0** |

---

## 3. Canonical End-to-End Workflow

```
USER/CHANNEL
→ generate_video (video_pipeline)
→ assert_production_scenes_validated (SceneIntent + ContinuityTracker + audio/creative plans)
→ per-scene TTS (idempotent bridge) + visual (agnes_bridge / builders)
→ idempotent_compose_final_video (render_bridge → ffmpeg_exec)
→ ship / technical gates
→ Artifact Verification
→ Audio design gate
→ Localization gate (contract; mandatory if multilingual)
→ Creative production gate
→ Rendering integrity gate
→ BUILD-04F creative quality + evaluate_publishability (AND)
→ upload_status=ready_to_upload  [only if publishable]
→ (optional) localize_master_clip language packages
```

| Transition | Authority | Connected? | Method |
|------------|-----------|------------|--------|
| Script → SceneIntent | `scene_runtime.assert_production_scenes_validated` | YES | STATIC + E2E |
| Continuity | ContinuityTracker sole | YES | STATIC + inject |
| Prompt compile | `prompt_compiler` (+ legacy LEGACY dual) | YES / LEGACY | STATIC |
| Generation | BUILD-03 bridges | YES | STATIC |
| Artifact observe | Artifact Verification | YES | E2E/P04/P10 |
| Audio/TTS | AudioPlan + tts_bridge | YES | STATIC/H3 |
| Localization gate | localization_consistency | YES | STATIC |
| Loc packages | `localize_master_clip` | YES (often **after** ready) | STATIC |
| Creative | BUILD-04F + creative_production | YES | STATIC |
| Compose/RI | render_bridge + RI gate | YES | E2E/P08/P10 |
| Publishability | `evaluate_publishability` | YES | E2E inject |
| ready_to_upload | Only after publishable | YES | E2E |

Static call-graph audit: **PASS**, missing `[]`. Authority singletons: **no issues**. Bypass audit: **no BUG class**.

---

## 4. Single-Scene Workflow

| Boundary | Result | Evidence |
|----------|--------|----------|
| Fixture → scenes | PASS | Offline E2E fixture |
| Continuity/plans | PASS / PARTIAL* | E2E; *soft handoff if full preflight fails offline |
| Compose + observe | PASS | E2E final + gates |
| Publishability | PASS | `publishable=True` |
| ready_to_upload | PASS | Written only when publishable |

**Executed:** `run_e2e_industrial(use_mock_render=True)` → `final_status=PASS`.

---

## 5. Multi-Scene Workflow

| Check | Result | Evidence |
|-------|--------|----------|
| Ordering / identity | PASS | Phase-09 identity tests; ContinuityTracker entity IDs |
| Cross-scene contamination inject | PASS (detected) | `inject=continuity` → FAIL_DETECTED, no upload |
| Wrong project | PASS (detected) | `inject=wrong_project` → FAIL_DETECTED |
| Unaffected reuse | PASS (architecture) | BUILD-03 fingerprints; H3 concurrent reuse tests (prior) |

---

## 6. Continuity Workflow

- **Sole authority:** ContinuityTracker (`apply_production_continuity` in scene validation).  
- Contradictory entity inject: **FAIL_DETECTED**.  
- No second continuity engine required.  
- Repair vs continuity overlap remains deferred (DEF-AMP004-006) — local FFmpeg risk, not publish bypass.

---

## 7. Artifact Verification

| Invariant | Status |
|-----------|--------|
| PROMPT SUCCESS ≠ ARTIFACT SUCCESS | PASS (observe gates) |
| UNKNOWN ≠ PASS | PASS (RI/artifact UNKNOWN fail-closed in `generate_video`) |
| Missing visual inject | FAIL_DETECTED, no upload |

VLM/ASR deep semantic: **PARTIAL** (DEF-AMP004-001) — technical L0/L1 present; not full provider VLM.

---

## 8. Audio / TTS Workflow

| Item | Status |
|------|--------|
| Canonical TTS | `idempotent_synthesize_narration` |
| Legacy fallback | Disciplined (H3) — NON_RETRYABLE no fallback |
| Duplicate prevention | BUILD-03 + H3 |
| Audio gate before publish | YES in `generate_video` |
| Paid TTS this audit | 0 (not invoked in E2E mock path) |

---

## 9. Localization Workflow

| Item | Status |
|------|--------|
| Gate before publish (multilingual) | YES |
| Dedupe / translate reuse | H3 CLOSED |
| Package remux (`localize_master_clip`) | Often **after** `ready_to_upload` for EN master | **PARTIAL** |
| Duplicate language collision | Mitigated by H3 dedupe |

**Finding DEF-H4-001 (P2):** EN master can be marked `ready_to_upload` before localized packages finish; multilingual gate covers contracts, not necessarily completed remux packages.

---

## 10. Creative Quality Workflow

- BUILD-04F sole creative score + publishability AND.  
- Repair cycles capped (≤3).  
- Critic cost-skip remains (DEF-H3-008) — quality tradeoff, not publish AND bypass.  
- Offline heuristics labeled — UNKNOWN not silently PASS (Phase-02/09).

---

## 11. Cross-Modal Workflow

- `multimodal_consistency` + aggregate → publishability.  
- Injects `mandatory_unknown` / `multimodal_blocked`: **FAIL_DETECTED**, no upload.  
- Deterministic vs heuristic vs provider-verified: documented in Phase-09; VLM still deferred.

---

## 12. Rendering Workflow

- Canonical: `idempotent_compose_final_video` + `ffmpeg_exec`.  
- RI gate fail-closed on BLOCKED/UNKNOWN.  
- Host: FFMPEG=True, FFPROBE=True.  
- `inject=ffmpeg_fail` → FAIL_DETECTED, no upload.  
- Phase-10 real lavfi path previously certified.

---

## 13. ready_to_upload Boundary

| Path | Guard |
|------|-------|
| `generate_video` | Raises if not `publishability.publishable` before job update |
| E2E runner | Writes `UPLOAD_STATUS.json` **only if** `pub.publishable` |
| Alternate bypass | Bypass audit: **no BUG** |

All failure injects this audit: `upload=False`.

---

## 14. Failure Workflows

| Inject | final_status | upload | Evidence |
|--------|--------------|--------|----------|
| continuity | FAIL_DETECTED | False | Executed |
| missing_visual | FAIL_DETECTED | False | Executed |
| publishability_fail | FAIL_DETECTED | False | Executed |
| mandatory_unknown | FAIL_DETECTED | False | Executed |
| ffmpeg_fail | FAIL_DETECTED | False | Executed |
| wrong_project | FAIL_DETECTED | False | Executed |

---

## 15. Retry / Recovery

- H3 bounds + NON_RETRYABLE/UNKNOWN classification retained.  
- H1 locks retained (Phase suites green).  
- Interrupted work / stale reclaim: covered by BUILD-03 / H1 prior evidence — **PARTIAL** for full production crash matrix (not fully re-executed as live crash this audit).

---

## 16. Repeated Request Workflow

- Same fingerprint → reuse (BUILD-03 / H3 tests prior + architecture).  
- Changed inputs → new fingerprint.  
- This audit: static + prior H3 concurrent reuse; not a new paid generation loop.

---

## 17. Multilingual End-to-End Workflow

| Aspect | Classification |
|--------|----------------|
| Localization gate + contracts | SUPPORTED (P06 + E2E/P09) |
| Translate/TTS reuse | SUPPORTED (H3) |
| Full paid-free multi-lang remux E2E this session | PARTIAL (fixture/offline; packages after ready) |
| Locale collision | Mitigated |

---

## 18. Long-Form Workflow

| Aspect | Classification |
|--------|----------------|
| Duration budget / many scenes | PARTIALLY_SUPPORTED |
| Industrial long-form certification | UNKNOWN / not separately certified beyond short fixture |
| Cost × scenes × langs | Bounded but **POTENTIALLY EXPENSIVE** (H3) |

Do not claim full long-form production certification from this pre-audit alone.

---

## 19. Batch Workflow

| Aspect | Classification |
|--------|----------------|
| work_dir / job isolation | SUPPORTED (design + wrong_project detect) |
| Shared Google circuit across jobs | PARTIAL (DEF-H3-009) |
| Large multi-project load | NOT_SUPPORTED as certified claim |

---

## 20. Resume / Crash Recovery

| Aspect | Classification |
|--------|----------------|
| Checkpoints / idempotency resume | SAFE_TO_RESUME (BUILD-03 evidence) |
| Partial artifacts | PARTIAL (fail-closed publish) |
| Live crash of paid provider mid-call | PARTIAL / UNKNOWN without paid run |

---

## 21. Observability

| Field | Available |
|-------|-----------|
| job/scene/artifact IDs | YES (evidence + gates) |
| provider call counts (E2E/mock) | YES |
| H3 usage ledger | YES when work_dir used |
| monetary cost | COST_NOT_DETERMINABLE |
| Secret redaction | H2/evidence redact retained |

---

## 22. Cost / Performance Evidence

| Metric | This audit |
|--------|------------|
| Paid API calls | **0** |
| E2E provider | Mock render |
| Monetary | COST_NOT_DETERMINABLE |
| Failure injects | No upload amplification |

---

## 23. Production / Test Boundary

| Check | Result |
|-------|--------|
| admin/admin123 production login | Denied (H2 smoke) |
| AMP_SKIP_LOCALIZE in PRODUCTION | Blocked |
| dry_run_publish default | True (Settings without env override in smoke) |
| E2E does not weaken publishability | Phase-09 tests PASS |

---

## 24. Test Matrix

| Workflow | Local/Offline | Existing Test | Executed | Result | Evidence |
|----------|---------------|---------------|----------|--------|----------|
| Call graph / authorities | Static | P09/P10 | YES | PASS | authority_audit |
| Single-scene E2E | Mock | P09 runner | YES | PASS | run_e2e_industrial |
| Multi-scene / continuity | Inject | P09 | YES | PASS | inject continuity |
| Artifact verification | Fixture | P04/P09/P10 | YES | PASS | suites |
| Audio/TTS path | Static/H3 | P05/H3 | PARTIAL | PASS arch | no live TTS |
| Localization | Gate+H3 | P06 | PARTIAL | PASS/PARTIAL | post-ready package |
| Creative / publishability | Gates | P02/P07/P09 | YES | PASS | inject |
| Cross-modal UNKNOWN | Inject | P09 | YES | PASS | mandatory_unknown |
| Render / RI | Local FFmpeg | P08/P10 | YES | PASS | capability + suite |
| ready_to_upload | E2E | P09/P10 | YES | PASS | upload only if pub |
| Failure/recovery | Inject ×6 | P09 | YES | PASS | no false upload |
| Retry / H1 | Prior + suites | H1/H3/P09 | YES | PASS | 97 tests |
| Repeated request | Arch/H3 | BUILD-03 | PARTIAL | PASS | not re-gen |
| Multilingual full remux | Offline | P06 | PARTIAL | PARTIAL | DEF-H4-001 |
| Long-form | Fixture only | — | NO full | PARTIAL | classification |
| Batch isolation | Inject | P09 | PARTIAL | PASS/PARTIAL | wrong_project |
| Resume/crash | BUILD-03 prior | BUILD-03 | PARTIAL | PASS | prior |
| Observability | Evidence | P09 | YES | PASS | JSON evidence |
| Phase-09 suite | Offline | test_amp004_phase09… | YES | **72 implied in 97** | OK |
| Phase-10 suite | Offline | test_amp004_phase10… | YES | **25 in 97** | OK |

---

## 25. Findings by Severity

| ID | Sev | Workflow | Location | Behavior | Reachability | Evidence | Action |
|----|-----|----------|----------|----------|--------------|----------|--------|
| DEF-H4-001 | **P2** | Multilingual package | `video_pipeline` localize after ready | EN ready before lang packages | Production multi-lang | Source order + gate | H4: optionally gate package completion or clarify upload semantics |
| DEF-H4-002 | **P2** | SceneIntent E2E | `e2e_industrial.runner` soft handoff | Continue with plan rows if full validate fails offline | Offline E2E | Runner source | Keep fail-closed in live `generate_video`; document soft handoff |
| DEF-H4-003 | **P2** | Artifact semantics | DEF-AMP004-001 | VLM/ASR incomplete | Production semantic depth | Deferred issues | Future observation depth |
| DEF-H4-004 | **P2** | Long-form / batch | Scalability | Not fully certified | Ops | Classification | Document limits; optional H4 stress with fixtures |
| DEF-H4-005 | **P3** | Prompt | Dual compilers | LEGACY dual remains | Production | authority_audit | Merge later (DEF-AMP004-005) |
| DEF-H4-006 | **P3** | TTS | Legacy adapter | Still exists (disciplined) | Bridge failure | H3 | Monitor fallback metric |

**Carry-forward (not new):** DEF-H2-007, DEF-H3-008/009/010.

**P0:** 0 · **P1:** 0 · **P2:** 4 · **P3:** 2  

---

## 26. Authority Duplication Audit

No new workflow/orchestration/continuity/artifact/audio/localization/repair/render/publishability engines required or introduced by this audit. Existing authorities remain singular.

---

## 27. Known Limitations

- Offline E2E may soft-handoff SceneIntent when enrichment absent.  
- Localized remux packages may trail `ready_to_upload` for EN master.  
- VLM/ASR semantic observation incomplete.  
- Long-form/batch not fully load-certified.  
- H2 channel keys at-rest; H3 critic skip / shared circuit / repair overlap.  
- Monetary cost not determinable.

---

## 28. Minimal H4 Actions (future implementation only)

1. Clarify or tighten **ready_to_upload vs localized package completion** (DEF-H4-001).  
2. Document/contain E2E soft handoff vs production hard fail (DEF-H4-002).  
3. Expand offline multi-lang / long-form / resume fixtures without paid APIs.  
4. Do **not** create WorkflowEngine2.  
5. Preserve H1/H2/H3 boundaries and Phase-10 gates.

---

## 29. H4 Scope Decision

```
H4_PRE_AUDIT_GO_WITH_LIMITATIONS
```

**Rationale:** Core single/multi-scene → gates → publishability → ready_to_upload is demonstrably connected and fail-closed offline; no P0/P1. Limitations on multilingual packaging order, soft handoff, VLM depth, and long-form/batch certification.

---

## 30. Exact Checkpoint

```
AMP004-H4-PRE-AUDIT-PASS
```

---

```
H4_PRE_AUDIT_STATUS: GO_WITH_LIMITATIONS
```

**CHECKPOINT:** `AMP004-H4-PRE-AUDIT-PASS`

**STOP** — do not implement H4; do not start H5 / Phase-11.
