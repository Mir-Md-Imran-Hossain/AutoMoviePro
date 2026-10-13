"""Idempotent Agnes visual beat generation — BUILD-04A runtime hook."""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.visual_request import (
    GenerationMode,
    VisualIdentityError,
    VisualRequestSpec,
    compute_visual_fingerprint,
    image_url_identity,
    validate_visual_request_identity,
)
from pipeline.idempotency.visual_runtime import VisualGenerationResult, execute_visual_request

logger = logging.getLogger(__name__)


class AgnesBeatOutcome(str, Enum):
    """Canonical Agnes beat semantics (T004-C2-2-B)."""

    SUCCESS = "SUCCESS"
    REUSED = "REUSED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    UNKNOWN = "UNKNOWN"
    IDENTITY_BLOCKED = "IDENTITY_BLOCKED"


def classify_agnes_beat_outcome(result: VisualGenerationResult) -> AgnesBeatOutcome:
    """Map VisualGenerationResult to canonical outcome — no string guessing."""
    if result.action == "identity_blocked":
        return AgnesBeatOutcome.IDENTITY_BLOCKED
    if result.action == "semantic_blocked":
        return AgnesBeatOutcome.FAILED_FINAL
    if result.success and result.action == "reuse":
        return AgnesBeatOutcome.REUSED
    if result.success and result.action in ("execute", "reconciled"):
        return AgnesBeatOutcome.SUCCESS
    if result.state == IdempotencyState.UNKNOWN or result.action == "unknown":
        return AgnesBeatOutcome.UNKNOWN
    if result.state == IdempotencyState.FAILED_FINAL:
        return AgnesBeatOutcome.FAILED_FINAL
    if result.state == IdempotencyState.FAILED_RETRYABLE or result.action == "failed":
        return AgnesBeatOutcome.FAILED_RETRYABLE
    if result.action == "duplicate_prevented" and result.state == IdempotencyState.UNKNOWN:
        return AgnesBeatOutcome.UNKNOWN
    if not result.success:
        return AgnesBeatOutcome.FAILED_RETRYABLE
    return AgnesBeatOutcome.SUCCESS


def try_reconcile_agnes_beat_unknown(
    work_dir: Path,
    *,
    job_id: str,
    scene_id: int,
    part_index: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    override_prompt: str,
    narration_hint: str,
    size: str,
    duration_hint: float,
    image_url: str = "",
    use_catalog_image: bool = True,
    niche: str = "",
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    local_artifact: str = "",
) -> Optional[Path]:
    """Attempt UNKNOWN reconciliation via existing BUILD-03/04A path."""
    from pipeline.idempotency.visual_runtime import reconcile_visual_unknown
    from pipeline.idempotency.visual_validation import validate_visual_asset

    spec = _build_agnes_spec(
        job_id=job_id,
        scene_id=scene_id,
        part_index=part_index,
        product_name=product_name,
        element=element,
        visual_prompt=visual_prompt,
        override_prompt=override_prompt,
        narration_hint=narration_hint,
        size=size,
        duration_hint=duration_hint,
        image_url=image_url,
        use_catalog_image=use_catalog_image,
        niche=niche,
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        segment_id=segment_id,
        revision_id=revision_id,
    )
    recon = reconcile_visual_unknown(work_dir, spec, local_artifact=local_artifact)
    if recon.success and recon.path and recon.path.is_file():
        ok, _ = validate_visual_asset(str(recon.path), mode="video")
        if ok:
            return recon.path
    return None


