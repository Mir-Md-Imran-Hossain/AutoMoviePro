# H1 PRE-AUDIT — Idempotency Concurrency

**BUILD:** BUILD-04G-H1  
**ভাষা:** বাংলা  
**তারিখ:** ২০২৬-০৮-৩১

---

## 1. Locking model (বর্তমান)

| উপাদান | বিবরণ |
|--------|--------|
| `_REGISTRY_LOCK` | Global lock — lock registry তৈরি সুরক্ষিত |
| `_STORE_LOCKS[path]` | প্রতি `IDEMPOTENCY.json` path-এ একটি `threading.Lock` |
| `atomic_claim()` | `_store_lock(self.path)` এর ভিতরে load → decide → write |
| `get()` / `put()` | lock নিয়ে reload/write |

**Store identity:** `IdempotencyStore.path` = `{base_dir}/IDEMPOTENCY.json` (resolved absolute path key)

**Fingerprint identity:** `compute_fingerprint(job_id, stage, entity_id, inputs, provider, model)`

---

## 2. Callsite matrix (সংক্ষিপ্ত)

| ফাইল | ব্যবহার |
|------|---------|
| `executor.py` | `get()` → `atomic_claim()` → `execute_fn()` → `put(SUCCEEDED)` |
| `*_runtime.py` (audio/visual/script/render/subtitle/quality/research) | `IdempotentExecutor.execute()` |
| `factpack_bridge.py` | `IdempotentExecutor.execute()` |
| `test_build03_idempotency.py` | store + executor concurrent test (2 workers) |

---

## 3. Concurrent execution flow

```
Worker → store.get(fingerprint)     [fast-path reuse if SUCCEEDED]
       → store.atomic_claim()       [IN_PROGRESS claim — serialized by store lock]
       → if claimed: execute_fn()
       → put(SUCCEEDED)
```

অন্য worker:

- `IN_PROGRESS` → wait (`_wait_for_completion`) → reuse
- `SUCCEEDED` → reuse
- claim না পেলে → duplicate_prevented / unknown / failed

---

## 4. শনাক্তকৃত দুর্বলতা

### A. Lock registry (আগের audit — **ইতিমধ্যে ঠিক**)

আগের unsafe pattern:

```python
if key not in _STORE_LOCKS:
    _STORE_LOCKS[key] = threading.Lock()
```

বর্তমানে `_REGISTRY_LOCK` দিয়ে thread-safe।

### B. Executor fall-through (**মূল race — H1 fix target**)

`executor.py` line ~161: `not claimed` হলেও সব handler miss করলে `execute_fn()` চালু হয়।

উদাহরণ:

- `prior=SUCCEEDED` কিন্তু validation fail
- `IN_PROGRESS` wait শেষে validation fail
- অন্যান্য unhandled `not claimed` state

ফলাফল: **provider execution > 1**

### C. `get()` TOCTOU (secondary)

`get()` lock ছাড়ার পর `_data` পড়ে — optimization path-এ stale read। Authority `atomic_claim()`-এ থাকা উচিত; executor শুধু `claimed=True` হলে execute করলে safe।

---

## 5. Checkpoint / reuse behavior (অপরিবর্তিত)

- SUCCEEDED + valid artifact → `action=reuse`
- IN_PROGRESS → wait → reuse
- FAILED_RETRYABLE → `atomic_claim` retry (bounded)
- UNKNOWN → no blind execute
- Checkpoint after SUCCEEDED persist

---

## 6. Multi-process সীমা

এই fix **process-internal** threading-এর জন্য। আলাদা process একই `IDEMPOTENCY.json` লিখলে filesystem-level race থাকতে পারে — **documented limitation**, এই BUILD-এ distributed lock নয়।
