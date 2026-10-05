# Cross-Modal Contract (Frozen)

**Authority:** `pipeline/multimodal_consistency` — **একমাত্র** cross-modal boundary  
**Companion:** `visual_semantic` (feeds semantic; not a second cross-modal engine)  
**Creative aggregation:** signals → BUILD-04F (score authority নয় এখানে)

---

## Required axes (eventual)

| Axis | Status today |
|------|--------------|
| SCRIPT ↔ SCENE | Partial (scene_runtime + intent) |
| SCRIPT ↔ VISUAL | Partial (alignment / C3) |
| SCRIPT ↔ AUDIO | Partial (identity + gates) |
| VISUAL ↔ AUDIO | Partial (duration/desync gates) |
| VISUAL ↔ SUBTITLE | Partial |
| AUDIO ↔ SUBTITLE | Partial (timeline) |
| TIMELINE ↔ ALL MEDIA | Partial |
| LOCALIZATION ↔ ORIGINAL MEANING | Offline contract exists |

---

## Industrial layers (must remain separate booleans)

TECHNICAL · SEMANTIC · CROSS_MODAL · CONTINUITY · LOCALIZATION · PROMPT  

`final_status=BLOCKED` যদি যেকোনো hard layer BLOCKED।

---

## Propagation (frozen)

```
IndustrialValidationReport.blocked == true
  → publishability MUST block   # wire in PHASE-02
```

---

## Forbidden

- দ্বিতীয় competing cross-modal engine  
- Heuristic result-কে PROVIDER_VERIFIED বলা  
- multimodal BLOCKED + publish PASS  

---

## Adapter honesty

`evaluator_adapter.py`: HEURISTIC | OFFLINE_TEST_ONLY | PROVIDER_VERIFIED  
Future VLM/ASR এই adapter দিয়ে — নতুন parallel package নয়।
