# Render Failure Recovery — BUILD-04D

| Scenario | Behavior | Test |
|----------|----------|------|
| Transient network/FS error | Bounded retry | D24 |
| FFmpeg failure | FAILED, no infinite loop | D31 |
| UNKNOWN | reconcile first, no blind rerender | D20, D22 |
| Partial output | Rejected before promote | D18 |
| Corrupt/zero output | Not checkpointed | D12, D13 |
| Invalid SUCCEEDED record | Invalidated, regen | D11 pattern |
| Crash before render | IN_PROGRESS recovery | D19 |
| Crash after render | Reuse validated output | D21 |
