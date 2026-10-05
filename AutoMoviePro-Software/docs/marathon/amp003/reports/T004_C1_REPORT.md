# T004-C1 — Visual Request Contract Audit & Identity Hardening

**Marathon:** AMP-003 / TASK-004 / T004-C  
**Phase:** C-1 (C1-0 … C1-11)  
**Date:** 2026-08-31  
**Checkpoint:** AMP003-T004-C1-PASS

---

## 1. উদ্দেশ্য

Production visual request-এর canonical identity, deterministic fingerprint, fail-closed validation এবং provenance/idempotency compatibility নিশ্চিত করা — Agnes runtime rewrite, image fallback rewrite, বা provider পরিবর্তন ছাড়াই।

---

## 2. Contract Discovery

C1-0-এ `VisualRequestSpec`, `Scene`, `Dialogue`, `Script`, `VisualPlan` inspect করা হয়েছে।  
Discovery report: `docs/marathon/amp003/reports/T004_C1_CONTRACT_DISCOVERY.md`

---

## 3. Identity Source Map

| Field | Source | Status |
|-------|--------|--------|
| job_id | work.name / handoff metadata | VERIFIED |
| scene_id (int) | scene_index / loop idx | VERIFIED |
| canonical_scene_id | T004-B handoff Scene.id | PROPAGATED |
| dialogue_id | T004-B handoff Script dialogue UUID | PROPAGATED |
| script_id | T004-B handoff | PROPAGATED |
| segment_id | scene_builder split `seg-{n:02d}` | OPERATIONAL (not domain) |
| part_index | split loop i+1 | VERIFIED |
| revision_id | caller-supplied (mirror script pattern) | ADDED |
| seed | VisualRequestSpec optional | Agnes: NOT SUPPORTED |
| visual_plan_id | element / p{part_index} | VERIFIED |

---

## 4. Visual Identity Model

**Minimum logical identity:**
- job + scene (int index + canonical UUID) + dialogue + visual request + provider + model + generation mode + meaningful generation params

**Single-beat path:**
- entity_id = `scene-{idx:02d}-{dialogue_id}` (dialogue_id absent হলে visual_plan_id fallback — legacy/mock only)
- part_index=0, segment_id empty

**Split-dialogue path:**
- entity_id = `scene-{idx:02d}-{dialogue_id}-seg-{nn}` (অথবা `-p{n}`)
- part_index=i+1, segment_id=`seg-{i+1:02d}` — TTS path-এর সাথে aligned
- production split-এ segment_id mandatory — missing হলে BLOCK

---

## 5. Scene Identity

- Runtime int `scene_id` = T004-B `scene_index`
- Canonical UUID = `canonical_scene_id` — production validation-এ mandatory
- Cross-scene contamination: expected_scene_index / expected_canonical_scene_id mismatch → BLOCK

---

## 6. Dialogue Identity

- Canonical dialogue UUID from validated handoff
- Production path: `dialogue_id` mandatory
- Cross-dialogue contamination: expected_dialogue_id mismatch → BLOCK
- Split TTS-এ `split-{idx:02d}` operational string exists — visual Agnes path এখন canonical UUID ব্যবহার করে; TTS split string alignment **DEFERRED T004-E**

---

## 7. Segment Identity

- Domain Scene-এ explicit `segment_id` field **নেই** → **DEFERRED T004-E**
- C1-এ operational `segment_id` string (`seg-01`, `seg-02`) fingerprint + entity_id-তে bind করা হয়েছে
- Fake domain segment ID invent করা হয়নি
- Split part-এ segment_id missing + part_index>0 → BLOCK (agnes_bridge)

---

## 8. Revision Identity

- `revision_id` empty = base identity (retry same fingerprint)
- `revision_id` non-empty = intentional repair/regeneration → new fingerprint
- attempt number fingerprint-এ exclude (BUILD-03 semantics preserved)
- `_legacy_key` এখন `entity_id` ব্যবহার করে — revision change stale cache reuse block

---

## 9. Seed Policy

| Provider | Seed |
|----------|------|
| Agnes | **NOT SUPPORTED** — `generate_agnes_dialogue_clip` has no seed param |
| Mock visual | Supported — fingerprint-এ include |
| Image fallback | Separate path — `character_base_seed` — **C-4 scope** |

**Decision:** Fake seed metadata তৈরি করা হয়নি; Agnes limitation documented.

---

## 10. Fingerprint Model

```
compute_fingerprint(
  job_id, stage="visual",
  entity_id=spec.entity_id,  # includes dialogue, segment, revision
  provider, model,
  inputs=normalized_inputs()  # all identity + generation params
)
```

Meaningful change → different fingerprint verified for: prompt, scene, dialogue, segment, provider, model, resolution, seed, revision.

