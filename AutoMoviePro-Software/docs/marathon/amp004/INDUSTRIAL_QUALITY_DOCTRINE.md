# Industrial Quality Doctrine — AutoMoviePro

**AMP-004** · বাংলা doctrine · Technical identifiers English

---

## মূল নীতি

> AI ভুল করতে পারে।  
> সিস্টেমকে আশা করতে হবে যে generation ভুল হবে।  
> তাই: **CONSTRAIN → VALIDATE → VERIFY → REJECT → REPAIR (minimal) → RE-VALIDATE → PUBLISH**

“১০০% perfect AI generation” কোনো engineering claim নয়।

---

## স্তরবিন্যাস (authoritative)

1. **TECHNICAL** — file/container/duration/stream (deterministic)  
2. **IDENTITY** — scene_id / dialogue_id / revision / fingerprint  
3. **SEMANTIC** — SceneIntent vs analysis (heuristic/offline/future VLM)  
4. **CROSS-MODAL** — dialogue ↔ visual ↔ audio ↔ subtitle  
5. **CREATIVE** — BUILD-04F retention/hook/coherence (canonical soft+hard issues)  
6. **ARTIFACT** — Layer D/E: what is actually in media  
7. **PUBLISHABILITY** — AND of required passes; score alone never overrides CRITICAL fail  

---

## Hard rules

| ID | Rule |
|----|------|
| D-01 | UNKNOWN ≠ PASS |
| D-02 | Score average CRITICAL contradiction লুকায় না |
| D-03 | Prompt correctness ≠ artifact correctness |
| D-04 | Metadata correctness ≠ media correctness |
| D-05 | Attractive visual ≠ correct visual |
| D-06 | Fallback ≠ primary success semantics |
| D-07 | Repair = smallest invalidated scope |
| D-08 | BUILD-03 only idempotency authority |
| D-09 | BUILD-04F only creative-quality authority |
| D-10 | Deterministic checks before paid VLM/ASR |

---

## Evaluation honesty labels

| Label | অর্থ |
|-------|------|
| `HEURISTIC` | Prompt/text-derived; not vision |
| `OFFLINE_TEST_ONLY` | Fixture-driven tests |
| `PROVIDER_VERIFIED` | Future real VLM/ASR |
| `TYPE-1` … `TYPE-5` | Deterministic → human judgment |

---

## Publish formula (target architecture — implement নয়)

```
TECHNICAL_PASS
∧ SEMANTIC_PASS (or UNKNOWN→block if required)
∧ CROSS_MODAL_PASS
∧ CREATIVE_PASS (04F)
∧ ARTIFACT_PASS (or explicit UNKNOWN policy)
∧ PROVENANCE_COMPLETE
= PUBLISHABLE
```

বর্তমানে: technical ship + 04F publishability production-connected; multimodal semantic production-এ partial (strict/fixture / identity); Layer-D incomplete।