def _build_agnes_spec(
    *,
    job_id: str,
    scene_id: int,
    part_index: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    override_prompt: str,
    narration_hint: str,
    size: str,
    duration_hint: float,
    image_url: str,
    use_catalog_image: bool,
    niche: str,
    dialogue_id: str,
    canonical_scene_id: str,
    script_id: str,
    segment_id: str,
    revision_id: str,
    generation_mode: Optional[GenerationMode] = None,
    generation_payload: Optional[dict] = None,
) -> VisualRequestSpec:
    """Build VisualRequestSpec for Agnes. C05-GP: mode/payload override when provided."""
    prompt = (override_prompt or visual_prompt or "").strip()
    payload = dict(generation_payload or {})
    if generation_mode is not None:
        mode = generation_mode
    elif payload.get("generation_mode"):
        try:
            mode = GenerationMode(str(payload.get("generation_mode")))
        except Exception:
            mode = None
        if mode is None:
            mode = GenerationMode.IMAGE_TO_VIDEO if image_url else (
                GenerationMode.TEXT_TO_VIDEO if not use_catalog_image else GenerationMode.IMAGE_TO_VIDEO
            )
    else:
        mode = GenerationMode.IMAGE_TO_VIDEO if image_url else (
            GenerationMode.TEXT_TO_VIDEO if not use_catalog_image else GenerationMode.IMAGE_TO_VIDEO
        )
        if not image_url and use_catalog_image:
            mode = GenerationMode.IMAGE_TO_VIDEO
    # Honest capability: Agnes does not serve pure IMAGE mode
    if mode == GenerationMode.IMAGE_GENERATION or str(payload.get("visual_mode") or "").upper() == "IMAGE":
        raise VisualIdentityError("agnes_adapter_rejects_IMAGE_mode_use_image_route")
    meta = {
        "beat_id": payload.get("beat_id") or segment_id,
        "visual_mode": payload.get("visual_mode") or payload.get("actual_mode") or "",
        "requested_mode": payload.get("requested_mode") or "",
        "actual_mode": payload.get("actual_mode") or "",
        "route": payload.get("route") or "VIDEO_PROVIDER",
        "location_identity": payload.get("location_identity") or "",
        "character_identity": (payload.get("character_state") or {}).get("identity")
        if isinstance(payload.get("character_state"), dict)
        else "",
        "object_state": list(payload.get("object_state") or []),
        "relationships": list(payload.get("relationships") or []),
        "coverage": payload.get("coverage") or {},
        "timing": payload.get("timing") or {},
        "continuity_fingerprint": payload.get("continuity_fingerprint") or "",
        "alignment_fingerprint": (payload.get("provenance") or {}).get("alignment_fingerprint") or "",
        "prompt_fingerprint": (payload.get("provenance") or {}).get("prompt_fingerprint") or "",
        "fallback_used": bool(payload.get("fallback_used")),
        "fallback_reason": payload.get("fallback_reason") or "",
        "capability_status": payload.get("capability_status") or "",
        "canonical_prompt": payload.get("canonical_prompt") or visual_prompt,
        "negative_constraints": list(payload.get("negative_constraints") or []),
        "customer_id": payload.get("customer_id") or "",
        "channel_id": payload.get("channel_id") or "",
        "generation_id": payload.get("generation_id") or "",
        "adapter": payload.get("adapter") or "agnes_bridge",
        "language_entitlement": payload.get("language_entitlement") or "",
        "camera": payload.get("camera") or "",
        "lighting": payload.get("lighting") or "",
    }
    return VisualRequestSpec(
        job_id=job_id,
        scene_id=scene_id,
        visual_plan_id=element or f"p{part_index}",
        provider="agnes",
        model="agnes-video-v2.0",
        generation_mode=mode,
        prompt=prompt,
        visual_prompt=str(payload.get("canonical_prompt") or visual_prompt),
        narration_hint=narration_hint,
        element=element,
        product_name=product_name,
        size=size,
        duration_sec=duration_hint,
        image_url_hash=image_url_identity(image_url),
        niche=niche,
        dialogue_id=dialogue_id or str(payload.get("dialogue_id") or ""),
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        part_index=int(part_index or 0),
        segment_id=segment_id or str(payload.get("beat_id") or ""),
        revision_id=revision_id,
        metadata=meta,
    )


def _validate_production_identity(
    spec: VisualRequestSpec,
    *,
    scene_id: int,
    dialogue_id: str,
    canonical_scene_id: str,
    part_index: int,
    segment_id: str,
    production_identity: bool,
) -> None:
    use_production = production_identity or bool(dialogue_id.strip() and canonical_scene_id.strip())
    if (dialogue_id.strip() or canonical_scene_id.strip()) and not use_production:
        raise VisualIdentityError("partial production identity: dialogue_id and canonical_scene_id required together")
    if use_production:
        validate_visual_request_identity(
            spec,
            production=True,
            expected_scene_index=scene_id,
            expected_dialogue_id=dialogue_id,
            expected_canonical_scene_id=canonical_scene_id,
        )
        if int(part_index or 0) > 0 and not segment_id.strip():
            raise VisualIdentityError("missing segment_id for split visual part")


