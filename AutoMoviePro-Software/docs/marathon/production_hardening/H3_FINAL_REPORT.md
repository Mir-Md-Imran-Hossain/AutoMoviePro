# H3 Final Report — Performance & Cost Control

**Date:** 2026-09-03  
**Final status:** `H3-PERFORMANCE-COST-PASS-WITH-LIMITATION`  
**Checkpoint:** `AMP004-H3-PERFORMANCE-COST-PASS-WITH-LIMITATION`

---

## 1. Executive Summary

H3 hardens cost/performance under existing authorities: tighter retry classification, documented nested attempt bounds, disciplined TTS legacy fallback, localization language dedupe + translate reuse cache, ffprobe duration cache, and usage/latency ledger (`COST_NOT_DETERMINABLE` for money). No second engines. Paid APIs = **0**. H1/H2/BUILD-03/04A/G + Phase-02→10 regressions PASS. P3 critic-skip / shared circuit / repair-overlap remain documented limitations.

---

## 2. Baseline

| Checkpoint | Status |
|------------|--------|
| H1 | `H1-PRODUCTION-RELIABILITY-PASS` |
| H2 | `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION` |
| H3 pre-audit | `AMP004-H3-PRE-AUDIT-PASS` |
| Phase-10 | `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS` |
| DEF-H2-007 | Still open (plaintext channel keys) |

---

## 3. H3 Pre-Audit Reference

`docs/marathon/production_hardening/H3_PRE_AUDIT.md` — GO_WITH_LIMITATIONS; DEF-H3-001…010.

---

## 4. Implementation Plan

`docs/marathon/production_hardening/H3_IMPLEMENTATION_PLAN.md`

---

## 5. Authority Map

Unchanged canonical map: BUILD-03 idempotency, H1 locks, BUILD-04F/G, ContinuityTracker, `render_bridge`, `ffmpeg_exec`, Artifact Verification, Publishability, H2 Settings. GenerationCache clarified as nested helper only.

---

## 6. Retry Hardening

- Expanded NON_RETRYABLE (auth/config/circuit/budget/credential/…).  
- Unlabeled errors → **UNKNOWN** (no blind expensive retry).  
- Explicit retryable terms include `transient` / `network` / `temporary`.  
- `worst_case_expensive_attempts()` documents nested product bound.

---

## 7. TTS Path Consolidation

- Canonical: `idempotent_synthesize_narration`.  
- Legacy `synthesize_narration` only if NON_RETRYABLE not raised, no usable artifact, once; metric `tts_legacy_fallback` + usage event.

---

## 8. FFmpeg / Render Path Consolidation

- Documented `idempotent_compose_final_video` as sole final-compose entry.  
- `ffprobe_duration` process cache (path+mtime+size) reduces repeat probes.

---

## 9. Localization Cost Control

- `dedupe_language_codes` on localize targets.  
- Translate text sidecar reuse under `work_dir/TRANSLATE_CACHE` (same source+locale).

---

## 10. Cache / Reuse Improvements

- Translate cache + ffprobe cache + existing BUILD-03/TTS sidecars.  
- No GenerationCache2.

---

## 11. Repair Cost Control

- Unchanged cycle caps (≤3). DEF-H3-010 deferred.

---

## 12. Critic / Intelligence Cost Control

- Critic skip unchanged (DEF-H3-008 deferred / known H2).  
- Research path unchanged.

---

## 13. Cost Accounting

- Extended `IdempotencyMetrics` + `H3_USAGE_LEDGER.json` via `record_usage_event`.  
- `monetary_cost = COST_NOT_DETERMINABLE` always.

---

## 14. Latency / Performance Accounting

- Events store `latency_sec` when provided; accounting never calls providers.

---

## 15. Concurrency Safety

- H1 lock identity + concurrent identical execute single provider proven in H3 tests.

---

## 16. Resource Efficiency

- Fewer ffprobe subprocesses via cache; fewer duplicate lang/translate calls.

---

## 17. Security Regression

- H2 suite PASS (20); production login/skip/dry_run helpers intact (H3 smoke).

---

## 18. Reliability Regression

- H1 suite PASS (9) after retry keyword fix for `transient`.

---

