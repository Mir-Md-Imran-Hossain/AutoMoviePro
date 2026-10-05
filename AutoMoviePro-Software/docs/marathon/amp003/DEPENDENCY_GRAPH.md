# AMP-003 Dependency Graph

```
TASK-001 Domain Contracts
    ↓
TASK-002 Pipeline Wiring
    ↓
TASK-003 Idempotency + Recovery
    ↓
TASK-004 Media Runtime
    ↓
TASK-005 Quality Gate
    ↓
TASK-006 Topic Research
    ↓
TASK-007 Duplicate + Channel DNA
    ↓
TASK-008 Trend + SEO + Gap
    ↓
TASK-009 Reserve Queue
    ↓
TASK-010 Localization
    ↓
TASK-011 Publication + Upload
    ↓
TASK-012 End-to-End + Agent
```

**Rule:** Each task depends on all prior tasks PASS. No parallel task execution.

**Baseline overlays:** RV-006..RV-012 and BUILD suites provide regression anchors but do not skip AMP-003 tasks.
