# PUBLISHABILITY_GATE

Final verdict requires:
1. Technical validation PASS (`MASTER_SHIP_GATE.json`)
2. Creative quality PASS (`CREATIVE_QUALITY_GATE.json`)
3. Subtitle structural validation (BUILD-04E reuse)
4. Provenance present

States: `PUBLISHABLE`, `NOT_PUBLISHABLE`, `REPAIR_REQUIRED`, `BLOCKED`, `UNKNOWN`

`video_pipeline.py` blocks `ready_to_upload` when not publishable.
