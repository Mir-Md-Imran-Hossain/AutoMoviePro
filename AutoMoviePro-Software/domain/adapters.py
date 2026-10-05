"""Legacy payload → canonical contract adapters (BUILD-01)."""
from __future__ import annotations

from typing import Any, Optional

from domain.common import new_id
from domain.enums import EvidenceStatus, JobState, Verdict
from domain.execution import Checkpoint, Job
from domain.fact_pack import FactClaim, FactPack
from domain.scene import Scene, ShotPlan, SubtitleCue, SubtitlePlan, VisualEvidence, VisualPlan
from domain.script import Dialogue, Script
from domain.topic import Topic
from domain.validation import ValidationIssue, ValidationResult


def legacy_version_to_semver(v: str) -> str:
    raw = (v or "").strip().lower()
    if raw.startswith("v"):
        body = raw[1:]
        if body.replace(".", "").isdigit():
            return f"{body}.0" if body.count(".") == 0 else body
    if raw.count(".") >= 1:
        return raw
    return "1.0.0"


def topic_from_plan(plan: dict[str, Any]) -> Topic:
    title = str(plan.get("topic") or plan.get("title") or "").strip()
    return Topic(
        title=title or "untitled",
        normalized_title=title.lower() if title else None,
        niche=str(plan.get("niche") or plan.get("style_family") or "") or None,
        content_type=str(plan.get("video_type") or "short"),
        source=str(plan.get("director_provider") or "pipeline"),
        metadata={
            "max_seconds": plan.get("max_seconds"),
            "tags": plan.get("tags"),
        },
    )


def fact_pack_from_legacy(
    legacy: dict[str, Any],
    *,
    topic_id: Optional[str] = None,
) -> FactPack:
    claims: list[FactClaim] = []
    for row in legacy.get("claims") or []:
        if not isinstance(row, dict):
            continue
        status = EvidenceStatus.UNVERIFIED
        ev = str(row.get("evidence") or "")
        conf = float(row.get("confidence") or 0.5)
        if ev not in ("UNVERIFIED", "research_notes") and conf >= 0.75:
            status = EvidenceStatus.VERIFIED
        elif conf >= 0.4:
            status = EvidenceStatus.UNCERTAIN
        else:
            status = EvidenceStatus.UNSUPPORTED
        claims.append(
            FactClaim(
                claim_id=str(row.get("id") or new_id()),
                claim=str(row.get("claim") or ""),
                evidence=ev or "UNVERIFIED",
                source=str(row.get("source") or "unknown"),
                confidence=conf,
                freshness=str(row.get("freshness") or "UNVERIFIED"),
                evidence_status=status,
            )
        )
    return FactPack(
        schema_version=legacy_version_to_semver(str(legacy.get("version") or "v0")),
        topic_id=topic_id,
        topic_title=str(legacy.get("topic") or ""),
        claims=claims,
        unknowns=list(legacy.get("unknowns") or []),
    )


