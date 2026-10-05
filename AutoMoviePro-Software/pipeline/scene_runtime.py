"""Production Scene contract runtime boundary (AMP-003 T004-B)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from domain.adapters import scene_from_legacy_contract, script_from_plan
from domain.scene import AudioPlan, Scene, SubtitleCue, SubtitlePlan
from domain.script import Script
from domain.validation import validate_contract_version
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_text
from pipeline.scene_contract import attach_contracts_to_plan, plan_allows_generation, preflight_scene_contract
from pipeline.subtitle_align import proportional_cues

logger = logging.getLogger(__name__)

VALIDATED_SCENES_FILE = "VALIDATED_SCENES.json"
MIN_DIALOGUE_LEN = 8
MAX_DURATION_SEC = 600.0


class SceneValidationError(RuntimeError):
    """Fail-closed scene contract validation failure."""

    def __init__(self, message: str, *, scene_index: Optional[int] = None, issues: Optional[list[str]] = None) -> None:
        detail = message
        if scene_index is not None:
            detail = f"scene[{scene_index}]: {message}"
        if issues:
            detail = f"{detail} ({';'.join(issues)})"
        super().__init__(detail)
        self.scene_index = scene_index
        self.issues = list(issues or [])


def _dialogue_id_for_index(script: Script, index: int) -> Optional[str]:
    if 0 <= index < len(script.sections):
        dialogues = script.sections[index].dialogues
        if dialogues:
            return dialogues[0].id
    return None


def _scene_duration_hint(row: dict[str, Any]) -> Optional[float]:
    try:
        end = float(row.get("end_hint_s") or 0)
        start = float(row.get("start_hint_s") or 0)
        if end > start:
            dur = end - start
            if dur > MAX_DURATION_SEC:
                raise SceneValidationError(f"duration exceeds max {MAX_DURATION_SEC}s")
            return dur
        if end > 0 and start >= end:
            raise SceneValidationError("invalid duration: end_hint_s must exceed start_hint_s")
    except SceneValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise SceneValidationError(f"invalid duration hints: {exc}") from exc
    return None


def build_canonical_scene(
    row: dict[str, Any],
    contract: dict[str, Any],
    *,
    script: Script,
    scene_index: int,
    job_id: str,
) -> Scene:
    """Legacy scene_contract row → canonical Scene with plans attached."""
    pf = preflight_scene_contract(contract)
    if pf.get("verdict") != "PASS":
        raise SceneValidationError(
            f"preflight {pf.get('verdict')}",
            scene_index=scene_index,
            issues=list(pf.get("issues") or []),
        )

    scene = scene_from_legacy_contract(contract, script_id=script.id, scene_index=scene_index)
    scene.script_id = script.id
    dialogue_id = _dialogue_id_for_index(script, scene_index)
    if not dialogue_id:
        raise SceneValidationError("missing dialogue binding", scene_index=scene_index)

    narr = str(row.get("narration") or contract.get("dialogue") or "").strip()
    if len(narr) < MIN_DIALOGUE_LEN:
        raise SceneValidationError("missing or too-short dialogue", scene_index=scene_index)

    scene.dialogue_id = dialogue_id
    if scene.visual_plan is None:
        raise SceneValidationError("missing visual_plan", scene_index=scene_index)
    scene.visual_plan.dialogue_id = dialogue_id
    scene.visual_plan.scene_id = scene.id

    audio_raw = row.get("audio") or contract.get("audio") or {}
    dur = _scene_duration_hint(row)
    scene.duration_target_sec = dur
    scene.audio_plan = AudioPlan(
        scene_id=scene.id,
        dialogue_id=dialogue_id,
        language=str(audio_raw.get("language") or script.language),
        voice_profile=str(audio_raw.get("voice_profile") or audio_raw.get("voice") or "") or None,
        duration_target_sec=dur,
        metadata=dict(audio_raw),
    )

    cue_dur = dur or 8.0
    cues_raw = proportional_cues(narr, cue_dur)
    cues = [
        SubtitleCue(
            scene_id=scene.id,
            dialogue_id=dialogue_id,
            cue_id=f"cue_{scene_index}_{j}",
            start_time=float(c["start"]),
            end_time=float(c["end"]),
            text=str(c["text"]),
            language=script.language,
        )
        for j, c in enumerate(cues_raw)
    ]
    scene.subtitle_plan = SubtitlePlan(scene_id=scene.id, language=script.language, cues=cues)

    ok, reason = validate_contract_version(Scene, scene.to_json_dict())
    if not ok:
        raise SceneValidationError(reason or "schema validation failed", scene_index=scene_index)

    if not (scene.visual_plan.shot.subject or "").strip():
        raise SceneValidationError("visual_plan.shot.subject required", scene_index=scene_index)

    scene.metadata.setdefault("job_id", job_id)
    scene.metadata.setdefault("canonical_scene_id", scene.id)
    return scene


def scene_to_handoff_dict(scene: Scene, row: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Validated handoff dict for legacy downstream engines — locked canonical IDs."""
    out = dict(row)
    narr = str(contract.get("dialogue") or row.get("narration") or "").strip()
    out["narration"] = narr
    out["element"] = scene.element
    out["claim_id"] = scene.claim_id or contract.get("claim_id")
    out["scene_contract"] = contract
    out["canonical_scene_id"] = scene.id
    out["dialogue_id"] = scene.dialogue_id
    out["script_id"] = scene.script_id
    out["scene_index"] = scene.scene_index
    out["contract_preflight"] = {"passed": True, "verdict": "PASS", "issues": []}
    compiled = str((contract.get("prompt_fields") or {}).get("visual_prompt") or row.get("visual_prompt") or "")
    try:
        from pipeline.visual_semantic.scene_intent import build_scene_intent_from_scene
        from pipeline.multimodal_consistency.prompt_compiler import compile_provider_prompt

        intent = build_scene_intent_from_scene(scene)
        provider_prompt = compile_provider_prompt(intent)
        compiled = provider_prompt.positive
        out["scene_intent_fingerprint"] = provider_prompt.intent_fingerprint
        out["compiled_negative_prompt"] = provider_prompt.negative
    except Exception as exc:
        logger.debug("scene_intent prompt compile skipped: %s", exc)
    if compiled:
        out["visual_prompt"] = compiled
        if not out.get("exact_ai_video_prompt"):
            out["exact_ai_video_prompt"] = compiled
    out["_validated"] = True
    return out