## 19. Focused Tests

| Command | Result |
|---------|--------|
| `python -m unittest scripts.test_amp004_h3_performance_cost -v` | **12/12 PASS** |

---

## 20. Full Regression

| Suite | Result |
|-------|--------|
| H1 reliability | **9 PASS** |
| H2 security | **20 PASS** |
| BUILD-03 | **PASS** (in combined run) |
| BUILD-04A | **PASS** |
| BUILD-04G + G-H1 | **PASS** |
| Phase-02→10 | **398 PASS** |
| Combined H1+H3+B03+04A | **OK** (~71s) |

---

## 21. Paid API Usage

**0**

---

## 22. Findings Closed

| ID | Status | Evidence |
|----|--------|----------|
| DEF-H3-001 | **CLOSED** | `worst_case_expensive_attempts` + metrics |
| DEF-H3-002 | **CLOSED** | TTS fallback discipline |
| DEF-H3-003 | **CLOSED** | dedupe + translate cache |
| DEF-H3-004 | **CLOSED** | ffprobe cache |
| DEF-H3-005 | **CLOSED** | GenerationCache docstring ownership |
| DEF-H3-006 | **CLOSED** | usage ledger (no USD) |
| DEF-H3-007 | **CLOSED** | classify_error UNKNOWN default + NON_RETRYABLE expand |

---

## 23. Findings Deferred

| ID | Sev | Reason | Risk | Future |
|----|-----|--------|------|--------|
| DEF-H3-008 | P3 | Critic skip is intentional cost/quality tradeoff | Lower critic coverage | Policy review |
| DEF-H3-009 | P3 | Shared Google circuit is ops isolation | Multi-job budget share | Process isolation docs |
| DEF-H3-010 | P3 | Repair overlap = DEF-AMP004-006 | Duplicate local FFmpeg work | Merge repair later |
| DEF-H2-007 | P2 | Out of H3 | At-rest keys | Future crypto |

---

## 24. Known Limitations

- No monetary pricing.  
- Critic skip / shared circuit / repair overlap deferred.  
- Channel keys at-rest plaintext (H2).  
- Probe cache is process-local (not cross-process).

---

## 25. Performance Evidence

- ffprobe cache: 2 calls → 1 subprocess (H3 test_30).  
- Translate cache: 2 requests → 1 provider mock call (test_21).  
- Concurrent 8 workers → 1 provider (test_41).

---

## 26. Cost-Control Evidence

- Config/auth errors: 1 attempt only (test_05).  
- Unlabeled: no retry (test_02).  
- Transient still retryable within max (test_03).  
- Ledger never invents USD.

---

## 27. Code-Quality Audit

- No new engines; no secret logging; accounting fail-soft; H1 locks untouched; no AMP_SKIP weakening.

---

## 28. Final Acceptance Criteria

A–Q satisfied for core H3 scope with documented P3 limitations → **PASS-WITH-LIMITATION**.

---

## 29. Final Status

```
H3-PERFORMANCE-COST-PASS-WITH-LIMITATION
```

---

## 30. Exact Checkpoint

```
AMP004-H3-PERFORMANCE-COST-PASS-WITH-LIMITATION
```

### Changed files

| Path | Reason | Authority | Tests |
|------|--------|-----------|-------|
| `pipeline/idempotency/retry_policy.py` | Retry tighten + bound helper | BUILD-03 retry | H3 + BUILD-03 |
| `pipeline/idempotency/metrics.py` | Usage/latency ledger | BUILD-03 metrics | H3 |
| `pipeline/video_pipeline.py` | TTS fallback discipline | tts_bridge | H3 |
| `pipeline/localization.py` | Dedupe + translate cache | localization | H3/P06 |
| `pipeline/compose.py` | ffprobe cache | FFmpeg compose | H3/P08 |
| `pipeline/generation_cache.py` | Ownership docstring | nested helper | — |
| `pipeline/idempotency/render_bridge.py` | Canonical compose docstring | render_bridge | — |
| `scripts/test_amp004_h3_performance_cost.py` | NEW | — | 12 PASS |
| Docs plan/report/state/audit/deferred | Traceability | — | — |

**STOP** — do not start H4/H5/Phase-11.
