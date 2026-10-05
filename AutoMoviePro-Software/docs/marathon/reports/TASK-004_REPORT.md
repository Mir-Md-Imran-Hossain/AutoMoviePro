# TASK-004 প্রতিবেদন — Fail-Closed Intelligence Gate

**Protocol:** AMP-001  
**Task ID:** TASK-004  
**Status:** PASS  
**Checkpoint:** TASK-004-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## উদ্দেশ্য

Production pipeline-এ valid intelligence result না থাকলে pipeline silently legacy topic path-এ fallback করে চলতে পারবে না।

---

## বর্তমান আচরণ (অডিট — পরিবর্তনের আগে)

### Production flow (আগে)

```
plan নেই + allow_duplicate=False
    ↓
reserve থেকে topic (ঐচ্ছিক)
    ↓
topic থাকলে → run_intelligence_gate() → block_if_not_pass()
    ↓
topic খালি হলে → gate skip
    ↓
trending_search legacy fallback (বাড়ি niche)
    ↓
director planning → video generation
```

### সমস্যা (Root Cause)

1. **P0 — Legacy bypass:** `topic` খালি থাকলে intelligence gate চলত না; `find_trending_gadgets()` সরাসরি topic সেট করত (লাইন 179–202)।
2. **P0 — Empty reserve bypass:** Reserve খালি + caller topic না দিলে production-এ gate PASS ছাড়াই pipeline এগোত।
3. **ঠিক ছিল:** Topic দিলে gate fail হলে `block_if_not_pass()` RuntimeError দিত — exception swallow হত না।

---

## Root Cause বিশ্লেষণ

| প্রশ্ন | উত্তর |
|--------|--------|
| Intelligence failure হলে pipeline কোথায় যায়? | Topic থাকলে → BLOCK (আগে থেকেই) |
| Missing topic হলে কী হয়? | **আগে:** trending fallback; **এখন:** BLOCK |
| Empty reserve হলে কী হয়? | **আগে:** trending; **এখন:** BLOCK |
| Research failure হলে কী হয়? | `enrich_channel_topic` → `accepted=False` → BLOCK |
| Gate exception হলে কী হয়? | `gate_error` → UNKNOWN → BLOCK |
| Legacy discovery gate bypass? | **আগে:** হ্যাঁ; **এখন:** না |
| Production vs test mode আলাদা? | হ্যাঁ — `DEVELOPMENT` bypass অনুমোদিত (explicit) |
| Invalid intelligence video পর্যন্ত? | **আগে:** trending path দিয়ে হতে পারত; **এখন:** না |

---

## পরিবর্তিত ফাইল

| ফাইল | পরিবর্তন |
|------|----------|
| `pipeline/intelligence/gate.py` | `assert_production_intelligence_validated()` যোগ |
| `pipeline/video_pipeline.py` | `intelligence_gate_passed` ট্র্যাক; production-এ legacy trending ব্লক |
| `scripts/test_marathon_task004_fail_closed_gate.py` | **নতুন** — 11টি acceptance test |

**অপরিবর্তিত (scope অনুযায়ী):** research provider, trend engine, SEO, duplicate, FactPack, script/visual/audio/render।

---

## Production flow (পরিবর্তনের পর)

```
plan নেই + allow_duplicate=False
    ↓
reserve → topic (ঐচ্ছিক)
    ↓
topic থাকলে → run_intelligence_gate() → block_if_not_pass()
    ↓
intelligence_gate_passed == False + PRODUCTION
    ↓
assert_production_intelligence_validated() → BLOCK
    ↓
topic খালি + PRODUCTION → legacy trending BLOCK (defense in depth)
    ↓
শুধুমাত্র validated intelligence সহ CONTINUE
```

---

## Test Matrix

| ID | Scenario | Expected | Result |
|----|----------|----------|--------|
| TEST-A | valid intelligence | CONTINUE | PASS |
| TEST-B | intelligence = None | BLOCK | PASS |
| TEST-C | intelligence exception | BLOCK | PASS |
| TEST-D | invalid intelligence | BLOCK | PASS |
| TEST-E | empty reserve | BLOCK | PASS |
| TEST-F | insufficient research | BLOCK | PASS |
| TEST-G | legacy available, intelligence unavailable | BLOCK + legacy না চলে | PASS |
| TEST-H | valid intelligence + valid topic | CONTINUE | PASS |
| EXTRA | DEVELOPMENT bypass isolation | bypass allowed | PASS |
| EXTRA | DEVELOPMENT assert no raise | isolated | PASS |
| INTEG | pipeline director reached after gate | CONTINUE | PASS |

**মোট:** 11/11 PASS

---

## Negative Test (TEST-G) — গুরুত্বপূর্ণ

```python
mock_trend.return_value = [{"name": "Legacy Gadget X"}]
generate_video(..., topic="", ...)
→ RuntimeError INTELLIGENCE_GATE_BLOCKED
mock_trend.assert_not_called()  # legacy চলেনি
```

---

## Regression

| Suite | ফলাফল |
|-------|--------|
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |
| TASK-002 | 2/2 PASS |

**Paid API calls:** 0

---

## Acceptance Evidence

| Criterion | Evidence |
|-----------|----------|
| production intelligence gate exists | `run_intelligence_gate()` + `video_pipeline.py` |
| invalid intelligence blocks | TEST-D |
| missing intelligence blocks | TEST-B |
| intelligence exception blocks | TEST-C |
| empty reserve blocks | TEST-E + TEST-G |
| insufficient research blocks | TEST-F |
| legacy fallback cannot bypass | TEST-G negative |
| valid intelligence continues | TEST-A, TEST-H, pipeline test |
| test/mock mode isolated | DEVELOPMENT tests |
| no unrelated rewrite | শুধু gate + video_pipeline hook |
| targeted tests PASS | 11/11 |
| negative tests PASS | TEST-G |
| regression PASS | উপরে |
| no P0/P1 | 0 |
| no unexplained bypass | trending production-এ বন্ধ |
| documentation complete | এই ফাইল |

---

## Unresolved / Deferred

- Resume path (`director_plan.json` exists) — gate skip intentional (partial job resume)
- `allow_duplicate=True` — admin override; gate skip intentional

---

## Checkpoint

`TASK-004-PASS` — documented; git tag তৈরি হয়নি

---

## পরবর্তী

**TASK-005** — Research Provider Boundary
