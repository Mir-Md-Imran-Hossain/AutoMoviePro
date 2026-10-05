# Repair Contract (Frozen)

**Authority:** BUILD-04F `repair_planner` + `repair_runtime`  
**Adapters:** `visual_semantic/repair_bridge`, `multimodal_consistency/quality_bridge`  
**Legacy overlap:** `av_self_repair_agent` → DOCUMENT → MERGE later (এখন rewrite নয়)

---

## Principle

**Minimal-scope dependency-aware repair.**

Visual scene fail → শুধু visual repair (যদি dialogue/intent invalidate না হয়)।

```
failed visual
  → repair visual (VISUAL_ASSET / scene scope)
  → verify visual (tech + semantic + cross-modal as required)
  → invalidate affected render/final
  → rerender
  → verify final artifact
  → publishability re-check
```

**MUST NOT** automatically regenerate Research / Script / Dialogue / Subtitle unless invalidation graph proves dependency।

---

## Repair identity (required)

`job_id`, `scene_id`, `dialogue_id`, `revision_id`, `intent_fingerprint`, `attempt`, `issue_fingerprint`

---

## Budget

`DEFAULT_MAX_SCENE_REPAIRS` — infinite loop নিষিদ্ধ; escalate when exceeded।

---

## Re-verify

Repair পরে stale SUCCESS reuse নিষিদ্ধ — নতুন verification বাধ্যতামূলক।

---

## Idempotency

সব repair execution BUILD-03 executor/fingerprint দিয়ে — দ্বিতীয় repair cache নেই।
