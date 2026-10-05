# Multimodal Consistency Architecture

**AMP-004** · based on verified T004-C3 modules

---

## Package

`pipeline/multimodal_consistency/`

- `boundary.py` — industrial gate  
- `entity_grounding.py`  
- `prompt_compiler.py` / `prompt_validator.py`  
- `cross_modal.py` / `timeline.py` / `localization_semantic.py`  
- `evaluator_adapter.py` — future VLM/ASR  
- `quality_bridge.py` — into BUILD-04F  
- `industrial_status.py` — layered status  

Companion: `pipeline/visual_semantic/*`

---

## Production coupling

`agnes_bridge` post-success → `multimodal_gate_for_spec`  
- Identity mismatch: always block  
- Full semantic block: strict / analysis fixture  
- Heuristic-only: advisory (honest — not fake vision)

---

## Cross-modal axes

Dialogue ↔ Visual  
Audio ↔ Dialogue identity  
Subtitle ↔ Dialogue + timing  
Localization ↔ semantic events  

---

## Gaps (audit)

1. Multimodal BLOCKED always → publishability input (wire later)  
2. ContinuityTracker not always passed production-wide  
3. Layer-D still HEURISTIC  
4. Do not create competing multimodal score system  

---

## Future evaluator honesty

`HEURISTIC` | `OFFLINE_TEST_ONLY` | `PROVIDER_VERIFIED`  
Never label heuristic as vision verification.
