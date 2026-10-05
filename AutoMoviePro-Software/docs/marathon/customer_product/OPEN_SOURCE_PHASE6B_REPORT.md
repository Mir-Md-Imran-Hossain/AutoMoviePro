# Open-Source Integration — Phase 6B Report

**Date:** 2026-09-09  
**Scope:** CLIP + FAISS + real-footage retrieval (AMP-owned adapters)  
**OpenMontage AGPL code imported/copied:** **No** (verified: no `third_party.OpenMontage` imports under `pipeline/retrieval/`)  
**REAL Marathon:** **Not run**  
**Verdict:** **PASS_WITH_LIMITATION**

---

## CLIP selection

| Option | Status on this Windows machine | Decision |
|--------|--------------------------------|----------|
| open_clip / transformers CLIP | **Not installed** (no torch) | Primary backend when present; lazy load |
| Forced torch install | Rejected as startup/GPU-heavy mandate | Optional only |
| `amp_hash_embed_v1` | Deterministic CPU | **Test / explicit fallback only** (`allow_hash_embedder=True`); marked **HEURISTIC**, not claimed as CLIP |

**Production default:** `ClipEmbeddingBackend` → if unavailable → `RETRIEVAL_UNAVAILABLE` (startup does not import CLIP).  
**Model target when available:** `openai/clip-vit-base-patch32` (transformers) or `open_clip:ViT-B-32:openai`.  
**Device:** CPU default; GPU not mandatory.

---

## FAISS selection

| Item | Detail |
|------|--------|
| Package | `faiss-cpu` **1.15.0** (installed for Phase 6B) |
| Index type | `IndexFlatIP` on L2-normalized vectors (cosine) |
| Metadata | `metadata.json` 1:1 with vector ids; `content_hash` dedupe |
| Corruption | Load fails with explicit `FAIL` / `RETRIEVAL_UNAVAILABLE` — no silent success |
| Rebuild | `FaissAssetIndex.rebuild` / `index_local_assets` |
| Isolation | `customer_id` / `channel_id` stored; mismatch → FAIL |
| BUILD-03 | Separate index path; no conflict with `IdempotencyStore` fingerprints |

Optional pin noted (commented) in `requirements.txt` — not a hard startup dependency.

---

## Dependency / CPU–GPU

| Dep | Required at startup? | Behavior if missing |
|-----|----------------------|---------------------|
| faiss-cpu | No | `RETRIEVAL_UNAVAILABLE` |
| torch / open_clip / transformers | No | CLIP probe fails → unavailable |
| Pillow | Already required | Local image embed / fixtures |
| PEXELS_API_KEY | No | Pexels source deactivated with explicit reason |

---

## Retrieval architecture

```
DirectedVisualBeat / Visual Contract fields
  → pipeline.retrieval.query.build_retrieval_query
  → sources (local_licensed, pexels)
  → optional CLIP embed + FAISS search
  → ranking (explainable multi-score)
  → evidence via story_visual_direction.attach_visual_retrieval_evidence
  → optional hint on C05-MR units via materialize_visual_beats(retrieval_by_beat=…)
  → existing SceneIntent / ContinuityTracker / semantic_coverage / generation
```

External retrieval **never**: publishes, approves, repairs, grants publishability PASS, replaces ContinuityTracker, or acts as semantic final authority.

---

## Real-footage sources

| Source | Activated | Terms |
|--------|-----------|-------|
| `local_licensed` | Yes | Customer-owned/licensed folder |
| `pexels` | Yes (key required) | AMP-owned adapter over existing `fetch_pexels_videos` + image search |
| OpenMontage stock adapters | **No** | AGPL isolation |
| archive.org / unsplash / etc. | **No** | Terms not verified in AMP |

Provenance fields: `source`, `source_url`, `license_usage`, `retrieved_at`, `content_hash`. API keys stripped from metadata.

---

## Ranking logic

Explainable scores (non-model factors marked **HEURISTIC**):

- `candidate_score` (weighted blend)
- `semantic_score` (CLIP/index when available, else token HEURISTIC)
- `entity_score`, `relationship_score`, `location_score`
- `technical_score`, `media_score`, `source_score`, `continuity_score`

Media preference: IMAGE / IMAGE_WITH_MOTION → image (+ existing motion path note); VIDEO → video.  
Real footage is **not** accepted solely for being “real” — semantic coverage / existing gates remain.

---

## Duplicate handling

`pipeline.retrieval.reuse.detect_reuse_risk`:

- Same beat identical asset → evidence + `automatic_failure` hint  
- Cross-scene continuity reuse → **not** automatic failure when allowed  
- BUILD-03 authority unchanged  

---

## Windows behavior

Tested: paths with spaces, Unicode (`日本語`), nested/long index dirs, index persist + reload, corrupted index FAIL, missing CLIP → UNAVAILABLE. GPU not required.

---

## Existing authority preserved

| Authority | Preserved? |
|-----------|------------|
| C05-S DirectedVisualBeat | Yes (query input only) |
| SceneIntent | Yes |
| Visual Contract / prompt compiler | Yes |
| ContinuityTracker | Yes |
| C05-MR materialization | Yes (optional retrieval hints) |
| BUILD-03 idempotency | Yes |
| semantic_coverage / publishability | Yes |
| Duplicate engines created? | **No** |

Wiring:

- `pipeline/story_visual_direction.py` → `attach_visual_retrieval_evidence` + architecture flags  
- `pipeline/generation_payload.py` → optional `retrieval_by_beat` on `materialize_visual_beats`

---

## Tests

`python -m scripts.test_phase6b_retrieval` → **16/16 OK**

Covers: CLIP missing, hash embed, FAISS index/search/dedupe/corrupt/isolation, Windows paths, entity/relationship/location query, ranking, fallback, secrets strip, reuse, C05/BUILD-03 bridge, AGPL import guard, unverified sources.

Fixtures/MOCK/hash embedder are **not** production CLIP certification.

---

## Regressions

| Suite | Result |
|-------|--------|
| Phase 6A observation | OK (15) |
| Phase 6B retrieval | OK (16) |
| RCP-06A | OK (10) |
| RCP-06B | OK (15) |
| RCP-06C | OK (10) |
| RCP-06D | OK (12) |
| RCP-07 blocker fix | OK (9) |
| BUILD-03 | OK (14) |
| C05-S | OK (79) |
| C05-MR | OK (140) |

---

## Limitations

1. **CLIP weights not installed** on this production Windows env — live semantic embed requires optional torch/open_clip or transformers install; until then production CLIP path reports `RETRIEVAL_UNAVAILABLE` unless `allow_hash_embedder` is explicitly enabled (tests only).  
2. Video assets use text/caption embedding until a frame sampler is added.  
3. Pexels candidates may be URL-only until download; provenance retained.  
4. Unverified third-party stock sources intentionally inactive.  
5. No REAL Marathon / customer SHORT cert in this phase.  
6. Hash embedder must never be reported as CLIP PASS.

---

## OpenMontage AGPL proof

- New code lives only under `pipeline/retrieval/` (AMP-owned).  
- Tests assert source files do not import OpenMontage.  
- Architecture snapshot: `openmontage_agpl_imported: false`.  
- Documentary retrieval ideas used as **reference only** (query richness, multi-source, CLIP+index) — no AGPL code copy.

---

## Verdict

**PASS_WITH_LIMITATION**

Integration + regression proof complete. Limitation is environmental: CLIP runtime optional/unavailable without torch; FAISS + full adapter contracts proven with CPU hash embedder for index mechanics and with explicit CLIP-unavailable path for production honesty.
