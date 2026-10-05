# Script Orphan Audit — BUILD-04C

| Check | Result |
|-------|--------|
| Script without topic | Rejected at validation |
| Script without FactPack when required | FactPack optional at director stage; hash empty if absent |
| Script without fingerprint | None on covered path |
| Script without provenance | None on successful execute/reuse |
| Generation without script artifact | Failed validation — not checkpointed |
| Checkpoint without script | IdempotentExecutor requires persist_fn output |
| Malformed script marked successful | Prevented by validate_plan_and_script |

## Storage

- Artifact: `{work_dir}/director_plan.json`
- Provenance: `{work_dir}/script_provenance/{fp[:24]}.json`

## Verdict

No orphans on canonical production path.
