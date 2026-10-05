# CORE ENGINE — Real Live Six-Language Marathon Report

**Marathon ID:** `mr_core_engine_20260909T122850Z_d28d7146`  
**Overall verdict:** `FAIL`  
**Started:** 2026-09-09T12:28:50Z  
**Ended:** 2026-09-09T13:39:23Z (last resume attempt)  
**Approx. wall runtime:** ~70+ minutes across initial run + 3 resumes  
**Job:** `2300`  
**Work dir:** `data/customer_generation_work/c11_marathon_customer/job2300`  
**Evidence run dir:** `docs/marathon/runs/mr_core_engine_20260909T122850Z_d28d7146/`

## Scope (honored)

| Item | Status |
|------|--------|
| Customer entitlement / payment / website admin | **OUT OF SCOPE** — not forged |
| DB `languages_json` | Preserved as `["en","bn"]` |
| Cert languages | In-memory overlay only: EN BN HI UR TA ML |
| YouTube publish | **NO** |
| Mock/fixture claimed as PASS | **NO** |
| Gate weakening | **NO** |
| Duplicate engines | **NO** |

## Objective answer

**Can AutoMovie Pro currently go topic → six industrial-grade final videos (EN/BN/HI/UR/TA/ML) on this live path?**  
**No — not yet.** Upstream intelligence/script/plan and multi-language audio preflight (after fix) work; **visual materialization fails closed** before master concat / six-language finals.

---

## 1. Topic

- **Text:** How lunar polar permanently shadowed craters preserve water ice that Artemis prospectors can map with neutron spectrometers (202609091228 cert)
- **Source:** MANUAL_CONCRETE_NICHE_GROUNDED (suggest fallback)
- **Duplicate gate:** UNIQUE
- **Sector status:** **PASS**

## 2. Research

- Live research completed (`02_RESEARCH.json`, `ok: true`)
- **Sector status:** **PASS**

## 3. Script (forensic)

| Check | Result |
|-------|--------|
| Topic relevance | PASS — lunar PSR / ice / Artemis / neutron spectrometers |
| Hook | “At the lunar poles, deep craters never see the sun…” — strong open |
| Structure | 8 beats, ~short target packing |
| Classification | REAL (not mock) |
| AI-like / denseness | HEURISTIC — acceptable documentary density; some abstract openers (“Temperatures…”) |
| Sector | **PASS** (content); generation later failed on visuals |

Preview beats (EN master intent) present in `03_SCRIPT.json`.

## 4–7. Dialogue / Visual direction / Continuity / Audio plan

- Production plan: `READY_FOR_GENERATION` (`05_PRODUCTION_PLAN.json`)
- Director plan locked: `CUSTOMER_APPROVED_PLAN` + `c06e_customer_approved_plan.lock` (skipped TRS re-intelligence DUPLICATE)
- Continuity authority: ContinuityTracker (no duplicate engine)
- Subject extraction improved mid-run (hardware phrases); still HEURISTIC weaknesses on abstract nouns
- **Sectors:** Dialogue **PASS**; Visual direction **HEURISTIC**; Continuity **HEURISTIC**

## 8. Visual assets (critical)

| Observation | Evidence |
|-------------|----------|
| Scenes completed as beats | 3 files: `scene_01/02/03_beat.mp4` (scene 00 missing after regen) |
| Scene 3 hard-fail | `scene_03_AV_FAIL.txt` — `visual_anchors_missing` (+ earlier wrong_subject/nebula) |
| Provider | Pollinations IMAGE + Agnes attempts + Ken Burns docref |
| Critic | Google multimodal; frequent 503/429 free-tier pressure |

**Sector: FAIL** — gates correctly refused unshippable visuals.

## 9. Audio / Voice

- EN narration WAV/M4A produced for attempted scenes
- Per-scene localize **succeeded for scenes 01 & 02** in all of BN/HI/UR/TA/ML after preflight fix
- Acoustic voice identity: **UNKNOWN** (no approved embedding)
- **Sectors:** Audio **HEURISTIC**; Voice **UNKNOWN**

## 10. Six-language production

| Lang | Script loc | Audio (scene packs) | Subtitle | Final video |
|------------------|---------------------|----------|-------------|
| EN | master | partial scenes | partial | **NO final** |
| BN | via localize | scenes 01–02 OK | OK in packs | **NO final** |
| HI | via localize | scenes 01–02 OK | OK in packs | **NO final** |
| UR | via localize | scenes 01–02 OK | OK in packs | **NO final**; RTL shaping **UNKNOWN** |
| TA | via localize | scenes 01–02 OK | OK in packs | **NO final** |
| ML | via localize | scenes 01–02 OK | OK in packs | **NO final** |

**Sectors:** Localization **FAIL** (incomplete job); Subtitle **FAIL** (no finals); Final video **FAIL**

## 11. Dialogue → visual alignment

Reconstructed for scene 3:

dialogue (rover + neutron spectrometer) → intended hardware beat → generated/docref still → observed **lunar rocks / no spectrometer** (earlier: **JWST nebula**)

**Sector: FAIL** (critical)

## 12. Ten-minute health

See `HEALTH_TIMELINE.jsonl` + operator external watchdogs. States observed: HEALTHY → PROGRESSING → FAILED → resume PROGRESSING → FAILED. Provider waits (503/429) labeled waiting/slow, not false STUCK.

## 13. Interventions (minimal targeted)

