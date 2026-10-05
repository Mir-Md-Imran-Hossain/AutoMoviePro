# Marathon Stop Cause Analysis

## What stopped

The checklist marathon (`পুরো AutoMovie Pro Production Pipeline — এক নজরে.md`, PART–2 onward) did **not** stop because of a single production code crash. It stopped because of **process / session limits**.

## Root causes

1. **Context / conversation summarization**
   - PART–5 alone has ~200 questions across A–Q + Critical 12.
   - The agent session hit length limits, was summarized, and the continuous one-question-at-a-time loop broke.

2. **Premature “ALL POSITIVE” closure**
   - After batch audits + targeted fixes, progress was marked POSITIVE for entire sections without a durable, machine-checkable per-question registry that survives session restarts.
   - That violates the user’s rule: *do not advance until the current question is 100% POSITIVE*.

3. **No durable marathon runner**
   - Progress lived only in chat + a summary markdown file.
   - There was no restartable script that reloads the next unfinished question after a stop.

## Fix (this restart)

1. Add `scripts/marathon_checklist_runner.py` — extracts questions, runs code-backed checks, writes `MARATHON_QUESTION_REGISTRY.json`.
2. Treat any FAIL/UNKNOWN-as-fail as the next work item.
3. Implement fixes until registry shows all POSITIVE from PART–2 onward.
4. Keep going across sessions by reading the registry, not chat memory.

## Authority reminder

UNKNOWN ≠ PASS. Do not weaken ContinuityTracker, duration_budget, semantic_coverage, or compose.
