# TASK-005 প্রতিবেদন — Research Provider Boundary

**Protocol:** AMP-001  
**Task ID:** TASK-005  
**Status:** PASS  
**Checkpoint:** TASK-005-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## উদ্দেশ্য

MOCK এবং LIVE provider সম্পূর্ণ আলাদা; MOCK কখনো production default নয়; LIVE mode fake local evidence-কে external research হিসেবে উপস্থাপন করবে না।

---

## Root Cause / Gap

- Default ইতিমধ্যে `LIVE` (`app/config.py`)
- `resolve_research_use_mock()` production LIVE-এ explicit mock নিষিদ্ধ
- **Gap:** `LiveResearchProvider` `provider: "live"` লেবেল দিত — local `build_fact_pack` কে external মনে হতে পারত

---

## পরিবর্তন

| ফাইল | পরিবর্তন |
|------|----------|
| `pipeline/intelligence/research_provider.py` | LIVE → `live_local`, `external_api: False`; MOCK adapter → `mock`, `external_api: False` |
| `scripts/test_marathon_task005_research_provider_boundary.py` | **নতুন** 6টি test |

---

## Test Matrix

| Test | ফলাফল |
|------|--------|
| Default LIVE not MOCK | PASS |
| MOCK explicit env only | PASS |
| Production LIVE + mock forbidden | PASS |
| Provider types separated | PASS |
| LIVE no mock sources | PASS |
| MOCK explicitly labeled | PASS |

**মোট:** 6/6 PASS

---

## Regression

BUILD-04G-H 21/21, TASK-004 11/11 — PASS

---

## Checkpoint

`TASK-005-PASS`

---

## পরবর্তী

**TASK-006** — Real Research Execution
