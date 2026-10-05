# H1 CONCURRENCY TEST

**Script:** `scripts/test_build04g_h1_idempotency_concurrency.py`

## Primary acceptance

| মেট্রিক | মান |
|---------|-----|
| rounds | 100 |
| workers_per_round | 20 |
| total_attempts | 2000 |
| duplicate_execution_rounds | **0** |
| max_provider_executions_per_round | **1** |

## Scenarios

| ID | বিবরণ | ফলাফল |
|----|--------|--------|
| A | প্রথম worker success, অন্যরা concurrent | 1 execution, SUCCEEDED |
| B | failure → safe retry | bounded attempts |
| C | stale IN_PROGRESS | safe recovery, ≤1 execution |
| D | pre-cached SUCCEEDED | 0 executions |
| E | different fingerprints | independent (5 executions) |

## Mock only

কোনো paid API call নেই — শুধু local counter + mock `execute_fn`.
