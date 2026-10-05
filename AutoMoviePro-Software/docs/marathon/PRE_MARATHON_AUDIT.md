# AMP-001 প্রি-ম্যারাথন অডিট (PRE_MARATHON_AUDIT)

**Protocol ID:** AMP-001  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা  
**স্ট্যাটাস:** COMPLETE  
**Marathon Status:** IN_PROGRESS

---

## ১. অডিট স্কোপ

বর্তমান working codebase (`AutoMoviePro-Software/`) কে source of truth হিসেবে ব্যবহার করা হয়েছে।  
পূর্ববর্তী BUILD-00R → BUILD-04G-H ডকুমেন্টেশন পড়া হয়েছে।  
**এই ধাপে কোনো production code পরিবর্তন করা হয়নি** — শুধুমাত্র অডিট ও ম্যারাথন state infrastructure।

---

## ২. কোডবেস সারাংশ

| স্তর | অবস্থান | ভূমিকা |
|------|---------|--------|
| Domain/Contracts | `domain/`, `pipeline/contracts/` | BUILD-01 enum ও contract |
| Wiring | `pipeline/wiring/` | BUILD-02 dependency injection |
| Idempotency | `pipeline/idempotency/` | BUILD-03 — fingerprint, store, executor |
| Runtime stages | `pipeline/stages/` | BUILD-04A–04F audio/visual/script/render/subtitle/quality |
| Intelligence | `pipeline/intelligence/` | BUILD-04G topic research, ranking, reserve, evidence |
| Entry | `pipeline/video_pipeline.py` | Production pipeline + intelligence gate hook |
| Config | `app/config.py` | `intelligence_research_mode`, `intelligence_mode` |
| Tests | `scripts/test_build*.py` | Per-build acceptance suites |

---

## ৩. পূর্ববর্তী বিল্ড স্ট্যাটাস

| BUILD | ডকুমেন্ট | ঘোষিত স্ট্যাটাস |
|-------|----------|-----------------|
| BUILD-04G | `docs/build04g/` | PASS (58/58) |
| BUILD-04G-H | `docs/build04g_hardening/` | PASS (21/21) |
| BUILD-04G-H1 | `docs/build04g_hardening/H1_*.md` | PASS (6/6) — idempotency only |

**নোট:** BUILD-04G-H ব্যাপক hardening ঘোষণা করেছে, কিন্তু AMP-001 প্রতিটি TASK আলাদাভাবে verify করবে। পূর্বের PASS ম্যারাথন TASK PASS-এর substitute নয়।

---

## ৪. বর্তমান টেস্ট বেসলাইন (অডিট সময়)

| Suite | ফলাফল | বিবরণ |
|-------|--------|--------|
| `compileall pipeline` | PASS | Syntax/import integrity |
| BUILD-00R | PASS | Import smoke |
| BUILD-01 | PASS | Contracts |
| BUILD-02 | PASS | Wiring |
| BUILD-03 | PASS | Idempotency (14 tests) |
| BUILD-04G | PASS | 58/58 |
| BUILD-04G-H | PASS | 21/21 |
| BUILD-04G-H1 | PASS | 6/6 — 100 rounds × 20 workers = 2000 attempts |

**Paid API calls during audit tests:** 0  
**Environment:** Windows 10, local Python, no external provider opt-in

---

## ৫. প্রাসঙ্গিক ফাইল — কী আছে / কী নেই

### ৫.১ Idempotency (TASK-001)

| আইটেম | অবস্থা |
|-------|--------|
| `store.py` — `_REGISTRY_LOCK` thread-safe lock registry | আছে |
| `store.py` — `get()` under store lock | আছে |
| `executor.py` — `execute_fn()` শুধু `claimed=True` | আছে |
| `executor.py` — `SUCCEEDED` reuse on claim race | আছে |
| `executor.py` — `_wait_for_completion()` for IN_PROGRESS | আছে |
| Dedicated concurrency test `test_build04g_h1_idempotency_concurrency.py` | আছে |
| Multi-process (cross-process) file locking | **নেই** — thread-level only |

### ৫.২ Reserve (TASK-002, TASK-003, TASK-016)

| আইটেম | অবস্থা |
|-------|--------|
| Persistent reserve `DATA_DIR/intelligence/reserves/ch{id}/` | আছে (BUILD-04G-H) |
| Atomic write with unique temp + fsync | আছে |
| Per-format LONG/SHORT paths | আছে |
| Marathon-level dedicated stress test | **আলাদা verify দরকার** (H2 test exists in hardening suite) |

### ৫.৩ Intelligence Gate (TASK-004)

| আইটেম | অবস্থা |
|-------|--------|
| `run_intelligence_gate()` fail-closed | আছে (BUILD-04G-H) |
| Marathon isolated verification | NOT_STARTED |

### ৫.৪ Research Provider (TASK-005, TASK-006)

| আইটেম | অবস্থা |
|-------|--------|
| `INTELLIGENCE_RESEARCH_MODE=LIVE` default | আছে |
| MOCK explicit opt-in | আছে |
| External live API adapter (Google/LLM) | **DEFERRED** — local `build_fact_pack` provider |
| Provenance fields (source, timestamp, query, provider) | আংশিক — marathon verify |

