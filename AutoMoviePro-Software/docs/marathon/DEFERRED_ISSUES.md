# AMP-001 Deferred Issues

Issues discovered during marathon that are **outside current task scope**.  
Do not implement here — track for future tasks or post-marathon work.

---

## DEF-001 — Multi-Process Idempotency

| Field | Value |
|-------|-------|
| Discovered | PRE_MARATHON_AUDIT |
| Related TASK | TASK-001 (documented limitation) → **RESOLVED H1** |
| Severity | Was P2 |
| Description | Was thread-only. H1 added `pipeline/idempotency/fs_lock.exclusive_path_lock` (thread + OS advisory file lock) on IdempotencyStore, reserve_queue, CheckpointStore, GenerationCache critical sections. Multi-process claim/reserve tests PASS. |
| Action | Closed for local multi-process workers. NFS/network FS lock semantics remain uncertified (H1 limitation). |

---

## DEF-002 — External Live Research API Adapter

| Field | Value |
|-------|-------|
| Discovered | BUILD-04G-H baseline |
| Related TASK | TASK-006 |
| Severity | P1 (for true external research) |
| Description | LIVE mode uses local `build_fact_pack` provider. Google/LLM external research adapter not implemented. |
| Action | TASK-006 must clarify acceptance: local LIVE provider vs external API. External adapter may become TASK-021 if opt-in required. |

---

## DEF-003 — Windows Shared CI Reserve Stress

| Field | Value |
|-------|-------|
| Discovered | BUILD-04G-H |
| Related TASK | TASK-002 |
| Severity | P2 |
| Description | 100-round reserve writer stress on shared Windows CI paths deferred; retry mitigation exists. |
| Action | TASK-002 acceptance test should use isolated temp paths; shared-path stress optional |

---

## DEF-004 — BUILD-04G-H Pre-Implementation Overlap

| Field | Value |
|-------|-------|
| Discovered | PRE_MARATHON_AUDIT |
| Related TASK | TASK-002–TASK-017 |
| Severity | Info |
| Description | Many hardening fixes exist from BUILD-04G-H. Marathon must verify each task independently; pre-existing code does not auto-PASS. |
| Action | Verify-only path allowed when acceptance tests pass without new code |
