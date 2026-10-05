# Architecture Contracts — Index

**Freeze:** `AMP004-ARCHITECTURE-FREEZE`  
**Production code changed:** `false`

এই index সব freeze contracts-এর pointer। বিস্তারিত প্রতিটি `*_CONTRACT.md` / policy file-এ।

| Contract | File | Owner |
|----------|------|-------|
| Quality gate / publishability | `QUALITY_GATE_CONTRACT.md` | BUILD-04F + publishability + multimodal AND |
| Validation tiers | `VALIDATION_TIER_CONTRACT.md` | L0–L4 |
| Artifact layers A–E | `ARTIFACT_LAYER_CONTRACT.md` | All validators must declare layer |
| Continuity | `CONTINUITY_CONTRACT.md` | ContinuityTracker only |
| Cross-modal | `CROSS_MODAL_CONTRACT.md` | multimodal_consistency only |
| Prompt | `PROMPT_CONTRACT.md` | SceneIntent compiler canonical |
| Repair | `REPAIR_CONTRACT.md` | BUILD-04F repair_* |
| Invalidation | `INVALIDATION_CONTRACT.md` | quality/invalidation.py graph |
| Bypass | `BYPASS_POLICY.md` | Production NO BYPASS default |
| Domain boundaries | `DOMAIN_BOUNDARIES.md` | Domain owners |
| Duplication | `DUPLICATION_REGISTER.md` | KEEP / MERGE later |
| Roadmap | `IMPLEMENTATION_ROADMAP.md` | PHASE-01…12 bounded |

## Invariants (সব contract-এ প্রযোজ্য)

1. BUILD-03 = sole idempotency  
2. BUILD-04F = sole creative-quality score authority  
3. SceneIntent = sole semantic source  
4. UNKNOWN ≠ PASS  
5. multimodal BLOCKED ⇒ publishability BLOCKED (conceptual; wire in PHASE-02)  
6. Repair = minimal invalidated scope  
7. Stale downstream after upstream change = INVALID  
