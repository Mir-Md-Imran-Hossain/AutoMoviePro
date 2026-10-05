# Validation Layer Architecture

**AMP-004** · design doctrine

---

## Layers

| Layer | Authority | TYPE bias |
|-------|-----------|-----------|
| TECHNICAL_VALIDATION | visual/audio/render validation, ffprobe | TYPE-1 |
| IDENTITY_VALIDATION | dialogue_id, scene_id, fingerprint | TYPE-1 |
| PROMPT_VALIDATION | prompt_validator | TYPE-1/2 |
| SEMANTIC_VALIDATION | visual_semantic + entity_grounding | TYPE-2 (now) / 3–4 (future) |
| CROSS_MODAL_VALIDATION | multimodal cross_modal + 04F | TYPE-2–4 |
| CONTINUITY_VALIDATION | ContinuityTracker | TYPE-2–4 |
| LOCALIZATION_VALIDATION | localization_semantic + 04E | TYPE-2–4 |
| CREATIVE_VALIDATION | BUILD-04F | TYPE-2/5 |
| ARTIFACT_VALIDATION | visual_qa + future VLM/ASR | TYPE-1 + 3–4 |
| PUBLISHABILITY | publishability.py AND | TYPE-1 policy |

---

## Aggregation

`aggregate_final_status`: যেকোনো BLOCKED → overall BLOCKED।  
UNKNOWN never coerces to PASS।

---

## Deterministic vs AI (TYPE map)

| TYPE | Definition | UNKNOWN behavior |
|------|------------|------------------|
| 1 | Code/media metadata | Fail if check fails |
| 2 | Strong heuristic | Advisory unless strict; critical identity still blocks |
| 3 | CV/audio analysis | UNKNOWN if analyzer absent |
| 4 | VLM/ASR/ML | UNKNOWN unless PROVIDER_VERIFIED |
| 5 | Human | Escalation only |

---

## Duplicate validators — disposition

| Item | Disposition |
|------|-------------|
| 04F evaluators vs multimodal | MERGE signals into 04F issues; keep multimodal industrial report |
| av_quality_gates vs 04F | KEEP separate (technical vs creative) |
| visual_qa vs visual_validation | KEEP (content vs container) |
| plan_quality vs 04F script | DOCUMENT → prefer 04F |
