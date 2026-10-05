"""BUILD-02 per-stage contract wiring (STAGE-01 through STAGE-15)."""
from __future__ import annotations

from typing import Any, Optional

from domain.adapters import (
    fact_pack_from_legacy,
    scene_from_legacy_contract,
    script_from_plan,
    topic_from_plan,
)
from domain.common import ExternalRef, new_id
from domain.engagement import Comment, EngagementAction, Message
from domain.enums import EvidenceStatus, LifecycleStatus, ResearchStatus, Verdict
from domain.fact_pack import FactPack
from domain.localization import Localization, LocalizedDialogue, VoiceProfile
from domain.media import ImageAsset, Provenance, ThumbnailAsset
from domain.publication import Publication, PublicationTarget, UploadJob, VideoMetadata
from domain.render import RenderArtifact, RenderJob, RenderManifest
from domain.research import ResearchEvidence, TopicResearch
from domain.scene import AudioPlan, Scene, SubtitleCue, SubtitlePlan, VisualPlan
from domain.script import Dialogue, Script
from domain.topic import Topic
from pipeline.contract_wiring.core import (
    StageWireResult,
    run_stage,
    validate_instance,
    validate_required_dict,
)
from pipeline.fact_pack import build_fact_pack
from pipeline.scene_contract import attach_contracts_to_plan
from pipeline.subtitle_align import proportional_cues


# ---------------------------------------------------------------------------
# STAGE-01 Topic
# ---------------------------------------------------------------------------

