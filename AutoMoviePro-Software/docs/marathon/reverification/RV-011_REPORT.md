# RV-011 প্রতিবেদন — Trend + Freshness + SEO + Content-Gap

**Protocol:** AMP-002  
**Maps to:** AMP-001 TASK-010  
**Verdict:** VERIFIED_PASS  
**Checkpoint:** RV-011-PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Objective

Unique candidate-এর পর freshness, trend, SEO, content-gap signals সঠিকভাবে গণনা হয় এবং final score/ranking-এ প্রভাব ফেলে কিনা — independent runtime verification।

---

## ২. Pre-Audit

| Module | Role |
|--------|------|
| `trend.py` | Trend classification, SEO heuristic, content gap, decay |
| `scoring.py` | 12-dimension weighted `score_candidate()` |
| `topic_scoring.py` | Legacy trend/freshness/channel_fit engine |
| `ranking.py` | Diversity penalty + eligibility |
| `orchestrator.py` | Gap calc, research → score → rank |

### Gap (pre-fix)

- Freshness শুধু explicit `metadata.freshness` float — `discovered_at`/`researched_at` ব্যবহার হত না
- Invalid numeric inputs (NaN/inf) clamp ছিল না
- Exact historical duplicate-এ content gap min bound ambiguous
- `researched_at` orchestrator-এ stamp হত না

---

## ৩. Score Architecture

```
score_candidate()
  → score_topic() [legacy: trend, freshness, channel_fit]
  → dimensions (12) × DIMENSION_WEIGHTS
  → total_score (PASS ≥ 0.45)
```

| Dimension | Weight | Source | Label |
|-----------|--------|--------|-------|
| CHANNEL_RELEVANCE | 17% | `topic_scoring.channel_fit` | HEURISTIC |
| AUDIENCE_VALUE | 8% | legacy | HEURISTIC |
| RECENCY | 8% | legacy freshness / `resolve_freshness_score()` | HEURISTIC/METADATA |
| TREND_SIGNAL | 8% | legacy trend (capped if UNVERIFIED) | METADATA_HEURISTIC |
| SEARCH_INTENT | 8% | title token count | HEURISTIC |
| SEO_HEURISTIC_SCORE | 8% | `seo_heuristic_score()` | HEURISTIC (NOT live SEO) |
| EVIDENCE_AVAILABILITY | 9% | research evidence_count | LIVE (post-research) |
| CONTENT_GAP | 8% | `content_gap_score()` vs historical | HEURISTIC |
| NOVELTY | 8% | duplicate verdict | CONNECTED |
| FORMAT_FIT | 8% | LONG=0.85, SHORT=0.9 | HEURISTIC |
| PRODUCTION_FEASIBILITY | 5% | constant 0.8 | MOCK |
| DUPLICATE_RISK | 5% | duplicate verdict | CONNECTED |

**External trend API:** NOT_CONNECTED — trend from candidate metadata only.

---

## ৪. Freshness — VERIFIED (post-fix)

`resolve_freshness_score()`:
1. Explicit `metadata.freshness` if set
2. Else `freshness_from_timestamps(discovered_at, researched_at)` — 14-day half-life decay
3. Default 0.5

Runtime: newer timestamp → higher freshness; stale (120d) → < 0.3

---

## ৫. Trend — PARTIAL (metadata-driven)

- Source: `metadata.trend_score`, `trend_evidence`, `source_count`
- `classify_trend_from_signals()` — evidence required for TRENDING
- UNVERIFIED trend capped at 0.35 in legacy `score_topic()`
- `apply_trend_decay()` — TRENDING → LOW_RECENCY after 14 days
- **No external Google Trends / live feed** — `TREND_SIGNAL_SOURCE = metadata_heuristic`

Controlled ordering: trend 0.9 > 0.5 > 0.1 (with live evidence) — VERIFIED

---

## ৬. SEO — HEURISTIC (honest)

`seo_heuristic_score()` — clarity, specificity, niche keyword presence.  
**NOT** search volume, NOT external SEO API.  
`SEO_HEURISTIC_SOURCE = local_heuristic_v1`

Strong title > weak title in SEO dimension — VERIFIED

---

## ৭. Content Gap — VERIFIED

`content_gap_score(topic, historical)`:
- No historical → 0.7 default
- Exact canonical match → 0.05 (already covered)
- Jaccard max similarity → `1.0 - max_sim` (min 0.1)

Duplicate case: "How Black Holes Form" vs same historical → 0.05  
Novel related: "How Black Holes Affect Nearby Stars" → higher gap

Consistent with RV-010 historical duplicate corpus.

---

## ৮. Score Normalization — VERIFIED (post-fix)