def idempotent_generate_agnes_beat_result(
    *,
    work_dir: Path,
    job_id: str,
    scene_id: int,
    part_index: int,
    attempt: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    out_path: Path,
    narration_hint: str = "",
    size: str = "1080x1920",
    duration_hint: float = 5.0,
    override_prompt: str = "",
    niche: str = "",
    image_url: str = "",
    use_catalog_image: bool = True,
    provider_fn=None,
    fallback_provider_fn=None,
    use_mock: bool = False,
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    production_identity: bool = False,
    generation_mode: Optional[GenerationMode] = None,
    generation_payload: Optional[dict[str, Any]] = None,
) -> VisualGenerationResult:
    """
    Canonical Agnes gateway — returns explicit VisualGenerationResult.
    Identity failures → action=identity_blocked (non-success, no provider call).
    """
    try:
        spec = _build_agnes_spec(
            job_id=job_id,
            scene_id=scene_id,
            part_index=part_index,
            product_name=product_name,
            element=element,
            visual_prompt=visual_prompt,
            override_prompt=override_prompt,
            narration_hint=narration_hint,
            size=size,
            duration_hint=duration_hint,
            image_url=image_url,
            use_catalog_image=use_catalog_image,
            niche=niche,
            dialogue_id=dialogue_id,
            canonical_scene_id=canonical_scene_id,
            script_id=script_id,
            segment_id=segment_id,
            revision_id=revision_id,
            generation_mode=generation_mode,
            generation_payload=generation_payload,
        )
    except VisualIdentityError as exc:
        # Capability / mode rejection before fingerprint of a bogus IMAGE→Agnes call
        return VisualGenerationResult(
            success=False,
            action="identity_blocked",
            fingerprint="",
            state=IdempotencyState.FAILED_FINAL,
            detail=str(exc),
        )
    try:
        _validate_production_identity(
            spec,
            scene_id=scene_id,
            dialogue_id=dialogue_id,
            canonical_scene_id=canonical_scene_id,
            part_index=part_index,
            segment_id=segment_id,
            production_identity=production_identity,
        )
    except VisualIdentityError as exc:
        fp = compute_visual_fingerprint(spec)
        return VisualGenerationResult(
            success=False,
            action="identity_blocked",
            fingerprint=fp,
            state=IdempotencyState.FAILED_FINAL,
            detail=str(exc),
        )

    # AMP-004 Phase-02: reject production semantic bypass BEFORE provider call
    prod_like = bool(
        production_identity or (dialogue_id.strip() and canonical_scene_id.strip())
    )
    try:
        from pipeline.quality.multimodal_aggregate import assert_production_semantic_bypass_forbidden

        assert_production_semantic_bypass_forbidden(
            spec.metadata,
            production=prod_like,
            allow_test_only=bool(spec.metadata.get("allow_test_only_bypass")),
        )
    except PermissionError as bypass_exc:
        fp = compute_visual_fingerprint(spec)
        return VisualGenerationResult(
            success=False,
            action="identity_blocked",
            fingerprint=fp,
            state=IdempotencyState.FAILED_FINAL,
            detail=str(bypass_exc),
        )

    if provider_fn is None and not use_mock:

        def _agnes():
            from pipeline.media_assets import generate_agnes_dialogue_clip

            res = generate_agnes_dialogue_clip(
                product_name=product_name,
                element=element,
                visual_prompt=visual_prompt,
                out_path=out_path,
                narration_hint=narration_hint,
                size=size,
                duration_hint=duration_hint,
                image_url=image_url,
                override_prompt=override_prompt,
                niche=niche,
                use_catalog_image=use_catalog_image,
            )
            if res and res.exists() and res.stat().st_size > 5000:
                return res

            import logging, os
            logger = logging.getLogger(__name__)
            logger.warning("Agnes exhausted/failed. Trying Seedance, Kling, Luma fallbacks...")

            try:
                from pipeline.custom_pipeline.media_providers import video_kling, video_luma, video_seedance
                from pipeline.custom_pipeline.session_keys import _env_map, _collect_numbered
                w, h = (int(x) for x in size.split("x"))
                dur = duration_hint or 5.0
                env = _env_map()
                
                # 1. Seedance
                if _collect_numbered(env, ["SEEDANCE_API_KEY", "REPLICATE_API_TOKEN"], max_n=5):
                    try:
                        logger.warning("Attempting Seedance fallback...")
                        p = video_seedance(override_prompt or visual_prompt, out_path, w=w, h=h, duration=dur)
                        if p and p.exists() and p.stat().st_size > 5000:
                            return p
                        else:
                            logger.warning("Seedance returned None or invalid file")
                    except Exception as e:
                        logger.warning("seedance fallback failed: %s", e)

                # 2. Kling
                if _collect_numbered(env, ["KLING_API_KEY"], max_n=5):
                    try:
                        logger.warning("Attempting Kling fallback...")
                        p = video_kling(override_prompt or visual_prompt, out_path, w=w, h=h, duration=dur)
                        if p and p.exists() and p.stat().st_size > 5000:
                            return p
                        else:
                            logger.warning("Kling returned None or invalid file")
                    except Exception as e:
                        logger.warning("kling fallback failed: %s", e)

                # 3. Luma
                if _collect_numbered(env, ["LUMA_API_KEY"], max_n=5):
                    try:
                        logger.warning("Attempting Luma fallback...")
                        p = video_luma(override_prompt or visual_prompt, out_path, w=w, h=h, duration=dur)
                        if p and p.exists() and p.stat().st_size > 5000:
                            return p
                        else:
                            logger.warning("Luma returned None or invalid file")
                    except Exception as e:
                        logger.warning("luma fallback failed: %s", e)
            except Exception as outer_e:
                logger.error("Outer exception in fallback chain: %s", outer_e)

            logger.warning("All fallbacks exhausted. Returning None.")
            return None

        provider_fn = _agnes

    result = execute_visual_request(
        work_dir,
        spec,
        out_path,
        provider_fn=provider_fn,
        use_mock=use_mock,
        fallback_provider_fn=fallback_provider_fn,
    )

    if result.success and result.path and result.path.is_file():
        if not spec.metadata.get("skip_semantic_validation"):
            try:
                from pipeline.multimodal_consistency.boundary import multimodal_gate_for_spec
                from pipeline.quality.multimodal_aggregate import persist_multimodal_report

                mm = multimodal_gate_for_spec(
                    asset_path=result.path,
                    narration_hint=narration_hint,
                    visual_prompt=visual_prompt or override_prompt,
                    scene_id=str(scene_id),
                    dialogue_id=dialogue_id,
                    script_id=script_id,
                    revision_id=revision_id,
                    analysis_fixture=spec.metadata.get("semantic_analysis_fixture"),
                    strict=bool(spec.metadata.get("strict_semantic_validation")),
                )
                # Persist for job-level publishability AND (AMP-004 Phase-02)
                try:
                    persist_multimodal_report(
                        work_dir,
                        mm,
                        scene_key=f"{scene_id}_{part_index}_{dialogue_id or 'dlg'}",
                    )
                except Exception as persist_exc:
                    logger.warning("multimodal persist failed scene=%s: %s", scene_id, persist_exc)

                block_on_heuristic = bool(
                    spec.metadata.get("strict_semantic_validation") or spec.metadata.get("semantic_analysis_fixture")
                )
                identity_blocked = any(
                    layer.layer.value == "CROSS_MODAL_VALIDATION"
                    and any(i.get("code") == "DIALOGUE_IDENTITY_MISMATCH" for i in layer.issues)
                    for layer in mm.layers
                )
                if mm.blocked and (block_on_heuristic or identity_blocked):
                    logger.warning(
                        "multimodal_consistency blocked scene=%s status=%s fp=%s",
                        scene_id,
                        mm.final_status.value,
                        mm.intent_fingerprint,
                    )
                    result.success = False
                    result.action = "semantic_blocked"
                    result.state = IdempotencyState.FAILED_FINAL
                    all_issues = [i for layer in mm.layers for i in layer.issues]
                    result.detail = next(
                        (i.get("message", "semantic_blocked") for i in all_issues if i.get("severity") in ("CRITICAL", "HIGH")),
                        "semantic_blocked",
                    )
            except Exception as exc:
                logger.warning("multimodal_consistency gate error scene=%s: %s", scene_id, exc)

        logger.info(
            "visual_runtime scene=%s action=%s fp=%s invocations=%s outcome=%s",
            scene_id,
            result.action,
            result.fingerprint[:12],
            result.provider_invocations,
            classify_agnes_beat_outcome(result).value,
        )
    else:
        logger.warning(
            "visual_runtime failed scene=%s action=%s state=%s outcome=%s",
            scene_id,
            result.action,
            result.state,
            classify_agnes_beat_outcome(result).value,
        )
    return result


