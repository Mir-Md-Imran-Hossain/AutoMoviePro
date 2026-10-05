# SUBTITLE_AUDIO_ALIGNMENT

Actual audio duration is authoritative. SubtitleRequestSpec includes:
- `audio_fingerprint` — hash of audio file
- `audio_duration_sec` — ffprobe duration

Fingerprint changes when audio identity or duration changes → stale subtitle detected.

Production paths use narration audio (not final video) for timing.
