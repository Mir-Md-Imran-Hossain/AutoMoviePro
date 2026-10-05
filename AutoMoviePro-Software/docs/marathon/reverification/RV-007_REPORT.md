# RV-007 প্রতিবেদন — Research → Evidence → FactPack → Final Ranking

**Protocol:** AMP-002  
**Maps to:** AMP-001 TASK-007  
**Verdict:** VERIFIED_PASS  
**Checkpoint:** RV-007-PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Objective

Research → Evidence → FactPack → Final Score → Ranking → Reserve chain বাস্তবে সঠিক order-এ কাজ করছে কিনা independent runtime verification।

---

## ২. Pre-Audit

AMP-001 report historical claim হিসেবে — truth নয়।  
বর্তমান codebase audit করা হয়েছে, প্রথমে কোনো code change ছাড়া।

---

## ৩. Existing Implementation

| Stage | File | Function |
|-------|------|----------|
| Orchestration | `orchestrator.py` | `run_topic_intelligence()` |
| Research | `research_runtime.py` | `execute_research_request()` |
| FactPack gate | `factpack_gate.py` | `validate_fact_pack()` |
| Scoring | `scoring.py` | `score_candidate()` |
| Ranking | `ranking.py` | `rank_candidates()` |
| Reserve | `reserve_queue.py` | `update_reserve()` |
| Production bridge | `bridge.py` | `enrich_channel_topic()` → orchestrator |
| Production entry | `video_pipeline.py` | `run_intelligence_gate()` → bridge |

---

## ৪. Production Call Graph

```
video_pipeline.run_intelligence_gate()
    → bridge.enrich_channel_topic()
        → orchestrator.run_topic_intelligence(do_research=True)
            → _preliminary_filter()
            → per candidate:
                → _research_candidate()
                    → execute_research_request()
                    → validate_fact_pack()
                → score_candidate(evidence_count=...)
            → rank_candidates(scores=scores)
            → update_reserve()
            → record_topic_provenance()
```

**TEST_ONLY paths:** `evaluate_candidates(do_research=False)` — legacy test API, production default `do_research=True`।

---

## ৫. Research → Evidence Flow

```
ResearchRequest(topic_id, query, canonical_topic)
    → execute_research_request()
    → fact_pack.claims
    → validate_fact_pack() → gate verdict
    → success = rr.success AND gate.verdict == PASS
    → evidence_count = len(claims)
```

প্রতিটি topic-এর research `research_results[topic_id]`-তে আলাদা সংরক্ষিত।

---

## ৬. FactPack Flow

| Case | Verdict | Runtime |
|------|---------|---------|
| Valid evidence (≥2 supported) | PASS | scoring continues |
| No fact_pack | RESEARCH_REQUIRED | hard_blocked |
| Unsupported only | RESEARCH_REQUIRED | hard_blocked |
| Conflict | RESEARCH_CONFLICT | hard_blocked |
| Insufficient (<2 supported) | RESEARCH_REQUIRED | hard_blocked |

Gate bypass করে ranking হয় না — `success=False` → `continue` before `score_candidate`.

---

## ৭. Scoring Flow

`score_candidate()` research-পরবর্তী `evidence_count` ব্যবহার করে `EVIDENCE_AVAILABILITY` dimension গণনা করে।  
Research fail হলে `hard_blocked=True`, `total_score=0`.

---

## ৮. Ranking Flow

`rank_candidates()` production path-এ `scores` dict পাস করে।  
`hard_blocked` → `eligible=False`.  
Diversity penalty প্রয়োগ।  
Sort by `total_score` descending.

---

## ৯. Reserve Flow

`update_reserve()` ranked eligible entries থেকে reserve file লেখে।  
`bridge.pick_topic_from_reserve()` → `select_topic_for_production()` → `consume_top()`.

---

## ১০. Problems Discovered

| # | সমস্যা | Severity |
|---|--------|----------|
| P1 | `do_research=False` path-এ `evidence_count` uninitialized (NameError risk) | P2 |
| P2 | `rank_candidates()` scores dict-এ না থাকলে `score_candidate(evidence_count=0)` দিয়ে silent rescore | P1 |

---

## ১১. Root Causes

1. `evidence_count` শুধু `if do_research` block-এ set — else branch missing init
2. `rank_candidates` fallback `or score_candidate()` research bypass path তৈরি করতে পারত

---

## ১২. Code Changes

| File | Change |
|------|--------|
| `orchestrator.py` | `evidence_count = 0` init before research branch |
| `ranking.py` | scores dict দেওয়া থাকলে missing entry → `MISSING_RESEARCH_SCORE` block, no silent rescore |
| `scripts/test_reverification_rv007.py` | **নতুন** — 20 runtime tests |

---

## ১৩. Positive Tests

| Test | Result |
|------|--------|
| Integration chain (research→gate→score→rank→reserve) | PASS |
| Research before ranking order (call order) | PASS |
| FactPack CASE-A valid | PASS |
| Scoring isolation (distinct fingerprints per topic) | PASS |
| Idempotency reuse | PASS |

---

## ১৪. Negative Tests

| ID | Scenario | Expected | Result |
|----|----------|----------|--------|
| TEST-01 | research missing | not eligible | PASS |
| TEST-02 | evidence missing | hard_blocked | PASS |
| TEST-03 | invalid FactPack | hard_blocked | PASS |
| TEST-04 | conflicting evidence | RESEARCH_CONFLICT | PASS |
| TEST-05 | prompt version change | fingerprint changes | PASS |
| TEST-06 | duplicate topic | filtered (0 evaluated) | PASS |
| TEST-07 | cross-topic contamination | distinct fingerprints + own claims | PASS |
| TEST-08 | ranking before research | order violation | PASS (not violated) |
| TEST-09 | gate fail before rank | hard_blocked, not eligible | PASS |
| TEST-10 | tampered cache | hard_blocked on re-run | PASS |

---

## ১৫. Integration Test

`test_positive_integration_chain` — full trace:
- research ✓ gate PASS ✓ scored ✓ ranked ✓ reserve ✓
- artifact `topic_intelligence_result.json` persisted ✓

---

## ১৬. Idempotency Test

Same topic দ্বিতীয় run → mock provider call count unchanged (reuse).

---

## ১৭. Cost-Control Test

12 concurrent threads, same fingerprint → 1 provider execution.

---

## ১৮. Regression Results

| Suite | Result |
|-------|--------|
| RV-007 | 20/20 PASS |
| RV-006 | 13/13 PASS |
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |

**Paid API calls:** 0

---

## ১৯. Evidence

```
python scripts/test_reverification_rv007.py → 20/20 PASS
```

কোনো source-string-only verification নেই। সব runtime behavior assertion।

---

## ২০. Limitations / PARTIAL

| Dimension | Status |
|-----------|--------|
| relevance | IMPLEMENTED |
| evidence quality | IMPLEMENTED (evidence_count) |
| freshness | PARTIAL (metadata-driven, not research timestamp in score) |
| duplicate penalty | IMPLEMENTED |
| trend signal | IMPLEMENTED (requires evidence for TRENDING) |
| SEO/content-gap | IMPLEMENTED (heuristic) |
| diversity | IMPLEMENTED (ranking penalty) |

---

## ২১. Deferred

- External API research (RV-DEF-001) — not in RV-007 scope
- `evaluate_candidates(do_research=False)` — legacy test API only

---

## ২২. Final Verdict

**VERIFIED_PASS** — RV-007-PASS

Mandatory acceptance criteria সব runtime evidence দ্বারা পূরণ হয়েছে।

---

**STOP** — RV-008 শুরু হয়নি (user command অনুযায়ী)।
