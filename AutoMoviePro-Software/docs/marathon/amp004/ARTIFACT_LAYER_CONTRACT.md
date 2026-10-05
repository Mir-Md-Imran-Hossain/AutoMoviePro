# Artifact Layer Contract A–E (Frozen)

---

## Layers

| ID | Name | Definition | Validated by (examples) |
|----|------|------------|-------------------------|
| **A** | INTENT | কী হওয়া উচিত | Scene, SceneIntent, dialogue_id, revision_id |
| **B** | PROMPT | Provider request text/params | prompt_compiler, prompt_validator |
| **C** | PROVIDER ARTIFACT | Returned file + provenance | path, fingerprint, SUCCESS/REUSED/FAILED, container |
| **D** | OBSERVED MEDIA | Generated media-তে observable content | visual_qa, future VLM/ASR — **not** prompt text alone |
| **E** | FINAL COMPOSITE | Muxed/encoded master content | MASTER_SHIP, future master semantic |

---

## Inequality (frozen)

```
PROMPT VALID
≠ ASSET VALID (C)
≠ SEMANTICALLY CORRECT (D vs A)
≠ CROSS-MODALLY CORRECT
≠ FINAL VIDEO CORRECT (E)
```

---

## Future verification interfaces (design — implement নয়)

প্রতিটি interface: `layer`, `confidence_label`, `status`, `issues[]`, `evidence`

| Interface | Media | Min layers |
|-----------|-------|------------|
| `ImageArtifactVerifier` | IMAGE | C + D |
| `VideoArtifactVerifier` | VIDEO | C + D |
| `AudioArtifactVerifier` | AUDIO | C + D |
| `SubtitleArtifactVerifier` | SUBTITLE | A + C + timing |
| `TextOverlayVerifier` | TEXT | A + E |
| `FinalRenderVerifier` | FINAL RENDER | E (+ D sample) |

External AI provider **আজ mandatory নয়** — adapter optional; absent → UNKNOWN per policy।

---

## Claim ban

Validator যে শুধু A/B/C চেক করে সে Layer-D বা Layer-E “verified” claim করতে পারবে না।  
Label করতে হবে: `HEURISTIC` / `STRUCTURAL_ONLY` / `OFFLINE_TEST_ONLY`।
