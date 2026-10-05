# BUILD-04B-H Hardening Final Report

## Executive summary

BUILD-04B-H completes the three deferred TTS runtime paths from BUILD-04B:

1. **localization.py** — all production TTS calls pass `work_dir` / idempotency context through `reuse_or_synthesize_tts` and `synthesize_narration` kwargs.
2. **scene_builder split-path** — per-segment TTS via `idempotent_synthesize_narration` with stable `segment_id`.
3. **edge_tts fallback** — canonical `idempotent_edge_tts` with distinct provider identity; UNKNOWN blocks blind fallback.

## Changes

| File | Change |
|------|--------|
| `pipeline/idempotency/tts_bridge.py` | Unified entry, edge wrap, mock_provider passthrough |
| `pipeline/idempotency/audio_request.py` | `segment_id` in identity |
| `pipeline/localization.py` | work_dir/job_id/scene_id/dialogue_id on all TTS paths |
| `pipeline/scene_builder.py` | Split + cutoff repair wrapped |
| `pipeline/tts_google.py` | Idempotency kwargs, edge bridge |
| `pipeline/tts_reuse.py` | Route to bridge when work_dir set |
| `scripts/test_build04b_hardening.py` | 19 offline hardening tests |

## Test results

| Suite | Result |
|-------|--------|
| BUILD-04B-H | 19/19 PASS |
| BUILD-04B | 21/21 PASS |
| BUILD-04A | 18/18 PASS |
| BUILD-03 | 14/14 PASS |
| BUILD-02 | 17/17 PASS |
| BUILD-01 | 18/18 PASS |
| BUILD-00R | 5/5 PASS |
| Smoke `/api/status` | PASS (200) |

## Residual items

| Priority | Item | Status |
|----------|------|--------|
| P2 | `av_self_repair_agent` direct TTS | BLOCKED (repair utility) |
| P2 | Legacy `tts_reuse` without work_dir | BLOCKED (callers must pass work_dir) |
| P2 | Dev scripts direct TTS | BLOCKED (non-production) |

## Five-pass verification

| Pass | Result |
|------|--------|
| PASS-1 CALLSITE | All production paths identified; matrix complete |
| PASS-2 IDENTITY | Language, segment, provider dimensions verified |
| PASS-3 IDEMPOTENCY | Duplicate → one generation (mock) |
| PASS-4 FAILURE/RECOVERY | UNKNOWN, retry, invalid audio, partial split |
| PASS-5 REGRESSION | All prior builds PASS |

---

```
BUILD-04B-H STATUS:
    PASS

LOCALIZATION TTS:
    PASS

SPLIT TTS:
    PASS

EDGE_TTS:
    PASS

ALL TTS CALLSITES:
    COVERED (production) / BLOCKED (legacy-repair-dev)

IDEMPOTENCY:
    PASS

DUPLICATE PREVENTION:
    PASS

CONCURRENT DUPLICATE:
    PASS

UNKNOWN HANDLING:
    PASS

AUDIO VALIDATION:
    PASS

DURATION:
    PASS

PROVENANCE:
    PASS

CHECKPOINT:
    PASS

CRASH RECOVERY:
    PASS

FALLBACK:
    PASS

API COST CONTROL:
    PASS

DIRECT TTS BYPASS:
    4 / N (legacy-repair-dev only; production pipeline 0)

IMPORT:
    PASS

BUILD-00R:
    PASS

BUILD-01:
    PASS

BUILD-02:
    PASS

BUILD-03:
    PASS

BUILD-04A:
    PASS

BUILD-04B:
    PASS

BUILD-04B-H TESTS:
    19 / 19

P0:
    0

P1:
    0

P2:
    3

UNRESOLVED:
    0 (production scope)

NEXT BUILD:
    BUILD-04C
```
