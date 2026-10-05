# Invalidation Contract (Frozen)

**Source graph:** `pipeline/quality/invalidation.py` (authoritative starting point)  
**Extend later — replace নয়**

---

## Authoritative chain

```
Research
  → FactPack
  → Script
  → SceneIntent
  → Visual / Audio / Subtitle / Text / VFX / SFX / Music plans
  → Assets
  → Scene mux
  → Render / Concat
  → Final artifact
  → Publishability decision
```

Upstream identity/content change → downstream dependents **INVALID**।  
Stale artifact silently publishable থাকতে পারবে না।

---

## Current INVALIDATION_GRAPH (freeze baseline)

| Changed | Stale |
|---------|-------|
| script / dialogue | script, scene, visual, audio, subtitle, cross_modal, render, final |
| visual / visual_plan | visual, cross_modal, render, final |
| audio | audio, subtitle, cross_modal, render, final |
| subtitle | subtitle, render, final |
| render | render, final |

Helpers: `scene_only_invalidation`, `audio_only_invalidation`

---

## Future extensions (document only)

- SFX / Music / Ambience / Mix plans  
- Text overlay / VFX plans  
- Localization packs  

---

## Rule

Repair বা regenerate পরে invalidated stages-এর cached PASS **discard** বা re-verify।
