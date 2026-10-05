# Open-Source Phase 6I — Implementation Report

**Date:** 2026-09-09 (Windows)  
**Customer:** `c11_marathon_customer` / channel `4`  
**Verdict:** **PASS_WITH_LIMITATION**

---

## Pre-audit

`OPEN_SOURCE_PHASE6I_PRE_AUDIT_REPORT.md` — **Option A**.

- No acoustic speaker-embedding capability in repo  
- pyannote/speechbrain/resemblyzer **not installed** (license/model terms not cleared)  
- Do **not** integrate embedding stack in this phase  

---

## Selected technology

| Layer | Choice |
|-------|--------|
| Features | existing ffprobe + `audio_design.loudness` + Phase 6A/6H faster-whisper |
| Speaker embedding | **Not integrated** → UNKNOWN |
| Generation hint | HEURISTIC TTS voice-name consistency only |
| Naturalness | UNKNOWN (no fake AI detector) |
| Emotion observation | UNKNOWN (intent ≠ actual) |
| Repair | existing `plan_audio_design_repair` AUDIO_ASSET |

**Windows / CPU:** Option A path only. **GPU:** N/A. **Model download:** none new (whisper cache may already exist).

---

## Files

| Path | Role |
|------|------|
| `pipeline/observation/audio_evidence/acoustic.py` | Features, delivery, acoustic UNKNOWN, hint HEURISTIC, master/localized UNKNOWN |
| `pipeline/observation/audio_evidence/__init__.py` | Exports |
| `pipeline/story_visual_direction.py` | Snapshot flags |
| `scripts/test_phase6i_voice_verification.py` | Tests |
| `scripts/cert_phase6i_voice.py` | Cert |
| `docs/.../OPEN_SOURCE_PHASE6I_*.md` | Reports |
| `docs/.../phase6i_evidence/*` | Evidence |

---

## Certification results

| Item | Result |
|------|--------|
| Acoustic features | Observed (PASS technical/ASR path) |
| Acoustic VoiceIdentity | **UNKNOWN** |
| Same voice + emotion change | Contract stable; no false identity FAIL |
| Different TTS voice negative | **HEURISTIC mismatch** detected; acoustic still UNKNOWN |
| Delivery | NORMAL on positive clip |
| UNKNOWN | Blocks semantic; no repair |
| Repair | AUDIO_ASSET EXECUTED (handoff + targeted regen); whole-video false |
| Paid Google | **0** |

---

## Limitations (honest)

1. Cannot PROVIDER_VERIFY same/different speaker acoustically without approved embedding provider.  
2. Cross-language acoustic identity remains UNKNOWN.  
3. Naturalness remains UNKNOWN.  
4. Generation voice-name hint is not acoustic proof.

---

## Tests / regressions

- Phase 6I tests: **14/14 OK**  
- Regressions 6A–6H + RCP/BUILD/C05: **REGRESSION_FAILS=0**

---

## HARD STOP

Phase 6I complete. **Do not start Phase 6J** until explicitly requested.
