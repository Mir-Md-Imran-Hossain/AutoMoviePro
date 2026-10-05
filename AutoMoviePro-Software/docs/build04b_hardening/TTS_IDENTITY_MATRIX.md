# TTS Identity Matrix — BUILD-04B-H

## Fingerprint inputs (normalized)

| Dimension | Included | Notes |
|-----------|----------|-------|
| job_id | Yes | Per work directory |
| entity_id | Yes | `scene-{id}-{dialogue_id}[-segment]` |
| dialogue_text | Yes | Stripped |
| language | Yes | Lowercase |
| provider | Yes | `google` vs `edge_tts` distinct |
| model | Yes | Provider-specific |
| voice_id / voice_profile | Yes | Resolved voice |
| emotion | Yes | Default neutral |
| speaking_speed | Yes | Rounded 4dp |
| part_index | Yes | Split order |
| segment_id | Yes | Stable logical segment |
| audio_plan_id | Yes | Plan scope |
| timestamp | **No** | |
| attempt number | **No** | |

## Collision prevention

| Case | Distinct? | Test |
|------|-----------|------|
| Same text, different language | Yes | H02 |
| Same text, en vs es vs bn vs hi | Yes | H02 |
| Scene-A seg-01 "Hello" vs Scene-B seg-01 "Hello" | Yes | H07 |
| Google vs edge_tts same text | Yes | H09, H14 |
| Same request twice | Same fingerprint | H01, H06, H10 |
| Retry after transient fail | Same fingerprint | H03, H12 |

## Localization identity

- `dialogue_id`: `loc-{scene:02d}-{lang}` or `master-{slug}-{lang}`
- Language in normalized inputs prevents cross-language cache reuse.

## Split identity

- `dialogue_id`: `split-{scene:02d}`
- `segment_id`: `seg-{n:02d}`
- `entity_id`: e.g. `scene-10-split-10-seg-02`

## Fallback identity

Fallback is **not** a retry of primary — separate `provider=edge_tts` fingerprint.
