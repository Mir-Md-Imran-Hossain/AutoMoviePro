# T004-C2-2-C-3-FP — Failure Propagation Phase Report

**Checkpoint:** AMP003-T004-C2-C3-FP-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

> সম্পূর্ণ feature report: `T004_C2_SINGLE_AGNES_FAILURE_PROPAGATION.md`

---

## Current flow (post-fix)

```
agnes_keys present?
  → _resolve_single_agnes_beat_src()
  → outcome classification
  → SUCCESS/REUSED + valid path → return Path
  → IDENTITY_BLOCKED → raise AgnesOutcomeError
  → UNKNOWN → try_reconcile → raise if unresolved
  → FAILED_* → log → image fallback (if allowed)
  → Exception → log EXCEPTION → image fallback (if allowed)
  → no BYP-02
```

## Root cause

Pre-fix: structured non-success outcomes silently fell through to image fallback; UNKNOWN/IDENTITY not fail-closed; BYP-02 on Exception bypassed idempotency.

## Outcome semantics

| Outcome | Caller behavior |
|---------|---------------|
| SUCCESS | Return Agnes Path |
| REUSED | Return cached Path |
| FAILED_* | Explicit log + image fallback |
| UNKNOWN | Reconcile or raise |
| IDENTITY_BLOCKED | Raise (provider=0) |
| EXCEPTION | Image fallback (no direct Agnes) |

## BYP-02 status

**REMOVED** from single path. BYP-01 (split L1464) remains.

## Tests

20/20 dedicated + full regression PASS — see main report §১৯–২০.

## Final verdict

**PHASE STATUS: PASS**
