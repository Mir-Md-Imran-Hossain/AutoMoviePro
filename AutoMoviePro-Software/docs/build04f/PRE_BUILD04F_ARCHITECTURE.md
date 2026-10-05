# PRE_BUILD04F_ARCHITECTURE

## Baseline
BUILD-00R through BUILD-04E PASS. All generation stages use BUILD-03 idempotency.

## Existing Quality Infrastructure (preserved)
| Component | Path | Role |
|-----------|------|------|
| AV quality gates | `pipeline/av_quality_gates.py` | Deterministic technical gates |
| AV sync critic | `pipeline/av_sync_critic.py` | LLM multimodal critique |
| Self-repair agent | `pipeline/av_self_repair_agent.py` | Targeted AV repair |
| Robot detector | `pipeline/robot_detector.py` | Naturalness heuristics |
| Plan quality | `pipeline/plan_quality.py` | FactPack + speech audit |
| Master ship gate | `evaluate_master_shippable` | Pre-upload technical block |
| Domain validation | `domain/validation.py` | ValidationResult contract |

## BUILD-04F Extension
```
Generate → Technical Validation (reuse BUILD-04A–04E)
         → Creative Quality Evaluate
         → Verdict (PASS / REPAIR / REGENERATE / BLOCKED / UNKNOWN)
         → Repair Planner (smallest scope)
         → Existing bridges (no engine rewrite)
         → Publishability Gate
```

## New Package: `pipeline/quality/`
- `contracts.py` — CreativeQualityResult, QualityIssue, QualityVerdict
- `evaluators.py` — script, visual, audio, subtitle, cross-modal
- `orchestrator.py` — quality_gate_orchestrator
- `repair_planner.py` — targeted repair scope
- `repair_runtime.py` — idempotent repair execution
- `runtime.py` — cached quality evaluation
- `publishability.py` — final PUBLISHABLE verdict
- `bridge.py` — production integration

## Integration Point
`video_pipeline.py` — after MASTER_SHIP_GATE, before `ready_to_upload`:
- `CREATIVE_QUALITY_GATE.json`
- `quality_report.json`
- `PUBLISHABILITY_GATE.json`
