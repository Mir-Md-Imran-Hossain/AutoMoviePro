# Open-Source Phase 6D — Implementation Report

**Date:** 2026-09-09  
**Verdict:** **PASS**  
**HARD STOP:** Phase 6E not started  
**New production engines:** **None** (certification-only)

---

## Pre-audit

`OPEN_SOURCE_PHASE6D_PRE_AUDIT_REPORT.md` → **AUDIT PASS**  
Existing Phase 6C + RCP-03 paths sufficient; no new implementation engines.

---

## Exact real media used

| Role | Path | content_hash (sha256) |
|------|------|------------------------|
| IMAGE | `data/customer_generation_work/c11_marathon_customer/job2108/_fallback_i2v/fb_beat_00.png` | `b790e53eca50ef7aaee0fdbc079a825f9369402ff7c64bc08f30989430d34473` |
| VIDEO | `data/customer_generation_work/c11_marathon_customer/job2108/scene_00_beat.mp4` | `cbf9d0dfc1e03eb801bac2edb6675bb7d7dbf500937dd3962e1f1a24a79af0cf` |
| Duration (video) | 7.24s | |

Customer scope: `c11_marathon_customer` / channel `4`.

---

## Sampling

| Media | Strategy | Frame count | Bounded | FFmpeg |
|-------|----------|-------------|---------|--------|
| IMAGE | `image_single_frame` | 1 | yes | compose reuse |
| VIDEO | `long_uniform_bounded` | 5 | yes (≤7) | compose reuse |

Timestamps (video): `0.724, 2.172, 3.62, 5.068, 6.516`  
`semantic_pass: false` on sampling.

Evidence: `phase6d_evidence/01_image.json`, `02_video.json`.

---

## Provider used / results

| Step | live_status | provider | provider_verified | status |
|------|-------------|----------|-------------------|--------|
| IMAGE | LIVE | `PROVIDER_FRAME:gemini-flash-latest` | true | **FAIL** (expected spacecraft/Earth; observed astronaut woman — honest mismatch vs beat) |
| VIDEO frames | LIVE | `PROVIDER_FRAME:gemini-*` | true | **FAIL** vs optimistic space beat |
| NEGATIVE (hospital required) | LIVE | `PROVIDER_FRAME:gemini-3.6-flash` | true | **FAIL** (not PASS) |
| UNKNOWN (no keys) | controlled | n/a | false | **UNKNOWN** + ABSENT |

Heuristic never used as PASS. Caption/filename never treated as PROVIDER_VERIFIED.

---

## Coverage / temporal / negative / UNKNOWN / repair

| Check | Result |
|-------|--------|
| Beat coverage vocab | FULL/PARTIAL/NONE/UNKNOWN (C05-S) |
| IMAGE coverage overall | PARTIAL (environment FULL; subject/entity NONE) |
| VIDEO coverage overall | NONE |
| Temporal | FAIL (location string drift between frames) — ContinuityTracker remains policy authority |
| Negative | FAIL accepted; `is_not_pass=true` |
| UNKNOWN | blocks semantic (`overall→UNKNOWN`, blocking); repair **not** triggered |
| FAIL repair handoff | `repair_triggered=true`, scope **VISUAL_ASSET**, no whole-video regen |

---

## Retrieval lineage

`retrieval_candidate → asset_identity → sampled_frames → frame_observation → temporal_evidence → beat_coverage`  
Provenance retained (`source`, `license_usage`, `content_hash`).  
Cross-customer: **FAIL** `customer_isolation_blocked`.

CLIP: still **RETRIEVAL_UNAVAILABLE** (no torch) — not claimed as certified.

---

## Paid API count

| Metric | Value |
|--------|-------|
| Attempts | **4** |
| Successes | **4** |
| Key masks used | `…syGE` (single sticky key) |
| Marathon / C11 full / YouTube | **0** |
| Secrets exposed in evidence | **0** |

Source: `phase6d_evidence/00_paid_api.json`.

---

## Tests / regressions

| Suite | Result |
|-------|--------|
| Phase 6D focused | **25/25 OK** |
| Phase 6A | OK (15) |
| Phase 6B | OK (16) |
| Phase 6C | OK (26) |
| RCP-06A–D | OK |
| RCP-07 blocker | OK |
| BUILD-03 | OK |
| C05-S | OK |
| C05-MR | OK (140) |

---

## Windows / dependencies

- Real paths under `data/customer_generation_work/...` on Windows  
- Bundled FFmpeg used  
- CLIP unavailable (honest)  
- No torch install forced  

---

## Limitations

1. Optimistic beat text (spacecraft/Earth) intentionally differed from C11 astronaut-interior media → provider **FAIL**/coverage NONE–PARTIAL proves honesty, not product “visual PASS”.  
2. Temporal FAIL includes coarse location-string inequality; ContinuityTracker remains policy authority for production decisions.  
3. CLIP not certified on this machine.  
4. Repair = handoff evidence only (BUILD-04F plan); no live asset regenerate executed.  
5. Evidence JSONs under `docs/marathon/customer_product/phase6d_evidence/` are certification artifacts, not publishability PASS.

---

## OpenMontage isolation

AGPL imports/copies in observation path = **0**. Authority audit attached.

---

## Acceptance (1–16)

All met with live provider-verified evidence distinguishable from heuristic.  
No false production certification of publishability.

**Verdict: PASS**  
**HARD STOP — do not start Phase 6E.**
