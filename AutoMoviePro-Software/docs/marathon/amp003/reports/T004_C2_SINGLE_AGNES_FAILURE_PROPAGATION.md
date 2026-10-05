# T004-C2 — Single Agnes Failure Propagation Hardening

**Marathon:** AMP-003  
**Task:** TASK-004 / T004-C  
**Phase:** C2-SINGLE-FAILURE-PROPAGATION (C2-2-C-3-FP)  
**Checkpoint:** AMP003-T004-C2-SINGLE-FAILURE-PROPAGATION-PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## ১. উদ্দেশ্য

এই ফেজের লক্ষ্য হলো single-beat Agnes production runtime-কে এমনভাবে শক্ত করা যাতে `SUCCESS`, `REUSED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `UNKNOWN`, `IDENTITY_BLOCKED` এবং unexpected `Exception` — প্রতিটির জন্য deterministic, explicit এবং safe runtime semantics থাকে।

প্রতিরোধ করতে হবে:

- false SUCCESS
- blind provider retry
- silent UNKNOWN degradation
- identity bypass
- uncontrolled direct Agnes execution
- unintended failure masking

একই সাথে intentionally configured image fallback সংরক্ষণ করতে হবে, তবে Agnes SUCCESS হিসেবে mislabel করা যাবে না।

---

## ২. বর্তমান architecture

```
Scene
  ↓
Visual Request Identity (dialogue_id, canonical_scene_id, job_id, script_id)
  ↓
_resolve_footage() — single Agnes path
  ↓
_resolve_single_agnes_beat_src()
  ↓
idempotent_generate_agnes_beat_result()  [agnes_bridge.py]
  ↓
visual_runtime (BUILD-03/04A idempotency)
  ↓
VisualGenerationResult
  ↓
classify_agnes_beat_outcome() → AgnesBeatOutcome
  ↓
Controlled Failure/Success Boundary (_resolve_footage)
  ↓
