# AMP-004 Dependency Graph (Frozen)

```
PHASE-01 Architecture Freeze ─────────────────────────────┐
                                                          │
BUILD-03 Idempotency (sole) ◄── all generate/repair ──────┤
BUILD-04G Intelligence → FactPack → Script (04C)          │
         ↓                                                │
AMP-003 Scene Runtime → SceneIntent (semantic sole)       │
         ↓                                                │
    ┌────┴────┬─────────┬──────────┐                      │
 Visual(04A) Audio(04B) Subtitle  Text/VFX(future)        │
    │         │         │                                 │
 multimodal_consistency (sole cross-modal)                │
 ContinuityTracker (sole continuity)                      │
 av_quality_gates (technical HARD)                        │
 visual_qa / future ArtifactVerifier (Layer D/E)          │
         ↓                                                │
 BUILD-04F Creative + Repair (sole creative authority)    │
         ↓                                                │
 publishability AND ← multimodal BLOCKED (PHASE-02 wire)  │
         ↓                                                │
 FFmpeg / Render (04D) → Final E → Publish                │
                                                          │
Roadmap: 02→03→04; 05∥06∥07∥08 →09→10→11→12 ─────────────┘
```

## Invalidation (summary)

Upstream change ⇒ downstream INVALID (see `INVALIDATION_CONTRACT.md`).  
Visual-only fail ⇒ do not invalidate Research/Script by default.

## Acyclic check

Roadmap phases have no cycle: 01…12 linear with parallel 05–08 after 04.
