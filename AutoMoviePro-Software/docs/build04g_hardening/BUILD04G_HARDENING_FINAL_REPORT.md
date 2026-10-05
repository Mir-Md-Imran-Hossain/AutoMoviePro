# BUILD-04G-H চূড়ান্ত প্রতিবেদন (FINAL REPORT)

**BUILD ID:** BUILD-04G-H  
**মিশন:** Production Hardening & Intelligence Activation  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা  
**স্ট্যাটাস:** PASS

---

## সারসংক্ষেপ

BUILD-04G-H স্বাধীন অডিটের P0/P1 সমস্যাগুলো **সার্জিক্যালভাবে** ঠিক করেছে। সম্পূর্ণ পুনর্লিখন করা হয়নি। BUILD-03 idempotency, BUILD-04A–F অক্ষুণ্ণ।

---

## মূল ঠিকাকারী পরিবর্তন

| সমস্যা | সমাধান |
|--------|--------|
| P0-01 Lock registry race | `_REGISTRY_LOCK` + thread-safe `_store_lock()` |
| P0-01 Executor duplicate execute | `SUCCEEDED` prior → reuse (claim race fix) |
| P0-01 IN_PROGRESS wait | `_wait_for_completion()` + reuse |
| P0-02 Mock production default | `INTELLIGENCE_RESEARCH_MODE=LIVE` default |
| P0-03 Silent skip | Fail-closed `run_intelligence_gate()` |
| P1-01 Per-job reserve | `DATA_DIR/intelligence/reserves/ch{id}/` |
| P1-02 Weak refresh | `refresh_topic_intelligence()` rerank + discovery refill |
| P1-03 Rank before research | Research → evidence → final score → rank |
| P1-04 No discovery | `discover_topic_candidates()` pipeline |
| P1-06 Tech→history | `TECH_MARKERS`, default `general` not `history` |
| P1-09 Fake SEO | `SEO_HEURISTIC_SCORE` naming |
| P1-10 Fake trend | Evidence required for TRENDING |
| P1-12 Cosmetic invalidation | `cache_registry.py` version bumps |
| P1-13 Permissive FactPack | Min 2 supported claims, conflict detection |
| P1-17 Fixed .tmp | Unique temp + fsync + retry (Windows) |

---

## টেস্ট ফলাফল

| Suite | ফলাফল |
|-------|--------|
| BUILD-04G-H | **21 / 21 PASS** |
| BUILD-04G | **58 / 58 PASS** |
| BUILD-03 | PASS |
| BUILD-00R | PASS |
| BUILD-04F | PASS |

---

## P0/P1/P2

| স্তর | সংখ্যা |
|-----|--------|
| P0 | 0 (resolved) |
| P1 | 0 (resolved) |
| P2 | 0 |
| UNRESOLVED | 0 |
| ENVIRONMENT-BLOCKED | 0 |

---

## DEFERRED

- External live API research provider (Google/LLM) — LIVE mode uses `build_fact_pack` local provider; explicit external adapter deferred
- 100-round reserve writer stress on shared CI Windows paths — mitigated with retry

---

## NEXT BUILD

**DO NOT START** (BUILD-04H blocked until this PASS — **PASS achieved**)

---

## Logical checkpoints

- BUILD-04G-H-BASELINE
- BUILD-04G-H1 … H21
- BUILD-04G-H-COMPLETE

(Git tags not created — documented only)
