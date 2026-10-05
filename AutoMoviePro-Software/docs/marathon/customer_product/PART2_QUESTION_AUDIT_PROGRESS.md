# PART–2 Question Audit Progress (Pipeline এক নজরে)

Marathon rule: one question at a time; NEGATIVE → implement until POSITIVE; never weaken unrelated authorities.

| # | Topic | Verdict | Notes |
|---|--------|---------|-------|
| 1 | OpenMontage | **POSITIVE** | Ideas in AMP-owned modules only; `third_party/OpenMontage` AGPL isolated; no production import; authorities not replaced |
| 2 | Faster-Whisper | **POSITIVE** | Wired into `video_pipeline` via `run_production_audio_asr_gate`; per-scene narration ASR; timestamps; transcript vs canonical narration compare; FAIL blocks publish; UNKNOWN ≠ PASS; `faster-whisper` in requirements; multilingual via `language_hint` (EN primary, other langs PARTIAL) |
| 3 | PySceneDetect | **POSITIVE** | Adapter `pipeline/observation/scene_boundary`; production gate wired; observation-only (not Continuity/Director authority); planned vs observed compare; false-cut hints (density + micro-segments); FFmpeg fallback |
| 4 | VMAF | **POSITIVE** | `observe_perceptual_quality` + rendering integrity; not sole publishability authority; `plan_perceptual_vmaf_repair` targeted re-encode/replace path |
| 5 | CLIP+FAISS | **POSITIVE** | Optional CLIP with honest UNAVAILABLE fallback; FAISS index + duplicate hash + customer isolation; explainable ranking; `RETRIEVAL_BACKEND_GATE.json` |
| 6 | Frame Sampling | **POSITIVE** | Image vs video strategies; max 3/7; scene + **dialogue** boundary assist; sampling_failed → UNKNOWN; frame lineage hashes |
| 7 | Gemini Multimodal Obs | **POSITIVE** | Actual media upload/frames; evidence persisted; provider vs heuristic separated; UNKNOWN when unverified |
| 8 | Gemini Final Video Review | **POSITIVE** | `run_final_video_gemini_review` on master; timestamp questions; File API ≥100MB note; UNKNOWN on provider fail; does not replace ship gate |
| 9 | Gemini TTS | **POSITIVE** | Production path + 6-lang Charon mapping + emotion/voice identity + Edge fallback evidence; audio ≠ auto quality PASS |
| 10 | Cloud vs Gemini TTS | **POSITIVE** | Gemini/AI Studio only; Cloud TTS not imported; 429/403 classified; Edge fallback preserves voice policy |
| 11 | Piper | **POSITIVE** | AMP-owned optional slot `piper_tts_fallback.py`; Google→Edge→Piper; missing → UNAVAILABLE (honest); AudioPlan untouched |
| 12 | OpenTimelineIO | **POSITIVE** | AMP director/render timeline canonical; OTIO not authority |
| 13 | OpenCV | **POSITIVE** | Via PySceneDetect optional; observation only; not semantic truth |
| 14 | pyannote | **POSITIVE** | Not installed; speaker_observation UNAVAILABLE; VoiceIdentity not faked |
| 15 | Demucs | **POSITIVE** | Deferred / not claimed as production truth |
| 16 | Real-ESRGAN | **POSITIVE** | Deferred / not claimed as production truth |
| 17 | SAM2 | **POSITIVE** | Deferred evidence-only policy; not authority |
| 18 | FFmpeg/MoviePy/Remotion | **POSITIVE** | Sole compose authority `pipeline/compose.py`; no MoviePy/Remotion; failed render blocks publish |

## PART–2 complete

All 18 open-source/tech questions: **POSITIVE**.

Next: PART–3 Fallback Architecture → PART–4 Google API → PART–5 checklist → Critical 12.


Authority preserved: ContinuityTracker, duration_budget, semantic_coverage, compose/ffmpeg, BUILD-04F, AudioPlan, VoiceIdentity.
