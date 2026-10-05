# Quality Gate Architecture — PHASE-7

**Production code changed:** `false`

---

## Target AND model

```
TECHNICAL_PASS
∧ IDENTITY_PASS
∧ SEMANTIC_PASS
∧ CROSS_MODAL_PASS
∧ CREATIVE_PASS (BUILD-04F)
∧ ARTIFACT_PASS (or policy-handled UNKNOWN)
∧ PROVENANCE_COMPLETE
= PUBLISHABLE
```

Score average **কখনোই** CRITICAL fail লুকাবে না।

উদাহরণ: Visual=95, Audio=95, Script=95, Dialogue↔Visual=FAIL → **NOT PASS**।

---

## Current production wiring (verified)

| Gate | Module | Connected? |
|------|--------|------------|
| Intelligence | `intelligence/gate.py` | Yes — fail-closed |
| Plan wiring | `production_bridge.py` | Yes |
| Scene runtime | `scene_runtime.py` | Yes |
| Visual identity | `agnes_bridge` | Yes |
| Multimodal semantic | `multimodal_gate_for_spec` | Partial (strict/fixture / identity) |
| AV hard gates | `av_quality_gates` | Yes — scene + master |
| Creative 04F | `quality/bridge.py` | Yes — end of pipeline |
| Publishability | `publishability.py` | Yes — UNKNOWN→false |

---

## Hard vs soft

| Class | Examples | Behavior |
|-------|----------|----------|
| HARD BLOCK | identity mismatch, technical invalid, desync, cutoff, CRITICAL contradiction (strict), provenance incomplete | Stop publish |
| REPAIRABLE | scene visual mismatch, soft retention, subtitle text drift | Targeted repair |
| SOFT SCORE | hook strength, naturalness | Dimension score |
| UNKNOWN/BLOCK | no pixel evidence, no VLM subject match | Not PASS; publishable=false unless explicit policy |

---

## Canonical authorities

- Creative quality: **BUILD-04F only**  
- Idempotency: **BUILD-03 only**  
- Technical AV: `av_quality_gates` (keep distinct from creative score)  
- Semantic industrial layers: `multimodal_consistency.industrial_status`  

Do **not** implement second scoring system.

---

## PHASE-7 acceptance

- [x] AND model  
- [x] Hard vs soft  
- [x] No implementation  

**→ PHASE-7 PASS.**
