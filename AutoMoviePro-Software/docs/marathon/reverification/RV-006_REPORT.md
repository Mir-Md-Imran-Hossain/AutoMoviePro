# RV-006 প্রতিবেদন — Real Research Execution

**Protocol:** AMP-002  
**Maps to:** AMP-001 TASK-006  
**Verdict:** VERIFIED_PASS  
**Checkpoint:** RV-006-PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Requirement

Production research configured provider ব্যবহার করবে এবং result-এ সংরক্ষণ করবে:

- provider identity
- query
- timestamp
- source / evidence
- provenance / fingerprint
- persistence artifact

Local `build_fact_pack()` কে external live research হিসেবে উপস্থাপন করা যাবে না — `live_local` + `external_api=false` বাধ্যতামূলক।

---

## ২. Existing Implementation

| Component | File |
|-----------|------|
| Provider abstraction | `pipeline/intelligence/research_provider.py` |
| Runtime + idempotency | `pipeline/intelligence/research_runtime.py` |
| Fingerprint | `pipeline/intelligence/fingerprint.py` |
| Production callsite | `pipeline/intelligence/orchestrator.py` → `_research_candidate()` |

---

## ৩. Production Callsites

```
run_topic_intelligence()
    → _research_candidate()
        → execute_research_request()
            → get_research_provider(LIVE) | MockResearchProviderAdapter
            → IdempotentExecutor (claim/execute/reuse)
            → persist work_dir/research/{topic_id}.json
```

---

## ৪. Data Flow

```
ResearchRequest
    ↓ normalize query
    ↓ compute fingerprint (job_id aligned with idempotency)
    ↓ provider.research(req)
    ↓ _stamp_research_metadata()
    ↓ validate artifact (claims + sources required)
    ↓ atomic persist JSON
    ↓ ResearchResult (success only if artifact valid)
```

---

## ৫. Root Cause / Gaps Found

| Gap | Impact | Fix |
|-----|--------|-----|
| Fingerprint mismatch (`job_id` vs `topic_id`) | Persisted `research_fingerprint` ≠ `ResearchResult.fingerprint` | Aligned `compute_fingerprint` with executor inputs |
| Missing source not rejected at runtime | Unsafe research could PASS | `_validate_research_artifact()` requires claim sources |
| Tampered cache could report success | Invalid cache accepted on reuse | Final `success` re-validates loaded artifact |

---

## ৬. Changes

| File | Change |
|------|--------|
| `research_runtime.py` | `_validate_research_artifact()`, fingerprint alignment, artifact re-validation on success |
| `fingerprint.py` | `compute_research_fingerprint()` optional `job_id`/`provider` |
| `scripts/test_reverification_rv006.py` | **নতুন** — 13 runtime tests |

---

## ৭. Tests (Dedicated)

`python scripts/test_reverification_rv006.py` → **13/13 PASS**

| Category | Count |
|----------|-------|
| Vertical slice (LIVE local + orchestrator) | 1 |
| Provider boundary | 2 |
| Negative (unavailable, exception, empty, malformed, missing source/evidence, tampered cache, duplicate) | 9 |
| Idempotency reuse | 1 |

**নোট:** কোনো source string search test নেই — সব runtime behavior।

---

## ৮. Negative Tests

| Scenario | Expected | Result |
|----------|----------|--------|
| provider unavailable | success=False | PASS |
| provider exception | success=False | PASS |
| empty response | success=False | PASS |
| malformed (no claims) | success=False | PASS |
| missing source | success=False | PASS |
| tampered cache | success=False | PASS |
| duplicate concurrent | 1 provider call | PASS |
| live provider exception | success=False | PASS |

---

## ৯. Integration

- Orchestrator vertical slice: `run_topic_intelligence(use_mock_research=False)` → research success in orchestrator output

---

## ১০. Regression

| Suite | Result |
|-------|--------|
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |

---

## ১১. Evidence

**LIVE local artifact (runtime):**
- `provider`: `live_local`
- `external_api`: `false`
- `provider_kind`: `configured_local`
- `query`: normalized preserved
- `timestamp`: present
- `sources`: present
- `research_fingerprint`: matches `ResearchResult.fingerprint`

**Paid API calls:** 0

---

## ১২. Known Limitations

- External live API adapter নেই (RV-DEF-001) — `ENVIRONMENT_BLOCKED` for true external provider evidence
- `live_local` is configured local research, not external API — honestly labeled

---

## ১৩. Deferred

`REVERIFICATION_DEFERRED.md` → RV-DEF-001

---

## ১৪. Final Verdict

**VERIFIED_PASS** — RV-006-PASS

Acceptance criteria সব runtime evidence দ্বারা পূরণ হয়েছে (external API ছাড়া — documented deferred).

---

## পরবর্তী

**RV-007** — Research → Evidence → Final Ranking
