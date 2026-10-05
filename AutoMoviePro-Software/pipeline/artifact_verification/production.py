"""Production entry for industrial artifact verification (AMP-004 Phase-04).

Wired into generate_video before publishability. Not test-only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.artifact_verification.contracts import ArtifactObservation
from pipeline.artifact_verification.gate import (
    aggregate_artifact_gate,
    load_artifact_gate,
    persist_artifact_gate,
    persist_observation,
)
from pipeline.artifact_verification.verifiers import (
    verify_audio_artifact,
    verify_composite_artifact,
    verify_subtitle_artifact,
    verify_visual_artifact,
)

logger = logging.getLogger(__name__)


def _discover_scene_media(work_dir: Path, scenes: list[dict[str, Any]]) -> list[tuple[str, Path, dict]]:
    """Best-effort discovery of per-scene artifacts in work_dir."""
    found: list[tuple[str, Path, dict]] = []
    work_dir = Path(work_dir)
    for i, sc in enumerate(scenes or []):
        if not isinstance(sc, dict):
            continue
        meta = {
            "scene_id": str(sc.get("canonical_scene_id") or sc.get("scene_id") or i),
            "dialogue_id": str(sc.get("dialogue_id") or ""),
            "intent_fp": str(sc.get("scene_intent_fingerprint") or ""),
            "prompt_fp": "",
        }
        for key in ("video_path", "clip_path", "visual_path", "media_path"):
            p = sc.get(key)
            if p and Path(p).is_file():
                found.append(("visual", Path(p), meta))
                break
        for key in ("audio_path", "narration_path", "tts_path"):
            p = sc.get(key)
            if p and Path(p).is_file():
                found.append(("audio", Path(p), meta))
                break
    # Glob common patterns
    for p in sorted(work_dir.glob("scene_*.mp4"))[:32]:
        found.append(("visual", p, {"scene_id": p.stem, "dialogue_id": "", "intent_fp": "", "prompt_fp": ""}))
    for p in sorted(work_dir.glob("narration_*.m4a"))[:32]:
        found.append(("audio", p, {"scene_id": "", "dialogue_id": p.stem, "intent_fp": "", "prompt_fp": ""}))
    for p in sorted(work_dir.glob("narration_*.wav"))[:16]:
        found.append(("audio", p, {"scene_id": "", "dialogue_id": p.stem, "intent_fp": "", "prompt_fp": ""}))
    for p in sorted(work_dir.glob("*.srt"))[:16]:
        found.append(("subtitle", p, {"scene_id": "", "dialogue_id": "", "intent_fp": "", "prompt_fp": ""}))
    return found


def run_production_artifact_verification(
    work_dir: Path,
    *,
    final_path: Optional[Path] = None,
    scenes: Optional[list[dict[str, Any]]] = None,
    job_id: str = "",
    expected_duration_sec: Optional[float] = None,
    contradiction_issues: Optional[list] = None,
    discover_sources: bool = True,
) -> dict[str, Any]:
    """
    Observe actual artifacts → persist observations → ARTIFACT_GATE.json.

    Final composite is verified independently (Layer E).
    """
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    observations: list[ArtifactObservation] = []
    scenes = scenes or []

    if discover_sources:
        seen: set[str] = set()
        for kind, path, meta in _discover_scene_media(work_dir, scenes):
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            if kind == "visual":
                obs = verify_visual_artifact(
                    path,
                    artifact_id=f"visual:{path.name}",
                    job_id=job,
                    scene_id=meta.get("scene_id", ""),
                    dialogue_id=meta.get("dialogue_id", ""),
                    intent_fp=meta.get("intent_fp", ""),
                    contradiction_issues=contradiction_issues,
                )
            elif kind == "audio":
                obs = verify_audio_artifact(
                    path,
                    artifact_id=f"audio:{path.name}",
                    job_id=job,
                    scene_id=meta.get("scene_id", ""),
                    dialogue_id=meta.get("dialogue_id", ""),
                    intent_fp=meta.get("intent_fp", ""),
                )
            else:
                obs = verify_subtitle_artifact(
                    path,
                    artifact_id=f"subtitle:{path.name}",
                    job_id=job,
                    scene_id=meta.get("scene_id", ""),
                    dialogue_id=meta.get("dialogue_id", ""),
                )
            persist_observation(work_dir, obs)
            observations.append(obs)

    final_verified = False
    if final_path is not None:
        final_path = Path(final_path)
        comp = verify_composite_artifact(
            final_path,
            artifact_id=f"composite:{final_path.name}",
            job_id=job,
            expected_duration_sec=expected_duration_sec,
            contradiction_issues=contradiction_issues,
        )
        persist_observation(work_dir, comp)
        observations.append(comp)
        final_verified = True
    else:
        # Try common final names
        for name in ("final_product_review.mp4", "final_video.mp4", "final.mp4"):
            cand = work_dir / name
            if cand.is_file():
                comp = verify_composite_artifact(
                    cand,
                    artifact_id=f"composite:{cand.name}",
                    job_id=job,
                    expected_duration_sec=expected_duration_sec,
                )
                persist_observation(work_dir, comp)
                observations.append(comp)
                final_verified = True
                break
        if not final_verified:
            for cand in work_dir.glob("final_*.mp4"):
                comp = verify_composite_artifact(
                    cand,
                    artifact_id=f"composite:{cand.name}",
                    job_id=job,
                    expected_duration_sec=expected_duration_sec,
                )
                persist_observation(work_dir, comp)
                observations.append(comp)
                final_verified = True
                break

    gate = aggregate_artifact_gate(
        observations,
        job_id=job,
        final_verified=final_verified,
    )
    # Provenance chain note (reuse existing — do not invent second system)
    gate["provenance_chain"] = [
        "Research",
        "FactPack",
        "Script",
        "SceneIntent",
        "Plan",
        "Prompt",
        "Generation",
        "ProviderArtifact",
        "Observation",
        "Repair?",
        "Render",
        "FinalObservation",
        "Publication",
    ]
    gate["authority"] = "pipeline.artifact_verification"
    persist_artifact_gate(work_dir, gate)
    logger.info(
        "artifact verification job=%s status=%s observations=%s final=%s",
        job,
        gate.get("status"),
        len(observations),
        final_verified,
    )
    return gate


# re-export
__all__ = ["run_production_artifact_verification", "load_artifact_gate"]
