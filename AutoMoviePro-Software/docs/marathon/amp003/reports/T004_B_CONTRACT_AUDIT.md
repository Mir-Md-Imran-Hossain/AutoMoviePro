# T004-B B-1 — Canonical Scene Contract Audit

**Marathon:** AMP-003 / TASK-004 / T004-B  
**Phase:** B-1  
**Date:** 2026-08-31

---

## Scene Model (`domain/scene.py`)

### Scene (TimestampedContract)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | str | yes | default `"1.0.0"`, semver validated |
| `id` | str (UUID) | yes | auto `new_id()` |
| `created_at` | datetime | yes | auto |
| `updated_at` | datetime | optional | |
| `script_id` | str | optional | set at runtime boundary |
| `scene_index` | int | yes | `ge=0`, unique per job |
| `legacy_scene_id` | int | optional | legacy idx mirror |
| `element` | str | yes | non-empty, stripped |
| `claim_id` | str | optional | |
| `dialogue_id` | str | optional | required at production boundary |
| `primary_claim` | str | optional | |
| `visual_plan` | VisualPlan | optional | required at production boundary |
| `audio_plan` | AudioPlan | optional | set at runtime boundary |
| `subtitle_plan` | SubtitlePlan | optional | set at runtime boundary |
| `duration_target_sec` | float | optional | `ge=0.0` |
| `metadata` | dict | optional | dialogue text, job_id |

### VisualPlan

| Field | Required |
|-------|----------|
| `scene_id` | yes (UUID str) |
| `dialogue_id` | optional → set at boundary |
| `shot` | yes (ShotPlan) |
| `evidence` | default VisualEvidence |

### ShotPlan — required strings

`subject`, `action`, `environment` (camera/lighting/composition have defaults)

### AudioPlan

| Field | Required at boundary |
|-------|---------------------|
| `scene_id` | yes |
| `dialogue_id` | yes |
| `language` | default `"en"` |

### SubtitlePlan

| Field | Required at boundary |
|-------|----------|
| `scene_id` | yes |
| `cues` | generated from dialogue |

---

## Legacy → Canonical Mapping

```
legacy plan row (narration, element, visual_prompt, ...)
        ↓
build_scene_contract(row, scene_id=i)  → scene_contract v0 dict
        ↓
preflight_scene_contract()  → PASS/FAIL/UNKNOWN
        ↓
scene_from_legacy_contract(contract)  → Scene + VisualPlan
        ↓
runtime enrichment  → dialogue_id, audio_plan, subtitle_plan
        ↓
validate_contract_version(Scene)  → schema guard
```

---

## Validation Policy

| Check | Enforcer |
|-------|----------|
| extra fields forbidden | Pydantic `extra=forbid` |
| schema major version | `from_json_dict` / `validate_contract_version` |
| preflight PASS | `preflight_scene_contract` |
| dialogue present | `build_canonical_scene` (min 8 chars) |
| visual_plan present | `build_canonical_scene` |
| shot.subject non-empty | `build_canonical_scene` |
| identity unique | `_assert_identity_integrity` |
| ordering contiguous 0..N-1 | `_assert_identity_integrity` |
| duration valid | `_scene_duration_hint` |

---

## Serialization

- `Scene.to_json_dict()` → JSON-serializable
- `Scene.from_json_dict()` → major version guard
- Checkpoint: `{work_dir}/VALIDATED_SCENES.json`

---

## B-1 Acceptance

Valid Scene → PASS; missing/malformed/invalid duration/wrong schema/extra fields → FAIL (verified in dedicated tests).

**B-1 = PASS**
