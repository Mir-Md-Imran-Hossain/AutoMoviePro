# SUBTITLE_DIALOGUE_MAPPING

Explicit binding via SubtitleRequestSpec:
```
subtitle.meta.dialogue_id == source_dialogue.dialogue_id
```

No list-position inference. Segment-level entity IDs prevent split-dialogue collision.

Validation: `validate_subtitle_bindings` + meta sidecar check.
