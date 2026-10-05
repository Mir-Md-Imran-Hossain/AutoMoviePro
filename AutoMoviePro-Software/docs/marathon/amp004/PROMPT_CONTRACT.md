# Prompt Contract (Frozen)

---

## Canonical pipeline

```
Canonical Scene
  → SceneIntent          # semantic source of truth
  → Prompt Compiler      # multimodal_consistency/prompt_compiler.py  = CANONICAL
  → Prompt Validator     # prompt_validator.py
  → Provider Request
  → Artifact Verification (C then D)
```

Prompt **কখনোই** source of truth নয়।

---

## Disposition of overlapping modules

| Module | Role (frozen) |
|--------|----------------|
| `multimodal_consistency/prompt_compiler.py` | **CANONICAL** |
| `multimodal_consistency/prompt_validator.py` | **CANONICAL** validator |
| `scene_contract.compile_prompt_from_contract` | **ADAPTER** / legacy handoff |
| `pipeline/prompt_engineering.py` | **LEGACY** — MERGE later into SceneIntent path |
| `pipeline/prompt_hardening.py` | **ADAPTER** utilities (anchors etc.) |
| `pipeline/prompt_registry.py` | **LEGACY** registry — DOCUMENT |

এই task-এ rewrite/merge **নেই**।

---

## Rules

1. FORBIDDEN elements positive body-তে নয় — negative/constraints-এ  
2. Entity relationships flatten করে ambiguous free text-এ critical ownership হারানো যাবে না  
3. High-priority semantic constraints silent mutate করা যাবে না  
4. Compiled prompt + `intent_fingerprint` provenance-এ রাখা (future enforce)  

---

## Inequality

```
Prompt contradiction check PASS ≠ Layer-D semantic PASS
```
