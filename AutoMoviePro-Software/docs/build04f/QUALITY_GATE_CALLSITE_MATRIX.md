# QUALITY_GATE_CALLSITE_MATRIX

| Callsite | Stage | Creative Eval | Technical Reuse | Repair Scope | Publish Block | Status |
|----------|-------|-----------------|-----------------|--------------|---------------|--------|
| scene_builder accept | scene | partial (critic+gates) | av_quality_gates | scene/visual | indirect | COVERED (legacy) |
| video_pipeline ship gate | final | NEW orchestrator | MASTER_SHIP_GATE | render | Y | COVERED |
| video_pipeline publishability | final | quality_report | ship + creative | scoped | Y | COVERED |
| ready_to_upload transition | upload | PUBLISHABILITY_GATE | all | N | Y | COVERED |
| upload_service | upload | indirect (job status) | file exists | N | partial | COVERED |
| plan_quality post-process | script | fact + speech | FactPack | dialogue | N | COVERED (upstream) |

Direct upload without quality gate: **0** production paths (blocked at publishability).
