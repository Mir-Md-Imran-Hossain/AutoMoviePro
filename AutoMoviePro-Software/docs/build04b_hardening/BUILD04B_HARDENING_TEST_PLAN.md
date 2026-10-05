# BUILD-04B-H Hardening Test Plan

## Suite

`scripts/test_build04b_hardening.py` — offline, `MockAudioProvider` only (RULE 07).

## Mandatory tests

| ID | Name | Phase |
|----|------|-------|
| H01 | Localization idempotency | H-06 |
| H02 | Localization language identity | H-05 |
| H03 | Localization retry fingerprint | H-07 |
| H04 | Localization crash recovery | H-08 |
| H05 | Split segment identity | H-10 |
| H06 | Split duplicate prevention | H-12 |
| H07 | Split collision prevention | H-13 |
| H08 | Split partial recovery | H-14, H-15 |
| H09 | Edge TTS identity | H-18 |
| H10 | Edge TTS idempotency | H-21 |
| H11 | Edge TTS concurrency | H-23 |
| H12 | Edge TTS retry fingerprint | H-22 |
| H13 | UNKNOWN no blind edge | H-20 |
| H14 | Primary/fallback separation | H-24 |
| H15 | Invalid fallback rejected | H-25 |
| H16 | Provenance | H-26 |
| H18 | Complete traceability | H-32 |
| H19 | No direct bypass (localization AST) | H-28 |
| H20 | API-call accounting | H-31 |

## Regression (required)

| Suite | Script |
|-------|--------|
| BUILD-00R | `scripts/test_build_00r_imports.py` |
| BUILD-01 | `scripts/test_build01_contracts.py` |
| BUILD-02 | `scripts/test_build02_wiring.py` |
| BUILD-03 | `scripts/test_build03_idempotency.py` |
| BUILD-04A | `scripts/test_build04a_visual_runtime.py` |
| BUILD-04B | `scripts/test_build04b_audio_runtime.py` |

## Smoke

`GET /api/status` via FastAPI TestClient — expect HTTP 200, `ok: true`.

## Pass criteria

- 19/19 BUILD-04B-H tests PASS
- All regression suites PASS
- No paid provider calls in automated tests