def compute_scene_identity_fingerprint(scene: Scene, *, job_id: str) -> str:
    """Deterministic fingerprint for idempotency compatibility (TASK-003)."""
    payload = {
        "job_id": job_id,
        "scene_id": scene.id,
        "scene_index": scene.scene_index,
        "dialogue_id": scene.dialogue_id,
        "element": scene.element,
        "primary_claim": scene.primary_claim or "",
        "dialogue_hash": hash_text(str(scene.metadata.get("dialogue") or ""))[:16],
        "visual_prompt_hash": scene.visual_plan.prompt_hash if scene.visual_plan else "",
        "duration": scene.duration_target_sec,
    }
    return compute_fingerprint(job_id=job_id, stage="scene", entity_id=scene.id, inputs=payload)


def _assert_identity_integrity(scenes: list[Scene], script: Script) -> None:
    seen_scene_ids: set[str] = set()
    seen_indices: set[int] = set()
    seen_dialogue_ids: set[str] = set()
    for scene in scenes:
        if scene.id in seen_scene_ids:
            raise SceneValidationError(f"duplicate scene id {scene.id}", scene_index=scene.scene_index)
        seen_scene_ids.add(scene.id)
        if scene.scene_index in seen_indices:
            raise SceneValidationError(f"duplicate scene_index {scene.scene_index}", scene_index=scene.scene_index)
        seen_indices.add(scene.scene_index)
        if not scene.dialogue_id:
            raise SceneValidationError("missing dialogue_id", scene_index=scene.scene_index)
        if scene.dialogue_id in seen_dialogue_ids:
            raise SceneValidationError(
                f"duplicate dialogue_id {scene.dialogue_id}",
                scene_index=scene.scene_index,
            )
        seen_dialogue_ids.add(scene.dialogue_id)
        expected = _dialogue_id_for_index(script, scene.scene_index)
        if expected and scene.dialogue_id != expected:
            raise SceneValidationError(
                f"dialogue_id mismatch: got {scene.dialogue_id}, expected {expected}",
                scene_index=scene.scene_index,
            )
    indices = sorted(s.scene_index for s in scenes)
    if indices != list(range(len(indices))):
        raise SceneValidationError(f"scene ordering not contiguous: {indices}")


