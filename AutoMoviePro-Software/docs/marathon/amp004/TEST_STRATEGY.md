# Test Strategy — AMP-004 Audit

**Production code changed:** `false`

---

## Existing inventory (discovered)

| Bucket | Count / examples |
|--------|------------------|
| Total `scripts/test_*.py` | 76 |
| AMP-003 | 17 |
| BUILD-03/04 | 11 |
| AV / visual QA / ffmpeg | `test_av_quality_gates`, `test_visual_qa`, `test_ffmpeg_exec`, `test_black_tail_repair` |
| 04F | `test_build04f_quality_gate.py` (42 tests historically) |

---

## Per future domain — required test types

| Type | Purpose |
|------|---------|
| Unit | Validators, compilers, fingerprints |
| Contract | Schema / SceneIntent / RepairScope |
| Negative | Wrong action/entity → BLOCK |
| Corruption | Truncated mp4, bad wav |
| Concurrency | Idempotency locks (04G-H1, TASK-003) |
| Integration | Bridge → gate → repair |
| Regression | BUILD + AMP suites |
| Fixture media | OFFLINE_TEST_ONLY analyses |
| E2E | Golden harness / limited |

---

## Missing infrastructure

| Gap | Priority |
|-----|----------|
| Shared fixture media library for Layer-D | P1 |
| Master filtergraph contract tests | P2 |
| Loudness/ducking tests (when feature exists) | P1 later |
| Publishability AND multimodal BLOCKED | P0 next impl |
| No fake `assert True` semantic PASS | Doctrine |

---

## Read-only verification this audit

```
IMPORT_OK=13 IMPORT_FAIL=0
TEST_SCRIPTS=76
```

Full mutation-heavy E2E intentionally not re-run as “PASS fabrication”; prior AMP-003 regression evidence retained as historical, re-verify at ARCHITECTURE_FREEZE / next impl gate.
