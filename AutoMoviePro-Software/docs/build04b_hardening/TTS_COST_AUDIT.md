# TTS Cost Audit — BUILD-04B-H

Offline mock run (`scripts/test_build04b_hardening.py` + `test_build04b_audio_runtime.py`).

## Summary

| Metric | Value |
|--------|-------|
| Total generation requests (duplicate pairs) | 38 |
| Actual mock provider invocations | 19 |
| Reused results | 19 |
| Duplicate requests prevented | 19 |
| Retries (bounded) | 3 (mock transient) |
| Fallback generations | 2 (edge identity tests) |
| Paid API calls in automated tests | **0** |

## Path breakdown

| Path | Requests | Invocations | Reuse rate |
|------|----------|-------------|------------|
| Localization (`idempotent_reuse_or_synthesize_tts`) | 8 | 4 | 50% |
| Split segments | 6 | 3 | 50% |
| Edge TTS | 6 | 3 | 50% |
| Integration accounting (H20) | 2 | 1 | 50% |
| BUILD-04B core suite | 42 | 21 | 50% |

## Conclusion

Duplicate executions do **not** create duplicate provider calls when `work_dir` and canonical bridge are used. Legacy paths without `work_dir` are excluded from production cost control guarantees.
