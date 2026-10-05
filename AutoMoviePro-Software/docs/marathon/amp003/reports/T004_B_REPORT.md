# T004-B প্রতিবেদন — Scene Contract Runtime Boundary

**Marathon:** AMP-003 / TASK-004  
**Sub-task:** T004-B  
**Checkpoint:** AMP003-T004-B-PASS  
**Verdict:** PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. উদ্দেশ্য

Production pipeline-এ Script/Director Plan → Legacy Scene Dict → Canonical Scene → Validation Gate → Validated Handoff boundary runtime-এ enforce করা। Invalid Scene downstream-এ যেতে পারবে না (fail-closed)।

---

## ২. Pre-Audit

`T004_B_PRE_AUDIT.md` — production scene loop raw dict ব্যবহার করছিল, canonical Scene runtime-এ invoke হচ্ছিল না।

---

## ৩. Current Scene Architecture

```
director_plan.json → plan["scenes"][] (legacy dict)
        ↓
dialogue sanitize (video_pipeline)
        ↓
assert_production_scenes_validated()  [NEW]
        ↓
validated handoff dict (_validated=True)
        ↓
existing scene loop / build_dialogue_clip
```

---

## ৪. Canonical Contract

`domain/scene.py` — Scene, VisualPlan, AudioPlan, SubtitlePlan  
Audit: `T004_B_CONTRACT_AUDIT.md`

---

## ৫. Legacy Adapter

Reuse path:
- `attach_contracts_to_plan` → `preflight_scene_contract`
- `scene_from_legacy_contract` (domain/adapters.py)
- Runtime enrichment: dialogue_id, audio_plan, subtitle_plan

নতুন module: `pipeline/scene_runtime.py`

---

## ৬. Runtime Integration

`video_pipeline.py` — contract wiring gate + dialogue sanitize-এর **পরে**:
```python
assert_production_scenes_validated(plan, job_id=work.name, work_dir=work)
```
Failure → `RuntimeError("scene_contract_blocked:...")` — job stop.

---

## ৭. Identity Model

| Field | Source |
|-------|--------|
| scene UUID | Scene.id |
| scene_index | loop index 0..N-1 contiguous |
| dialogue_id | script.sections[i].dialogues[0].id |
| script_id | script_from_plan().id |
| job_id | work.name (metadata) |

Duplicate scene_id / dialogue_id / non-contiguous order → BLOCK.

---

## ৮. Validation

- preflight PASS required
- dialogue min 8 chars
- visual_plan + shot.subject required
- duration hints validated
- Pydantic extra=forbid + schema version guard

---

## ৯. Fail-Closed Behavior

Invalid Scene → `SceneValidationError` → `scene_contract_blocked` → pipeline stop.  
No log-and-continue for validation failure.

---

## ১০. Scene Ordering

Contiguous indices [0..N-1] enforced in `_assert_identity_integrity`.

---

## ১১. Serialization

`VALIDATED_SCENES.json` checkpoint in work_dir.  
Round-trip: Scene → JSON → Scene (identity preserved).

---

## ১২. Checkpoint/Resume

`persist_validated_scenes()` / `load_validated_scenes()` for resume compatibility.

---

## ১৩. Idempotency Compatibility

`compute_scene_identity_fingerprint()` — same scene → same fingerprint; dialogue change → different fingerprint. Visual/Audio runtime rewire করা হয়নি (T004-C scope)।

---

## ১৪. Orphan Audit

Raw dict consumption after boundary: handoff dict only (`_validated=True`).  
Dialogue sanitize runs **before** validation gate.

---

## ১৫. Bypass Audit

| Bypass | Status |
|--------|--------|
| Raw scene before gate | FIXED — gate before loop |
| attach_contracts offline only | FIXED — runtime call |
| scene_builder direct dict | OK — receives validated handoff |
| Visual/Audio/Render fallbacks | DOCUMENTED — T004-C/H scope |

---

## ১৬. Test Integrity

Real validation paths tested; no weakened assertions; fail-closed verified.

---

## ১৭. Dedicated Tests

| Suite | Result |
|-------|--------|
| `test_amp003_task004_b_scene_contract.py` | 7/7 PASS |
| `test_amp003_task004_b_scene_adapter.py` | 8/8 PASS |
| `test_amp003_task004_b_runtime.py` | 5/5 PASS |
| `test_amp003_task004_b_identity.py` | 6/6 PASS |
| **Total** | **26/26 PASS** |

---

## ১৮. Regression

| Suite | Result |
|-------|--------|
| TASK-001/002/003 | PASS |
| BUILD-00R through BUILD-04E | PASS |
| BUILD-04F | 121 tests PASS |
| BUILD-04G / 04G-H / 04G-H1 | PASS |

---

## ১৯. Files Changed

- `pipeline/scene_runtime.py` (NEW)
- `pipeline/video_pipeline.py` (runtime gate)
- `scripts/test_amp003_task004_b_*.py` (4 files NEW)
- `docs/marathon/amp003/reports/T004_B_*.md`

---

## ২০. Root Causes

| ID | Cause |
|----|-------|
| RC-B01 | BUILD-02 Scene wiring offline-only |
| RC-B02 | No fail-closed preflight at runtime |
| RC-B03 | No stable scene UUID at production handoff |

---

## ২১. Limitations

- Handoff dict still legacy-shaped for scene_builder compatibility (locked canonical IDs embedded)
- segment_id explicit field not in Scene model — deferred to T004-E
- Resume reload from VALIDATED_SCENES.json not auto-wired in video_pipeline resume path (P2)

---

## ২২. Deferred Issues

| ID | Issue | Task |
|----|-------|------|
| DEF-T004-B-01 | Auto-resume from VALIDATED_SCENES.json | T004-J |
| DEF-T004-B-02 | segment_id explicit contract field | T004-E |

---

## ২৩. P0/P1/P2

| Severity | Count |
|----------|-------|
| P0 | 0 |
| P1 | 0 |
| P2 | 2 (documented) |

---

## ২৪. Final Verdict

Mandatory acceptance criteria — ALL MET.

**T004-B = PASS**  
**Checkpoint = AMP003-T004-B-PASS**  
**T004-C = NOT_STARTED**

---

**STOP — T004-C implementation শুরু করা হয়নি।**
