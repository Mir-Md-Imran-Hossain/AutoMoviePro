# AUTO MOVIE PRO — MATURE TOOL INTEGRATION T1-B REPORT

**Phase:** T1-B — Real CLIP + FAISS Independent Visual Retrieval Evidence  
**Date:** 2026-09-11  
**Prior:** T1-A PASS (`docs/MATURE_TOOL_INTEGRATION_T1A_REPORT.md`)  
**Verdict:** **BLOCKED**

---

## 1. Scope

Strengthen AMP retrieval with a real CLIP production embedding backend behind the existing interface; validate vs hash fallback; preserve FAISS / customer isolation / montage authority.

**Completed without new installs:** embedding contract, HEURISTIC_NON_SEMANTIC policy, FAISS namespaces, golden job2333 dataset, hash retrieval, failure paths, tests, this report.

**Blocked:** Real CLIP inference (torch / open-clip not installed). Per T1-B stop rule: **did not install dependencies**.

Out of scope: VMAF, MoneyPrinter, ShortGPT, OTIO, Piper, pyannote, agents, SAM2, ESRGAN, Demucs, Remotion, T1-C.

---

## 2. Existing Retrieval Architecture

```
SceneIntent / C05-S beat
  → pipeline/retrieval/query.build_retrieval_query
  → sources (local_licensed, Pexels; OpenMontage AGPL isolated)
  → embedding.resolve_embedding_backend (CLIP preferred)
  → FaissAssetIndex (Flat IP, L2-normalized cosine)
  → ranking.rank_candidates (multi-factor HEURISTIC marks)
  → bridge.attach_retrieval_evidence → montage_brain (candidate only)
```

| Module | Role |
|--------|------|
| `embedding.py` | ClipEmbeddingBackend + HashEmbeddingBackend |
| `faiss_index.py` | AMP-owned FAISS + metadata |
| `retrieve.py` | Orchestration |
| `bridge.py` | Evidence into materialization (no authority replace) |
| `montage_brain/production.py` | Soft retrieval-first; Agnes unchanged |
| `backend_gate.py` | Honest CLIP/FAISS readiness |

Hash embedder previously labeled `HEURISTIC`; CLIP optional and already stubbed for open_clip/transformers.

---

## 3. CLIP Backend Selected

**ONE production backend (when deps present):**

| Field | Value |
|-------|-------|
| Package | `open-clip-torch` |
| Architecture | `ViT-B-32` |
| Pretrained | `openai` |
| Model id | `open_clip:ViT-B-32:openai` |
| Device | `cpu` default (`AMP_CLIP_DEVICE` optional) |
| dtype | float32 |
| Normalization | L2 → cosine via FAISS IndexFlatIP |
| Embedding dim | 512 (from model) |
| Cache | `data/models/open-clip` / `AMP_CLIP_CACHE` |
| Lazy load | process-local `_CLIP_MODEL_CACHE` |
| GPU | optional only; **not mandatory** |

Secondary load path: `transformers` + `openai/clip-vit-base-patch32` only if open_clip import fails — same conceptual model family, **not** a second competing engine.

**Runtime probe (this machine):** `available=false` — `No module named 'torch'`.

---

## 4. Model / Dependency / License

### Present

| Package | Version | Notes |
|---------|---------|-------|
| faiss | 1.15.0 | Index path proven |
| Pillow | 11.3.0 | Image IO |
| numpy | (env) | Vectors |

### STOP — required before real CLIP (not installed)

| Package | Approx version | License | Size (approx) | CPU/GPU | Windows |
|---------|----------------|---------|---------------|---------|---------|
| `torch` | ≥2.1 CPU wheel | BSD-style | ~200–250 MB wheel | CPU OK | Yes |
| `torchvision` | matching torch | BSD-style | ~5–15 MB | CPU OK | Yes |
| `open-clip-torch` | ≥2.24 | MIT | small package | CPU OK | Yes |
| Weights `ViT-B-32/openai` | first run | OpenAI CLIP weights (research/use per upstream) | ~350 MB download | CPU | Yes |

