# Script Validation — BUILD-04C

## Layers

### 1. Director plan validation (`validate_director_plan`)

- Plan is dict with non-empty title/topic
- `scenes` is non-empty list
- Each scene has non-empty `narration` or `dialogue`
- Optional `dialogue_id` / `scene_id` must be unique

### 2. Script contract validation (`validate_script_contract`)

- Builds `Script` via `script_from_plan`
- Pydantic validators (title, dialogue text)
- Each section has at least one dialogue
- No duplicate dialogue scene_id keys

### 3. Combined (`validate_plan_and_script`)

Used at runtime checkpoint boundary — invalid scripts are **not** marked SUCCEEDED.

## Explicitly excluded (deferred builds)

- Human-like dialogue quality
- Hook / retention scoring
- Emotional naturalness

## Test coverage

| Case | Test |
|------|------|
| Duplicate dialogue IDs | test_13 |
| Missing narration | test_14 |
| Empty response | test_12 |
| Invalid existing reuse | test_10 |
| Malformed / empty title | test_11 |
