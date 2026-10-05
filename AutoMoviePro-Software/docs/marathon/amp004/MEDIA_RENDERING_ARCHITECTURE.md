# Media Rendering Architecture (FFmpeg) — Audit

**AMP-004** · reference: official FFmpeg stream mapping semantics  
**Production code changed:** `false`

---

## Entry points (verified)

| Module | Role |
|--------|------|
| `pipeline/compose.py` | ffmpeg_bin, ffprobe_duration, concat, logo, trim, title card |
| `pipeline/ffmpeg_exec.py` | exec wrapper |
| `pipeline/scene_builder.py` | scene mux, filter_complex concat, -map v/a |
| `pipeline/fallback_image_video.py` | still→motion ffmpeg |
| `pipeline/idempotency/render_*` | BUILD-04D render identity |
| `pipeline/system_profile.py` | x264 args |

---

## Observed patterns

- `-map` video + audio on mux paths (scene_builder)  
- `filter_complex` concat `n=…:v=1:a=1[v][a]`  
- Hard gates: black_tail, end_frame_freeze, leading_silence, duration windows  
- Atomic promotion: idempotent render runtime patterns  

---

## Audit checklist status

| Concern | Status |
|---------|--------|
| Input/output mapping | Present in mux paths; not single schema |
| Subtitle burn vs softsubs | Mixed legacy paths; 04E structural |
| Timebase/FPS/SAR/DAR | Partial via encode args; not fully contracted |
| Pixel format / codec / bitrate | x264 profile helpers |
| Audio sample rate / layout | Partial |
| Loudness / ducking | **MISSING** |
| A/V sync | Duration-based gates; not sample-accurate |
| Black/frozen frames | Detected (gates + visual_qa) |
| Partial/corrupt output | Container size/ftyp checks |
| Temp files / retry | Idempotency + mock providers |
| Final container validity | validate + ship gate |

---

## Gaps (P1/P2)

- Formal FiltergraphContract  
- Loudness (LUFS) + music ducking  
- Unified master encode policy  
- Comprehensive filter ordering documentation per scene template  

**এই audit FFmpeg rewrite করে না।**
