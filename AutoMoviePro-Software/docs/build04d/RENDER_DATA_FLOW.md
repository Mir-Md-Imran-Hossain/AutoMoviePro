# Render Data Flow — BUILD-04D

```
Job (work_dir)
      ↓
Script (director_plan.json / script_provenance fingerprint)
      ↓
Scene clip list (visual+audio muxed per scene)
      ↓
Logo asset (optional)
      ↓
RenderAssemblyManifest
      ↓
RenderRequestSpec + SHA-256 fingerprint
      ↓
IdempotentExecutor claim / reuse
      ↓
FFmpeg: concat → logo → trim/re-encode
      ↓
.tmp.mp4 → validate → atomic promote → final_{type}.mp4
      ↓
render_provenance + checkpoint
      ↓
Ship gate / localization (downstream)
```

## Invalidation

Upstream asset hash change in manifest → new fingerprint → new render allowed.

Render retry alone does **not** regenerate script/visual/audio upstream assets.
