# SUBTITLE_VALIDATION

## Timestamp Rules
- start >= 0
- end > start
- duration > 0
- no unintended overlap (tolerance 0.05s)

## Binding Rules
- meta sidecar scene_id, dialogue_id, language, segment_id must match request
- provider cues validated before write

## Scene Boundary
- cue end <= audio_duration + 0.25s tolerance
- 0.5s margin when scene_duration_sec provided

## Rejection Codes
`missing_or_empty`, `malformed_or_empty`, `cue_N_negative_start`, `cue_N_end_before_start`, `cue_N_overlap`, `meta_wrong_*`, `duplicate_cue_id`, `exceeds_audio_duration`, `margin_impossible`

## Checkpoint Rule
Invalid subtitle MUST NOT reach SUCCEEDED checkpoint.
