# BUILD04E_TEST_PLAN

| ID | Test | Status |
|----|------|--------|
| E01 | same-request idempotency | PASS |
| E02-E08 | identity fingerprints | PASS |
| E09 | concurrent duplicate prevention | PASS |
| E10-E11 | cache reuse/rejection | PASS |
| E12-E21 | validation failures | PASS |
| E22-E24 | split + localization | PASS |
| E25-E30 | recovery/repair | PASS |
| E31-E34 | provenance/checkpoint/orphan | PASS |
| E35-E38 | render dep + regression | PASS |

Run: `python scripts/test_build04e_subtitle_runtime.py`
