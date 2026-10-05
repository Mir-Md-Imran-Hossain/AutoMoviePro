# SUBTITLE_RETRY_POLICY

Retry: FAILED_RETRYABLE provider/network errors (bounded max_attempts=3)

Non-retryable: malformed request, validation failures, wrong identity

UNKNOWN: reconcile first (no blind loop)

Infinite loop protection: bounded executor attempts + recorded repair reasons
