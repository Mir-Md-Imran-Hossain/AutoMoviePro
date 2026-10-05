# PHASE6 — Real Certification Matrix

**Date:** 2026-09-09  
**Rule:** PROVEN requires real media / provider evidence, not unit tests alone.

Legend: **GREEN** proven · **YELLOW** limited · **BLUE** heuristic · **GRAY** UNKNOWN · **RED** failed/unproven

---

## Phase slice certifications (existing evidence)

| Phase | Verdict | Real media? | Paid Google | Notes |
|-------|---------|-------------|-------------|-------|
| 6A | PASS / adapters | local tools | 0 | faster-whisper, PySceneDetect, VMAF |
| 6B | PASS_WITH_LIMITATION | local | 0 | CLIP often unavailable on machine |
| 6C | PASS_WITH_LIMITATION | sampling | 0 | foundation; limited live provider |
| 6D | PASS | C11 frames | 4/4 | IMAGE/VIDEO/NEGATIVE LIVE |
| 6E | PASS | C11 + repair | 1 + gen | temporal normalize; VISUAL repair EXECUTED; hash change; re-observe PASS |
| 6F | PASS | reuse + LIVE | 4 attempts | cross-beat; negative FAIL |
| 6G | PASS | reuse + LIVE | 3/3 | dialogue/visual timing; no silent drop |
| 6H | PASS | edge-tts + ASR | 0 Google | speech/dialogue; AUDIO repair EXECUTED |
| 6I | PASS_WITH_LIMITATION | edge-tts | 0 Google | acoustic identity **UNKNOWN**; no embedding |
| 6J | PASS | reuse 6D/6E/6H | 0 | fusion projection; never directly publishable |

---

## RCP / Marathon (customer product path)

| Slice | Classification | Result | Publish |
|-------|----------------|--------|---------|
| RCP-02 plan | REAL | plan READY; execute CONTRACT fail historically | mixed |
| RCP-03 | REAL | semantic PASS reported in slice | PUBLISHABLE claimed at plan |
| RCP-04 | REAL | PASS_WITH_LIMITATION; BN packaging / semantic UNKNOWN | limited |
| RCP-07 short/long/blocker | REAL | **FAILED** | **FAIL** |
| C11 marathon (`mr_05d3459f7f87438b`) | REAL | PASS-WITH-LIMITATION class; jobs **COMPLETED/APPROVED** | publish FAIL (`VALIDATION_FAILURE`) |
| C11 job2272 “long” | REAL file | duration **~8.85s** (not ~180) | RED vs duration contract |
| C11 job2273 “short” | REAL file | duration **~7.2s** (not ~60) | RED vs duration contract |
| YouTube upload success | — | **not proven** | RED |
| Long-form ~180s completed master | — | contract exists; **no 180s completed artifact proven** | RED |

---

## Requirement × real evidence (summary)

| Area | Color | Real proof basis |
|------|-------|------------------|
| Provider frame/video observe | GREEN | 6D/6E Gemini |
| Location contradiction FAIL | GREEN | 6D/6E/6J hospital vs spacecraft |
| Visual targeted repair + re-observe | GREEN | 6E hash lineage |
| Dialogue/visual alignment | GREEN/YELLOW | 6G LIVE + reuse |
| Cross-beat entity/state | GREEN/YELLOW | 6F |
| ASR transcript / coverage | GREEN/YELLOW | 6H faster-whisper |
| Audio targeted repair | YELLOW | 6H edge-tts path (not full Google TTS marathon) |
| Adaptive pacing / no fixed-N | YELLOW | 6G policy + tests; not full video marathon |
| Duration contract short/long numbers | GREEN (contract) | duration_budget defaults |
| Duration long runtime ~180s | GRAY/RED | not proven in Phase 6 cert media |
| Acoustic voice identity | GRAY | 6I UNKNOWN by design |
| Emotion acoustic observation | GRAY | UNKNOWN |
| Multilingual BN semantic | YELLOW/GRAY | RCP-04 limited |
| Full batch / YouTube | RED | RCP-07 FAIL |
| UNKNOWN blocks publishability | GREEN | semantic + publishability code + 6F–6J tests |
| OpenMontage AGPL imports | GREEN | 0 |

---

## Customer journey (AUTH → SCHEDULE)

| Stage | Status |
|-------|--------|
| AUTH / entitlement / channel | IMPLEMENTED (out of Phase 6 scope; not re-certified here) |
| Topic → research → script → TRS → plan | IMPLEMENTED; RCP slices REAL with limitations |
| Generation | IMPLEMENTED; REAL on C11 |
| Observation 6C–6J | IMPLEMENTED; REAL on slices |
| Quality / repair | IMPLEMENTED; REAL visual/audio repair slices |
| Render / preview | IMPLEMENTED; not fully re-proven in Phase 6K |
| Approval → publishability → publish → schedule | IMPLEMENTED; **publish SUCCESS not proven** (RCP-07 FAIL) |

---

## Paid API rollup (Phase 6 recorded)

| Phase | Attempts | Successes | Notes |
|-------|----------|-----------|-------|
| 6D | 4 | 4 | …syGE |
| 6E | 1 (+gen) | 1 | repair re-observe |
| 6F | 4 | 2 | + LIVE reuse |
| 6G | 3 | 3 | |
| 6H–6J | 0 Google | 0 | local ASR / reuse |

Do not treat this rollup as full Marathon cost model.
