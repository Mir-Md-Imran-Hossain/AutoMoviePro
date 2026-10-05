# SUBTITLE_FAILURE_RECOVERY

## Crash Before Generation
IN_PROGRESS claim → retry on restart

## Crash After Generation
Valid artifact + idempotency SUCCEEDED → reuse without duplicate provider call

## UNKNOWN
TimeoutError from provider → UNKNOWN state → reconcile before blind regenerate

## Partial Segment Recovery
Failed segment regenerates independently; passing segments retained
