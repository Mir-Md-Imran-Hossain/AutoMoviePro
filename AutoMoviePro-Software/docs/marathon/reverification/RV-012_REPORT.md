# RV-012 প্রতিবেদন — Reserve Queue + Topic Lifecycle

**Protocol:** AMP-002  
**Maps to:** AMP-001 Reserve Queue / Topic Lifecycle  
**Verdict:** VERIFIED_PASS  
**Checkpoint:** RV-012-PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Objective

Topic Intelligence-এর ranked candidates সঠিকভাবে persistent reserve queue-তে প্রবেশ করে এবং Discovery → Duplicate → Research → Evidence → FactPack → Final Score → Ranking → Reserve → Consume → Published History পুরো lifecycle-এ data integrity বজায় থাকে কিনা — independent runtime verification।

---

## ২. Pre-Audit

| Module | Role |
|--------|------|
| `reserve_queue.py` | Persistent JSON queue, load/save, update, consume, repair |
| `orchestrator.py` | `run_topic_intelligence()` → rank → `update_reserve()`; `select_topic_for_production()` → `consume_top()`; `refresh_topic_intelligence()` |
| `bridge.py` | `pick_topic_from_reserve()` → production consume path |
| `candidates.py` | Candidate normalization for refresh re-eval |
| `ranking.py` | Score-based ordering before reserve admission |
| `scoring.py` | Final score + hard_block gate |
| `duplicate.py` | Historical/semantic duplicate corpus (RV-010 integration) |

### Production callsites (verified)

| Function | Caller | Path |
|----------|--------|------|
| `update_reserve()` | `orchestrator.run_topic_intelligence()` | Ranked eligible → reserve |
| `consume_top()` | `orchestrator.select_topic_for_production()` | Reserve → production |
| `pick_topic_from_reserve()` | `bridge.py` | Video pipeline entry |
| `repair_reserve()` | `refresh_topic_intelligence()` | Daily maintenance |
| `load_reserve()` | `run_topic_intelligence()` auto_discover blocked list | Refill context |

**Bypass audit:** Production code-এ `save_reserve()` সরাসরি call নেই — শুধু test suite-এ। Reserve mutation production path = `update_reserve` / `consume_top` / `repair_reserve` only — VERIFIED।

### Gap (pre-fix)

- `update_reserve()` পুরো queue **replace** করত — refresh merge/idempotency weak
- Reserve entry-তে `channel_id`, `language`, `fingerprint`, `refreshed_at` stamp ছিল না
- Tie-break deterministic ছিল না reserve ordering-এ
- `validate_reserve_integrity()` CONSUMED status reject করত না

---

## ৩. Reserve Architecture

```
run_topic_intelligence()
  → rank_candidates()
  → update_reserve(LONG/SHORT)   [merge + sort + persist]

select_topic_for_production() / pick_topic_from_reserve()
  → consume_top()                [pop rank-1, re-rank remainder]

refresh_topic_intelligence()
  → repair_reserve()
  → re-evaluate existing entries
  → auto_discover if count < 5
```

**Storage path (persistent):**

`DATA_DIR/intelligence/reserves/ch{channel_id}/{lang}/{long|short}_topic_reserve.json`

`channel_id=0` হলে fallback: `{work_dir}/intelligence/{long|short}_topic_reserve.json`

---

## ৪. Data Model

| Field | Status | Runtime |
|-------|--------|---------|
| `topic_id` | VERIFIED | Candidate থেকে copy; consume/provenance-এ ব্যবহৃত |
| `topic` / `title` | VERIFIED | Primary display key |
| `channel_id` | VERIFIED (post-fix) | `normalize_reserve_entry()`-এ stamp |
| `format` | VERIFIED (post-fix) | LONG/SHORT |
| `language` | VERIFIED (post-fix) | Path segment + entry field |
| `score` | VERIFIED | `total_score` float on entry |
| `rank` | VERIFIED | 1 = next production topic |
| `fingerprint` | VERIFIED (post-fix) | `discovery_fingerprint` or `topic_id` |
| `created_at` | NOT_IMPLEMENTED | — |
| `reserved_at` | VERIFIED | First admission timestamp |
| `refreshed_at` | VERIFIED (post-fix) | Score refresh timestamp |
| `status` | VERIFIED | RESERVED / CONSUMED (on pop, not kept in queue) |
| `reserve_schema_version` | VERIFIED (post-fix) | `RESERVE_SCHEMA_VERSION = 1` |