| ID | Problem | Fix | Authority |
|----|---------|-----|-----------|
| INT-001 | TRS DUPLICATE on generate re-entry | CUSTOMER_APPROVED_PLAN director lock | `customer_plan_adapter` / `generate_video` |
| INT-002 | `invalid_language` ur/ta/ml | `VALID_LANGUAGES` ∪ `TARGET_LANG_CODES` | `pipeline/audio_design/preflight.py` |
| INT-003 | Scene3 wrong subject / fake SKU from cert stamp | Lunar hardware phrases + `sku_tokens` skip long digit stamps | `customer_plan_adapter` / `prompt_engineering` |
| INT-004 | Docref mapped moon/cislunar → JWST nebula | Lunar rover/ice still keys; remove bare moon→nebula | `fallback_image_video.select_documentary_reference_url` |

Regression: Phase-05 audio tests **OK** after INT-002.

## 14. Sector scorecard (A–T)

| Sector | Status |
|--------|--------|
| A Topic | PASS |
| B Research | PASS |
| C Script | PASS |
| D Dialogue | PASS |
| E Visual direction | HEURISTIC |
| F Visual assets | FAIL |
| G Character continuity | HEURISTIC |
| H Location continuity | HEURISTIC |
| I Object continuity | FAIL |
| J Camera / lighting | UNKNOWN |
| K Audio | HEURISTIC |
| L Voice | UNKNOWN |
| M Localization | FAIL |
| N Subtitle | FAIL |
| O Dialogue→visual | FAIL |
| P Render | FAIL |
| Q Final video | FAIL |
| R Audience / creative | HEURISTIC |
| S Production efficiency | HEURISTIC |
| T Failure / recovery | PASS |

## 15. Final video artifacts

**None** for any of the six languages (no `final.mp4` / `LOCALIZED/*/video.mp4` package set).

Partial only: per-scene `SCENE_LOCAL/01` and `02` five-language packs (plus EN master clips for some beats).

## 16. Overall verdict

# **FAIL**

Not PASS / PASS_WITH_LIMITATION: industrial visual generation could not clear scene 3 under real gates; six-language finals never rendered. Recovery behavior and entitlement separation behaved correctly.

---

## POST-MARATHON IMPROVEMENT BACKLOG

| ID | Sev | Symptom | Evidence | Root cause | Stage | Artifact | Why allowed | Recommended fix | Authority to extend | Whole regen? | Impact |
|----|-----|---------|----------|------------|-------|----------|-------------|-----------------|---------------------|--------------|--------|
| BL-01 | P0 | Scene hard-fail missing rover/spectrometer anchors | `scene_03_AV_FAIL.txt` | IMAGE/docref stills lack required hardware entities | VISUAL GEN | scene_03 | Fail-closed (correct) | Stronger subject-locked image gen + curated hardware still library; use critic `revised_prompt` as first IMAGE prompt | `fallback_image_video`, scene_builder IMAGE path | Scene+ | Unblocks shorts |
| BL-02 | P0 | No six-language finals | job2300 incomplete | Blocked by BL-01 | LOCALIZE/RENDER | LOCALIZED/ | Downstream never reached | Finish after BL-01 | existing localize_master_clip | Yes for finals | Cert completeness |
| BL-03 | P1 | Docref moon/cislunar→JWST nebula | pre-fix critiques | Over-broad still keying | VISUAL FALLBACK | early reference stills | Silent wrong CDN match | Keep INT-004; expand still catalog per niche | `select_documentary_reference_url` | Partial | Stops nebula b-roll |
| BL-04 | P1 | Audio preflight rejected ur/ta/ml | SCENE_LOCAL/00 old manifest | VALID_LANGUAGES incomplete | AUDIO PREFLIGHT | TTS request | Catalog langs ≠ audio allowlist | Keep INT-002; add unit asserting TARGET_LANG_CODES | `audio_design.preflight` | No | Unblocks 6-lang TTS |
| BL-05 | P1 | Cert timestamp treated as SKU | revised prompts with SKU 20260909… | `sku_tokens` digit match | PROMPT | product_name | Stamp in topic | Keep INT-003; avoid numeric stamps in cert topics | `prompt_engineering.sku_tokens` | No | Cleaner critic |
| BL-06 | P2 | Abstract subjects (“Temperatures”, water ice as character) | director_plan subjects | Entity extraction heuristics | PLAN→DIRECTOR | director_plan.json | Soft mapping | Prefer concrete nouns / C05-S entities | `customer_plan_adapter` | Plan rewrite | Continuity + prompts |
| BL-07 | P2 | Google critic 503/429 | console logs | Free-tier quota | CRITIC | AV critiques | Failover partial | Quota pacing / paid critic tier | existing quota_backoff | No | Stable scores |
| BL-08 | P2 | UR RTL shaping unknown | no burn-in proof | No FriBidi cert | SUBTITLE | UR packs | Not instrumented | Observed shaping proof later | localization RTL helpers | No | UR publishability |
| BL-09 | P2 | Acoustic VoiceIdentity UNKNOWN | design | No embedding provider | AUDIO | voice | By design | Optional approved embedder | VoiceIdentity | No | Speaker lock |
| BL-10 | P3 | Watchdog during generate_video | no 10m CP inside long call | Runner only checkpoints between stages | OBSERVE | HEALTH_TIMELINE | Sync generate blocks | Threaded watchdog in cert runner | cert script only | No | Ops visibility |
| BL-11 | P4 | Cert language overlay UX | runbook | Overlay vs C04 separation | ENTITLEMENT BOUNDARY | channel dict | Intentional | Document operator cert runbook; never merge into C04 | lang_entitlement | No | Clarity |

---

## HARD STOP

Marathon + forensic audit complete. **No further large feature implementation in this turn.**

Next work should pick backlog items in severity order (BL-01 → BL-02), one targeted fix at a time, with focused regression — then re-run core-engine marathon.
