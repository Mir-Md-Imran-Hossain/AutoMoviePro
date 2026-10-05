# AMP-004 Pre-Audit — PHASE-1 Discovery Evidence

**তারিখ:** ২০২৬-০৮-৩১  
**Production code changed:** `false`  
**Phase:** PHASE-1 PASS → PHASE-2

---

## ১. Repository map (verified)

| Path | Evidence |
|------|----------|
| `pipeline/` | ~195 Python modules; core orchestration |
| `domain/` | contracts: Scene, Script, SceneIntent, FactPack, Render, … |
| `pipeline/idempotency/` | BUILD-03/04A–E runtime bridges |
| `pipeline/quality/` | BUILD-04F creative quality |
| `pipeline/intelligence/` | BUILD-04G topic/research |
| `pipeline/visual_semantic/` | AMP-003 T004-C3 visual semantic |
| `pipeline/multimodal_consistency/` | AMP-003 T004-C3 multimodal |
| `scripts/` | 76 `test_*.py` (17 amp003, 11 build03/04) |
| `docs/marathon/amp003/` | AMP-003 state + reports |
| `docs/build04f/` … `build04g_hardening/` | BUILD docs exist |

Product-plan PDF: **repo-তে পাওয়া যায়নি** (পূর্ববর্তী AMP-003 note-এর সাথে সামঞ্জস্যপূর্ণ)।

---

## ২. Historical claim → disk verification

| Claim | Disk/module check | Verdict |
|-------|-------------------|---------|
| BUILD-04A visual idempotency | `pipeline/idempotency/visual_*.py`, `agnes_bridge.py`, `test_build04a_visual_runtime.py` | **VERIFIED EXISTS** |
| BUILD-04B audio/TTS | `audio_*.py`, `tts_bridge.py`, `test_build04b_*` | **VERIFIED EXISTS** |
| BUILD-04C script | `script_*.py`, `test_build04c_script_runtime.py` | **VERIFIED EXISTS** |
| BUILD-04D render | `render_*.py`, `test_build04d_render_runtime.py` | **VERIFIED EXISTS** |
| BUILD-04E subtitle | `subtitle_*.py`, `test_build04e_subtitle_runtime.py` | **VERIFIED EXISTS** |
| BUILD-04F quality | `pipeline/quality/*`, `test_build04f_quality_gate.py` | **VERIFIED EXISTS** |
| BUILD-04G intelligence | `pipeline/intelligence/*`, `test_build04g_*` | **VERIFIED EXISTS** |
| AMP-003 T001–T003 | `domain/*`, `contract_wiring/*`, `idempotency/executor.py`, tests | **VERIFIED EXISTS** |
| T004-B scene runtime | `scene_runtime.py`, `test_amp003_task004_b_*` | **VERIFIED EXISTS** |
| T004-C1 visual identity | `visual_request.py`, C1 tests | **VERIFIED EXISTS** |
| T004-C2 Agnes hardening | `agnes_bridge.py`, C2 tests; scene_builder → bridge only | **VERIFIED EXISTS** |
| T004-C3 multimodal | `visual_semantic/`, `multimodal_consistency/`, C3 tests | **VERIFIED EXISTS** |

**নোট:** “EXISTS” ≠ “production-এ প্রতিটি path fail-closed” — PHASE-2/3-এ call-path যাচাই।

---

## ৩. Production entrypoint

`pipeline/video_pipeline.py` → `generate_video()`:

1. Intelligence gate (BUILD-04G-H) — fail-closed  
2. Director / plan (`_plan_niche_production_idempotent`)  
3. Contract wiring (`assert_production_plan_wiring`)  
4. Scene validation (`assert_production_scenes_validated`)  
5. Scene build (visual/audio/subtitle via `scene_builder`)  
6. Compose / FFmpeg  
7. Master ship gate (`evaluate_master_shippable`)  
8. Creative quality + publishability (BUILD-04F)

---

## ৪. Read-only verification (এই audit)

```
IMPORT_OK 13 / IMPORT_FAIL 0
TEST_SCRIPTS 76
AMP003_TESTS 17
BUILD03_04_TESTS 11
```

কোনো production behavior পরিবর্তন হয়নি।

---

## ৫. PHASE-1 acceptance

- [x] Repo structure mapped  
- [x] Claimed modules verified on disk  
- [x] Entry pipeline located  
- [x] Test inventory counted  
- [x] No production code change  

**→ PHASE-1 PASS. Continue PHASE-2.**
