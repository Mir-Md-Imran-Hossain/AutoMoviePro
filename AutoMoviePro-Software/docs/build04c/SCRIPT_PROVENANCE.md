# Script Provenance — BUILD-04C

Stored at `{work_dir}/script_provenance/{fingerprint[:24]}.json`

## Fields

- job_id, fingerprint, entity_id
- topic, topic_identity, niche, niche_id
- fact_pack_id, fact_pack_hash
- prompt_version, prompt_template_hash
- provider, model, generation_id
- plan_path, plan_hash
- saved_at timestamp

## Never stored

- API keys, tokens, passwords, cookies
- Full research notes (hash only in spec)

## Load

`load_script_provenance(work_dir, fingerprint)`
