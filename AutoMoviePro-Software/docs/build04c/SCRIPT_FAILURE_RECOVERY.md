# Script Failure Recovery — BUILD-04C

| Scenario | Behavior | Test |
|----------|----------|------|
| Transient network error | Bounded retry, same fingerprint | test_20 |
| Permanent rejection | FAILED_FINAL, no infinite loop | implicit |
| UNKNOWN (timeout/response lost) | state=UNKNOWN, no blind regen | test_16 |
| Invalid script | validation FAIL, not checkpointed | test_11–14 |
| Invalid existing SUCCEEDED | Invalidated, controlled regen | test_10 |
| Crash before provider | IN_PROGRESS → safe recovery | test_15 |
| Crash after persistence | Reuse on restart | test_17 |
| Concurrent duplicate | Single generation | test_08 |

## UNKNOWN policy

`RuntimeError("Script generation UNKNOWN — reconciliation required before retry")` from bridge when state persists UNKNOWN.

## No blind fallback

LLM router fallback inside `plan_niche_production` is part of the **same** generation attempt (single provider_fn invocation), not a separate idempotency identity.
