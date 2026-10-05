# Implementation Roadmap (Bounded)

**Freeze checkpoint:** `AMP004-ARCHITECTURE-FREEZE`  
**Next implementable:** PHASE-02 only after explicit command  
**Recursive micro-task trees:** নিষিদ্ধ

Dependency order **acyclic**:

```
01 Freeze → 02 Gate → 03 Continuity → 04 Artifact
                ↓
         05 Script ─┬→ 06 Visual
                    ├→ 07 Audio
                    └→ 08 Localization/Subtitle/Text
                              ↓
                         09 VFX/FFmpeg
                              ↓
                         10 E2E Industrial QA
                              ↓
                         11 Cost/Perf
                              ↓
                         12 Independent Final Audit
```

---

## PHASE-01 — Architecture Freeze

**Status:** PASS (এই task)  
Deliverable: contracts + authority map + this roadmap  
Production change: none

---

## PHASE-02 — Quality Gate Foundation

**Next checkpoint:** `AMP004-QUALITY-GATE-FOUNDATION`  
**Status:** NOT_STARTED  

Scope:
- multimodal BLOCK → publishability BLOCK propagation  
- mandatory semantic validation production policy  
- production bypass containment (`skip_semantic_validation` forbid)  
- publishability contract enforcement alignment  

Does **not** include: VLM, ASR, full Continuity always-on, SFX/music

---

## PHASE-03 — Production Continuity

Always-on ContinuityTracker wiring; scene-identity binding; unexplained break policy

---

## PHASE-04 — Artifact Verification Foundation

Layer D/E interfaces; visual_qa mandatory paths; honesty labels; optional L3 adapter **boundary only**

---

## PHASE-05 — Script / Narrative Quality

Independent script domain evaluations; feed 04F; no second score

---

## PHASE-06 — Visual Quality

Entity/action/spatial/temporal detection hardening; failure taxonomy coverage; still honest about TYPE-3/4 gaps

---

## PHASE-07 — Audio / SFX / Music / Mixing

Dialogue≠entire audio; SFX/Music/Ambience/Mix/Ducking/Loudness/timeline

---

## PHASE-08 — Localization / Subtitle / Text

Meaning preservation; timing; density; typography contracts

---

## PHASE-09 — VFX / FFmpeg / Rendering

Purposeful effects; formal filtergraph/stream contracts; no FFmpeg rewrite for its own sake

---

## PHASE-10 — End-to-End Industrial QA

Full AND publishability; golden/regression harness

---

## PHASE-11 — Cost / Performance Optimization

L0–L4 enforcement; budget; skip redundant L3

---

## PHASE-12 — Independent Final Audit

Re-verify architecture vs code; no silent drift

---

## Mapping to AMP-003 leftovers (informational)

| Legacy label | Roadmap home |
|--------------|--------------|
| T004-C4 | Likely PHASE-02/04 (fallback + artifact) — separate command |
| T004-D | PHASE-07 audio contracts |
| T004-E | PHASE-08 localization/subtitle |
| TASK-005 | Overlaps 04F creative — align under PHASE-05/10, not duplicate score |

এই freeze সেগুলো **start করে না**।
