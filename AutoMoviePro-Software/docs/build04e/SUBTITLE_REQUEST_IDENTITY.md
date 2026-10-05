# SUBTITLE_REQUEST_IDENTITY

## Hierarchy
```
Job (job_id)
  └── Scene (scene_id)
        └── Dialogue (dialogue_id)
              └── Segment (segment_id, optional)
                    └── Language (language)
```

## Entity ID
`sub-{scene_id}-{dialogue_id}[-{segment_id}]-{language}`

## SubtitleRequestSpec Fields (fingerprint inputs)
- scene_id, dialogue_id, segment_id, language
- localized_text_hash (not raw text)
- audio_fingerprint, audio_duration_sec
- subtitle_format, subtitle_template_version, timing_model
- scene_duration_sec, leading_gap_sec, trailing_gap_sec
- provider, model, subtitle_contract_version

## Excluded from fingerprint
- retry number, execution UUID, timestamps

## Stable Identity Rule
Identity MUST NOT depend only on filename, list index, or random ID.
