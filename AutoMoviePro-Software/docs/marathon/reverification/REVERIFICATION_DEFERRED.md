# AMP-002 Deferred Issues

---

## RV-DEF-001 — External Live Research API

| Field | Value |
|-------|-------|
| Related | RV-006 |
| Severity | P1 (future) |
| Status | DOCUMENTED |
| Description | বর্তমান LIVE mode `build_fact_pack()` local provider ব্যবহার করে। External Google/LLM adapter নেই। |
| RV-006 verdict | VERIFIED_PASS for `live_local` + `external_api=false` honest labeling |
| Real external API | ENVIRONMENT_BLOCKED until adapter + credentials exist |

---

## RV-DEF-002 — AMP-001 Batch Test Not Sole Proof

| Field | Value |
|-------|-------|
| Related | AMP-002 all |
| Description | `test_marathon_tasks_006_020.py` batch suite AMP-002-এ sole evidence নয় |

---

## RV-DEF-001 (AMP-001 carryover) — Multi-Process Locks

| Field | Value |
|-------|-------|
| Related | RV-016, RV-017 |
| Severity | P2 |
