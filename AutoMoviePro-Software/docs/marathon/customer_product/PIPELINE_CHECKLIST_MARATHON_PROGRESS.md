# Pipeline Checklist Marathon Progress

## Stop / Restart
- **Stop cause:** session context summarization + premature section-level POSITIVE without durable registry  
  → see `MARATHON_STOP_CAUSE.md`
- **Restart fix:** `scripts/marathon_checklist_runner.py` + `MARATHON_QUESTION_REGISTRY.json`

## Latest registry run
```
POSITIVE=244 NEGATIVE=0 UNKNOWN=0
NEXT_QUESTION=
```

## PART–2 (18/18) — COMPLETE / ALL POSITIVE
See `PART2_QUESTION_AUDIT_PROGRESS.md` (prior marathon wave).

## PART–3 Fallback — POSITIVE
## PART–4 Google capability matrix — POSITIVE

## PART–5 A–Q + Critical Core 12
**Registry: 244/244 POSITIVE** (code-backed probes; UNKNOWN≠PASS)

Machine authority for restart continuity:
- `docs/marathon/customer_product/MARATHON_QUESTION_REGISTRY.json`
- Re-run: `python scripts/marathon_checklist_runner.py`

## Honesty
- Probes verify symbols/paths/behavior gates — not a substitute for a full live production job.
- Audience gate still sets `claims_human_certification: false`.
- Optional CLIP/FAISS: POSITIVE via honest `UNAVAILABLE` backend gate (not “must be installed”).
