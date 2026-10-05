# C11 Final Live — Checkpoint Log

## CP-00 | 2026-09-06T15:45:16Z | START
- run_id: `mr_a39b8889d65f4f78`
- session: `ms_9ab8015ff538400b`
- topic: How James Webb Space Telescope images reveal early galaxies for space science
- stage: GENERATION LONG starting
- classification: PROGRESSING

## CP-01 | ~T+30s | SCRIPT (LONG)
- stage: SCRIPT via chat_text
- last ops: groq JSON fail → groq request-too-large/circuit → cerebras 402/circuit → falling through (Google AFC warning seen)
- classification: PROGRESSING (legitimate provider fallback, not stuck)
- progress: yes

## CP-02 | ~T+3m | LONG FAILED
- job_id: 2264
- classification: FAILED
- root cause: visual generation produced talking-head face; must_show=['Narrator','space science']; critic correctly failed (talking_head/wrong_subject)
- evidence: job2264/scene_00_critique_attempt1.json; C11_INCIDENTS.md

## CP-03 | ~T+8m | SHORT FAILED (same root cause)
- job_id: 2265
- classification: FAILED
- marathon verdict: C11-REAL-MARATHON-FAIL

## INT-003 | DETECT→FIX
- defect: voice-role 'Narrator' used as visual subject → talking-head assets
- fix: `app/customer_plan_adapter.py` prefer narration concrete anchors; demote Narrator; establishing camera for voice-role hooks
- also: refresh C11 channel niche seed on existing channel
## INT-004 | DETECT→FIX (after mr_aa34dd8615a54a9f)
- defect: Ken Burns accepted on audio-agent pass while critic still had talking_head/wrong_subject; niche Nature's Wrath face policy allowed cinematic humans; Pollinations generated portraits
- evidence: job2266 critique talking_head woman portrait; plan_av failed_hard false; final_long.mp4 existed but publishability blocked
- fix: scene_builder re-critique after Ken Burns; face_policy science/nature no portraits; fallback profile anti-face; C11 niche_id cleared
- next: resume marathon production again

## INT-006 | creative score false REPAIR
- defect: `_score_from_issues` filled missing dimensions as 0.5 across full weight table → issue-free visual/script scored REPAIR
- evidence: job2270 critique passed=85 space landscape; creative REPAIR_REQUIRED issues=[] score=0.704
- fix: renormalize score over evaluated dimensions only
- also: installed `edge-tts` for TTS fallback after Google TTS key suspension

## CP-FINAL | 2026-09-06T16:19:13Z | COMPLETED
- run_id: `mr_05d3459f7f87438b`
- session: `ms_9d63683a25c94529`
- topic: How James Webb Space Telescope images reveal early galaxies for space science
- LONG job2272: COMPLETED APPROVED PREVIEW_READY; creative PASS 0.820; publishability PUBLISHABLE
- SHORT job2273: COMPLETED APPROVED PREVIEW_READY; creative PASS 0.820; publishability PUBLISHABLE
- localization: ABSENT / not_applicable (en only — not faked)
- publish: FAIL `publish_validation_failed` / MOCK publish path — no live YouTube OAuth publish
- marathon verdict: `C11-REAL-MARATHON-PASS-WITH-LIMITATION`
- classification: COMPLETED
- forensic: `docs/marathon/runs/mr_05d3459f7f87438b/MARATHON_REPORT.md`
- STOP
