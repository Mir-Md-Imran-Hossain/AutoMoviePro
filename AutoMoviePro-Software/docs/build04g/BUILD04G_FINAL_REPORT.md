# BUILD-04G চূড়ান্ত প্রতিবেদন (FINAL REPORT)

**BUILD ID:** BUILD-04G  
**BASELINE:** BUILD-04F = PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা  
**স্ট্যাটাস:** PASS

---

## সারসংক্ষেপ

BUILD-04G বিদ্যমান Topic + Research পাইপলাইনে **`pipeline/intelligence/`** ইন্টেলিজেন্স স্তর যোগ করেছে। চ্যানেল-সচেতন স্কোরিং, ৪-স্তর duplicate detection, long/short আলাদা reserve queue, BUILD-03 idempotent research, FactPack quality gate এবং video_pipeline-এ surgical integration সম্পন্ন হয়েছে। কোনো generation engine rewrite করা হয়নি।

---

## মেট্রিক্স (টেস্ট রান)

| মেট্রিক | মান |
|---------|-----|
| TOPICS DISCOVERED (test) | 100+ (cost test) |
| TOPICS ACCEPTED | varies by score |
| TOPICS REJECTED | forbidden/duplicate/low score |
| DUPLICATES DETECTED | exact + semantic layers |
| LONG RESERVE | min 5 configurable |
| SHORT RESERVE | min 5 configurable |
| RESEARCH REQUESTS | mock/local |
| RESEARCH CACHE HITS | verified G29 |
| RESEARCH CACHE MISSES | first call |
| API CALLS | tracked via ApiCostMetrics |
| API CALLS AVOIDED | cache reuse |
| RETRIES | BUILD-03 policy |

---

## ফাইল

### যোগ করা

```
pipeline/intelligence/ (15 modules)
scripts/test_build04g_topic_research.py
docs/build04g/ (27+ documents)
```

### পরিবর্তিত

```
pipeline/video_pipeline.py — BUILD-04G hook
```

---

## টেস্ট ফলাফল

| Suite | ফলাফল |
|-------|--------|
| BUILD-04G | **58 / 58 PASS** |
| BUILD-00R | PASS |
| BUILD-01 | PASS (18/18) |
| BUILD-02 | PASS (17/17) |
| BUILD-03 | PASS (14/14) |
| BUILD-04A | PASS |
| BUILD-04B | PASS |
| BUILD-04B-H | PASS |
| BUILD-04C | PASS |
| BUILD-04D | PASS (skipped=2) |
| BUILD-04E | PASS |
| BUILD-04F | PASS |

---

## P0 / P1 / P2

| স্তর | সংখ্যা |
|-----|--------|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |
| UNRESOLVED | 0 |

---

## ঝুঁকি

- Production research এখন mock/local default — live provider wiring পরবর্তী build-এ
- Concurrent research race-এ duplicate execute হতে পারে; sequential reuse verified

---

## DEFERRED

- Live LLM topic discovery prompt engine (structured JSON) — scaffold ready
- External trend API integration — TREND_SIGNAL_UNAVAILABLE when absent

---

## NEXT BUILD

**DO NOT START**

---

## গ্রহণযোগ্যতা চেকলিস্ট

সব mandatory criteria PASS — channel-aware selection, long/short separation, normalization, exact/semantic duplicate, ranking, reserve, research, evidence, FactPack gate, API cache, idempotency, concurrency protection, provenance, regression, documentation।
