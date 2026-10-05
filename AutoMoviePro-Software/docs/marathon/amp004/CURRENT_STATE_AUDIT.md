# AMP-004 Current State Audit (PHASE-2)

**Production code changed:** `false`  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Canonical layers (verified)

| Layer | Canonical authority | Evidence |
|-------|---------------------|----------|
| Idempotency | BUILD-03 `pipeline/idempotency/executor.py` + store | Fingerprint-based execute/reuse |
| Domain contracts | AMP-003 TASK-001 `domain/*` | Scene, Script, SceneIntent, registry |
| Production wiring | AMP-003 TASK-002 `contract_wiring/production_bridge.py` | Fail-closed plan wiring |
| Scene boundary | T004-B `scene_runtime.py` | Canonical Scene → handoff |
| Visual generation | T004-C1/C2 `agnes_bridge.py` only | No direct Agnes in scene_builder |
| Semantic/multimodal | T004-C3 `visual_semantic` + `multimodal_consistency` | SceneIntent → compile + validate |
| Creative quality | BUILD-04F `pipeline/quality/*` | CreativeQualityResult + publishability |
| Topic/research | BUILD-04G `pipeline/intelligence/*` | Gate before director |
| Technical AV ship | `av_quality_gates.py` | HARD_QUALITY_GATES + master ship |

---

## ২. Parallel / legacy quality systems (duplication candidates)

| System | Role | Risk |
|--------|------|------|
| `pipeline/quality/` (04F) | Canonical creative + publishability | **KEEP** |
| `pipeline/av_quality_gates.py` | Technical/timing hard gates | **KEEP** (technical layer) — MERGE policy docs |
| `pipeline/av_sync_critic.py` | Multimodal critic (LLM/heuristic) | DOCUMENT — cost/skip policy via playbook |
| `pipeline/av_self_repair_agent.py` | Scene AV self-repair | DOCUMENT vs 04F repair_runtime |
| `pipeline/visual_qa.py` | Frame extract + motion/black; UNKNOWN without VLM | **KEEP** as Level-1 media analysis |
| `pipeline/visual_semantic/` | SceneIntent semantic validators | **KEEP** — feeds multimodal |
| `pipeline/multimodal_consistency/` | Industrial layers + prompt compiler | **KEEP** — bridge to 04F via quality_bridge |
| `pipeline/plan_quality.py` | Plan-level checks | DOCUMENT — overlap with 04F script evaluator |
| `pipeline/robot_detector.py` | Robotic text signals | DOCUMENT — soft signal |

**নীতি:** নতুন score system তৈরি নয়। Soft signals → 04F dimensions; hard technical → av_quality_gates / media validation।

---

## ৩. Intent vs artifact layers (critical finding)

| Layer | Meaning | Current coverage |
|-------|---------|------------------|
| A Intent | SceneIntent / Scene / dialogue | Strong (T004-B/C3) |
| B Prompt | Compiled / visual_prompt | Strong compiler + contradiction check |
| C Provider return | Path + provenance + fingerprint | Strong (04A bridge) |
| D Visible/audible content | What frames/audio actually contain | **WEAK** — HEURISTIC / OFFLINE fixture; `visual_qa` motion/black only; no production VLM |
| E Final render | Master mux/encode | Partial — ship gates + container checks; not full semantic of master |

**Major architectural finding:** System mostly validates A/B/C; D/E largely UNKNOWN or heuristic. UNKNOWN must not become PASS (`visual_qa` protocol already states this).

---

## ৪. What is strong

- Fail-closed intelligence + scene + identity gates  
- Idempotent visual/audio/script/subtitle/render runtimes  
- Agnes bypass removal (C2-E)  
- Multimodal industrial status layers (not single boolean)  
- Publishability: UNKNOWN/BLOCKED → publishable=False  
- Dependency-aware invalidation graph in `quality/invalidation.py`  
- Targeted RepairScope enum (scene/visual/audio/…)  

---

## ৫. What is genuinely missing

- SFX / music / ducking / loudness pipeline (near-absent)  
- True Layer-D computer vision / ASR in production  
- Unified publishability that ANDs multimodal semantic BLOCKED with 04F  
- On-screen typography / purposeful VFX contract  
- Full FFmpeg filtergraph contract tests beyond compose helpers  
- Localization semantic preservation in live TTS path (offline contract exists in C3)  

---

## ৬. PHASE-2 acceptance

- [x] Canonical authorities identified  
- [x] Duplicate systems listed (KEEP/MERGE/DOCUMENT)  
- [x] A–E layer gap documented  
- [x] No code change  

**→ PHASE-2 PASS. Continue PHASE-3.**
