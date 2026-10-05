# PHASE-06 Final Report — Industrial Localization, Subtitle & Text Consistency

**Checkpoint:** `AMP004-LOCALIZATION-SUBTITLE-TEXT-PASS`  
**Date:** 2026-08-31  
**Paid API calls:** 0

**Roadmap note:** Frozen AMP004 roadmap listed localization/subtitle/text under PHASE-08. This checkpoint implements it as **user PHASE-06**. Visual quality (freeze PHASE-06) remains next as PHASE-07 under user ordering.

---

## 1. Implementation summary

Prevention-first localization: SceneIntent → LocalizationContract → deterministic preflight **before** translate provider → drift/entity/fact/negation/temporal validation → localized audio identity → SubtitlePlan rules → TextPlan → LOCALIZATION_GATE → publishability.

### Extended contracts
- `domain.scene_intent.LocalizationIntent` / `SubtitleIntent` 1.1.0 — entities, facts, RTL, reading-speed, policies, IDs
- `domain.localization.LocalizedDialogue` / `Localization` 1.1.0 — identity + provenance fields
- `RepairScope` — LOCALIZATION, TEXT_LAYOUT, TEXT_RENDER

### New package: `pipeline/localization_consistency/`
| Module | Role |
|--------|------|
| `contract.py` | LocalizationContract, TextPlan, TextElement, fingerprint, entity/fact extract |
| `drift.py` | Entity/fact/negation/temporal/omission/addition/speaker/emotion drift |
| `preflight.py` | BLOCK before provider (language, identity, source text, schema) |
| `subtitle_rules.py` | Identity, audio-authoritative timing, CPS, line-break |
| `rtl_font.py` | Honest RTL PARTIAL/UNKNOWN; font/glyph checks (no fake FriBidi) |
| `text_layout.py` | Overflow, safe-area, effects policy, visual↔text |
| `gate.py` | LOCALIZATION_GATE.json + contracts + repair cycle budget |
| `repair_bridge.py` | BUILD-04F minimal scopes |
| `production.py` | apply + gate production entry |

### Production wiring
- `localization.translate_text` → preflight before LLM; optional contract persist
- `video_pipeline` → `run_production_localization_gate` before creative/publishability
- `publishability` / `quality/bridge` — `localization_status` AND (ABSENT OK when localization not applicable)

---

## 2. Production call graph (proven)

```
generate_video
  → SceneIntent + Continuity (P03)
  → LocalizationContract + preflight (P06)   [BEFORE translate provider]
  → localized dialogue (existing localization.py)
  → AudioPlan / TTS (P05) + identity-bound audio
  → SubtitlePlan / subtitle generation (BUILD-04E)
  → subtitle timing/readability validation
  → TextPlan / layout / effects / glyph
  → artifact verification (P04)
  → multimodal / creative gates
  → repair (04F minimal; LOCALIZATION/TEXT_*/AUDIO/RENDER)
  → re-verify
  → final render + artifact observe
  → publishability (localization FAIL/mandatory UNKNOWN blocks when applicable)
```

TEST-ONLY wiring does not count — `video_pipeline` + `localization.translate_text` + publishability are production paths.

---

## 3. Honesty / UNKNOWN

| Claim | Status |
|-------|--------|
| Perfect linguistic naturalness | HEURISTIC / UNKNOWN without evaluator |
| Full HarfBuzz/FriBidi shaping | **Not claimed** — RTL PARTIAL/UNKNOWN |
| OCR of burned on-screen text | Deferred (artifact L3+) |
| Entity/fact/negation/temporal drift | DETERMINISTIC heuristics |
| Subtitle existence = correctness | **Rejected** — timing/CPS/identity validated |
| Source timing = localized timing | **Rejected** — audio-authoritative |
| UNKNOWN → PASS | **Forbidden** |

---

## 4. Tests & regression

| Suite | Result |
|-------|--------|
| `test_amp004_phase06_localization_subtitle_text.py` | **60/60 PASS** |
| Phase-02/03/04/05 | 114 PASS |
| BUILD-03/04B/C/E/F | 161 PASS |
| BUILD-04A/D/G/G-H | 136 PASS, 2 skip |
| AMP-003 relevant (T001–T003 + identity/C1/C2-E/C3) | 164 PASS |
| Import | `import_ok` |
| Paid external API | **0** |
| BUILD-04A flake (DEF-AMP004-011) | Not observed this run |

---

## 5. Acceptance (A–AJ)

| ID | Criterion | Result |
|----|-----------|--------|
| A–B | Canonical contract + production path | PASS |
| C–G | Entity/fact/action/speaker/emotion | PASS |
| H–J | Drift / negation / temporal | PASS |
| K–M | Audio-bound subtitle + readability | PASS |
| N–O | RTL honesty + glyph/font | PASS (honest UNKNOWN) |
| P–R | TextPlan + overflow/safe-area + effects | PASS |
| S–U | Loc↔visual/audio/SFX coherence hooks | PASS |
| V–X | BUILD-03 / 04F / P04 authorities | PASS |
| Y–Z | UNKNOWN≠PASS; loc failure blocks publish | PASS |
| AA–AJ | Composite verify path, bypass audit, tests, regression, 0 API, provenance/checkpoint, no Phase-07 | PASS |

**Remaining (documented):** Full FriBidi/HarfBuzz shaping and OCR burned-text verification deferred (DEF-AMP004-007 / DEF-AMP004-014). Typography stem depth still partial.

---

## 6. STOP

**phase_06_status = PASS**  
**checkpoint = AMP004-LOCALIZATION-SUBTITLE-TEXT-PASS**  
**next_phase = PHASE-07 / NOT_STARTED**  
**PHASE-07 STATUS: NOT_STARTED**

Do **not** start PHASE-07.
