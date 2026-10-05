# Script Regeneration Policy — BUILD-04C

## Categories

| Type | Identity | Example |
|------|----------|---------|
| **Retry** | Same fingerprint | Network timeout on same request |
| **Replan** | New fingerprint (inputs changed) | Duplicate topic → blocked list grows |
| **Revision** | New fingerprint (`revision_id`) | Explicit repair revision |
| **Quality repair** | New fingerprint if inputs change | Humanizer rewrite (non-generating) |

## video_pipeline replan triggers

1. Duplicate topic detected → new `research_notes`, `blocked_products` → new fingerprint
2. Gadget template on history niche → new research constraints → new fingerprint

These are **intentional new requests**, not retries.

## Infinite loop protection

- `IdempotentExecutor.max_attempts = 3`
- No `while True` script regeneration in bridge
- FAILED_FINAL blocks repeat provider calls for same fingerprint

## Deferred

Full prompt-engineering regeneration loops — BUILD-04D+
