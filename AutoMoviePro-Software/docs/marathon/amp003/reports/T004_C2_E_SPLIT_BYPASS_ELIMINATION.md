# T004-C2-E — Split Agnes BYP-01 Direct-Bypass Elimination

**Marathon:** AMP-003  
**Task:** TASK-004 / T004-C  
**Phase:** C2-2-E  
**Checkpoint:** AMP003-T004-C2-E-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## ১. উদ্দেশ্য

Single Agnes path-এ BYP-02 সরানোর পর production visual runtime-এ শেষ remaining bypass ছিল:

**BYP-01** — `scene_builder.py` split dialogue path-এ canonical runtime Exception হলে direct `generate_agnes_dialogue_clip()` call।

এই ফেজে BYP-01 surgical removal করা হয়েছে। Agnes generation engine rewrite করা হয়নি।

---

## ২. বর্তমান architecture (post-fix)

```
split dialogue
  ↓
_resolve_split_agnes_beat_src()
  ↓
idempotent_generate_agnes_beat_result()
  ↓
VisualGenerationResult + AgnesBeatOutcome
  ↓
valid path → continue mux/concat
  ↓
structured failure / Exception → src=None
  ↓
explicit image fallback via _resolve_footage (agnes disabled)
```

**কখনো নয়:**

```
canonical runtime exception → direct generate_agnes_dialogue_clip()
```

---

## ৩. Pre-audit findings

| Item | Pre-fix |
|------|---------|
| BYP-01 location | `_build_split_dialogue_clip()` L1441–1480 |
| Trigger | `except Exception` after `_resolve_split_agnes_beat_src()` |
| Effect | Idempotency bypass, no provenance, unbounded provider call |
| BYP-02 | Already removed (C2-C3-FP) |
| Split helper | Already on canonical API (C2-2-C-2) |

---

## ৪. Implementation

### `pipeline/scene_builder.py`

1. **Removed** `generate_agnes_dialogue_clip` import
2. **Replaced** BYP-01 `except` block:
   - Log: `"Split Agnes canonical path failed scene=... part=.../..."`
   - Set `split_agnes_outcome = "EXCEPTION"`, `src = None`
3. **Enhanced** fallback log with explicit outcome label
4. **Preserved** existing image fallback via `_resolve_footage(agnes_api_keys=[])` when `src` is None

---

## ৫. Outcome semantics (split path)

| Outcome | Behavior |
|---------|----------|
| SUCCESS / REUSED | Valid path → mux/concat (unchanged) |
| FAILED_* | `src=None` → image fallback (explicit log) |
| UNKNOWN | `src=None` → image fallback (unchanged from C2-2-C-2) |
| IDENTITY_BLOCKED | `src=None`, provider=0 |
| EXCEPTION | `src=None` → image fallback (no direct Agnes) |

---

## ৬. BYP-01 / BYP-02 status

| Bypass | Status |
|--------|--------|
| BYP-01 (split Exception → direct Agnes) | **REMOVED** |
| BYP-02 (single Exception → direct Agnes) | **REMOVED** (prior phase) |

---

## ৭. Direct provider audit

`generate_agnes_dialogue_clip(` in Python production code:

| Location | Classification |
|----------|----------------|
| `pipeline/media_assets.py:507` | Provider definition |
| `pipeline/idempotency/agnes_bridge.py:264` | **BRIDGE_INTERNAL** (only allowed production path) |
| `scripts/chernobyl_30_train.py:476` | DEV |
| `scripts/_smoke_agnes_clip.py:25` | DEV |
| `pipeline/scene_builder.py` | **NONE** — bypass eliminated |

**Acceptance:** Zero production bypass in `scene_builder.py`.

---

## ৮. Tests

### Dedicated: `test_amp003_task004_c2_e_split_bypass_elimination.py` — **13/13 PASS**

- BYP-01 removed from source
- SUCCESS/REUSED preserved
- FAILED/UNKNOWN/IDENTITY — no direct provider
- Exception → fallback, not direct Agnes
- `_build_split_dialogue_clip` integration (test_08, test_13)
- Identity propagation

### Updated: `test_amp003_task004_c2_c2_split_migration.py` — **18/18 PASS**

- Direct mock target → `pipeline.media_assets.generate_agnes_dialogue_clip`
- test_18 verifies `generate_agnes_dialogue_clip` absent from split caller source

---

## ৯. Regression

| Suite | Result |
|-------|--------|
| test_amp003_task004_c2_e_split_bypass_elimination.py | 13/13 PASS |
| test_amp003_task004_c2_c2_split_migration.py | 18/18 PASS |
| test_amp003_task004_c2_single_failure_propagation.py | 20/20 PASS |
| test_amp003_task004_c2_c3_single_success.py | 16/16 PASS |
| test_amp003_task004_c2_failure_contract.py | 15/15 PASS |
| test_amp003_task004_c2_boundary.py | 18/18 PASS |
| test_amp003_task004_c1_visual_identity.py | 21/21 PASS |
| test_build03_idempotency.py | 14/14 PASS |
| test_build04a_visual_runtime.py | 18/18 PASS |

---

## ১০. Limitations

- Split UNKNOWN/IDENTITY still fall through to image fallback (unlike single path fail-closed) — intentional scope boundary; separate hardening if required
- Image fallback subsystem unchanged (C-4 deferred)
- T004-C2 broader phases (C2-2-D..J, C2-3+) not started

---

## ১১. Deferred

| ID | Item |
|----|------|
| DEF-T004-C1-04 | Image fallback vs visual_runtime (C-4) |
| DEF-AMP003-008 | Live provider poll UNKNOWN |

---

## ১২. Final verdict

**FEATURE STATUS: PASS**

**CHECKPOINT: AMP003-T004-C2-E-PASS**

All production Agnes visual calls in `scene_builder.py` now route exclusively through the canonical idempotent bridge. BYP-01 and BYP-02 both eliminated.

**P0 = 0** | **P1 (BYP-01/02): RESOLVED**

**NEXT:** Remaining T004-C2 work (C2-2-D..J, C2-3+) — user command required.
