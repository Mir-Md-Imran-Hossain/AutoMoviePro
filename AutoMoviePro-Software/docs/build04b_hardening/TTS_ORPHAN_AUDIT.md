# TTS Orphan Audit — BUILD-04B-H

Audit date: BUILD-04B-H completion.

## Checks performed

| Orphan type | Result |
|-------------|--------|
| Audio without dialogue text in spec | None in covered paths |
| Audio without scene_id | Master localization uses scene_id=0 (intentional master scope) |
| Audio without fingerprint | None when bridge used |
| Audio without provenance | None on successful execute/reuse via `execute_audio_request` |
| Generation without asset file | Rejected at validation — not checkpointed |
| Checkpoint without asset | IdempotentExecutor requires persist_fn output |

## Provenance storage

`{work_dir}/audio_provenance/{fingerprint[:24]}.json`

Linked fields: job_id, scene_id, dialogue_id, language, provider, model, asset_path, asset_hash.

## Residual risks

- Legacy `tts_reuse` without `work_dir`: sidecar reuse only, no provenance file.
- `av_self_repair_agent`: TTS files may exist without canonical provenance (BLOCKED path).
- Dev scripts: out of orchestrator scope.

## Verdict

Canonical production paths produce paired asset + provenance + checkpoint. No unexplained orphans in covered runtime paths.
