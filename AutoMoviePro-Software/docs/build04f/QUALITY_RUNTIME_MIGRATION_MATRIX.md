# QUALITY_RUNTIME_MIGRATION_MATRIX

| Artifact | Stage | Evaluator | Verdict | Repair | Cache | Invalidation | Publish | Tests | Status |
|----------|-------|-----------|---------|--------|-------|--------------|---------|-------|--------|
| Script | script | evaluate_script_quality | Y | SCRIPT_SECTION | Y | Y | Y | F05-F09 | PASSED |
| Visual | visual | evaluate_scene_visual_alignment | Y | VISUAL_ASSET | Y | Y | Y | F10-F15 | PASSED |
| Audio | audio | evaluate_audio_quality | Y | AUDIO_ASSET | Y | Y | Y | F16-F18 | PASSED |
| Subtitle | subtitle | evaluate_subtitle_creative | Y | SUBTITLE | Y | Y | Y | F20 | PASSED |
| Cross-modal | cross_modal | evaluate_cross_modal | Y | scoped | Y | Y | Y | F21 | PASSED |
| Final | final | orchestrator aggregate | Y | scoped | Y | Y | Y | F39-F41 | PASSED |
| Repair | repair | repair_runtime | Y | idempotent | Y | N | N | F26-F28 | PASSED |
