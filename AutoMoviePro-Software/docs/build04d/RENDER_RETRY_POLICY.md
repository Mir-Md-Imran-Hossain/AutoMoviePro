# Render Retry Policy — BUILD-04D

## Retryable

- Temporary filesystem errors (ConnectionError)
- Transient FFmpeg failures (classified via retry_policy)
- Safe timeout with UNKNOWN state

## Non-retryable

- Invalid manifest
- Missing required assets
- Unsupported configuration
- Permanent FFmpeg rejection

## Bounds

`IdempotentExecutor.max_attempts = 3`

## Retry identity

Same fingerprint on retry — retry is not a new render request.

## Upstream

Render retry does **not** invoke script/visual/audio generation APIs.
