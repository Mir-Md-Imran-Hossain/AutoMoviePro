# PHASE-02 Call Graph (STEP-1)

**Production authority:** live `video_pipeline.py` + quality modules

---

## Decision answers

| Q | Answer | Evidence |
|---|--------|----------|
| A. Can multimodal BLOCKED reach publishability? | **NO** (pre-fix) | `evaluate_publishability` has no multimodal arg; bridge does not load MM |
| B. Can multimodal BLOCKED be lost/ignored? | **YES** | Scene may fail OR heuristic advisory; no job AND into publish |
| C. Can UNKNOWN become PASS? | Creative UNKNOWN → publishable False (OK). Multimodal UNKNOWN **ignored** (gap) | publishability.py lines 28–35 vs missing MM |
| D. Can production bypass semantic validation? | **YES if metadata set** | `skip_semantic_validation` in agnes_bridge |
| E. Can upload execute after mandatory quality BLOCK? | Creative/tech BLOCK → RuntimeError before ready_to_upload. Multimodal-only BLOCK at job end → **can still reach ready_to_upload** if scenes succeeded | video_pipeline 944–1026 |

---

## PASS / FAIL / BLOCKED / UNKNOWN today

| Stage | PASS | FAIL/BLOCK | UNKNOWN |
|-------|------|------------|---------|
| Master ship | ok && !unshippable | raise master_unshippable | exception → fail-closed |
| Creative 04F | verdict PASS | REPAIR/BLOCKED/… | publishable False |
| Multimodal beat | continue | semantic_blocked (conditional) | heuristic soft |
| Publishability | publishable True | raise publishability_blocked | creative UNKNOWN → False |
| Upload ready | ready_to_upload | not set if raise | — |

---

## Target after PHASE-02

```
multimodal aggregate (work_dir)
        ↓ BLOCKED | mandatory UNKNOWN
evaluate_publishability
        ↓ publishable=False
video_pipeline raise
        ↓
ready_to_upload NEVER set
```

---

## STEP-1 acceptance

- [x] Questions A–E answered from code  
- [x] Target path defined  

**→ STEP-2/3 implementation.**
