# BUILD-04C Test Plan

## Suite

`scripts/test_build04c_script_runtime.py` — 25 tests, offline `MockScriptProvider`.

| Test | Phase |
|------|-------|
| test_01_same_request_idempotency | 04C-14 |
| test_02_topic_change | 04C-15 |
| test_03_factpack_change | 04C-16 |
| test_04_prompt_version_change | 04C-17 |
| test_05_provider_change | 04C-18 |
| test_06_model_change | 04C-18 |
| test_07_retry_identity | 04C-19 |
| test_08_concurrent_duplicate | 04C-20 |
| test_09_existing_valid_reuse | 04C-21 |
| test_10_invalid_existing_script | 04C-22 |
| test_11–14 validation failures | 04C-23–27 |
| test_15–17 crash recovery | 04C-30–32 |
| test_19 repair generation | 04C-35 |
| test_20 infinite protection | 04C-36 |
| test_21–24 provenance/checkpoint/accounting | 04C-38–39, 04C-37 |
| test_no_direct_bypass | 04C-48 |

## Regression

BUILD-00R through BUILD-04B-H + BUILD-04C.

## Smoke

`GET /api/status` → 200.

## Real provider (opt-in)

Phases 04C-49/50 — not run in CI; mock-only PASS.
