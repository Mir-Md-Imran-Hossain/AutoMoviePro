# Cost / Latency Strategy — Tiered Evaluation

**AMP-004** · design only · no paid providers added

---

## Tiers

| Level | Content | Cost | Latency | When |
|-------|---------|------|---------|------|
| **L0** | Deterministic: identity, fingerprints, container, duration, forbidden prompt tokens | FREE | ms | Always |
| **L1** | Local media: ffprobe, frame extract, motion/black, silence | FREE/LOCAL | seconds | Always before publish |
| **L2** | Heuristic semantic: SceneIntent validators, keyword overlap | FREE | ms–s | Always; label HEURISTIC |
| **L3** | Optional VLM/ASR | PAID / HIGH | high | Only HARD UNKNOWN or sampled QA |
| **L4** | Human review | HIGH | days | Escalation / brand-critical |

---

## Policy

1. Never call L3 if L0 failed.  
2. L2 must not claim PROVIDER_VERIFIED.  
3. Skip redundant multimodal critic when self-repair already PASSED (existing playbook) — keep as cost control, not quality waiver for CRITICAL.  
4. Budget modules already exist: `api_budget.py`, `provider_budget.py` — reuse.

---

## Future validators cost map (estimate)

| Validator | Tier |
|-----------|------|
| Entity/prompt contradiction | L0/L2 |
| Continuity heuristic | L2 |
| visual_qa frames | L1 |
| Loudness LUFS | L1 |
| Object detector | L1/L3 |
| VLM scene describe | L3 |
| ASR dialogue verify | L3 |
| Retention “human feel” | L4 |
