# Render Validation — BUILD-04D

## Layers

1. **Container:** file exists, size ≥ 8000, MP4 ftyp header
2. **ffprobe (when available):** video/audio streams, duration, dimensions
3. **Duration tolerance:** max(2.0s, 5% of expected)
4. **Pre-promotion:** validate `.tmp.mp4` before atomic rename

## Failure codes

- `file_missing`, `zero_bytes`, `too_small`, `invalid_container`
- `missing_video_stream`, `missing_audio_stream`
- `dimension_mismatch`, `duration_mismatch`

## Fallback

If ffprobe unavailable: container + min size validation (`ok_container_only`).
