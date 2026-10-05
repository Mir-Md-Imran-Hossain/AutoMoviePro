"""Full pipeline contract trace (BUILD-02)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.common import new_id
from domain.fact_pack import FactPack
from domain.script import Script
from domain.topic import Topic
from pipeline.contract_wiring.core import StageWireResult
from pipeline.contract_wiring.stages import (
    wire_audio_plan,
    wire_comment,
    wire_fact_pack,
    wire_metadata,
    wire_publication,
    wire_render,
    wire_research,
    wire_scenes_from_plan,
    wire_script,
    wire_subtitle_plan,
    wire_thumbnail,
    wire_topic,
    wire_upload_job,
    wire_visual_plan,
)
from pipeline.niche_director import _fallback_history_plan


@dataclass
class PipelineTrace:
    job_id: str
    topic: Optional[StageWireResult[Topic]] = None
    research: Optional[StageWireResult] = None
    fact_pack: Optional[StageWireResult[FactPack]] = None
    script: Optional[StageWireResult[Script]] = None
    scenes: list[StageWireResult] = field(default_factory=list)
    visual_plans: list[StageWireResult] = field(default_factory=list)
    audio_plans: list[StageWireResult] = field(default_factory=list)
    subtitle_plans: list[StageWireResult] = field(default_factory=list)
    render: Optional[StageWireResult] = None
    metadata: Optional[StageWireResult] = None
    thumbnail: Optional[StageWireResult] = None
    upload: Optional[StageWireResult] = None
    publication: Optional[StageWireResult] = None
    engagement: Optional[StageWireResult] = None
    stopped_at: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    executed_stages: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.stopped_at:
            return False
        checks = [
            self.topic and self.topic.passed,
            self.research and self.research.passed,
            self.fact_pack and self.fact_pack.passed,
            self.script and self.script.passed,
            all(s.passed for s in self.scenes),
            all(s.passed for s in self.visual_plans),
            all(s.passed for s in self.audio_plans),
            all(s.passed for s in self.subtitle_plans),
        ]
        return all(checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "passed": self.passed,
            "stopped_at": self.stopped_at,
            "errors": self.errors,
            "executed_stages": self.executed_stages,
            "stages": {
                "topic": self.topic.passed if self.topic else None,
                "research": self.research.passed if self.research else None,
                "factpack": self.fact_pack.passed if self.fact_pack else None,
                "script": self.script.passed if self.script else None,
                "scenes": [s.passed for s in self.scenes],
                "visual": [s.passed for s in self.visual_plans],
                "audio": [s.passed for s in self.audio_plans],
                "subtitle": [s.passed for s in self.subtitle_plans],
                "render": self.render.passed if self.render else None,
                "metadata": self.metadata.passed if self.metadata else None,
                "thumbnail": self.thumbnail.passed if self.thumbnail else None,
                "upload": self.upload.passed if self.upload else None,
                "publication": self.publication.passed if self.publication else None,
                "engagement": self.engagement.passed if self.engagement else None,
            },
        }


def _stop(trace: PipelineTrace, stage: str, result: StageWireResult) -> PipelineTrace:
    trace.stopped_at = stage
    if result.error:
        trace.errors.append(f"{stage}: {result.error.code}")
    else:
        trace.errors.append(f"{stage}: validation failed")
    return trace


def wire_pipeline_from_plan(
    plan: dict[str, Any],
    *,
    job_id: Optional[str] = None,
    research_notes: str = "",
    render_legacy: Optional[dict[str, Any]] = None,
    upload_legacy: Optional[dict[str, Any]] = None,
    publication_legacy: Optional[dict[str, Any]] = None,
    include_engagement: bool = False,
) -> PipelineTrace:
    """Offline full-chain wiring — no external API calls."""
    jid = job_id or new_id()
    trace = PipelineTrace(job_id=jid)
    legacy = {**plan, "research_notes": research_notes or plan.get("research_notes") or ""}

    trace.topic = wire_topic(legacy, job_id=jid)
    trace.executed_stages.append("topic")
    if not trace.topic.passed:
        return _stop(trace, "topic", trace.topic)

    topic = trace.topic.canonical
    trace.research = wire_research(legacy, topic=topic, job_id=jid)
    trace.executed_stages.append("research")
    if not trace.research.passed:
        return _stop(trace, "research", trace.research)

    trace.fact_pack = wire_fact_pack(legacy, topic=topic, job_id=jid)
    trace.executed_stages.append("factpack")
    if not trace.fact_pack.passed:
        return _stop(trace, "factpack", trace.fact_pack)

    fp = trace.fact_pack.canonical
    trace.script = wire_script(plan, topic=topic, fact_pack=fp, job_id=jid)
    trace.executed_stages.append("script")
    if not trace.script.passed:
        return _stop(trace, "script", trace.script)

    script = trace.script.canonical
    trace.scenes = wire_scenes_from_plan(plan, script=script, job_id=jid)
    trace.executed_stages.append("scene")
    if not trace.scenes:
        from domain.validation import ValidationResult, ValidationIssue
        from domain.enums import Verdict, ErrorCategory
        from domain.errors import AppError
        from pipeline.contract_wiring.core import StageContext, StageWireResult

        fail = ValidationResult.fail(
            [ValidationIssue(object_type="Plan", rule="scenes", severity=Verdict.FAIL, message="no scenes")]
        )
        fake = StageWireResult.failed(
            stage="scene",
            context=StageContext(job_id=jid, stage="scene"),
            input_validation=fail,
            output_validation=fail,
            error=AppError(category=ErrorCategory.VALIDATION_ERROR, code="no_scenes", message="plan has no scenes"),
        )
        trace.scenes = [fake]
        return _stop(trace, "scene", fake)
    if not all(s.passed for s in trace.scenes):
        failed = next((s for s in trace.scenes if not s.passed), trace.scenes[0] if trace.scenes else None)
        if failed:
            return _stop(trace, "scene", failed)

    for sc_result in trace.scenes:
        scene = sc_result.canonical
        vp = wire_visual_plan(scene, job_id=jid)
        trace.visual_plans.append(vp)
        trace.executed_stages.append("visual")
        if not vp.passed:
            return _stop(trace, "visual", vp)
        ap = wire_audio_plan(scene, job_id=jid)
        trace.audio_plans.append(ap)
        trace.executed_stages.append("audio")
        if not ap.passed:
            return _stop(trace, "audio", ap)
        sp = wire_subtitle_plan(scene, job_id=jid)
        trace.subtitle_plans.append(sp)
        trace.executed_stages.append("subtitle")
        if not sp.passed:
            return _stop(trace, "subtitle", sp)

    render_data = render_legacy or {
        "path": "/tmp/fixture/output.mp4",
        "duration": 58.0,
        "job_id": jid,
        "has_audio": True,
    }
    trace.render = wire_render(render_data, job_id=jid)
    trace.executed_stages.append("render")
    if not trace.render.passed:
        return _stop(trace, "render", trace.render)

    meta_legacy = {
        "title": plan.get("title") or plan.get("topic") or "Untitled",
        "description": plan.get("description") or "",
        "tags": plan.get("tags") or [],
    }
    trace.metadata = wire_metadata(meta_legacy, job_id=jid)
    trace.executed_stages.append("metadata")
    if not trace.metadata.passed:
        return _stop(trace, "metadata", trace.metadata)

    thumb_legacy = {"path": "/tmp/fixture/thumb.jpg", "source": "fixture"}
    trace.thumbnail = wire_thumbnail(thumb_legacy, job_id=jid)
    trace.executed_stages.append("thumbnail")
    if not trace.thumbnail.passed:
        return _stop(trace, "thumbnail", trace.thumbnail)

    up_legacy = upload_legacy or {
        "title": meta_legacy["title"],
        "local_path": render_data["path"],
        "platform": "youtube",
        "dry_run": True,
        "render_job_id": trace.render.canonical.id if trace.render.canonical else jid,
    }
    trace.upload = wire_upload_job(up_legacy, job_id=jid)
    trace.executed_stages.append("upload")
    if not trace.upload.passed:
        return _stop(trace, "upload", trace.upload)

    pub_legacy = publication_legacy or {"ok": True, "url": "https://example.com/watch/fixture", "external_id": "fixture_vid"}
    trace.publication = wire_publication(pub_legacy, upload_job=trace.upload.canonical, job_id=jid)
    trace.executed_stages.append("publication")
    if not trace.publication.passed:
        return _stop(trace, "publication", trace.publication)

    if include_engagement:
        trace.engagement = wire_comment({"text": "Great video!", "platform": "youtube"}, job_id=jid)
        trace.executed_stages.append("engagement")

    return trace


def wire_sample_history_pipeline(*, job_id: Optional[str] = None) -> PipelineTrace:
    plan = _fallback_history_plan(
        "Ancient Civilizations",
        "Lost Library of Alexandria",
        "short",
        58,
        "TestChannel",
    )
    return wire_pipeline_from_plan(
        plan,
        job_id=job_id,
        research_notes="The library was a major center of learning in antiquity.",
    )