### ৫.৫ Pipeline Flow (TASK-007–TASK-015)

| আইটেম | অবস্থা |
|-------|--------|
| Research → evidence → ranking order | Implemented (H8) — marathon verify |
| Channel DNA hardening | Implemented (H7) — marathon verify |
| Discovery vs template distinction | Implemented (H6) — marathon verify |
| Trend evidence gate | Implemented (H9) — marathon verify |
| Semantic/multilingual duplicate | Implemented (H11) — marathon verify |
| Cache invalidation registry | Implemented (H13) — marathon verify |
| FactPack evidence gate | Implemented (H14) — marathon verify |
| Full provenance chain | Partial — marathon verify (TASK-014) |
| Daily refresh rerank | Implemented (H) — marathon verify (TASK-015) |

### ৫.৬ Integration & Environment (TASK-018–TASK-020)

| আইটেম | অবস্থা |
|-------|--------|
| Full chain integration test | **নেই** — TASK-018 |
| Clean environment reproducibility test | **নেই** — TASK-019 |
| Independent final audit | **নেই** — TASK-020 |

---

## ৬. BUILD-04G-H অডিট P0/P1 — বর্তমান মূল্যায়ন

PRE_HARDENING_BASELINE-এ তালিকাভুক্ত সমস্যাগুলোর বেশিরভাগ BUILD-04G-H-তে ঠিক হয়েছে বলে ঘোষিত।  
তবে AMP-001 প্রতিটি concern-কে সংশ্লিষ্ট TASK-এর acceptance criteria দিয়ে **পুনরায় verify** করবে।

| মূল P0 | ম্যারাথন TASK | কোডে implementation | Marathon verify |
|--------|---------------|---------------------|-----------------|
| Lock registry race | TASK-001 | হ্যাঁ | **PASS** (এই অডিটে) |
| Mock production default | TASK-005 | হ্যাঁ | NOT_STARTED |
| Silent intelligence skip | TASK-004 | হ্যাঁ | NOT_STARTED |
| Reserve per work_dir | TASK-002, TASK-003 | হ্যাঁ | NOT_STARTED |
| Rank before research | TASK-007 | হ্যাঁ | NOT_STARTED |

---

## ৭. Production vs Legacy Path

| Path | ব্যবহার |
|------|---------|
| `video_pipeline.py` → intelligence hook | Production entry |
| `pipeline/intelligence/orchestrator.py` | Topic intelligence orchestration |
| `pipeline/intelligence/bridge.py` | Pipeline bridge |
| `pipeline/idempotency/executor.py` | Stage-level idempotent execution |
| Per-`work_dir` reserve fallback | Legacy fallback when `channel_id=0` |

---

## ৮. পরিচিত সীমাবদ্ধতা (Marathon-এ document)

1. **Multi-process idempotency:** Thread-safe; cross-process duplicate prevention filesystem lock দিয়ে সম্পূর্ণ নিশ্চিত নয়।
2. **External research API:** LIVE mode local provider ব্যবহার করে; বাহ্যিক API adapter deferred।
3. **Windows shared CI paths:** Reserve writer stress — retry mitigation আছে, 100-round shared-path stress deferred।
4. **BUILD-04G-H PASS ≠ Marathon PASS:** প্রতিটি TASK আলাদা lifecycle।

---

## ৯. Marathon Infrastructure

| ফাইল | স্ট্যাটাস |
|------|----------|
| `docs/marathon/MARATHON_STATE.json` | তৈরি হয়েছে |
| `docs/marathon/TASK_REGISTRY.md` | তৈরি হয়েছে |
| `docs/marathon/DEPENDENCY_GRAPH.md` | তৈরি হয়েছে |
| `docs/marathon/DEFERRED_ISSUES.md` | তৈরি হয়েছে |

---

## ১০. TASK-001 প্রাথমিক মূল্যায়ন

**Objective:** একই fingerprint-এ concurrent execution একবারের বেশি হবে না।

**Discovery:**
- Root cause (BUILD-04G-H1): `claimed=False` হলেও `execute_fn()` fall-through।
- Fix already applied in `store.py` + `executor.py`।

**Test (অডিট সময় চালানো):**
```
python scripts/test_build04g_h1_idempotency_concurrency.py  → 6/6 PASS
duplicate_execution_rounds = 0
100 rounds × 20 workers = 2000 attempts
python scripts/test_build03_idempotency.py                  → PASS (regression)
```

**Acceptance criteria:** পূরণ হয়েছে → TASK-001 **PASS** (checkpoint: `TASK-001-PASS`)

---

## ১১. পরবর্তী পদক্ষেপ

1. ~~TASK-001 verify ও checkpoint~~ — সম্পন্ন
2. **TASK-002** — Multi-worker reserve atomicity (পরবর্তী)

---

## Logical Checkpoint

`AMP-001-PRE-MARATHON-AUDIT` (documented; git tag not created)
