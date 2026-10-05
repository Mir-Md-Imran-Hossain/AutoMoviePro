# Render Cost and Dependency Audit — BUILD-04D

## Mock suite metrics

| Metric | Value |
|--------|-------|
| Render requests (duplicate pairs) | 70 |
| Mock render invocations | 35 |
| Reused results | 35 |
| Duplicates prevented | 35 |
| Upstream API calls on render retry | **0** |

## Dependency separation (RULE D58)

| Event | Upstream regeneration |
|-------|----------------------|
| Render retry (same manifest) | **No** |
| Visual hash change in manifest | New render only |
| Script fingerprint change | New render only |
| Render failure | Does not call LLM/TTS/visual APIs |

Verified by test D33.
