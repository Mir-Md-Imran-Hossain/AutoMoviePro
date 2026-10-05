# BUILD-04B-H Pre-Hardening Audit

## Baseline (pre-H)

| Build | Status |
|-------|--------|
| BUILD-00R | PASS |
| BUILD-01 | PASS |
| BUILD-02 | PASS |
| BUILD-03 | PASS |
| BUILD-04A | PASS |
| BUILD-04B | PASS (core; 3 paths deferred) |

## Deferred from BUILD-04B (P2)

1. **localization.py** — per-scene and master localization TTS called `reuse_or_synthesize_tts` / `synthesize_narration` without canonical idempotency when `work_dir` was omitted.
2. **scene_builder split-path** — `CHERNOBYL_RE_TTS_PARTS` loop called `synthesize_narration` directly per segment.
3. **edge_tts fallback** — `tts_google.synthesize_narration` and `tts_reuse.reuse_or_synthesize_tts` invoked `synthesize_edge_tts` directly without fingerprint/idempotency.

## Existing BUILD-03 / BUILD-04B infrastructure (reused)

| Module | Role |
|--------|------|
| `pipeline/idempotency/audio_request.py` | `AudioRequestSpec`, fingerprint, `entity_id`, `segment_id` |
| `pipeline/idempotency/audio_runtime.py` | `execute_audio_request` lifecycle |
| `pipeline/idempotency/tts_bridge.py` | Canonical TTS entrypoints |
| `pipeline/idempotency/audio_validation.py` | Asset validation boundary |
| `pipeline/idempotency/audio_provenance.py` | Provenance persistence |
| `pipeline/idempotency/embedded_audio.py` | English embedded skip |
| `pipeline/idempotency/mock_audio_provider.py` | Offline test provider |

## Pre-H runtime gaps

- Localization paths did not always pass `work_dir` → bypassed `idempotent_reuse_or_synthesize_tts`.
- Split dialogue segments shared text-only identity risk (no stable `segment_id`).
- Edge fallback created competing assets without distinct provider fingerprint.
- UNKNOWN primary state could theoretically race with uncontrolled fallback (policy undefined).

## Hardening approach

- Extend `AudioRequestSpec.segment_id` and `entity_id` suffix for split segments.
- Route localization/split/reuse through `idempotent_reuse_or_synthesize_tts` / `idempotent_synthesize_narration`.
- Route edge fallback through `idempotent_edge_tts` with `provider=edge_tts`.
- Enforce: edge fallback only after Google **FAILED**, never on **UNKNOWN**.
- Do **not** rewrite `synthesize_narration` engine logic.

## Out of scope (this build)

- `av_self_repair_agent.py` direct TTS (repair utility; documented as BLOCKED)
- Training/dev scripts under `scripts/` (non-production entrypoints)
- Voice quality, dialogue quality, localization translation quality
