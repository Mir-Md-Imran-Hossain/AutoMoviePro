# TASK-002 Report — Multi-Worker Reserve Atomicity

**Protocol:** AMP-001  
**Task ID:** TASK-002  
**Status:** PASS  
**Checkpoint:** TASK-002-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## Objective

একই reserve item একাধিক worker একসাথে consume করতে পারবে না।

## Acceptance Criteria

| Metric | Required | Actual |
|--------|----------|--------|
| Duplicate consumption | 0 | **0** |
| Concurrent workers | 20 | 20 |
| Rounds | 100 | 100 |

---

## Phase A — Discovery

**Relevant files:**
- `pipeline/intelligence/reserve_queue.py` — `consume_top()`, `save_reserve()`, `_lock_for()`
- `pipeline/intelligence/orchestrator.py` — `select_topic_for_production()` → `consume_top()`
- `scripts/test_build04g_hardening.py` — `test_h2_reserve_atomic_concurrent_writers` (writer-only)
- `scripts/test_marathon_task002_reserve_atomicity.py` — **নতুন** marathon acceptance suite

**Production path:** `consume_top()` under per-path `threading.Lock` — read/pop/write atomic within lock.

**Gap found:** BUILD-04G-H H2 test শুধু concurrent **writers** verify করে; concurrent **consume** marathon acceptance-এর জন্য আলাদা test প্রয়োজন ছিল।

---

## Phase B — Root Cause Analysis

বর্তমান implementation-এ `consume_top()` ইতিমধ্যে `_lock_for(p)` এর অধীনে read-modify-write করে। Thread-level duplicate consumption theoretically impossible within single process.

Marathon gap: dedicated consume concurrency test ছিল না — verify-only path with new acceptance test.

---

## Phase C — Plan

| Action | File |
|--------|------|
| Add marathon acceptance test (consume + writer) | `scripts/test_marathon_task002_reserve_atomicity.py` (new) |
| Production code change | **None required** — existing lock sufficient for thread workers |

---

## Phase E — Target Test

```bash
python scripts/test_marathon_task002_reserve_atomicity.py
```

**Result:** 2/2 PASS  
- `test_concurrent_consume_no_duplicates_100_rounds` — 100 rounds × 20 workers, duplicate=0
- `test_concurrent_writers_no_corruption` — 20 concurrent writers, no JSON corruption

---

## Phase G — Regression

| Suite | Result |
|-------|--------|
| BUILD-04G-H | 21/21 PASS |
| BUILD-04G | 58/58 PASS |
| TASK-001 (H1) | 6/6 PASS |

**Paid API calls:** 0

---

## Phase H — Quality Check

| Check | Status |
|-------|--------|
| Test weakened | No |
| Production code bypass | No |
| Cross-process file lock | **Not in scope** — threading.Lock only (see DEF-001 pattern) |
| Silent corruption | No — empty reserve verified after consume |

---

## Changed Files

- `scripts/test_marathon_task002_reserve_atomicity.py` (new)

---

## Checkpoint

`TASK-002-PASS` — documented; git tag not created.

---

## Next Task

**TASK-003** — Long/Short Reserve Isolation
