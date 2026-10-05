# Open-Source Phase 6G — Authority Audit

**Date:** 2026-09-09  
**Verdict:** **PASS**

| Claim | Evidence |
|-------|----------|
| No second duration engine | `alignment_is_not_second_duration_engine`; cites `resolve_duration_contract` |
| No second pacing authority | Hold via `decide_visual_hold_policy` only; `second_pacing_authority: false` |
| No second audio engine | Audio timeline is cited ffprobe/AudioPlan; no invented clock |
| No second subtitle engine | Untouched |
| No second semantic gate | `semantic_coverage` + attach path; alignment `creates_final_gate: false` |
| No second continuity engine | ContinuityTracker unchanged; cross_beat helper only |
| No second repair engine | BUILD-04F handoff + existing repair_loop |
| No second quality engine | Untouched |
| No second FFmpeg engine | Sampling/compose only |
| BUILD-03 unchanged | Idempotency path reused |
| AudioPlan / Duration Contract / ContinuityTracker / BUILD-04F / semantic_coverage | Remain sole authorities |
| UNKNOWN ≠ PASS | Proven `03_unknown.json` |
| HEURISTIC ≠ PROVIDER_VERIFIED | Explicit flags on semantic align |
| Fixed-N switching | Forbidden as hard rule |
| OpenMontage AGPL | **0** imports/copies in alignment layer |
| Customer isolation | Fail-closed cross-customer merge |

**Paid (session):** attempts **3** / successes **3** (`…syGE`); gen invocations **1**.