---

## ৫. Channel Isolation — VERIFIED

প্রতি `channel_id` আলাদা persistent path (`ch4010`, `ch4020`, `ch4030`)।  
Channel-A topic Channel-B queue-তে যায় না — TEST-02 runtime PASS।

---

## ৬. LONG/SHORT Isolation — VERIFIED

আলাদা file: `long_topic_reserve.json` / `short_topic_reserve.json`  
LONG refresh শুধু LONG queue পরিবর্তন করে — SHORT অপরিবর্তিত — TEST-03 PASS।  
RV-009 format handling ও RV-010 duplicate policy-এর সঙ্গে সামঞ্জস্যপূর্ণ (same title cross-format = duplicate at intelligence layer)।

---

## ৭. Language Handling — VERIFIED

Reserve architecture **language-aware**: path-এ `{lang}` segment (`en`, `bn`, `hi`)।  
এক ভাষার topic অন্য ভাষার queue-তে যায় না — TEST-04 PASS।

---

## ৮. Minimum Reserve — VERIFIED

`DEFAULT_RESERVE_MIN = 5` (`contracts.py`, `TOPIC_RESERVE_QUEUE_POLICY.md`)

| Queue count | `needs_discovery` |
|-------------|-----------------|
| 0–4 | `true` |
| ≥5 | `false` |

`refresh_topic_intelligence()` count < 5 হলে `auto_discover=True` refill trigger — TEST-05 PASS।

---

## ৯. Ranking Order — VERIFIED

Score descending: A(0.95) > B(0.80) > C(0.65) → queue order A, B, C — TEST-06 PASS।

Tie-break: same score → `topic_id` lexicographic ascending — deterministic — TEST-07 PASS।

---

## ১০. Daily Refresh — VERIFIED

Existing reserve re-score/update-এ B score বৃদ্ধি পেলে queue reorder (B প্রথম) — TEST-08 PASS।  
Historical duplicate `_preliminary_filter()`-এ reject — published topic reserve-এ ফিরে আসে না — TEST-12 PASS।

---

## ১১. Queue Stability — VERIFIED

একই ranked input দিয়ে repeated `update_reserve()` → duplicate item তৈরি হয় না — TEST-09 PASS।

---

## ১২. Consume Lifecycle — VERIFIED

`consume_top()` → rank-1 topic selected, queue থেকে remove, remainder re-ranked — TEST-10 PASS।  
`pick_topic_from_reserve()` production integration — TEST-24 PASS।

---

## ১৩. Failed-Job Behavior — UNDEFINED_POLICY (documented)

Consume-এর পর topic queue থেকে স্থায়ীভাবে সরে যায়।  
Video generation fail হলে automatic re-queue / retry state **বর্তমান codebase-এ নেই** — UNDEFINED_POLICY।  
TEST-11: consume → empty queue, no auto-return — actual behavior documented।

---

## ১৪. Publication Lifecycle — VERIFIED

`historical_topics` corpus-এ published topic থাকলে `_preliminary_filter()` DUPLICATE reject → reserve admission block — RV-010 integration — TEST-12 PASS।

---

## ১৫. Refresh Merge — VERIFIED (post-fix)

`merge_reserve_entries()`:
- Existing A,B,C + new B,C,D,E → duplicate B/C merge, D/E add, A preserved
- Higher score wins on key collision — TEST-13 PASS

---

## ১৬. Priority Update — VERIFIED

