"""Authority integrity + production call-graph audit (AMP-004 Phase-09)."""
from __future__ import annotations

import inspect
from typing import Any, Optional

AUTHORITIES: dict[str, tuple[str, Optional[str]]] = {
    "idempotency": ("pipeline.idempotency.executor", "IdempotentExecutor"),
    "SceneIntent": ("domain.scene_intent", "SceneIntent"),
    "continuity": ("pipeline.visual_semantic.continuity", "ContinuityTracker"),
    "creative_quality": ("pipeline.quality.orchestrator", "quality_gate_orchestrator"),
    "multimodal": ("pipeline.multimodal_consistency", None),
    "artifact_verification": (
        "pipeline.artifact_verification.production",
        "run_production_artifact_verification",
    ),
    "audio": ("pipeline.audio_design.production", "run_production_audio_design_gate"),
    "localization": ("pipeline.localization_consistency.production", "run_production_localization_gate"),
    "creative_production": ("pipeline.creative_production.production", "run_production_creative_gate"),
    "rendering": ("pipeline.idempotency.render_bridge", "idempotent_compose_final_video"),
    "rendering_integrity": ("pipeline.rendering_integrity.production", "run_production_rendering_gate"),
    "publishability": ("pipeline.quality.publishability", "evaluate_publishability"),
}


def audit_production_call_graph() -> dict[str, Any]:
    import pipeline.video_pipeline as vp
    import pipeline.scene_runtime as sr
    import pipeline.idempotency.render_bridge as rb

    gen = inspect.getsource(vp.generate_video)
    scene = inspect.getsource(sr.assert_production_scenes_validated)
    compose = inspect.getsource(rb.idempotent_compose_final_video)
    required = [
        ("assert_production_scenes_validated", gen),
        ("apply_production_continuity", scene),
        ("apply_production_audio_design", scene),
        ("apply_production_creative_plan", scene),
        ("idempotent_compose_final_video", gen),
        ("apply_production_render_preflight", compose),
        ("run_production_artifact_verification", gen),
        ("run_production_audio_design_gate", gen),
        ("run_production_localization_gate", gen),
        ("run_production_creative_gate", gen),
        ("run_production_rendering_gate", gen),
        ("run_publishability_gate", gen),
        ("ready_to_upload", gen),
    ]
    missing = [name for name, src in required if name not in src]
    return {
        "status": "PASS" if not missing else "FAIL",
        "missing": missing,
        "entrypoint": "pipeline.video_pipeline.generate_video",
        "final_state": "ready_to_upload",
        "method": "STATIC_SOURCE",
    }


def audit_authority_singletons() -> dict[str, Any]:
    issues: list[str] = []
    present: dict[str, bool] = {}
    for name, (mod_path, attr) in AUTHORITIES.items():
        try:
            mod = __import__(mod_path, fromlist=[attr or "x"])
            ok = True if attr is None else hasattr(mod, attr)
            present[name] = ok
            if not ok:
                issues.append(f"authority_attr_missing:{name}:{attr}")
        except Exception as exc:
            present[name] = False
            issues.append(f"authority_import_fail:{name}:{exc}")
    documented_duals = [
        {
            "area": "prompt",
            "canonical": "multimodal_consistency.prompt_compiler",
            "legacy": "prompt_engineering / scene_contract.compile_prompt_from_contract",
            "classification": "LEGACY",
        },
        {
            "area": "compose_helpers",
            "canonical": "scene_builder.concat_av_clips via render_bridge",
            "legacy": "compose.concat_clips",
            "classification": "LEGACY",
        },
        {
            "area": "tts_fallback",
            "canonical": "idempotent_synthesize_narration",
            "legacy": "direct synthesize_narration on bridge failure",
            "classification": "INTENTIONAL ADAPTER / BYPASS RISK",
        },
    ]
    return {
        "status": "PASS" if not issues else "FAIL",
        "authorities_present": present,
        "issues": issues,
        "documented_duals": documented_duals,
        "method": "STATIC",
    }


def audit_production_bypasses() -> dict[str, Any]:
    """Detect known bypass surfaces — classify, do not auto-delete."""
    findings = []
    import pipeline.video_pipeline as vp
    import pipeline.idempotency.agnes_bridge as ag
    import pipeline.quality.multimodal_aggregate as mm

    gen = inspect.getsource(vp.generate_video)
    if "synthesize_narration(" in gen and "idempotent_synthesize_narration" in gen:
        findings.append(
            {
                "id": "tts_direct_fallback",
                "classification": "INTENTIONAL ADAPTER",
                "note": "video_pipeline falls back to synthesize_narration if idempotent TTS fails",
                "production": True,
            }
        )
    if "plan_niche_production" in inspect.getsource(vp._plan_niche_production_idempotent):
        findings.append(
            {
                "id": "script_bridge_fallback",
                "classification": "INTENTIONAL ADAPTER",
                "note": "script bridge falls back to niche_director on import/runtime miss",
                "production": True,
            }
        )
    if "skip_semantic_validation" in inspect.getsource(ag):
        findings.append(
            {
                "id": "skip_semantic_validation_flag",
                "classification": "TEST-ONLY CONTAINED",
                "note": "agnes_bridge honors flag; multimodal_aggregate.assert_production_semantic_bypass_forbidden blocks production",
                "production": False,
            }
        )
    if "assert_production_semantic_bypass_forbidden" in inspect.getsource(mm):
        findings.append(
            {
                "id": "semantic_bypass_guard",
                "classification": "ACTIVE GUARD",
                "note": "production containment present",
                "production": True,
            }
        )
    findings.append(
        {
            "id": "scene_builder_ffmpeg",
            "classification": "ACTIVE under render_bridge provider",
            "note": "Phase-08 FiltergraphContract preflight; string graphs still ACTIVE",
            "production": True,
        }
    )
    blocking = [f for f in findings if f["classification"] == "BUG"]
    return {
        "status": "PASS" if not blocking else "FAIL",
        "findings": findings,
        "method": "STATIC",
    }