**Optional alternative (not preferred):** `transformers` + same HF CLIP weights — larger stack; only fallback in code.

**Action required to unblock:** explicit approval to install the three packages above; then re-run `scripts/test_t1b_clip_faiss_retrieval.py`.

---

## 5. Embedding Contract

Evidence fields via `embedding_evidence()` / `embed_asset_record()`:

- backend, model, model_version  
- embedding_dim, normalized  
- source_hash, source_path, generated_at  
- device, dtype, kind  
- status (`PASS` only for successful CLIP vectorization — **not** publishability)  
- `claims_semantic_truth=false`, `semantic_pass=false`  
- index_namespace  

Schema base: `amp_retrieval_embedding_meta_v1`.

---

## 6. FAISS Integration

- Same `FaissAssetIndex` abstraction (no second engine).  
- **Namespaced roots:** `{base}/{kind}__{model}__d{dim}__{version}/`  
- Hash and CLIP **never share** an index (even at dim=512).  
- Preserved: metadata, customer_id isolation, content_hash dedupe, model/dim mismatch FAIL.  
- Controlled rebuild: `index_local_assets()` / `rebuild()` into namespace.  
- Metric: Inner Product on L2-normalized vectors (cosine).

---

## 7. Hash Fallback Policy

| Rule | Implementation |
|------|----------------|
| Label | `HEURISTIC_NON_SEMANTIC` |
| Prefer CLIP | default; hash only if `prefer=hash` or `allow_hash_fallback=True` |
| Fallback status | `UNKNOWN` + reason `CLIP_UNAVAILABLE_HASH_FALLBACK` |
| Not CLIP unavailable alone | `RETRIEVAL_UNAVAILABLE` / `EMBEDDING_BACKEND_UNAVAILABLE` |
| Never | hash → semantic PASS; CLIP fail → semantic PASS; UNKNOWN → PASS |

Retrieve path stores hash hits as `heuristic_score` (semantic_score cleared).

---

## 8. Golden Dataset

Built under `docs/marathon/evidence/t1b/golden_dataset/` from **job2333** (originals untouched):

- **12** JPEG frames from `final_short.mp4`, scene beats, Agnes i2v clips  
- **5** queries from `director_plan.json` C05-S scene prompts / visual purposes  

Manifest: `golden_dataset/manifest.json`.

---

## 9. Hash vs CLIP Comparison

Evidence: `docs/marathon/evidence/t1b/hash_vs_clip_comparison.json`  
Table: `docs/marathon/evidence/t1b/hash_vs_clip_table.md`

| Side | Result |
|------|--------|
| Hash | Ran — top-k + scores for all 5 queries |
| CLIP | **UNAVAILABLE** (torch missing) |

Cannot claim CLIP superiority — no CLIP rankings this run.

---

## 10. Retrieval Quality Results

| Query (abbrev) | Expected concept | Hash Top-1 | CLIP Top-1 | Relevant? |
|----------------|------------------|------------|------------|-----------|
| JWST Mid-Infrared… | JWST / exoplanet atmospheres | scene_01_beat_t010 | UNAVAILABLE | UNKNOWN |
| Visible / Mid-infrared… | IR vs visible / dust | scene_04_beat_t015 | UNAVAILABLE | UNKNOWN |
| Methane / penetrates… | spectral fingerprint | scene_02_beat_t020 | UNAVAILABLE | UNKNOWN |
| Star million× brighter… | starlight subtraction | agnes_00_beat_i2v_a1_t008 | UNAVAILABLE | UNKNOWN |
| Water vapor… | water vapor / clouds | final_short_t010 | UNAVAILABLE | UNKNOWN |

Hash rankings are **non-semantic** — do not interpret as visual relevance proof.

---

## 11. Real-Media Results

