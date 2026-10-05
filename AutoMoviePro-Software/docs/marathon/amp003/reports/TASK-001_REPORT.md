# TASK-001 প্রতিবেদন — Canonical Domain + Contract Integrity

**Marathon:** AMP-003  
**Task:** TASK-001  
**Checkpoint:** AMP003-T001-PASS  
**Verdict:** PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Objective

`domain/` canonical contract layer-এর UUID identity, schema versioning, serialization, validation, legacy adapters, registry completeness এবং backward compatibility runtime-এ verify করা।

---

## ২. Pre-Audit

| Area | Location | Pre-Audit Status |
|------|----------|------------------|
| Contract base | `domain/common.py` | VERIFIED |
| Enums / status taxonomy | `domain/enums.py` | VERIFIED |
| Domain models | `domain/*.py` | VERIFIED |
| Legacy adapters | `domain/adapters.py` | VERIFIED |
| Registry | `domain/registry.py` | PARTIAL (9 models missing) |
| Version compatibility | — | MISSING |
| BUILD-01 tests | `scripts/test_build01_contracts.py` | 18/18 PASS |

---

## ৩. Existing Architecture

```
ContractBase (UUID id, schema_version, extra=forbid)
    ↓
TimestampedContract (created_at, updated_at)
    ↓
Topic, FactPack, Scene, Job, ValidationResult, ...

CONTRACT_REGISTRY → producers/consumers metadata
domain/adapters.py → legacy payload → canonical contracts
```

---

## ৪. Gap Matrix

| Gap | Severity | Root Cause | Fix |
|-----|----------|------------|-----|
| Registry incomplete | P1 | Engagement/Render/JobAttempt/AppError not registered | Extended `CONTRACT_REGISTRY` (+9) |
| No major-version guard on deserialize | P1 | `from_json_dict` accepted any valid semver | `schema_versions_compatible` + `SchemaVersionMismatchError` |
| No deserialize helper | P2 | Scattered validation | `validate_contract_version`, `deserialize_contract` |

---

## ৫. Implementation

### `domain/common.py`
- `parse_schema_version()`, `schema_versions_compatible()`
- `SchemaVersionMismatchError`
- `ContractBase.from_json_dict()` — major version guard

### `domain/validation.py`
- `expected_schema_version()`, `validate_contract_version()`, `deserialize_contract()`

### `domain/registry.py`
- Added: JobAttempt, AppError, EngagementAction, Comment, Reply, Message, RenderArtifact, RenderManifest, RenderJob
- Added: `get_contract_spec()`, `registry_model_names()`

---

## ৬. Files Changed

- `domain/common.py`
- `domain/validation.py`
- `domain/registry.py`
- `domain/__init__.py`
- `scripts/test_amp003_task001.py`
- `docs/marathon/amp003/*` (state infrastructure)

---

## ৭. Tests

**Dedicated:** `scripts/test_amp003_task001.py` — **35/35 PASS**

| Category | Tests |
|----------|-------|
| UUID identity | 01–03 |
| Schema version | 04–09 |
| Serialization | 10–13 |
| Timestamps | 14–15 |
| Status taxonomy | 16–19 |
| Legacy adapters | 20–24 |
| Registry | 25–28 |
| Validation helpers | 29–31 |
| Error contracts | 32–33 |
| Backward compat | 34–35 |

---

## ৮. Regression

| Suite | Result |
|-------|--------|
| BUILD-01 contracts | 18/18 PASS |
| BUILD-00R imports | 5/5 PASS |

Legacy behavior unchanged — BUILD-01 full pass confirms no regression.

---

## ৯. Runtime Evidence

- Invalid UUID → `ValidationError` — TEST-02
- Unknown field → rejected (`extra=forbid`) — TEST-12
- Major version 2.0.0 → `SchemaVersionMismatchError` — TEST-06
- Minor 1.2.3 → accepted — TEST-07
- Legacy FSM `generate_short` → `JobState.GENERATING` — TEST-24
- Registry 28 models, all have `schema_version` — TEST-26

---

## ১০. Cost Analysis

No external API calls. All tests local/offline.

---

## ১১. Open-Source Audit

Pydantic v2 used for validation — existing dependency, no new OSS introduced.

---

## ১২. Limitations

- Cross-major migration adapter not implemented (DEF-AMP003-001)
- `created_at` field name used; no separate `created_at` alias for legacy payloads beyond iso parse

---

## ১৩. Deferred Issues

See `DEFERRED_ISSUES.md` — DEF-AMP003-001, DEF-AMP003-002

---

## ১৪. Evidence Matrix (সংক্ষিপ্ত)

| Requirement | Code | Test | Verdict |
|-------------|------|------|---------|
| UUID identity | `ContractBase._validate_id` | TEST-01–03 | PASS |
| Schema version format | `_validate_schema_version` | TEST-04–05 | PASS |
| Version mismatch | `from_json_dict` | TEST-06 | PASS |
| Serialization | `model_dump`/`validate` | TEST-10–11 | PASS |
| Unknown field block | `extra=forbid` | TEST-12 | PASS |
| Adapters | `domain/adapters.py` | TEST-20–24 | PASS |
| Registry | `CONTRACT_REGISTRY` | TEST-25–28 | PASS |
| Status taxonomy | `domain/enums.py` | TEST-16–19 | PASS |
| Backward compat | BUILD-01 + TEST-34–35 | regression | PASS |

---

## ১৫. Final Verdict

**TASK-001 = PASS**

Dedicated tests PASS, regression PASS, evidence complete, no unexplained P0/P1.

**Checkpoint:** AMP003-T001-PASS

---

*TASK-002 blocked until user issues next command or marathon continuation.*
