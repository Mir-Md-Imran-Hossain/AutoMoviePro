# Quality Gate Contract (Frozen)

**Checkpoint:** Architecture Freeze  
**Implement:** PHASE-02 — এই document শুধু contract

---

## Publishability formula

```
TECHNICAL_PASS
∧ CONTENT_SEMANTIC_PASS
∧ CROSS_MODAL_PASS
∧ CREATIVE_PASS          # BUILD-04F only
∧ ARTIFACT_PASS          # Layer D/E policy
∧ RENDER_PASS
∧ PROVENANCE_COMPLETE
∧ NO_MANDATORY_UNKNOWN
= PUBLISHABLE
```

যেকোনো operand FAIL বা mandatory UNKNOWN → `publishable=false`।

---

## Operand definitions

| Operand | Evidence sources (current / future) | Layer |
|---------|-------------------------------------|-------|
| TECHNICAL | visual/audio/render validation, HARD_QUALITY_GATES, MASTER_SHIP | C / E partial |
| CONTENT/SEMANTIC | visual_semantic, entity_grounding, SceneIntent | A + D (when available) |
| CROSS_MODAL | multimodal_consistency industrial layers | cross A–E |
| CREATIVE | BUILD-04F `CreativeQualityResult` / orchestrator | soft+hard issues |
| ARTIFACT | visual_qa + future VLM/ASR | **D/E** |
| RENDER | 04D + FFmpeg container/encode integrity | E |
| PROVENANCE | *_provenance + fingerprints | meta |

---

## Multimodal BLOCK propagation (frozen path — not wired yet)

```
multimodal_consistency.run_* 
  → IndustrialValidationReport.final_status == BLOCKED
       ↓  (PHASE-02 must implement)
quality.publishability / CREATIVE_QUALITY_GATE consumer
       ↓
publishable = false
verdict = BLOCKED | NOT_PUBLISHABLE
reason includes multimodal_blocked
```

**Forbidden path:**

```
multimodal=BLOCKED ∧ creative_score=high ∧ publishable=true   # ILLEGAL
```

---

## Score vs hard gate

- Dimension scores informational  
- CRITICAL / HARD class → verdict cannot be PASS via average  
- Example: Visual 95, Audio 95, Script 95, Cross-modal FAIL → **NOT PASS**

---

## Creative authority

BUILD-04F remains sole global creative-quality authority।  
Other modules emit **signals / reports / repair requests** — not competing overall scores.

---

## Current vs frozen

| Aspect | Today (Phase-02) | Notes |
|--------|------------------|-------|
| Technical + 04F publishability | Wired | Keep |
| Multimodal → publishability | **Wired** via MULTIMODAL_QUALITY_GATE.json AND | Phase-02 PASS |
| ARTIFACT Layer-D | Weak / optional ARTIFACT_GATE.json | PHASE-04 |

PHASE-02 PASS. PHASE-03 NOT_STARTED.
