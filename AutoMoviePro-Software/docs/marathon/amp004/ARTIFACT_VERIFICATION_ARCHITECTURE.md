# Artifact Verification Architecture — PHASE-5

**Production code changed:** `false`

---

## স্তর A–E

| Layer | প্রশ্ন | বর্তমান mechanism | Gap |
|-------|--------|-------------------|-----|
| **A** Intent | কী generate করতে চেয়েছি? | Scene, SceneIntent, dialogue_id, revision_id | Entity graph সবসময় dense নয় |
| **B** Prompt | কী পাঠানো হয়েছে? | prompt_compiler, visual_prompt, override | Provider-side silent rewrite |
| **C** Provider return | কী ফাইল এসেছে? | path, fingerprint, provenance, SUCCESS/REUSED/FAILED | Bytes ≠ semantics |
| **D** Actual media content | ফ্রেমে/অডিওতে কী আছে? | `visual_qa` frames/motion/black; HEURISTIC text; OFFLINE fixtures | **P0 architectural gap** — no production VLM/ASR |
| **E** Final render | Master-এ কী আছে? | compose + MASTER_SHIP + publishability | Master semantic Layer-D reuse নেই |

---

## নীতি

1. A/B PASS ≠ D PASS  
2. C technical PASS ≠ D semantic PASS  
3. D UNKNOWN → publish policy: **block or explicit waiver** — never silent PASS  
4. Future VLM/ASR = PROVIDER_VERIFIED label only when real  

---

## Recommended verification pipeline (design only)

```
Intent(A) → Compile(B) → Generate → Technical(C)
    → Local media analysis Level-1 (frames/loudness/duration)
    → Heuristic semantic Level-2
    → Optional VLM/ASR Level-3
    → Aggregate IndustrialValidationReport
    → Creative 04F
    → Publishability AND
```

---

## Existing assets to reuse (not duplicate)

- `visual_validation.py` — container  
- `visual_qa.py` — frames / motion / black / UNKNOWN protocol  
- `multimodal_consistency` — industrial layers  
- `av_quality_gates` — timing hard gates  
- `quality/publishability.py` — final AND  

---

## PHASE-5 acceptance

- [x] A–E separated  
- [x] Major gap documented  
- [x] No implementation  

**→ PHASE-5 PASS.**