| Check | Status |
|-------|--------|
| Frame extraction from job2333 | PASS (12 assets) |
| Hash FAISS index + search | PASS |
| Customer isolation mismatch | PASS (FAIL on wrong customer) |
| CLIP image embed | BLOCKED / UNAVAILABLE |
| Provenance on hash path | PASS (content_hash, namespace, kind) |

---

## 12. Windows/CPU Performance

| Item | Value |
|------|-------|
| OS | Windows-11-10.0.26200 |
| Python | 3.12.9 |
| faiss | 1.15.0 |
| torch / open_clip | **MISSING** |
| Device intended | cpu / float32 |
| GPU used | no |
| CLIP model load | n/a |
| CLIP inference | n/a |
| Hash+FAISS golden wall | ~3s for full T1-B suite |

CPU CLIP feasibility: **not measured** (blocked). After install, re-baseline; if too slow for production, recommend optional GPU or defer activation — do not fake PASS.

---

## 13. Failure/UNKNOWN Results

| Case | Status |
|------|--------|
| CLIP package missing | `RETRIEVAL_UNAVAILABLE` / `EMBEDDING_BACKEND_UNAVAILABLE` |
| Hash explicit prefer/fallback | `UNKNOWN`, non-semantic |
| Dim mismatch | FAIL `dim_mismatch` |
| Model mismatch | FAIL `embedding_model_mismatch` |
| Customer isolation | FAIL `customer_isolation_mismatch` |
| Empty index | PASS hits=[] empty=true |
| Corrupt image (CLIP) | would raise `corrupt_or_unreadable_image` (untested live) |
| Corrupt file (hash) | still embeds bytes (non-semantic) |

---

## 14. Montage Integration

`montage_brain/production.py` continues to call `attach_retrieval_evidence` softly.  
CLIP/hash scores remain **candidate evidence**.  
Agnes routing **unchanged**.  
No FFmpeg / duration / publishability / SceneIntent ownership changes.

---

## 15. Authority Safety Verification

| Authority | Changed? |
|-----------|----------|
| SceneIntent | No |
| montage_brain slots | No |
| ContinuityTracker | No |
| BUILD-04F | No |
| Publishability | No |
| Duration | No |
| FFmpeg | No |
| Idempotency | No |
| Second retrieval DB/engine | No |
| CLIP as semantic truth | No (`claims_semantic_truth=false`) |

---

## 16. Regression Results

| Suite | Result |
|-------|--------|
| `scripts/test_t1b_clip_faiss_retrieval.py` | **13 OK** |
| `scripts/test_phase6b_retrieval.py` | **16 OK** |

---

## 17. Remaining Problems

1. **BLOCKER:** `torch` + `torchvision` + `open-clip-torch` not installed — real CLIP cannot run.  
2. Hash-vs-CLIP quality table incomplete until CLIP available.  
3. First CLIP weight download ~350MB + Windows HF symlink warnings expected (same class as Whisper).  
4. CPU latency for ViT-B-32 unknown on this host until install.

---

## 18. T1-B Verdict

**BLOCKED**

Acceptance checklist:

- [ ] Real CLIP backend runs → **NO** (torch missing)  
- [x] Exact model/version documented (selected; not executed)  
- [ ] CPU path works for CLIP → **not proven**  
- [x] Lazy/cache behavior implemented  
- [x] Real AMP visual assets prepared/embedded (hash)  
- [x] FAISS retrieval works (hash namespace)  
- [x] Provenance preserved  
- [x] Hash fallback clearly non-semantic  
- [ ] Hash and CLIP comparison completed → **partial** (CLIP UNAVAILABLE)  
- [x] Real queries evaluated (hash only)  
- [x] Customer isolation preserved  
- [x] Dimension/model mismatch handled  
- [x] CLIP unavailable → UNAVAILABLE/UNKNOWN  
- [x] No semantic PASS by CLIP alone  
- [x] Montage / FFmpeg / Publishability unchanged  
- [x] Retrieval regression passes  
- [x] T1-B report created  

**STOP.** Do not start T1-C. Do not install CLIP deps until explicitly approved.
