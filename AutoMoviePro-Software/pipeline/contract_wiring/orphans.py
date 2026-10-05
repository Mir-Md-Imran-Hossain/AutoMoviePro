"""Orphan detection for wired pipeline contracts (BUILD-02)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.contract_wiring.trace import PipelineTrace


@dataclass
class OrphanReport:
    orphans: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    documented_exceptions: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.orphans) == 0


def detect_orphans(trace: PipelineTrace) -> OrphanReport:
    report = OrphanReport()
    if not trace.topic or not trace.topic.canonical:
        report.orphans.append("orphan: missing Topic root")
        return report

    topic_id = trace.topic.canonical.id

    if trace.research and trace.research.canonical:
        for ev in trace.research.canonical.evidence:
            if ev.topic_id != topic_id:
                report.orphans.append(f"orphan ResearchEvidence topic_id mismatch: {ev.id}")

    if trace.fact_pack and trace.fact_pack.canonical:
        fp = trace.fact_pack.canonical
        if fp.topic_id and fp.topic_id != topic_id:
            report.orphans.append("orphan FactPack topic_id mismatch")
        if not fp.claims:
            report.warnings.append("FactPack has zero claims")

    if trace.script and trace.script.canonical:
        script = trace.script.canonical
        if script.topic_id and script.topic_id != topic_id:
            report.orphans.append("orphan Script topic_id mismatch")
        dlg_ids = set()
        for sec in script.sections:
            for d in sec.dialogues:
                if d.script_id != script.id:
                    report.orphans.append(f"orphan Dialogue script_id mismatch: {d.id}")
                dlg_ids.add(d.id)
        for i, sc in enumerate(trace.scenes):
            if sc.canonical and sc.canonical.script_id != script.id:
                report.orphans.append(f"orphan Scene script_id mismatch at index {i}")

    if trace.upload and trace.publication:
        if trace.publication.canonical and trace.upload.canonical:
            if trace.publication.canonical.upload_job_id != trace.upload.canonical.id:
                report.orphans.append("orphan Publication upload_job_id mismatch")

    if trace.render and trace.render.canonical and trace.render.canonical.manifest:
        if not trace.render.canonical.manifest.artifacts:
            report.warnings.append("RenderJob manifest has no artifacts")

    # Engagement optional — documented exception
    if trace.engagement is None:
        report.documented_exceptions.append("Engagement not required for core video pipeline")

    return report
