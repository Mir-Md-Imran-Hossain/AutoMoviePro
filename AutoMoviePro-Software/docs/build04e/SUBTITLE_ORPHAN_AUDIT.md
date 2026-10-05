# SUBTITLE_ORPHAN_AUDIT

| Orphan Type | Detection |
|-------------|-----------|
| subtitle without dialogue binding | meta/dialogue_id mismatch validation |
| subtitle without scene | meta/scene_id mismatch |
| subtitle without language | meta/language mismatch |
| subtitle without audio dep | audio_fingerprint empty in spec (production paths require) |
| subtitle without fingerprint | no idempotency record |
| subtitle without provenance | missing subtitle_provenance entry after SUCCEEDED |
| checkpoint without valid subtitle | executor persist_validation + validate_subtitle_asset |
| render stale subtitle | subtitle_hash change invalidates render fingerprint |

All production paths now write meta + provenance on success.
