# Script Request Identity — BUILD-04C

## ScriptRequestSpec fields

| Field | In fingerprint | Notes |
|-------|----------------|-------|
| topic | Yes | Forced or auto-select seed |
| topic_identity | Yes (entity_id) | hash(niche_id + niche + topic) |
| niche, niche_id | Yes | Stable niche scope |
| video_type, max_seconds | Yes | Duration budget |
| language | Yes | Master language (en) |
| research_notes_hash | Yes | Not raw notes (privacy + stability) |
| fact_pack_id, fact_pack_hash | Yes | From FACT_PACK.json if present |
| prompt_version | Yes | prompt_registry director_system |
| prompt_template_hash | Yes | hash(DIRECTOR_SYSTEM + ELEMENT_GUIDE) |
| blocked_products | Yes | Sorted list |
| channel_specials | Yes | Sorted key-value |
| revision_id | Yes | Intentional revision only |
| provider, model | Yes | Default llm_router / purpose-script |
| timestamp | **No** | |
| attempt number | **No** | |
| execution UUID | **No** | |

## Entity ID

`script-{niche_id:04d}-{topic_identity[:16]}[-{revision_id}]`

## Helpers

- `build_script_spec()` — constructs spec from runtime kwargs
- `load_fact_pack_identity(work_dir)` — reads FactPack from work dir
- `director_prompt_identity()` — version + template hash