def scene_from_legacy_contract(
    contract: dict[str, Any],
    *,
    script_id: Optional[str] = None,
    scene_index: int = 0,
) -> Scene:
    scene_uuid = new_id()
    shot_raw = contract.get("shot") or {}
    ev_raw = contract.get("visual_evidence") or {}
    pf = contract.get("prompt_fields") or {}
    shot = ShotPlan(
        subject=str(shot_raw.get("subject") or ""),
        action=str(shot_raw.get("action") or ""),
        environment=str(shot_raw.get("environment") or ""),
        camera=str(shot_raw.get("camera") or "slow push-in, stable documentary"),
        lighting=str(shot_raw.get("lighting") or "natural cinematic grade"),
        composition=str(shot_raw.get("composition") or "subject-centered"),
        shot_type=str(shot_raw.get("shot_type") or ""),
        camera_position=str(shot_raw.get("camera_position") or ""),
        camera_motion=str(shot_raw.get("camera_motion") or shot_raw.get("motion") or ""),
        framing=str(shot_raw.get("framing") or ""),
        focus=str(shot_raw.get("focus") or ""),
        purpose=str(shot_raw.get("purpose") or shot_raw.get("shot_purpose") or ""),
    )
    visual = VisualPlan(
        scene_id=scene_uuid,
        evidence=VisualEvidence(
            must_show=list(ev_raw.get("must_show") or []),
            should_show=list(ev_raw.get("should_show") or []),
            must_not_show=list(ev_raw.get("must_not_show") or []),
        ),
        shot=shot,
        prompt_reference=str(pf.get("visual_prompt") or ""),
        continuity=dict(contract.get("continuity") or {}),
    )
    subtitle_raw = contract.get("subtitle") or {}
    subtitle_plan = None
    if subtitle_raw:
        cues = []
        for i, cue in enumerate(subtitle_raw.get("cues") or []):
            if not isinstance(cue, dict):
                continue
            cues.append(
                SubtitleCue(
                    scene_id=scene_uuid,
                    cue_id=str(cue.get("cue_id") or f"C{i:03d}"),
                    start_time=float(cue.get("start_time") or 0),
                    end_time=float(cue.get("end_time") or 0),
                    text=str(cue.get("text") or ""),
                    language=str(cue.get("language") or "en"),
                )
            )
        if cues:
            subtitle_plan = SubtitlePlan(scene_id=scene_uuid, cues=cues)
    legacy_id = contract.get("scene_id")
    return Scene(
        script_id=script_id,
        scene_index=scene_index,
        legacy_scene_id=int(legacy_id) if legacy_id is not None else scene_index,
        element=str(contract.get("element") or "beat"),
        claim_id=str(contract.get("claim_id") or "") or None,
        primary_claim=str(contract.get("primary_claim") or "") or None,
        visual_plan=visual,
        subtitle_plan=subtitle_plan,
        metadata={
            "dialogue": contract.get("dialogue"),
            "legacy_version": contract.get("version"),
        },
    )


def script_from_plan(plan: dict[str, Any], *, topic_id: Optional[str] = None) -> Script:
    script = Script(
        topic_id=topic_id,
        title=str(plan.get("title") or plan.get("topic") or "untitled"),
        language=str(plan.get("language") or "en"),
        metadata={
            "description": plan.get("description"),
            "tags": plan.get("tags"),
        },
    )
    for i, sc in enumerate(plan.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        text = str(sc.get("narration") or sc.get("dialogue") or "").strip()
        if not text:
            continue
        dlg = Dialogue(
            script_id=script.id,
            scene_id=new_id(),
            element=str(sc.get("element") or "beat"),
            text=text,
            claim_id=str(sc.get("claim_id") or "") or None,
        )
        from domain.script import ScriptSection

        script.sections.append(
            ScriptSection(
                script_id=script.id,
                section_key=dlg.element,
                dialogues=[dlg],
                order=i,
            )
        )
    return script


def validation_from_preflight(preflight: dict[str, Any], *, object_type: str = "Scene") -> ValidationResult:
    verdict_raw = str(preflight.get("verdict") or "UNKNOWN").upper()
    try:
        verdict = Verdict(verdict_raw)
    except ValueError:
        verdict = Verdict.UNKNOWN
    issues = [
        ValidationIssue(
            object_type=object_type,
            rule="preflight",
            severity=Verdict.FAIL if verdict == Verdict.FAIL else verdict,
            message=str(code),
        )
        for code in preflight.get("issues") or []
    ]
    passed = bool(preflight.get("passed")) and verdict == Verdict.PASS
    return ValidationResult(verdict=verdict, passed=passed, issues=issues)


def job_from_fsm_dict(data: dict[str, Any]) -> Job:
    from domain.enums import PHASE_TO_JOB_STATE

    raw_state = str(data.get("state") or "CREATED")
    up = raw_state.upper()
    if up in JobState.__members__:
        status = JobState(up)
    else:
        status = PHASE_TO_JOB_STATE.get(raw_state.lower(), JobState.CREATED)
    return Job(
        job_type=str(data.get("job_type") or "video_generation"),
        entity_id=str(data.get("entity_id") or "") or None,
        status=status,
        attempt=int(data.get("attempt") or 0),
        metadata={"history": data.get("history"), "legacy_job_id": data.get("job_id")},
    )


def checkpoint_from_meta(
    *,
    job_id: str,
    stage: str,
    state: JobState,
    input_hash: Optional[str] = None,
    output_hash: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Checkpoint:
    return Checkpoint(
        job_id=job_id,
        stage=stage,
        state=state,
        input_hash=input_hash,
        output_hash=output_hash,
        metadata=dict(meta or {}),
    )