def idempotent_generate_agnes_beat(
    *,
    work_dir: Path,
    job_id: str,
    scene_id: int,
    part_index: int,
    attempt: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    out_path: Path,
    narration_hint: str = "",
    size: str = "1080x1920",
    duration_hint: float = 5.0,
    override_prompt: str = "",
    niche: str = "",
    image_url: str = "",
    use_catalog_image: bool = True,
    provider_fn=None,
    fallback_provider_fn=None,
    use_mock: bool = False,
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    segment_id: str = "",
    revision_id: str = "",
    production_identity: bool = False,
) -> Optional[Path]:
    """
    Legacy adapter — returns Path on success, None on runtime failure.
    Raises VisualIdentityError for identity_blocked (backward compatible with C1 tests).
    """
    result = idempotent_generate_agnes_beat_result(
        work_dir=work_dir,
        job_id=job_id,
        scene_id=scene_id,
        part_index=part_index,
        attempt=attempt,
        product_name=product_name,
        element=element,
        visual_prompt=visual_prompt,
        out_path=out_path,
        narration_hint=narration_hint,
        size=size,
        duration_hint=duration_hint,
        override_prompt=override_prompt,
        niche=niche,
        image_url=image_url,
        use_catalog_image=use_catalog_image,
        provider_fn=provider_fn,
        fallback_provider_fn=fallback_provider_fn,
        use_mock=use_mock,
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        segment_id=segment_id,
        revision_id=revision_id,
        production_identity=production_identity,
    )
    if result.action == "identity_blocked":
        raise VisualIdentityError(result.detail or "identity blocked")
    if result.success and result.path and result.path.is_file():
        return result.path
    return None
