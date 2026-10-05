# Repair Dependency Architecture — PHASE-6

**Production code changed:** `false`  
**Source of truth:** `pipeline/quality/invalidation.py` + `RepairScope`

---

## Dependency graph (logical)

```
Topic / Research / FactPack
        ↓
     Script
        ↓
   Scene / SceneIntent / Dialogue
      ↙        ↓        ↘
 VisualPlan  AudioPlan  SubtitlePlan
      ↓          ↓          ↓
 VisualAsset AudioAsset SubtitleAsset
      ↘         ↓         ↙
           Scene Mux
              ↓
           Concat / Render
              ↓
           Final Master
              ↓
         Publishability
```

---

## Invalidation rules (existing code)

| Changed | Stale stages |
|---------|--------------|
| script / dialogue | script, scene, visual, audio, subtitle, cross_modal, render, final |
| visual / visual_plan | visual, cross_modal, render, final |
| audio | audio, subtitle, cross_modal, render, final |
| subtitle | subtitle, render, final |
| render | render, final |

Helpers: `scene_only_invalidation(scene_id)`, `audio_only_invalidation(scene_id)`

---

## Correct repair example

**Scene-05 visual fails**

DO:
1. Repair `VISUAL_ASSET` for scene-05 only  
2. Revalidate technical + semantic + cross-modal for scene-05  
3. Invalidate render/final  
4. Rerender / remux affected segments  
5. Re-run master ship + publishability  

DO NOT (unless dialogue/intent invalidated):
- Regenerate full script  
- Re-research topic  
- Regenerate all TTS  
- Regenerate all subtitles  

---

## Repair identity must include

`scene_id`, `dialogue_id`, `revision_id`, `intent_fingerprint`, attempt budget (`DEFAULT_MAX_SCENE_REPAIRS`)

Prevent: infinite repair, identical repair loops, semantic regression without revalidation.

---

## Duplicate repair systems

| System | Action |
|--------|--------|
| `quality/repair_runtime.py` | **KEEP** canonical |
| `visual_semantic/repair_bridge.py` | KEEP — adapter into 04F |
| `multimodal_consistency/quality_bridge.py` | KEEP — adapter |
| `av_self_repair_agent.py` | DOCUMENT — merge policy later; do not delete now |

---

## PHASE-6 acceptance

- [x] Graph documented  
- [x] Minimal scope rule  
- [x] No code change  

**→ PHASE-6 PASS.**
