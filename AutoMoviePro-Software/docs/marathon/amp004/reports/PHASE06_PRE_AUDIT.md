# PHASE-06 Pre-Audit — Industrial Localization, Subtitle & Text

**Date:** 2026-08-31  
**Checkpoint before:** `AMP004-AUDIO-SOUND-DESIGN-PASS`  
**Production code changed during STEP-0:** `false`

**Roadmap note:** Frozen AMP004 listed this under PHASE-08; user checkpoint assigns it as **PHASE-06**. Visual quality remains next.

---

## Production map (verified)

| Area | Status | Paths |
|------|--------|-------|
| Dialogue translation | EXISTS | `localization.translate_text` → LLM |
| TTS localization | EXISTS | `tts_reuse` → `tts_bridge` (+ preflight P05) |
| Subtitle generation | EXISTS | `subtitle_bridge` / `subtitle_engine` |
| Subtitle burn | EXISTS | `remux_replace_audio` SRT/drawtext |
| On-screen TextPlan | **ABSENT** | only ad-hoc drawtext / `burn_title_card` |
| Entity/fact drift validation | WEAK | prompt hints; `localization_semantic` not live-wired |
| Negation/temporal protection | **ABSENT** | — |
| Reading-speed / line-break policy | WEAK | structural only |
| RTL shaping | **PARTIAL** | Urdu font candidates; no bidi/shaping guarantee |
| Glyph coverage preflight | **ABSENT** | font pick only |
| Overflow / safe-area | **ABSENT** | fixed margins |
| Text effects policy | **ABSENT** | — |
| Loc idempotency for translation | WEAK | audio/subtitle FP yes; translate text weak |
| Loc repair | INLINE | re-translate in master body |

---

## Call graph today

```
generate_video → localize_scene_clip / localize_master_clip
  → translate_text (NO semantic preflight)
  → TTS (P05 preflight)
  → write_srt / idempotent_write_srt
  → remux_replace_audio
  → LOCALIZE_MANIFEST
```

**Gaps:** no LocalizationContract before provider; no drift/negation/entity gate after translate; no TextPlan; RTL honesty missing; no LOCALIZATION_GATE on publishability.

---

## EXTEND (not duplicate)

- `LocalizationIntent`, `LocalizedDialogue`, `Localization`
- `SubtitlePlan` / `SubtitleCue` / subtitle validation
- `localization_semantic.py` (promote to live)
- BUILD-03 subtitle/audio fingerprints
- BUILD-04F repair scopes
- Phase-04 artifact verification
- publishability AND

## OUT OF SCOPE

OCR of burned text · full HarfBuzz rewrite · new LLM translate engine · PHASE-07+

---

**→ Implement STEP-1…**
