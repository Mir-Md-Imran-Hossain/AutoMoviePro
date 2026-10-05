# Validation Tier Contract (Frozen)

---

## Levels

| Level | নাম | Examples | Cost | Honesty label |
|-------|-----|----------|------|---------------|
| **L0** | Deterministic / metadata / structural | identity, fingerprint, ftyp, duration metadata, forbidden prompt tokens | FREE | TYPE-1 |
| **L1** | Local media analysis | ffprobe, frame extract, motion/black, silence, future LUFS | FREE/LOCAL | TYPE-1/2 |
| **L2** | Deterministic + heuristic semantic | SceneIntent validators, keyword overlap, entity grounding fixtures | FREE | HEURISTIC |
| **L3** | Optional VLM / ASR / ML | Object detect, scene describe, ASR transcript | PAID/HIGH | PROVIDER_VERIFIED only if real |
| **L4** | Human | Brand-critical subjective | HIGH | HUMAN |

---

## Rules (frozen)

1. L3/L4 results **কখনোই** deterministic বলে claim করা যাবে না।  
2. Required evidence নেই → **UNKNOWN**।  
3. Mandatory publishability requirement + UNKNOWN → **BLOCK**।  
4. Non-critical advisory + UNKNOWN → **WARN / REVIEW**।  
5. L0 fail হলে L3 call করা যাবে না (cost + correctness)।  
6. Deterministic local check একই fact prove করলে expensive AI skip।  

---

## Mapping to artifact layers

| Level | Typical layers |
|-------|----------------|
| L0 | A identity, B structure, C container |
| L1 | C/D technical media, E master probes |
| L2 | A↔B, A↔C heuristic |
| L3 | D/E semantic observation |
| L4 | Subjective creative |

---

## Existing modules by tier

| Module | Tier |
|--------|------|
| idempotency / identity | L0 |
| visual_validation, audio_validation | L0/L1 |
| visual_qa | L1 |
| visual_semantic / multimodal (heuristic) | L2 |
| evaluator_adapter Offline fixture | L2 OFFLINE_TEST_ONLY |
| Future VLM/ASR adapter | L3 |
| Human escalation | L4 |
