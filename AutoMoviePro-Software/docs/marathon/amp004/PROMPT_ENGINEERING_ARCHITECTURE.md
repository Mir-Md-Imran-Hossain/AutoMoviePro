# Prompt Engineering Architecture

**AMP-004 audit** · implement নয়

---

## সঠিক flow

```
Canonical Scene / Dialogue
        ↓
   SceneIntent (source of truth)
        ↓
   Prompt Compiler (structured sections)
        ↓
   Prompt Contradiction Check
        ↓
   Provider Prompt (+ negative)
        ↓
   Generation
```

Prompt **কখনোই** source of truth নয়।

---

## Existing pieces

| Piece | Path | Status |
|-------|------|--------|
| Compiler | `multimodal_consistency/prompt_compiler.py` | Verified |
| Contradiction | `prompt_validator.py` | Verified |
| Legacy prompts | `prompt_engineering.py`, `prompt_hardening.py`, `prompt_registry.py` | Parallel — DOCUMENT/MERGE later |
| Scene contract compile | `scene_contract.compile_prompt_from_contract` | Legacy; handoff now also SceneIntent compile |

---

## Required sections (doctrine)

SUBJECT_ENTITIES, ATTRIBUTES, RELATIONSHIPS, ACTION, TEMPORAL_ORDER, ENVIRONMENT, CAMERA, LIGHTING, STYLE, EMOTION, AUDIO_CONTEXT, CONTINUITY, REQUIRED, FORBIDDEN, NEGATIVE_CONSTRAINTS

FORBIDDEN must live in **negative**, not positive prompt body.

---

## Gaps

- Provider-specific transform audit  
- Always persist compiled sections + fingerprint with visual provenance  
- Unify legacy prompt_engineering with SceneIntent compiler (future merge task)