def persist_validated_scenes(work_dir: Path, scenes: list[Scene], *, job_id: str, script_id: str) -> Path:
    work_dir = Path(work_dir)
    path = work_dir / VALIDATED_SCENES_FILE
    payload = {
        "job_id": job_id,
        "script_id": script_id,
        "schema_version": "1.0.0",
        "scenes": [s.to_json_dict() for s in scenes],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_validated_scenes(work_dir: Path) -> Optional[list[Scene]]:
    path = Path(work_dir) / VALIDATED_SCENES_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("scenes") or []
        return [Scene.from_json_dict(row) for row in rows if isinstance(row, dict)]
    except Exception as exc:
        logger.warning("validated scenes reload failed: %s", exc)
        return None


def assert_production_scenes_validated(
    plan: dict[str, Any],
    *,
    job_id: str,
    work_dir: Optional[Path] = None,
    persist: bool = True,
) -> tuple[list[Scene], list[dict[str, Any]]]:
    """
    Production fail-closed gate: legacy plan → canonical Scene → validated handoff dicts.
    Raises SceneValidationError on any invalid scene.
    """
    if not isinstance(plan, dict):
        raise SceneValidationError("plan must be a dict")
    raw_scenes = plan.get("scenes") or []
    if not raw_scenes:
        raise SceneValidationError("plan has no scenes")

    script = script_from_plan(plan, topic_id=job_id)
    enriched = attach_contracts_to_plan(dict(plan))
    if not plan_allows_generation(enriched):
        report = enriched.get("scene_contract_report") or {}
        failed = [s for s in (report.get("scenes") or []) if s.get("verdict") != "PASS"]
        issues = []
        for f in failed:
            issues.extend([f"scene[{f.get('scene_id')}]:{x}" for x in (f.get("issues") or [f.get("verdict")])])
        raise SceneValidationError("scene_contract_report failed", issues=issues or ["preflight_failed"])

    canonical: list[Scene] = []
    handoff: list[dict[str, Any]] = []
    for i, sc in enumerate(enriched.get("scenes") or []):
        if not isinstance(sc, dict):
            raise SceneValidationError("scene row must be dict", scene_index=i)
        contract = sc.get("scene_contract") or {}
        scene = build_canonical_scene(sc, contract, script=script, scene_index=i, job_id=job_id)
        canonical.append(scene)
        handoff.append(scene_to_handoff_dict(scene, sc, contract))

    _assert_identity_integrity(canonical, script)

    # AMP-004 Phase-03: PRE-generation continuity constraints → prompt compile
    try:
        from pipeline.visual_semantic.continuity_runtime import (
            ContinuityError,
            ContinuityPromptBlocked,
            apply_production_continuity,
        )

        cont_dir = Path(work_dir) if work_dir is not None else None
        if cont_dir is None:
            import tempfile

            cont_dir = Path(tempfile.mkdtemp(prefix="amp_cont_"))
        handoff = apply_production_continuity(
            cont_dir,
            handoff,
            job_id=job_id,
            block_on_critical=True,
        )
    except (ContinuityError, ContinuityPromptBlocked) as exc:
        raise SceneValidationError(str(exc), issues=[str(exc)]) from exc
    except Exception as exc:
        logger.error("production continuity failed closed: %s", exc)
        raise SceneValidationError(f"continuity_blocked:{exc}") from exc

    # AMP-004 Phase-05: canonical AudioPlan + preflight (before TTS provider)
    try:
        from pipeline.audio_design.preflight import AudioPreflightError
        from pipeline.audio_design.production import apply_production_audio_design

        aud_dir = Path(work_dir) if work_dir is not None else cont_dir
        handoff = apply_production_audio_design(
            aud_dir,
            handoff,
            job_id=job_id,
            block_on_critical=True,
        )
    except AudioPreflightError as exc:
        raise SceneValidationError(str(exc), issues=list(exc.issues)) from exc
    except Exception as exc:
        logger.error("production audio design failed closed: %s", exc)
        raise SceneValidationError(f"audio_design_blocked:{exc}") from exc

    # AMP-004 Phase-07: CreativeProductionPlan + preflight (before visual provider)
    try:
        from pipeline.creative_production.preflight import CreativePreflightError
        from pipeline.creative_production.production import apply_production_creative_plan

        cr_dir = Path(work_dir) if work_dir is not None else aud_dir
        handoff = apply_production_creative_plan(
            cr_dir,
            handoff,
            job_id=job_id,
            plan=enriched,
            block_on_critical=True,
        )
    except CreativePreflightError as exc:
        raise SceneValidationError(str(exc), issues=list(exc.issues)) from exc
    except Exception as exc:
        logger.error("production creative plan failed closed: %s", exc)
        raise SceneValidationError(f"creative_production_blocked:{exc}") from exc

    if persist and work_dir is not None:
        persist_validated_scenes(Path(work_dir), canonical, job_id=job_id, script_id=script.id)

    logger.info(
        "scene_runtime validated job=%s scenes=%s script=%s",
        job_id,
        len(canonical),
        script.id[:8],
    )
    return canonical, handoff
