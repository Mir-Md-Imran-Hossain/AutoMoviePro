# H3 Implementation Plan — Performance & Cost Control

**Baseline:** `AMP004-H3-PRE-AUDIT-PASS`  
**Date:** 2026-09-03  

## Finding map

| Finding | Sev | Authority | Root cause | Minimal fix | Tests | Regression |
|---------|-----|-----------|------------|-------------|-------|------------|
| DEF-H3-001 | P2 | `retry_policy` + `IdempotencyMetrics` | Nested caps undocumented / unaccounted | Document bound helper + metrics counters | H3 nested/bound | BUILD-03 |
| DEF-H3-002 | P2 | `tts_bridge` / `video_pipeline` | Blind fallback to direct TTS | Fail-closed on NON_RETRYABLE; one legacy fallback + metric | H3 TTS | P05/P09 |
| DEF-H3-003 | P2 | `localization` | Duplicate lang entries; no translate reuse | Dedupe langs; text translate sidecar reuse | H3 loc | P06 |
| DEF-H3-004 | P2 | `compose.ffprobe_duration` | Repeated probes | Path+mtime+size probe cache | H3 probe | P08/P10 |
| DEF-H3-005 | P2 | `GenerationCache` | Nested vs BUILD-03 unclear | Docstring: nested helper only | Doc | — |
| DEF-H3-006 | P2 | `idempotency.metrics` | Incomplete accounting | Extend usage ledger (no USD) | H3 accounting | BUILD-03 |
| DEF-H3-007 | P2 | `retry_policy.classify_error` | Default RETRYABLE | Expand NON_RETRYABLE; unlabeled → UNKNOWN | H3 + BUILD-03 | BUILD-03 |
| DEF-H3-008 | P3 | playbook | Critic skip | Document only | — | DEFERRED |
| DEF-H3-009 | P3 | google gate | Shared circuit | Document only | — | DEFERRED |
| DEF-H3-010 | P3 | repair overlap | Deferred | Document only | — | DEFERRED |

## In scope
Retry tighten, TTS fallback discipline, loc dedupe/reuse, probe cache, usage/latency metrics extend, H3 tests.

## Out of scope
CostEngine2, Cache2, RetryEngine2, H4/H5/Phase-11, USD pricing, encrypt-at-rest, critic redesign, repair merge.

## Invariants
C1–C13 from H3 master command; H1 locks; H2 security; paid APIs = 0.

## Rollback
Revert listed files; BUILD-03/H1 suites remain green before merge.