Scene Builder / downstream pipeline
```

**গুরুত্বপূর্ণ:** Provider invocation (`generate_agnes_dialogue_clip`) শুধুমাত্র bridge/runtime এর ভিতরে অনুমোদিত। Single path থেকে direct bypass (BYP-02) সরানো হয়েছে।

---

## ৩. Pre-audit findings (C2-2-C-3-3-1)

| Finding | Pre-fix অবস্থা |
|---------|----------------|
| Structured FAILED | `path=None` → silent image fallback |
| UNKNOWN | silent image fallback — job চলতে থাকত |
| IDENTITY_BLOCKED | fail-closed নয় — fallback হত |
| BYP-02 | Exception হলে `_resolve_footage` থেকে direct `generate_agnes_dialogue_clip()` |
| `_agnes_beat_result` | L2182-এ discard — outcome information loss |
| SUCCESS/REUSED | C2-2-C-3-2-এ ঠিক করা হয়েছিল — preserve |

---

## ৪. SUCCESS semantics

- `classify_agnes_beat_outcome()` → `SUCCESS`
- `validate_visual_asset()` PASS
- Valid `Path` → **immediate return**
- Image fallback **নয়**
- দ্বিতীয় provider call **নয়**

---

## ৫. REUSED semantics

- Cached idempotent result → `REUSED`
- `validate_visual_asset()` PASS
- Valid cached `Path` → **immediate return**
- Provider invocation count = 0 (reuse path)
- Image fallback **নয়**

---

## ৬. FAILED_RETRYABLE

- Runtime-এ bounded retry policy আগে থেকেই আছে (BUILD-03/04A)
- `_resolve_footage` থেকে **direct provider call নয়**
- Exhausted হলে explicit log:
  `"Agnes FAILED_RETRYABLE — not Agnes success; fallback may apply"`
- `allow_image_fallback=True` হলে image Ken-Burns fallback (explicit, Agnes SUCCESS নয়)
- `require_agnes=True` হলে fallback block হতে পারে (existing contract)

---

## ৭. FAILED_FINAL

- **কখনো SUCCESS হয় না**
- Fake Path তৈরি হয় না
- Explicit log → configured image fallback (যদি allowed)
- Fallback path Agnes generation হিসেবে report হয় না

---

## ৮. UNKNOWN

UNKNOWN = provider execution state uncertain।

**নিয়ম:**
- NO blind retry
- NO second provider invocation from scene_builder
- NO fabricated success
- `try_reconcile_agnes_beat_unknown()` — existing BUILD-03/04A reconciliation
- Reconcile fail → `raise AgnesOutcomeError("UNKNOWN", ...)`
- Image fallback **নয়** (fail-closed at boundary)

---

## ৯. IDENTITY_BLOCKED

Invalid/missing production identity (`dialogue_id`, `canonical_scene_id`, etc.):

- Provider invocation = **0**
- `segment_id` / `revision_id` fabricate হয় না
- `raise AgnesOutcomeError("IDENTITY_BLOCKED", ...)`
- Provider failure থেকে distinguishable

---

## ১০. Exception handling

- Unexpected Exception → log + `agnes_outcome_label="EXCEPTION"`
- **BYP-02 removed** — direct `generate_agnes_dialogue_clip()` নয়
- Configured image fallback (explicit log: `Agnes outcome=EXCEPTION`)
- Quota error → existing `record_quota_hit("agnes")`

---

## ১১. BYP-02

| Item | Status |
|------|--------|
| BYP-02 (single path Exception → direct Agnes) | **REMOVED** |
| BYP-01 (split path Exception → direct Agnes, L1464–1480) | **REMAINS** — deferred to C2-2-E |

Single path: Exception → image fallback only, never direct provider.

---

## ১২. Image fallback

- `build_image_video_fallback()` / Ken-Burns subsystem **অপরিবর্তিত** (C-4 scope নয়)
- Fallback log: `"image→video fallback (Agnes outcome=%s err=%s)"`
- Fallback success ≠ Agnes SUCCESS
- FAILED_* + EXCEPTION → fallback when `allow_image_fallback=True`
- UNKNOWN / IDENTITY_BLOCKED → **no fallback** (raise)

---

## ১৩. Identity propagation

| Field | Single path |
|-------|-------------|
| `canonical_scene_id` | bridge spec → runtime |
| `dialogue_id` | bridge spec → runtime |
| `job_id` | `work.name` fallback |
| `script_id` | preserved |
| `part_index` | 0 (single beat) |

Tests: TEST-12..14 in dedicated suite verify propagation.

---

## ১৪. Idempotency

- Same fingerprint → max one provider execution (BUILD-03 preserved)
- REUSED → zero additional provider calls
- UNKNOWN second call → same count (no blind retry)
- Concurrent duplicate protection unchanged (BUILD-04A test_06 PASS this run)

---

## ১৫. Retry control

- Retry budget inside `visual_runtime` / idempotency executor
- scene_builder independent retry loop **নেই**
- FAILED_RETRYABLE exhausted → controlled non-success → optional fallback
- Provider count bounded by existing policy

---

## ১৬. Failure masking audit

| Pattern | Result |
|---------|--------|
| failure → fake Path | **BLOCKED** — validate fails or no path |
| UNKNOWN → SUCCESS | **BLOCKED** — raise or reconcile only |
| identity failure → provider call | **BLOCKED** — provider=0 |
| FAILED → unlimited retry | **BLOCKED** — bounded runtime retry |
| bridge error → direct provider (single) | **REMOVED** (BYP-02) |
| invalid cached asset → accepted | **BLOCKED** — validate_visual_asset |
| invalid generated asset → accepted | **BLOCKED** |
| image fallback → Agnes success label | **BLOCKED** — explicit outcome log |

---

## ১৭. Direct provider audit

`generate_agnes_dialogue_clip(` occurrences:

| Location | Classification |
|----------|----------------|
| `pipeline/media_assets.py:507` | Provider definition |
| `pipeline/idempotency/agnes_bridge.py:264` | **BRIDGE_INTERNAL** |
| `pipeline/scene_builder.py:1465` | **PRODUCTION_BYPASS (BYP-01)** — split path only |
| `scripts/chernobyl_30_train.py:476` | **DEV** |
| `scripts/_smoke_agnes_clip.py:25` | **DEV** |
| `docs/marathon/amp003/reports/*` | Documentation |

**Acceptance:** No **NEW** production bypass. BYP-02 removed from single path. BYP-01 remains on split path.

---

## ১৮. Implementation

### Modified files

1. **`pipeline/scene_builder.py`**
   - `AgnesOutcomeError` exception class
   - `_resolve_footage()` single Agnes block: outcome-aware boundary
   - BYP-02 removed
   - UNKNOWN reconcile + fail-closed
   - IDENTITY_BLOCKED fail-closed

2. **`pipeline/idempotency/agnes_bridge.py`**
   - `try_reconcile_agnes_beat_unknown()` — wraps existing reconciliation

3. **`scripts/test_amp003_task004_c2_single_failure_propagation.py`** — NEW 20 tests

4. **`scripts/test_amp003_task004_c2_c3_single_success.py`** — TEST-14/15 updated for new semantics

---

## ১৯. Tests

### Dedicated suite: `test_amp003_task004_c2_single_failure_propagation.py`

**২০/২০ PASS**

| # | Scenario |
|---|----------|
| 1–2 | SUCCESS, REUSED |
| 3–4 | FAILED_RETRYABLE, FAILED_FINAL explicit fallback |
| 5–6 | UNKNOWN blocked, IDENTITY_BLOCKED fail-closed |
| 7 | Exception no direct bypass |
| 8–9 | Invalid asset, no false success |
| 10 | UNKNOWN no blind retry |
| 11 | Provider count on reuse |
| 12–14 | Identity propagation |
| 15 | Legacy API |
| 16 | Image fallback not Agnes path |
| 17 | BYP-02 removed |
| 18–20 | No direct provider, C3-2 preserved, split helper available |

---

## ২০. Regression

| Suite | Result |
|-------|--------|
| test_amp003_task004_c2_c3_single_success.py | 16/16 PASS |
| test_amp003_task004_c2_single_failure_propagation.py | 20/20 PASS |
| test_amp003_task004_c2_c2_split_migration.py | 18/18 PASS |
| test_amp003_task004_c2_failure_contract.py | 15/15 PASS |
| test_amp003_task004_c2_boundary.py | 18/18 PASS |
| test_amp003_task004_c1_visual_identity.py | 21/21 PASS |
| test_amp003_task004_b_identity.py | 6/6 PASS |
| test_build03_idempotency.py | 14/14 PASS |
| test_build04a_visual_runtime.py | 18/18 PASS (test_06 PASS this run) |
| test_amp003_task001.py | 35/35 PASS |
| test_amp003_task002.py | 21/21 PASS |
| test_amp003_task003.py | 20/20 PASS |

---

## ২১. Limitations

- Split path BYP-01 (Exception → direct Agnes) এখনো আছে — C2-2-E scope
- Image fallback subsystem redesign করা হয়নি (C-4 deferred)
- Live provider poll for UNKNOWN reconciliation নেই (DEF-AMP003-008)
- Production default `require_agnes=False` — FAILED still gets image fallback by design

---

## ২২. Deferred items

| ID | Item | Next |
|----|------|------|
| BYP-01 | Split path direct Agnes on Exception | C2-2-E |
| DEF-T004-C1-03 | Exception fallback bypass (split) | C2-2-E |
| DEF-T004-C1-04 | Image fallback vs visual_runtime | C-4 |
| DEF-AMP003-008 | Live provider poll UNKNOWN | Future |

---

## ২৩. Final verdict

**FEATURE STATUS: PASS**

**CHECKPOINT: AMP003-T004-C2-SINGLE-FAILURE-PROPAGATION-PASS**

Single-beat Agnes failure propagation hardened. SUCCESS/REUSED preserved. FAILED explicit fallback. UNKNOWN/IDENTITY fail-closed. BYP-02 removed. No new production bypass. All behavioral tests and regressions PASS.

**P0 = 0** | **No new unexplained P1**

**NEXT:** T004-C2-2-E (BYP-01 split path elimination) — user command required; do not auto-start.