Score update: C→0.95 reorder → C, A, B — TEST-14 PASS。  
Reorder trigger: `update_reserve()` refresh (daily maintenance সহ)।

---

## ১৭. Atomicity — VERIFIED (thread-level)

| Test | Workers | Result |
|------|---------|--------|
| Concurrent enqueue | 20 | 0 duplicate keys |
| Concurrent consume | 20 | 0 double-consume |
| Concurrent refresh | 20 | 0 duplicate keys |

**Process-level locking:** NOT_CONNECTED — same DEF-001 limitation as RV-010 (thread lock only)।

---

## ১৮. Crash Recovery — VERIFIED

Malformed JSON → quarantine `.corrupt`, load returns `[]` — explicit recovery — TEST-18 PASS。  
Atomic write (`tmp` + `os.replace`) partial main-file corruption prevent করে।

---

## ১৯. Persistence — VERIFIED

enqueue → persist → reload → same titles/ranks — TEST-19 PASS。  
`channel_id≠0` → `DATA_DIR` persistent path survives process restart。

---

## ২০. Corruption Handling — VERIFIED

| Case | Behavior |
|------|----------|
| Empty file | `[]` |
| Malformed JSON | Quarantine + `[]` |
| Duplicate records | `repair_reserve()` dedup |
| Invalid status | Removed on repair |
| Missing title | Flagged + repaired |

TEST-20, TEST-21 PASS。

---

## ২১. Idempotency — VERIFIED (post-fix)

`reserve_refresh_fingerprint()` + `merge_reserve_entries()` — same input repeated refresh → no duplicate items — TEST-22 PASS。

---

## ২২. Cost Control — VERIFIED

Reserve refresh নিজে discovery/research trigger করে না — শুধু `refresh_topic_intelligence()` / orchestrator path।  
`update_reserve()` local JSON merge only — `external_api=false`。  
Repeated refresh same ranked → no extra provider calls (merge only)。

---

## ২৩. Bypass Audit — VERIFIED

- No production `save_reserve()` bypass
- No direct JSON modification in production path
- `orchestrator.py` uses `update_reserve` only — TEST-25 PASS

---

## ২৪. Problems & Root Causes

| # | Problem | Root Cause | Fix |
|---|---------|------------|-----|
| P1 | Refresh merge missing | `update_reserve` full replace | `merge_reserve_entries()` + load-merge-save under lock |
| P2 | Entry schema incomplete | No normalize helper | `normalize_reserve_entry()` |
| P3 | Non-deterministic tie order | Sort by score only | Tie-break `topic_id` |
| P4 | CONSUMED in queue undetected | validate gap | Added CONSUMED to invalid status |

---

## ২৫. Code Changes

| File | Change |
|------|--------|
| `pipeline/intelligence/reserve_queue.py` | `RESERVE_SCHEMA_VERSION`, `normalize_reserve_entry`, `merge_reserve_entries`, `reserve_refresh_fingerprint`, merge-based `update_reserve`, strengthened `validate_reserve_integrity` |
| `scripts/test_reverification_rv012.py` | 25 dedicated runtime tests |

---

## ২৬. Tests

**Dedicated:** `scripts/test_reverification_rv012.py` — **25/25 PASS**

| ID | Test |
|----|------|
| TEST-01 | Reserve schema |
| TEST-02 | Channel isolation |
| TEST-03 | LONG/SHORT isolation |
| TEST-04 | Language isolation |
| TEST-05 | Minimum reserve |
| TEST-06 | Ranking order |
| TEST-07 | Deterministic tie-break |
| TEST-08 | Daily refresh reorder |
| TEST-09 | Repeated refresh stable |
| TEST-10 | Consume lifecycle |
| TEST-11 | Failed-job (UNDEFINED_POLICY) |
| TEST-12 | Publication blocks rediscovery |
| TEST-13 | Refresh merge |
| TEST-14 | Priority update |
| TEST-15 | Concurrent enqueue |
| TEST-16 | Concurrent consume |
| TEST-17 | Concurrent refresh |
| TEST-18 | Crash recovery |
| TEST-19 | Persistence reload |
| TEST-20 | Corrupted queue repair |
| TEST-21 | Schema mismatch / empty |
| TEST-22 | Idempotent refresh |
| TEST-23 | Duplicate prevention |
| TEST-24 | Production integration |
| TEST-25 | Bypass audit |

