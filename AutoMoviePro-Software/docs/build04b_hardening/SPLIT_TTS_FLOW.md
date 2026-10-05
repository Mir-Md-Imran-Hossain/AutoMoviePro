# Split-Path TTS Flow — BUILD-04B-H

## Trigger

Environment flag `CHERNOBYL_RE_TTS_PARTS=1` enables per-segment TTS in `_build_split_dialogue_clip` (`scene_builder.py`).

## Flow

```
split dialogue segments (segs[])
    ↓
for each segment i:
    segment_id = f"seg-{i+1:02d}"
    dialogue_id = f"split-{idx:02d}"
    part_index = i + 1
    ↓
idempotent_synthesize_narration(work, ...)
    ↓
build_audio_spec(... segment_id, part_index ...)
    ↓
execute_audio_request → fingerprint → idempotency → provider → validate → provenance → checkpoint
    ↓
part audio file: narr_tts_{i}.m4a
```

## Stable segment identity

| Field | Example |
|-------|---------|
| scene_id | `10` |
| dialogue_id | `split-10` |
| segment_id | `seg-01`, `seg-02`, `seg-03` |
| entity_id | `scene-10-split-10-seg-01` |

Identical text in different scenes or segments produces **distinct fingerprints** because `entity_id` includes scene, dialogue, and segment.

## Cutoff repair path

`_repair_cutoff_with_complete_tts` uses:

- `dialogue_id`: `scene-{idx:02d}-cutoff-repair`
- `segment_id`: `cutoff-repair`

## Fallback

If bridge import fails, `synthesize_narration` is called with full idempotency kwargs (same identity).

## Partial failure / crash recovery

Idempotency store tracks each segment independently. On restart:

- Completed segments → **reuse**
- Failed/in-progress segment → **resume/retry** (same fingerprint)
- Not-started segments → generate when reached
