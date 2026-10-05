# H1 ROOT CAUSE

**BUILD:** BUILD-04G-H1  
**ভাষা:** বাংলা

---

## প্রাথমিক সন্দেহ (আগের audit)

```python
if key not in _STORE_LOCKS:
    _STORE_LOCKS[key] = threading.Lock()
```

**বর্তমান স্ট্যাটাস:** ইতিমধ্যে `_REGISTRY_LOCK` দিয়ে ঠিক করা আছে (`store.py:15-27`)।

---

## প্রকৃত root cause (নিশ্চিত)

**`IdempotentExecutor.execute()` — unguarded execution path**

`atomic_claim()` `claimed=False` ফেরালেও, handler chain-এ return না হলে কোড `execute_fn()`-এ পড়ে (`executor.py:161`).

এটি TOCTOU window-এর সাথে মিলে:

1. Worker A ও B উভয়ে `get()` → `None`
2. A `atomic_claim()` → `True` → execute শুরু
3. B `atomic_claim()` → `False`, `IN_PROGRESS` → wait
4. যদি B-এর wait/validation path return না করে → B-ও `execute_fn()` চালায় → **duplicate execution**

অতিরিক্ত: `get()` SUCCEEDED fast-path ও claim-এর মধ্যে race-এ একই symptom দেখা যায় যদি fall-through থাকে।

---

## Fix strategy (surgical)

1. **`execute_fn()` শুধুমাত্র `claimed=True` হলে**
2. **`not claimed` → default safe return (`duplicate_prevented` / reuse / known terminal state)**
3. **`get()` read lock-এর ভিতরে** — consistent snapshot

Retry policy, UNKNOWN semantics, checkpoint flow — **অপরিবর্তিত**।