`normalize_score_component()` — clamps [0,1], handles None/NaN/inf

---

## ৯. Weight Analysis

Sum of `DIMENSION_WEIGHTS` = 1.0  
No single dimension dominates (>17% max = CHANNEL_RELEVANCE)  
Trend influence: ~8% weight on TREND_SIGNAL dimension

---

## ১০. Long/Short — VERIFIED (documented)

- FORMAT_FIT: SHORT=0.9, LONG=0.85
- Separate `topic_id` per format
- Duplicate check format-agnostic (same title = duplicate)

---

## ১১. Daily Reranking — VERIFIED

`refresh_topic_intelligence()` re-evaluates reserve with research.  
`apply_trend_decay()` + timestamp-based freshness support signal aging.

---

## ১২. Determinism — VERIFIED

Same inputs → same ranking order (TEST-18)

---

## ১৩. Missing Data — VERIFIED

| Missing | Fallback |
|---------|----------|
| trend | TREND_SIGNAL_UNAVAILABLE, cap 0.35 |
| freshness | 0.5 default |
| SEO | 0.0–0.4 range from empty title |
| content gap | 0.7 if no historical |

---

## ১৪. Research Dependency — VERIFIED

Production path: research → factpack gate → score → rank (TEST-25)  
Invalid research → hard_blocked, no ranking eligibility

---

## ১৫. Cache / Versioning — VERIFIED

`scoring_rule_fingerprint()` — `SCORING_SIGNAL_VERSION` based  
Stateless per-call scoring (no result cache)  
Rule version change → fingerprint change

---

## ১৬. Concurrency — VERIFIED (thread-level)

20 workers parallel scoring — consistent valid scores

---

## ১৭. Production Path — VERIFIED

`run_topic_intelligence()` → research → `score_candidate()` → `rank_candidates()` → reserve  
All signal dimensions present in production output (TEST-24)

---

## ১৮. Problems Found

| # | Issue | Fix |
|---|-------|-----|
| P1 | Freshness ignored timestamps | `resolve_freshness_score()` |
| P2 | No numeric sanitization | `normalize_score_component()` |
| P3 | Exact historical gap not minimal | canonical match → 0.05 |
| P4 | researched_at not stamped | orchestrator metadata stamp |

---

## ১৯. Code Changes

| File | Change |
|------|--------|
| `pipeline/intelligence/trend.py` | Freshness resolution, normalization, fingerprint, exact gap |
| `pipeline/intelligence/scoring.py` | Use resolve_freshness_score, normalize dimensions |
| `pipeline/intelligence/orchestrator.py` | Stamp researched_at after research |
| `scripts/test_reverification_rv011.py` | 28 dedicated tests |

---

## ২০. Test Matrix

| ID | Test | Result |
|----|------|--------|
| TEST-01 | score structure | PASS |
| TEST-02–04 | freshness | PASS |
| TEST-05–06, 15 | trend | PASS |
| TEST-07–08, 16 | SEO | PASS |
| TEST-09–11, 17 | content gap | PASS |
| TEST-12–13 | normalization | PASS |
| TEST-14 | weight influence | PASS |
| TEST-18–19 | determinism/rerank | PASS |
| TEST-20 | LONG/SHORT | PASS |
| TEST-21–22 | cache fingerprint | PASS |
| TEST-23 | concurrency | PASS |
| TEST-24–25 | production | PASS |

**Dedicated suite:** 28/28 PASS

---

## ২১. Regression

| Suite | Result |
|-------|--------|
| RV-010 | 26/26 PASS |
| RV-009 | 27/27 PASS |
| RV-008 | 21/21 PASS |
| RV-007 | 20/20 PASS |
| RV-006 | 13/13 PASS |
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |

---

## ২২. Limitations

1. **Trend:** metadata-driven heuristic — no external trending API
2. **SEO:** local heuristic — no search volume / SERP data
3. **Freshness:** half-life model — not calendar/event aware
4. **RV-010 constraints preserved:** duplicate engine not rewritten

---

## ২৩. Deferred

| ID | Issue |
|----|-------|
| RV-011-DEF-001 | External trend API integration |
| RV-011-DEF-002 | Real SEO/search volume provider |
| RV-011-DEF-003 | Embedding-based content gap |

---

## ২৪. Final Verdict

**RV-011 = VERIFIED_PASS**

Mandatory criteria runtime evidence সহ পূরণ। Trend/SEO external limitations সৎভাবে HEURISTIC/PARTIAL হিসেবে document করা হয়েছে।

---

*AMP-002 RV-011 সম্পন্ন — RV-012 শুরু হয়নি।*
