# BUILD-04D Test Plan

Suite: `scripts/test_build04d_render_runtime.py` — 35 tests (33 pass + 2 skip when ffmpeg/ffprobe unavailable).

Covers D01–D35 per build spec.

Regression: BUILD-00R through BUILD-04C + BUILD-04D.

Smoke: `/api/status` → 200.

Real FFmpeg test (04D-48/49): deferred opt-in; mock coverage complete.