def wire_topic(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[Topic]:
    inp = validate_required_dict(legacy, stage="topic", required_keys=("topic",))
    if not inp.passed and legacy.get("title"):
        inp = validate_required_dict({"topic": legacy.get("title")}, stage="topic", required_keys=("topic",))
        legacy = {**legacy, "topic": legacy.get("title")}
    return run_stage(
        stage="topic",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=lambda: topic_from_plan(legacy),
        entity_id=str(legacy.get("topic") or legacy.get("title") or "")[:80],
    )


# ---------------------------------------------------------------------------
# STAGE-02 Research
# ---------------------------------------------------------------------------

def wire_research(
    legacy: dict[str, Any],
    *,
    topic: Topic,
    job_id: str = "",
) -> StageWireResult[TopicResearch]:
    inp = validate_instance(topic, stage="research")
    notes = str(legacy.get("research_notes") or legacy.get("notes") or "").strip()
    trend_evidence = str(legacy.get("trend_evidence") or "UNVERIFIED")

    def _build() -> TopicResearch:
        evidence: list[ResearchEvidence] = []
        if notes:
            for i, chunk in enumerate(notes.split(". ")[:5]):
                chunk = chunk.strip()
                if len(chunk) < 12:
                    continue
                evidence.append(
                    ResearchEvidence(
                        topic_id=topic.id,
                        claim=chunk,
                        source="research_notes",
                        confidence=0.4,
                        evidence_status=EvidenceStatus.UNVERIFIED,
                        raw_excerpt=chunk[:500],
                    )
                )
        status = ResearchStatus.COMPLETED if evidence else ResearchStatus.REQUESTED
        return TopicResearch(
            topic_id=topic.id,
            status=status,
            query=topic.title,
            evidence=evidence,
            verdict=Verdict.UNKNOWN if trend_evidence == "UNVERIFIED" else Verdict.PASS,
            notes=notes or None,
            metadata={"trend_evidence": trend_evidence},
        )

    return run_stage(
        stage="research",
        job_id=job_id or topic.id,
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=topic.id,
    )


# ---------------------------------------------------------------------------
# STAGE-03 FactPack
# ---------------------------------------------------------------------------

def wire_fact_pack(
    legacy: dict[str, Any],
    *,
    topic: Topic,
    job_id: str = "",
) -> StageWireResult[FactPack]:
    inp = validate_instance(topic, stage="factpack")
    pack_legacy = legacy if legacy.get("claims") else build_fact_pack(
        topic.title,
        notes=str(legacy.get("research_notes") or legacy.get("notes") or ""),
        claims=legacy.get("claims"),
    )

    return run_stage(
        stage="factpack",
        job_id=job_id or topic.id,
        legacy=pack_legacy,
        input_validation=inp,
        build_fn=lambda: fact_pack_from_legacy(pack_legacy, topic_id=topic.id),
        entity_id=topic.id,
    )


# ---------------------------------------------------------------------------
# STAGE-04 Script
# ---------------------------------------------------------------------------

def wire_script(
    plan: dict[str, Any],
    *,
    topic: Topic,
    fact_pack: FactPack,
    job_id: str = "",
) -> StageWireResult[Script]:
    inp_topic = validate_instance(topic, stage="script")
    inp_fp = validate_instance(fact_pack, stage="script")
    if not inp_topic.passed:
        inp = inp_topic
    elif not inp_fp.passed:
        inp = inp_fp
    else:
        inp = validate_required_dict(plan, stage="script", required_keys=("scenes",))

    def _build() -> Script:
        script = script_from_plan(plan, topic_id=topic.id)
        script.fact_pack_id = fact_pack.id
        return script

    return run_stage(
        stage="script",
        job_id=job_id or topic.id,
        legacy=plan,
        input_validation=inp,
        build_fn=_build,
        entity_id=topic.id,
    )


# ---------------------------------------------------------------------------
# STAGE-05 Scene (+ embedded plans STAGE 06/07/09)
# ---------------------------------------------------------------------------

def wire_scenes_from_plan(
    plan: dict[str, Any],
    *,
    script: Script,
    job_id: str = "",
) -> list[StageWireResult[Scene]]:
    plan_with_contracts = attach_contracts_to_plan(dict(plan))
    results: list[StageWireResult[Scene]] = []
    for i, sc in enumerate(plan_with_contracts.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        contract = sc.get("scene_contract") or {}
        legacy = {"scene": sc, "contract": contract, "index": i}

        def _build(c=contract, idx=i) -> Scene:
            scene = scene_from_legacy_contract(c, script_id=script.id, scene_index=idx)
            scene.script_id = script.id
            # STAGE-06 VisualPlan (already in scene_from_legacy_contract)
            if scene.visual_plan:
                scene.visual_plan.dialogue_id = _dialogue_id_for_index(script, idx)
            # STAGE-07 AudioPlan
            audio_raw = sc.get("audio") or contract.get("audio") or {}
            scene.audio_plan = AudioPlan(
                scene_id=scene.id,
                dialogue_id=_dialogue_id_for_index(script, idx),
                language=str(audio_raw.get("language") or script.language),
                voice_profile=str(audio_raw.get("voice_profile") or audio_raw.get("voice") or None),
                duration_target_sec=_scene_duration_hint(sc),
                metadata=dict(audio_raw),
            )
            # STAGE-09 SubtitlePlan
            narr = str(sc.get("narration") or contract.get("dialogue") or "")
            dur = _scene_duration_hint(sc) or 8.0
            cues_raw = proportional_cues(narr, dur)
            cues = [
                SubtitleCue(
                    scene_id=scene.id,
                    dialogue_id=_dialogue_id_for_index(script, idx),
                    cue_id=f"cue_{idx}_{j}",
                    start_time=float(c["start"]),
                    end_time=float(c["end"]),
                    text=str(c["text"]),
                    language=script.language,
                )
                for j, c in enumerate(cues_raw)
            ]
            scene.subtitle_plan = SubtitlePlan(scene_id=scene.id, language=script.language, cues=cues)
            return scene

        inp = validate_required_dict(
            {"contract": contract},
            stage="scene",
            required_keys=("contract",),
        )
        if contract.get("dialogue") or contract.get("primary_claim"):
            inp = validate_instance(script, stage="scene")

        results.append(
            run_stage(
                stage="scene",
                job_id=job_id or script.id,
                legacy=legacy,
                input_validation=inp,
                build_fn=lambda c=contract, idx=i, sc=sc: _build(c, idx),
                entity_id=f"{script.id}:{i}",
            )
        )
    return results


def _dialogue_id_for_index(script: Script, index: int) -> Optional[str]:
    if index < len(script.sections):
        dialogues = script.sections[index].dialogues
        if dialogues:
            return dialogues[0].id
    return None


def _scene_duration_hint(sc: dict) -> Optional[float]:
    try:
        end = float(sc.get("end_hint_s") or 0)
        start = float(sc.get("start_hint_s") or 0)
        if end > start:
            return end - start
    except (TypeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# STAGE-06 VisualPlan (standalone from scene)
# ---------------------------------------------------------------------------

def wire_visual_plan(scene: Scene, *, job_id: str = "") -> StageWireResult[VisualPlan]:
    inp = validate_instance(scene, stage="visual")
    if scene.visual_plan is None:
        from domain.validation import ValidationResult, ValidationIssue

        fail = ValidationResult.fail(
            [ValidationIssue(object_type="Scene", rule="visual_plan", severity=Verdict.FAIL, message="missing visual_plan")]
        )
        from pipeline.contract_wiring.core import StageContext, StageWireResult, log_stage
        from domain.errors import AppError
        from domain.enums import ErrorCategory

        ctx = StageContext(job_id=job_id or scene.id, stage="visual", entity_id=scene.id)
        result = StageWireResult.failed(
            stage="visual",
            context=ctx,
            input_validation=inp,
            output_validation=fail,
            error=AppError(category=ErrorCategory.VALIDATION_ERROR, code="missing_visual_plan", message="no visual_plan"),
        )
        log_stage(result)
        return result
    return run_stage(
        stage="visual",
        job_id=job_id or scene.id,
        legacy={"scene_id": scene.id},
        input_validation=inp,
        build_fn=lambda: scene.visual_plan,
        entity_id=scene.id,
    )


# ---------------------------------------------------------------------------
# STAGE-07 AudioPlan
# ---------------------------------------------------------------------------

def wire_audio_plan(scene: Scene, *, job_id: str = "") -> StageWireResult[AudioPlan]:
    inp = validate_instance(scene, stage="audio")
    if scene.audio_plan is None:
        from domain.validation import ValidationResult, ValidationIssue
        from pipeline.contract_wiring.core import StageContext, StageWireResult, log_stage
        from domain.errors import AppError
        from domain.enums import ErrorCategory

        fail = ValidationResult.fail(
            [ValidationIssue(object_type="Scene", rule="audio_plan", severity=Verdict.FAIL, message="missing audio_plan")]
        )
        ctx = StageContext(job_id=job_id or scene.id, stage="audio", entity_id=scene.id)
        result = StageWireResult.failed(
            stage="audio",
            context=ctx,
            input_validation=inp,
            output_validation=fail,
            error=AppError(category=ErrorCategory.VALIDATION_ERROR, code="missing_audio_plan", message="no audio_plan"),
        )
        log_stage(result)
        return result
    return run_stage(
        stage="audio",
        job_id=job_id or scene.id,
        legacy={"scene_id": scene.id},
        input_validation=inp,
        build_fn=lambda: scene.audio_plan,
        entity_id=scene.id,
    )


# ---------------------------------------------------------------------------
# STAGE-08 Localization
# ---------------------------------------------------------------------------

def wire_localization(
    legacy: dict[str, Any],
    *,
    source_dialogue_id: str,
    job_id: str = "",
) -> StageWireResult[Localization]:
    inp = validate_required_dict(
        legacy,
        stage="localization",
        required_keys=("source_language", "target_language", "localized_text"),
    )

    def _build() -> Localization:
        loc_dlg = LocalizedDialogue(
            source_dialogue_id=source_dialogue_id,
            target_language=str(legacy["target_language"]),
            text=str(legacy["localized_text"]),
        )
        vp = None
        if legacy.get("voice_profile"):
            vp = VoiceProfile(language=str(legacy["target_language"]), voice_name=str(legacy["voice_profile"]))
        return Localization(
            source_language=str(legacy["source_language"]),
            target_language=str(legacy["target_language"]),
            source_dialogue_id=source_dialogue_id,
            localized_dialogue=loc_dlg,
            voice_profile=vp,
            cultural_adaptation_status=str(legacy.get("adaptation_status") or "draft"),
        )

    return run_stage(
        stage="localization",
        job_id=job_id or source_dialogue_id,
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=source_dialogue_id,
    )


# ---------------------------------------------------------------------------
# STAGE-09 Subtitle
# ---------------------------------------------------------------------------

def wire_subtitle_plan(scene: Scene, *, job_id: str = "") -> StageWireResult[SubtitlePlan]:
    inp = validate_instance(scene, stage="subtitle")
    if scene.subtitle_plan is None:
        from domain.validation import ValidationResult, ValidationIssue
        from pipeline.contract_wiring.core import StageContext, StageWireResult, log_stage
        from domain.errors import AppError
        from domain.enums import ErrorCategory

        fail = ValidationResult.fail(
            [ValidationIssue(object_type="Scene", rule="subtitle_plan", severity=Verdict.FAIL, message="missing subtitle_plan")]
        )
        ctx = StageContext(job_id=job_id or scene.id, stage="subtitle", entity_id=scene.id)
        result = StageWireResult.failed(
            stage="subtitle",
            context=ctx,
            input_validation=inp,
            output_validation=fail,
            error=AppError(category=ErrorCategory.VALIDATION_ERROR, code="missing_subtitle_plan", message="no subtitle_plan"),
        )
        log_stage(result)
        return result
    return run_stage(
        stage="subtitle",
        job_id=job_id or scene.id,
        legacy={"scene_id": scene.id},
        input_validation=inp,
        build_fn=lambda: scene.subtitle_plan,
        entity_id=scene.id,
    )


# ---------------------------------------------------------------------------
# STAGE-10 Render
# ---------------------------------------------------------------------------

def wire_render(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[RenderJob]:
    inp = validate_required_dict(legacy, stage="render", required_keys=("path",))

    def _build() -> RenderJob:
        artifact = RenderArtifact(
            file_path=str(legacy.get("path") or ""),
            duration_sec=float(legacy.get("duration") or 0) or None,
            metadata={"job_id": job_id, "provenance": "pipeline.render"},
        )
        manifest = RenderManifest(
            job_id=job_id or new_id(),
            artifacts=[artifact],
            output_path=str(legacy.get("path") or ""),
        )
        return RenderJob(
            pipeline_job_id=job_id,
            entity_id=str(legacy.get("job_id") or "") or None,
            status=LifecycleStatus.COMPLETED if legacy.get("path") else LifecycleStatus.PENDING,
            manifest=manifest,
            verdict=Verdict.PASS if legacy.get("path") else Verdict.UNKNOWN,
            metadata={"work_dir": legacy.get("work_dir"), "has_audio": legacy.get("has_audio")},
        )

    return run_stage(
        stage="render",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=str(legacy.get("path") or "")[:80],
    )


# ---------------------------------------------------------------------------
# STAGE-11 Metadata
# ---------------------------------------------------------------------------

def wire_metadata(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[VideoMetadata]:
    inp = validate_required_dict(legacy, stage="metadata", required_keys=("title",))

    def _build() -> VideoMetadata:
        tags = legacy.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return VideoMetadata(
            title=str(legacy["title"]),
            description=str(legacy.get("description") or "") or None,
            tags=list(tags),
            language=str(legacy.get("language") or "en"),
            thumbnail_asset_id=str(legacy.get("thumbnail_asset_id") or "") or None,
        )

    return run_stage(
        stage="metadata",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=str(legacy.get("title") or "")[:80],
    )


# ---------------------------------------------------------------------------
# STAGE-12 Thumbnail
# ---------------------------------------------------------------------------

def wire_thumbnail(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[ThumbnailAsset]:
    inp = validate_required_dict(legacy, stage="thumbnail", required_keys=("path",))

    def _build() -> ThumbnailAsset:
        return ThumbnailAsset(
            file_path=str(legacy["path"]),
            metadata={"job_id": job_id, "source": legacy.get("source", "generated")},
        )

    return run_stage(
        stage="thumbnail",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=str(legacy.get("path") or "")[:80],
    )


# ---------------------------------------------------------------------------
# STAGE-13 Upload
# ---------------------------------------------------------------------------

def wire_upload_job(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[UploadJob]:
    inp = validate_required_dict(legacy, stage="upload", required_keys=("title", "local_path"))

    def _build() -> UploadJob:
        platform = str(legacy.get("platform") or "youtube")
        meta = VideoMetadata(
            title=str(legacy["title"]),
            description=str(legacy.get("description") or "") or None,
            tags=[],
        )
        target = PublicationTarget(platform=platform, dry_run=bool(legacy.get("dry_run", True)))
        return UploadJob(
            render_job_id=str(legacy.get("render_job_id") or "") or None,
            target=target,
            video_metadata=meta,
            local_path=str(legacy["local_path"]),
            status=LifecycleStatus.PENDING,
        )

    return run_stage(
        stage="upload",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=str(legacy.get("local_path") or "")[:80],
    )


# ---------------------------------------------------------------------------
# STAGE-14 Publication
# ---------------------------------------------------------------------------

def wire_publication(
    legacy: dict[str, Any],
    *,
    upload_job: UploadJob,
    job_id: str = "",
) -> StageWireResult[Publication]:
    inp = validate_instance(upload_job, stage="publication")

    def _build() -> Publication:
        ext_id = str(legacy.get("external_id") or legacy.get("remote_url") or legacy.get("url") or "")
        provider = upload_job.target.platform
        external = ExternalRef(provider=provider, external_id=ext_id or "pending", label=legacy.get("title"))
        status = LifecycleStatus.COMPLETED if legacy.get("ok") else LifecycleStatus.PENDING
        return Publication(
            upload_job_id=upload_job.id,
            target=upload_job.target,
            external=external,
            verification_status=status,
            metadata={"url": legacy.get("url") or legacy.get("remote_url")},
        )

    return run_stage(
        stage="publication",
        job_id=job_id or upload_job.id,
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=upload_job.id,
    )


# ---------------------------------------------------------------------------
# STAGE-15 Engagement
# ---------------------------------------------------------------------------

def wire_comment(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[Comment]:
    inp = validate_required_dict(legacy, stage="engagement", required_keys=("text",))

    def _build() -> Comment:
        return Comment(
            publication_id=str(legacy.get("publication_id") or "") or None,
            text=str(legacy["text"]),
            author=str(legacy.get("author") or "") or None,
            language=str(legacy.get("language") or "en"),
            status=LifecycleStatus.PENDING,
            metadata={"platform": legacy.get("platform")},
        )

    return run_stage(
        stage="engagement",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
        entity_id=str(legacy.get("comment_id") or "")[:80] or None,
    )


def wire_engagement_action(legacy: dict[str, Any], *, job_id: str = "") -> StageWireResult[EngagementAction]:
    inp = validate_required_dict(legacy, stage="engagement_action", required_keys=("action_type", "platform"))

    def _build() -> EngagementAction:
        return EngagementAction(
            action_type=str(legacy["action_type"]),
            platform=str(legacy["platform"]),
            target_url=str(legacy.get("target_url") or "") or None,
            status=LifecycleStatus.PENDING,
        )

    return run_stage(
        stage="engagement_action",
        job_id=job_id or new_id(),
        legacy=legacy,
        input_validation=inp,
        build_fn=_build,
    )
