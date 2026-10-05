"""Consolidated lineage audit artifact (PART-5Q)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


LINEAGE_NAME = "LINEAGE_AUDIT.json"


def build_lineage_audit(work_dir: Path, *, job_id: str = "") -> dict[str, Any]:
    work_dir = Path(work_dir)
    job = job_id or work_dir.name
    nodes: list[dict[str, Any]] = []

    def _add(
        stage: str,
        *,
        file: str = "",
        function: str = "",
        artifact_id: str = "",
        status: str = "",
        provider: str = "",
        model: str = "",
        fallback: str = "",
        retry: Any = "",
        evidence: str = "",
    ) -> None:
        nodes.append(
            {
                "stage": stage,
                "file": file,
                "function": function,
                "artifact_id": artifact_id or f"{job}:{stage}",
                "status": status,
                "provider": provider,
                "model": model,
                "fallback": fallback,
                "retry": retry,
                "evidence": evidence,
            }
        )

    # Persist TRS chain snapshots if present
    for name, stage, fn in (
        ("TOPIC.json", "topic", "customer_trs_workflow.set_manual_topic"),
        ("RESEARCH.json", "research", "customer_trs_workflow.run_research"),
        ("FACTPACK.json", "factpack", "pipeline.intelligence.factpack_gate"),
        ("SCRIPT.json", "script", "pipeline.trs_facade.run_trs_pipeline"),
        ("03_SCRIPT.json", "script", "pipeline.trs_facade"),
    ):
        p = work_dir / name
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            _add(
                stage,
                file=str(p.name),
                function=fn,
                status=str(data.get("status") or data.get("topic_status") or "PRESENT"),
                evidence=str(p),
            )

    gate_files = [
        ("DURATION_RECONCILIATION.json", "duration", "pipeline.duration_budget"),
        ("SEMANTIC_COVERAGE_GATE.json", "semantic", "pipeline.semantic_coverage"),
        ("AUDIO_ASR_EVIDENCE_GATE.json", "audio_asr", "pipeline.observation.audio_evidence.production"),
        ("AUDIO_DESIGN_GATE.json", "audio_design", "pipeline.audio_design"),
        ("LOCALIZATION_GATE.json", "localization", "pipeline.localization_consistency.production"),
        ("RENDERING_INTEGRITY_GATE.json", "render", "pipeline.rendering_integrity"),
        ("PUBLISHABILITY_GATE.json", "publishability", "pipeline.quality.publishability"),
        ("AUDIENCE_QUALITY_GATE.json", "audience", "pipeline.quality.audience_quality"),
        ("SCENE_BOUNDARY_OBSERVATION_GATE.json", "scene_boundary", "pipeline.observation.scene_boundary"),
        ("CREATIVE_QUALITY_GATE.json", "creative", "pipeline.quality.bridge"),
    ]
    for fname, stage, fn in gate_files:
        p = work_dir / fname
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        _add(
            stage,
            file=fname,
            function=fn,
            status=str(data.get("status") or data.get("verdict") or data.get("overall_verdict") or "PRESENT"),
            provider=str(data.get("provider") or data.get("asr_provider") or ""),
            model=str(data.get("model") or ""),
            fallback=str(data.get("fallback") or data.get("fallback_used") or ""),
            retry=data.get("retry_count") or data.get("repair_loop") or "",
            evidence=str(p),
        )

    # Final media
    for media in ("final_short.mp4", "body_av.mp4", "english_master.srt"):
        p = work_dir / media
        if p.is_file():
            _add(
                "final_artifact",
                file=media,
                function="pipeline.compose / package_export",
                status="PRESENT",
                evidence=str(p),
            )

    edges = []
    order = [
        "topic",
        "research",
        "factpack",
        "script",
        "duration",
        "semantic",
        "audio_design",
        "audio_asr",
        "scene_boundary",
        "localization",
        "render",
        "creative",
        "audience",
        "publishability",
        "final_artifact",
    ]
    present = {n["stage"] for n in nodes}
    prev = None
    for st in order:
        if st not in present:
            continue
        if prev:
            edges.append({"from": prev, "to": st})
        prev = st

    return {
        "schema": "amp_lineage_audit_v1",
        "job_id": job,
        "nodes": nodes,
        "edges": edges,
        "authority": "pipeline.quality.lineage_audit",
        "complete": bool(nodes),
    }


def persist_lineage_audit(work_dir: Path, *, job_id: str = "") -> dict[str, Any]:
    audit = build_lineage_audit(work_dir, job_id=job_id)
    path = Path(work_dir) / LINEAGE_NAME
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
