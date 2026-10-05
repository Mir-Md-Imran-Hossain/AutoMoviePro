# Edge TTS Fallback Flow — BUILD-04B-H

## Entry points

1. **`idempotent_edge_tts`** — canonical edge generation (tests, explicit fallback)
2. **`idempotent_reuse_or_synthesize_tts`** — after Google **FAILED**
3. **`tts_google.synthesize_narration`** — when `idempotency_work_dir` set and Google raises, delegates to `idempotent_edge_tts`

## Provider identity

| Field | Primary (Google) | Fallback (Edge) |
|-------|------------------|-----------------|
| provider | `google` | `edge_tts` |
| model | `gemini-2.5-flash-preview-tts` | `edge-neural` |

Same dialogue text → **different fingerprints** when provider differs.

## Decision policy

```
Google TTS via execute_audio_request
    ↓
SUCCESS → return asset
    ↓
reuse → return cached asset
    ↓
UNKNOWN → RuntimeError (no fallback)
    ↓
FAILED + allow_edge_fallback → idempotent_edge_tts (new provider identity)
    ↓
edge SUCCESS → validate → provenance → checkpoint
```

## UNKNOWN-state rule (H-20)

**Never** transition UNKNOWN → automatic edge_tts. Caller must reconcile primary state first.

## Direct `synthesize_edge_tts`

Legacy direct calls remain in `edge_tts_fallback.py` for backward compatibility when idempotency context is absent. Production paths with `work_dir` use the bridge.

## Validation

Edge results pass the same `validate_audio_asset` boundary as Google. Invalid (empty/corrupt) assets are **not** checkpointed as success.

## Provenance

Records `provider=edge_tts`, fingerprint, dialogue_id, language, voice, duration, asset hash — no secrets.
