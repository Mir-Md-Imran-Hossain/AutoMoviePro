# TTS Failure Recovery — BUILD-04B-H

## Failure matrix (covered paths)

| Scenario | Behavior | Verified |
|----------|----------|----------|
| Success | Asset validated, provenance saved, checkpoint complete | H01, H06, H10 |
| Transient error | Bounded retry, same fingerprint | H03, H12, BUILD-04B test_08 |
| Permanent error | Failed state, no infinite retry | BUILD-04B test_16 |
| Timeout / UNKNOWN | No blind fallback; reconciliation required | H13, BUILD-04B test_13 |
| Invalid audio | Not checkpointed as success | H15, BUILD-04B test_11 |
| Crash before provider | Safe restart, no duplicate if unclaimed | H04, BUILD-04B test_12 |
| Crash after provider | Reuse on restart if artifact valid | H04, H08, BUILD-04B test_14 |
| Concurrent duplicate | Single generation | H11, BUILD-04B test_09 |
| Primary fail → edge | Distinct provider identity, edge idempotent | H09, H14, H21 |
| Split partial fail | Retry failed segment only | H08 |

## UNKNOWN handling (H-20)

```
Primary UNKNOWN → RuntimeError
                → NO edge_tts
                → reconcile via IdempotencyStore / ResumeResolver
                → then explicit retry or documented fallback policy
```

## Split partial recovery (H-14, H-15)

Segment-level idempotency records allow:

- Segment-01 PASS → reuse
- Segment-02 FAIL → retry Segment-02 only
- Segment-03 NOT_STARTED → generate when reached

## Localization crash recovery (H-04)

Simulated store interruption: second call reuses completed fingerprint without extra provider invocation.
