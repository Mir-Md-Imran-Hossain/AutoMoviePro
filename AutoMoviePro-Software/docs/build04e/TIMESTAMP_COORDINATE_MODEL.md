# TIMESTAMP_COORDINATE_MODEL

## Primary Model: `audio_relative`
Subtitle cue timestamps are **0 .. audio_duration_sec** relative to the narration audio track.

- Scene mux / remux: FFmpeg `subtitles` filter aligns SRT 0 to audio stream start
- Global video timing is **not** accumulated in subtitle generation
- Global concat timing computed only at render/concat layer

## Coordinate Conversion (when needed)
```
global_start = scene_global_start + cue_local_start
global_end   = scene_global_start + cue_local_end
```
Use scene boundary from ffprobe/ manifest — do not repeatedly accumulate floating offsets.

## Precision
- Internal: round to 3 decimal places (ms in SRT)
- Tolerance: `TIMING_TOLERANCE_SEC = 0.05`

## 0.5 Second Margin Rule
When `scene_duration_sec > 0`:
```
required = audio_duration + leading_gap + trailing_gap
PASS if required <= scene_duration + tolerance
FAIL with margin_impossible otherwise
```
Default gaps: 0.5s leading, 0.5s trailing.

## Anti-pattern (fixed in BUILD-04E)
Master SRT previously used **final concatenated video** duration — now uses **en_audio** (TTS/Agnes) as authoritative.