---

## ২৭. Regression

| Suite | Result |
|-------|--------|
| RV-011 | 28/28 PASS |
| RV-010 | 26/26 PASS |
| RV-009 | 27/27 PASS |
| RV-008 | 21/21 PASS |
| RV-007 | 20/20 PASS |
| RV-006 | 13/13 PASS |
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |

---

## ২৮. Evidence Matrix (সংক্ষিপ্ত)

| Requirement | Code Location | Test | Verdict |
|-------------|---------------|------|---------|
| Reserve schema | `normalize_reserve_entry()` | TEST-01 | PASS |
| Channel isolation | `persistent_reserve_path()` | TEST-02 | PASS |
| LONG/SHORT isolation | `reserve_path()` format segment | TEST-03 | PASS |
| Language isolation | path `{lang}/` | TEST-04 | PASS |
| Min reserve 5 | `DEFAULT_RESERVE_MIN`, `needs_discovery` | TEST-05 | PASS |
| Ranking order | `merge_reserve_entries` sort | TEST-06 | PASS |
| Tie-break | sort key tuple | TEST-07 | PASS |
| Daily refresh | score update merge | TEST-08 | PASS |
| Repeated refresh safe | merge dedup | TEST-09 | PASS |
| Consume lifecycle | `consume_top()` | TEST-10 | PASS |
| Failed job | — | TEST-11 | UNDEFINED_POLICY |
| Published block | `_preliminary_filter` + historical | TEST-12 | PASS |
| Refresh merge | `merge_reserve_entries()` | TEST-13 | PASS |
| Priority update | merge sort | TEST-14 | PASS |
| Concurrent enqueue | thread lock | TEST-15 | PASS |
| Concurrent consume | `_lock_for` | TEST-16 | PASS |
| Concurrent refresh | atomic merge | TEST-17 | PASS |
| Crash recovery | `_read_json` quarantine | TEST-18 | PASS |
| Persistence | JSON atomic write | TEST-19 | PASS |
| Corruption repair | `repair_reserve()` | TEST-20 | PASS |
| Idempotency | fingerprint + merge | TEST-22 | PASS |
| Production path | `bridge.pick_topic_from_reserve` | TEST-24 | PASS |
| Bypass audit | orchestrator only update_reserve | TEST-25 | PASS |

---

## ২৯. Limitations

1. **Failed-job retry:** UNDEFINED_POLICY — consume = permanent dequeue
2. **Process-level lock:** Thread-only; multi-process workers same host-এ race সম্ভব (DEF-001)
3. **`created_at`:** NOT_IMPLEMENTED — `reserved_at` ব্যবহার
4. **Max entries:** `max(min_size, 10)` cap — policy documented in code

---

## ৩০. Undefined Policies

| Policy | Status |
|--------|--------|
| Video generation fail → re-reserve | UNDEFINED_POLICY |
| Consumed topic history persistence in reserve file | N/A (removed from queue) |

---

## ৩১. Deferred Items

- Process-level file locking (fcntl/msvcrt) — out of RV-012 surgical scope
- Explicit failed-job retry queue — business policy decision required

---

## ৩২. Final Verdict

**RV-012 = VERIFIED_PASS**

সব mandatory criterion runtime evidence সহ প্রমাণিত। Dedicated suite 25/25 PASS, full regression PASS, evidence matrix complete।

**Checkpoint:** RV-012-PASS  
**paid_api_calls:** 0  
**external_api:** false (reserve operations local JSON only)

---

*AMP-002 RV-012 execution complete. STOP — RV-013 শুরু হয়নি।*