---

## 11. Normalization

- `canonical_json` + `normalize_value` — sorted keys, stripped strings, rounded floats
- attempt/timestamp excluded
- Whitespace normalization stable (TEST-12 PASS)
- JSON key ordering stable (TEST-11 PASS)

---

## 12. Validation

**Functions:**
- `validate_visual_request_identity()` — fail-closed
- `build_visual_request_from_handoff()` — validated handoff only

**Production mandatory:**
- job_id, scene_id≥0, visual_plan_id, provider, model
- dialogue_id, canonical_scene_id (production=True)

**BLOCK conditions:**
- missing mandatory identity
- invalid scene_id
- cross-scene / cross-dialogue mismatch
- split part without segment_id

---

## 13. Backward Compatibility

- Legacy mock/BUILD-04A callers: dialogue_id/canonical_scene_id empty → no production validation
- entity_id falls back to visual_plan_id when dialogue_id absent
- `scripts/test_build04a_visual_runtime.py` — **18/18 PASS**
- Silent compatibility forbidden — explicit opt-in via empty identity fields for test/legacy

---

## 14. Provenance Compatibility

- `save_visual_provenance` metadata extended: dialogue_id, canonical_scene_id, segment_id, part_index, revision_id, entity_id
- Test: request fingerprint == persisted provenance input_hash — **PASS**

---

## 15. Idempotency Compatibility

- Same request → same fingerprint → reuse (provider calls=0 on second run)
- Different revision → different fingerprint → new execution
- BUILD-03 executor compatible — entity_id + normalized_inputs passed to executor

---

## 16. Tests

**File:** `scripts/test_amp003_task004_c1_visual_identity.py`

| Test | Description | Result |
|------|-------------|--------|
| TEST-01 | same request → same fingerprint | PASS |
| TEST-02 | prompt change → different fingerprint | PASS |
| TEST-03 | scene change → different fingerprint | PASS |
| TEST-04 | dialogue change → different fingerprint | PASS |
| TEST-05 | segment change → different fingerprint | PASS |
| TEST-06 | provider change → different fingerprint | PASS |
| TEST-07 | model change → different fingerprint | PASS |
| TEST-08 | resolution change → different fingerprint | PASS |
| TEST-09 | seed change → different fingerprint | PASS |
| TEST-10 | revision change → different fingerprint | PASS |
| TEST-11 | JSON ordering → same fingerprint | PASS |
| TEST-12 | whitespace normalization stable | PASS |
| TEST-13 | missing mandatory identity → BLOCK | PASS |
| TEST-14 | invalid identity → BLOCK | PASS |
| TEST-15 | cross-scene contamination → BLOCK | PASS |
| TEST-16 | cross-dialogue contamination → BLOCK | PASS |
| TEST-17 | split segment collision → BLOCK | PASS |
| TEST-18 | intentional revision → new identity | PASS |

**Total: 21/21 PASS**

---

## 17. Regression

| Suite | Result |
|-------|--------|
| test_build04a_visual_runtime.py | 18/18 PASS |
| test_amp003_task004_b_identity.py | 6/6 PASS |

---

## 18. Limitations

- Agnes provider seed unsupported — documented, not faked
- Image fallback path still bypasses visual_runtime — **C-4 scope**
- Exception fallback in agnes_bridge still bypasses idempotency — **C-2 scope**
- `_resolve_footage` split fallback `scene_id=idx*10+i` hack unchanged — **C-2 scope**

---

## 19. Deferred Issues

| ID | Issue | Task |
|----|-------|------|
| DEF-T004-C1-01 | Domain explicit segment_id on Scene | T004-E |
| DEF-T004-C1-02 | Split TTS dialogue_id vs canonical UUID alignment | T004-E |
| DEF-T004-C1-03 | Agnes Exception fallback bypass | T004-C C-2 |
| DEF-T004-C1-04 | Image fallback visual_runtime wiring | T004-C C-4 |
| DEF-T004-C1-05 | idx*10+i split fallback identity hack | T004-C C-2 |

---

## 20. P0/P1/P2

| Priority | Count | Notes |
|----------|-------|-------|
| P0 | 0 | — |
| P1 | 0 | C1 scope items resolved or deferred with task ref |
| P2 | 2 | Agnes seed limitation; domain segment_id → T004-E |

---

## 21. Final Verdict

**C1 STATUS: PASS**  
**Checkpoint: AMP003-T004-C1-PASS**

C1-0 contract discovery complete. Identity model defined. Fingerprint deterministic. Fail-closed validation implemented. Provenance + idempotency compatible. Regression PASS. P0=0, P1=0.

**STOP — C-2, T004-D, TASK-005 NOT STARTED**
