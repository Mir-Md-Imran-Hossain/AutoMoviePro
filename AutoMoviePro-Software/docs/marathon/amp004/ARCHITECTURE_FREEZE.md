# Architecture Freeze — AutoMoviePro Industrial Quality

**Checkpoint:** `AMP004-ARCHITECTURE-FREEZE`  
**Status:** FROZEN  
**তারিখ:** ২০২৬-০৮-৩১  
**Production code changed:** `false`  
**Implementation:** নিষিদ্ধ এই task-এ

---

## ১. Freeze নীতি (authoritative)

AI output কখনোই trusted নয় শুধুমাত্র কারণে:

- prompt valid ছিল  
- provider file return করেছে  
- metadata valid  
- heuristic score উচ্চ  

**Lifecycle (frozen):**

```
PREVENT → GENERATE → DETECT → VERIFY → REJECT → REPAIR → RE-VERIFY → PUBLISH
```

- Failed verification **কখনোই** averaging দিয়ে PASS হয় না  
- UNKNOWN **কখনোই** silently PASS হয় না  

---

## ২. Authority Map (একক মালিক)

| Concern | Canonical Authority | Module / Boundary |
|---------|---------------------|-------------------|
| Idempotency | **BUILD-03** | `pipeline/idempotency/executor.py` + store |
| Creative quality + targeted repair | **BUILD-04F** | `pipeline/quality/*` |
| Technical AV hard gates | **av_quality_gates** | `pipeline/av_quality_gates.py` |
| Semantic intent | **SceneIntent** | `domain/scene_intent.py` |
| Visual semantic validators | **visual_semantic** | `pipeline/visual_semantic/*` |
| Cross-modal industrial layers | **multimodal_consistency** | `pipeline/multimodal_consistency/*` |
| Continuity (future single engine) | **ContinuityTracker** | `pipeline/visual_semantic/continuity.py` (extend; no second engine) |
| Prompt compile (canonical) | **SceneIntent Prompt Compiler** | `multimodal_consistency/prompt_compiler.py` |
| Prompt legacy | **ADAPTER / LEGACY** | `prompt_engineering.py` → MERGE later |
| Topic / research / evidence | **BUILD-04G + intelligence** | `pipeline/intelligence/*` |
| Scene runtime identity | **AMP-003 T004-B** | `scene_runtime.py` |
| Visual generation gateway | **agnes_bridge** | BRIDGE_INTERNAL only |
| Render engine | **FFmpeg** | `compose.py` / scene_builder / render_* |
| Final publishability policy | **publishability contract** | `quality/publishability.py` + future AND wiring |

**নিষিদ্ধ:** দ্বিতীয় global quality score · দ্বিতীয় idempotency · দ্বিতীয় cross-modal engine · দ্বিতীয় ContinuityTracker

---

## ৩. Five-Layer Content Model (frozen)

| Layer | নাম | অর্থ | Validator claim rule |
|-------|-----|------|----------------------|
| A | INTENT | সিস্টেম কী চেয়েছিল | Scene / SceneIntent |
| B | PROMPT | Provider-কে কী পাঠানো হয়েছে | Compiler + prompt_validator |
| C | PROVIDER ARTIFACT | Provider কী file দিয়েছে | path, fingerprint, provenance, container |
| D | OBSERVED MEDIA | Image/video/audio-তে আসলে কী দেখা/শোনা যায় | visual_qa / future VLM-ASR — **A/B/C নয়** |
| E | FINAL COMPOSITE | Final render-এ কী আছে | Master ship + future master semantic |

কোনো validator A/B/C চেক করে Layer-D/E verification দাবি করতে পারবে না।

---

## ৪. Validation Tiers (frozen)

| Level | Content | Determinism claim |
|-------|---------|-------------------|
| L0 | Metadata / structural / identity | Deterministic |
| L1 | Local media analysis | Deterministic signals |
| L2 | Heuristic semantic | HEURISTIC — not vision |
| L3 | Optional VLM / ASR / ML | PROVIDER_VERIFIED only when real |
| L4 | Human review | Subjective |

L3/L4 কখনো deterministic বলে represent করা যাবে না।

---

## ৫. Publishability (conceptual freeze)

```
TECHNICAL
∧ CONTENT/SEMANTIC
∧ CROSS-MODAL
∧ CREATIVE (BUILD-04F)
∧ ARTIFACT
∧ RENDER
= PUBLISHABLE
```

Score average hard failure override করে না।

**Multimodal propagation (frozen rule, implement PHASE-02):**

```
multimodal BLOCKED → publishability BLOCKED
```

কোনো path থাকবে না যেখানে multimodal=BLOCKED কিন্তু creative score উচ্চ বলে publish=PASS।

---

## ৬. Hard-block classes (frozen)

Identity mismatch · corrupt/invalid media · missing A/V stream · A/V sync beyond tolerance · known dialogue/visual contradiction · subtitle/dialogue identity contradiction · critical continuity contradiction · invalid/incomplete render · unresolved UNKNOWN on mandatory layer · provenance failure · unsupported mandatory factual claim · **multimodal BLOCKED** · explicit production safety/quality gate failure

---

## ৭. UNKNOWN policy (frozen)

| Context | Behavior |
|---------|----------|
| Mandatory publishability layer | UNKNOWN → **BLOCK** |
| Non-critical advisory | UNKNOWN → WARN / REVIEW |
| Never | UNKNOWN → silent PASS |

---

## ৮. Semantic derivation (frozen)

```
Canonical Scene → SceneIntent → { VisualPlan | DialoguePlan | SFXPlan | MusicPlan | SubtitlePlan | Text/VFX Plan }
```

Downstream generator authoritative SceneIntent থাকলে original script independently reinterpret করবে না।

---

## ৯. What this freeze does NOT do

- Production behavior change নেই  
- PHASE-02 (Quality Gate Foundation) implement নেই  
- C4 / T004-D / T004-E / TASK-005 / VLM / ASR / FFmpeg rewrite নেই  
- Duplicate MERGE এখন নেই — শুধু register  

---

## ১০. Next checkpoint

**`AMP004-QUALITY-GATE-FOUNDATION`** (PHASE-02) — আলাদা command ছাড়া শুরু নয়।

**এই checkpoint:** `AMP004-ARCHITECTURE-FREEZE` — **STOP**
