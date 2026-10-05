# H1 IMPLEMENTATION

**BUILD:** BUILD-04G-H1

## পরিবর্তন

### `pipeline/idempotency/executor.py`

- `not claimed` হলে আর `execute_fn()` চালানো হয় না
- handler miss হলে `duplicate_prevented` safe return

### `pipeline/idempotency/store.py`

- `get()` এখন lock-এর ভিতরে load+read — consistent snapshot

## অপরিবর্তিত

- `atomic_claim()` semantics
- retry policy
- UNKNOWN handling
- checkpoint flow
- `_REGISTRY_LOCK` (আগে থেকে)

## Scope বাইরে

কোনো intelligence/topic/research/reserve ফাইল স্পর্শ করা হয়নি।
