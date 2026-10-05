# AMP-001 Dependency Graph

**Protocol:** AMP-001  
**Last Updated:** 2026-08-31

---

## Graph (Mermaid)

```mermaid
flowchart TD
    T001[TASK-001 Idempotency Concurrency] --> T002[TASK-002 Reserve Atomicity]
    T002 --> T003[TASK-003 Long/Short Isolation]
    T003 --> T016[TASK-016 Reserve Self-Repair]

    T001 --> T004[TASK-004 Fail-Closed Gate]
    T004 --> T005[TASK-005 Research Provider Boundary]
    T005 --> T006[TASK-006 Real Research Execution]
    T005 --> T017[TASK-017 API Cost Governance]

    T006 --> T007[TASK-007 Research Evidence Ranking]
    T006 --> T010[TASK-010 Trend Intelligence]
    T006 --> T012[TASK-012 Cache Invalidation]

    T007 --> T008[TASK-008 Channel DNA]
    T008 --> T009[TASK-009 Topic Discovery]
    T009 --> T011[TASK-011 Semantic Duplicates]

    T007 --> T013[TASK-013 FactPack Gate]
    T013 --> T014[TASK-014 Provenance]

    T007 --> T015[TASK-015 Daily Refresh]
    T012 --> T015

    T007 --> T018[TASK-018 Full Integration]
    T014 --> T018
    T016 --> T018

    T018 --> T019[TASK-019 Clean Environment]
    T019 --> T020[TASK-020 Final Audit]
```

---

## Execution Order (Recommended)

Primary chain (sequential where no branch):

1. TASK-001 ✓
2. TASK-002 → TASK-003
3. TASK-004 → TASK-005 → TASK-006
4. TASK-007
5. TASK-008 → TASK-009 → TASK-011
6. TASK-010 (parallel-safe after TASK-006, but marathon runs one at a time)
7. TASK-012
8. TASK-013 → TASK-014
9. TASK-015
10. TASK-016
11. TASK-017
12. TASK-018 → TASK-019 → TASK-020

---

## Parallel-Safe Branches (Marathon: still sequential)

After TASK-006 completes, these can proceed in any order (but AMP-001 executes one task at a time):

- TASK-007, TASK-010, TASK-012

After TASK-007:

- TASK-008, TASK-013, TASK-015 (TASK-015 also needs TASK-012)

---

## Blocked Task Policy

If a task is BLOCKED (environment or external dependency):

- Document in `MARATHON_STATE.json` → `blocked_tasks`
- Only skip to next task if no dependency violation
- Never break dependency chain for convenience
