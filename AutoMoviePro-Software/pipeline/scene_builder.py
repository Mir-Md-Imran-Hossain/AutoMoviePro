from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.compose import (
    download_file,
    ffmpeg_bin,
    ffprobe_duration,
    make_color_clip,
)
from pipeline.ai_providers import fetch_pexels_videos
from pipeline.av_sync_critic import (
    critique_scene_clip,
    persist_critique,
    precheck_generation_prompt,
)
from pipeline.dialogue_sync import (
    AGNES_AUDIO_CHUNK_MAX,
    AGNES_MAX_SECONDS,
    AGNES_MIN_SECONDS,
    AGNES_TARGET_SECONDS,
    DIALOGUE_TAIL_PAD_SEC,
    duration_mismatch_issue,
    estimate_spoken_seconds,
    pad_av_tail,
    plan_agnes_segments,
    split_audio_file,
)
from pipeline.lang_config import SOURCE_LANG
from pipeline.media_assets import generate_product_still

logger = logging.getLogger(__name__)


class AgnesOutcomeError(RuntimeError):
    """Explicit single-beat Agnes outcome — not Agnes SUCCESS (T004-C2-C3-FP)."""

    def __init__(self, outcome: str, detail: str = ""):
        self.outcome = outcome
        self.detail = detail or ""
        super().__init__(f"Agnes outcome {outcome}: {self.detail}")


def _resolve_split_agnes_beat_src(
    *,
    work: Path,
    job_id: str,
    idx: int,
    part_index: int,
    attempt: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    visual_query: str,
    out_path: Path,
    narration_hint: str,
    size: str,
    duration_hint: float,
    override_prompt: str,
    niche: str,
    use_catalog_image: bool,
    dialogue_id: str,
    canonical_scene_id: str,
    script_id: str,
    segment_id: str,
    provider_fn=None,
    use_mock: bool = False,
) -> tuple[Optional[Path], "VisualGenerationResult"]:
    """
    Split-path Agnes beat via canonical result API (T004-C2-2-C-2).
    Returns (asset_path_or_none, full VisualGenerationResult).
    """
    from pipeline.idempotency.agnes_bridge import (
        AgnesBeatOutcome,
        classify_agnes_beat_outcome,
        idempotent_generate_agnes_beat_result,
    )
    from pipeline.idempotency.visual_runtime import VisualGenerationResult
    from pipeline.idempotency.visual_validation import validate_visual_asset

    result = idempotent_generate_agnes_beat_result(
        work_dir=work,
        job_id=job_id,
        scene_id=idx,
        part_index=part_index,
        attempt=attempt,
        product_name=product_name,
        element=element,
        visual_prompt=visual_prompt or visual_query,
        out_path=out_path,
        narration_hint=narration_hint,
        size=size,
        duration_hint=duration_hint,
        override_prompt=override_prompt,
        niche=niche,
        use_catalog_image=use_catalog_image,
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        segment_id=segment_id,
        provider_fn=provider_fn,
        use_mock=use_mock,
    )
    outcome = classify_agnes_beat_outcome(result)

    if outcome in (AgnesBeatOutcome.SUCCESS, AgnesBeatOutcome.REUSED):
        if result.path and result.path.is_file():
            ok, reason = validate_visual_asset(str(result.path), mode="video")
            if ok:
                return result.path, result
            logger.warning(
                "Split Agnes invalid asset scene=%s part=%s reason=%s outcome=%s",
                idx,
                part_index,
                reason,
                outcome.value,
            )
        else:
            logger.warning(
                "Split Agnes missing path scene=%s part=%s outcome=%s",
                idx,
                part_index,
                outcome.value,
            )
        return None, result

    if outcome == AgnesBeatOutcome.UNKNOWN:
        logger.warning(
            "Split Agnes UNKNOWN scene=%s part=%s fp=%s — no direct retry",
            idx,
            part_index,
            (result.fingerprint or "")[:12],
        )
        return None, result

    if outcome == AgnesBeatOutcome.IDENTITY_BLOCKED:
        logger.warning(
            "Split Agnes identity blocked scene=%s part=%s detail=%s",
            idx,
            part_index,
            result.detail,
        )
        return None, result

    logger.warning(
        "Split Agnes failed scene=%s part=%s outcome=%s state=%s",
        idx,
        part_index,
        outcome.value,
        result.state,
    )
    return None, result


def _resolve_single_agnes_beat_src(
    *,
    work: Path,
    job_id: str,
    idx: int,
    attempt: int,
    product_name: str,
    element: str,
    visual_prompt: str,
    visual_query: str,
    out_path: Path,
    narration_hint: str,
    size: str,
    duration_hint: float,
    override_prompt: str,
    niche: str,
    use_catalog_image: bool,
    dialogue_id: str,
    canonical_scene_id: str,
    script_id: str,
    provider_fn=None,
    use_mock: bool = False,
    generation_payload: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Path], "VisualGenerationResult"]:
    """
    Single-beat Agnes via canonical result API (T004-C2-2-C-3-2).
    Returns (asset_path_or_none, full VisualGenerationResult).
    """
    from pipeline.idempotency.agnes_bridge import (
        AgnesBeatOutcome,
        classify_agnes_beat_outcome,
        idempotent_generate_agnes_beat_result,
    )
    from pipeline.idempotency.visual_request import GenerationMode
    from pipeline.idempotency.visual_runtime import VisualGenerationResult
    from pipeline.idempotency.visual_validation import validate_visual_asset

    gen_mode = None
    payload = dict(generation_payload or {})
    if payload.get("generation_mode"):
        try:
            gen_mode = GenerationMode(str(payload.get("generation_mode")))
        except Exception:
            gen_mode = None

    result = idempotent_generate_agnes_beat_result(
        work_dir=work,
        job_id=job_id,
        scene_id=idx,
        part_index=0,
        attempt=attempt,
        product_name=product_name,
        element=element,
        visual_prompt=visual_prompt or visual_query,
        out_path=out_path,
        narration_hint=narration_hint,
        size=size,
        duration_hint=duration_hint,
        override_prompt=override_prompt,
        niche=niche,
        use_catalog_image=use_catalog_image,
        dialogue_id=dialogue_id,
        canonical_scene_id=canonical_scene_id,
        script_id=script_id,
        provider_fn=provider_fn,
        use_mock=use_mock,
        generation_mode=gen_mode,
        generation_payload=payload or None,
        segment_id=str(payload.get("beat_id") or ""),
    )
    outcome = classify_agnes_beat_outcome(result)

    if outcome in (AgnesBeatOutcome.SUCCESS, AgnesBeatOutcome.REUSED):
        if result.path and result.path.is_file():
            ok, reason = validate_visual_asset(str(result.path), mode="video")
            if ok:
                return result.path, result
            logger.warning(
                "Single Agnes invalid asset scene=%s reason=%s outcome=%s",
                idx,
                reason,
                outcome.value,
            )
        else:
            logger.warning(
                "Single Agnes missing path scene=%s outcome=%s",
                idx,
                outcome.value,
            )
        return None, result

    if outcome == AgnesBeatOutcome.UNKNOWN:
        logger.warning(
            "Single Agnes UNKNOWN scene=%s fp=%s — no direct retry",
            idx,
            (result.fingerprint or "")[:12],
        )
        return None, result

    if outcome == AgnesBeatOutcome.IDENTITY_BLOCKED:
        logger.warning(
            "Single Agnes identity blocked scene=%s detail=%s",
            idx,
            result.detail,
        )
        return None, result

    logger.warning(
        "Single Agnes failed scene=%s outcome=%s state=%s",
        idx,
        outcome.value,
        result.state,
    )
    return None, result


def build_dialogue_clip(
    *,
    work: Path,
    idx: int,
    narration_audio: Optional[Path] = None,
    visual_query: str,
    visual_prompt: str,
    element: str,
    size: str,
    product_name: str = "",
    pexels_api: str = "",
    pollinations_key: str = "",
    agnes_api: str = "",
    agnes_api_keys: Optional[List[str]] = None,
    google_api_keys: Optional[List[str]] = None,
    subtitle_text: str = "",
    narration: str = "",
    require_agnes: bool = True,
    keyword_triggers: Optional[List[str]] = None,
    exact_ai_video_prompt: str = "",
    niche: str = "",
    max_av_retries: int = 1,
    skip_av_critic: bool = False,
    prefer_agnes_native_audio: bool = True,
    allow_image_fallback: bool = True,
    job_id: str = "",
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    visual_mode: str = "",
    scene_context: Optional[Dict[str, Any]] = None,
    customer_id: str = "",
    channel_id: str = "",
    language_entitlement: str = "",
) -> Path:
    """
    Build one dialogue-synced scene with AV-sync critic loop.
    PRIMARY: Agnes VIDEO+AUDIO together (prefer_agnes_native_audio=True) for sync.
    Optional: replace audio with TTS when prefer_agnes_native_audio=False.
    C05-GP: visual_mode / scene_context drive IMAGE vs VIDEO provider routing.
    """
    work.mkdir(parents=True, exist_ok=True)
    try:
        from pipeline.media_assets import reset_agnes_scene_budget

        # Hard cap: at most 2 Agnes creates for this whole scene (incl. split parts)
        reset_agnes_scene_budget(2)
    except Exception:
        pass
    # narration drives critic/duration; subtitle_text is mux burn-in only (keep "" on EN master)
    narration = (narration or subtitle_text or "").strip()
    # Duration: prefer 7–10s window; spoken beats capped ~9s
    if narration_audio and Path(narration_audio).exists():
        dur = max(AGNES_MIN_SECONDS, ffprobe_duration(narration_audio))
    else:
        dur = max(AGNES_MIN_SECONDS, estimate_spoken_seconds(narration, lang="en"))
    if prefer_agnes_native_audio:
        dur = min(max(dur, AGNES_MIN_SECONDS), AGNES_AUDIO_CHUNK_MAX)
    else:
        dur = max(2.0, dur)
    element = (element or "feature").strip().lower()
    product = (product_name or "").strip() or _guess_product_from_query(visual_query)
    target = work / f"scene_{idx:02d}_{element}.mp4"
    keys = google_api_keys or []
    agnes_keys: List[str] = []
    for k in agnes_api_keys or []:
        kk = (k or "").strip()
        if kk and kk not in agnes_keys:
            agnes_keys.append(kk)
    if (agnes_api or "").strip() and (agnes_api or "").strip() not in agnes_keys:
        agnes_keys.insert(0, (agnes_api or "").strip())
    keywords = [str(k).strip() for k in (keyword_triggers or []) if str(k).strip()]
    from pipeline.prompt_engineering import resolve_visual_subject

    product = resolve_visual_subject(product, keywords, narration)
    prompt = (exact_ai_video_prompt or visual_prompt or visual_query or "").strip()

    # OpenMontage-inspired: retrieval-first stock fill when slot queries + Pexels available.
    # AGPL OpenMontage is NOT imported — AMP montage_brain only.
    try:
        import os as _os

        stock_first = str(_os.getenv("AMP_MONTAGE_STOCK_FIRST", "1") or "1").strip() not in (
            "0",
            "false",
            "False",
            "no",
        )
        sc_early = dict(scene_context or {})
        # Stock-first when env on (default) — documentary montage discipline.
        # Set AMP_MONTAGE_STOCK_FIRST=0 to force Agnes-only path.
        if stock_first and pexels_api:
            from pipeline.montage_brain import prefer_retrieved_stock_for_scene

            stock = prefer_retrieved_stock_for_scene(
                work=work,
                idx=idx,
                scene={
                    **sc_early,
                    "narration": narration,
                    "visual_mode": visual_mode or sc_early.get("visual_mode") or "VIDEO",
                    "keyword_triggers": keywords,
                    "element": element,
                    "search_queries": sc_early.get("search_queries")
                    or (sc_early.get("montage_slot") or {}).get("search_queries"),
                    "montage_slot": sc_early.get("montage_slot") or {},
                },
                topic=product or niche or "",
                pexels_api=pexels_api,
                size=size,
                customer_id=customer_id or str(sc_early.get("customer_id") or ""),
                channel_id=channel_id or str(sc_early.get("channel_id") or ""),
            )
            if stock and Path(stock).exists():
                # Prefer TTS/narration mux when we have audio; else return raw stock as base
                if narration_audio and Path(narration_audio).exists():
                    from pipeline.av_self_repair_agent import _mux_picture_with_audio

                    muxed = _mux_picture_with_audio(
                        video_src=Path(stock),
                        audio_src=Path(narration_audio),
                        dest=target,
                        work=work,
                        idx=idx,
                        tag="montage_stock",
                    )
                    if muxed and Path(muxed).exists() and Path(muxed).stat().st_size > 5000:
                        logger.info(
                            "Scene %s: montage brain stock-first ship (OpenMontage-style retrieval)",
                            idx,
                        )
                        return Path(muxed)
                else:
                    shutil.copy2(stock, target)
                    if target.exists() and target.stat().st_size > 5000:
                        logger.info("Scene %s: montage brain stock-first (no TTS yet)", idx)
                        return target
    except Exception as _mb_exc:
        logger.debug("montage stock-first soft-fail: %s", _mb_exc)

    # LONG AUDIO → split into ≤9s Agnes AV beats
    spoken_est = estimate_spoken_seconds(narration, lang="en")
    if narration_audio and Path(narration_audio).exists():
        spoken_est = max(spoken_est, ffprobe_duration(narration_audio))
    if spoken_est > AGNES_AUDIO_CHUNK_MAX + 0.35 and require_agnes and agnes_keys:
        logger.info(
            "Scene %s: audio/narration %.1fs > chunk max %.1fs — splitting into ≤9s clips",
            idx,
            spoken_est,
            AGNES_AUDIO_CHUNK_MAX,
        )
        if not narration_audio or not Path(narration_audio).exists():
            narration_audio = work / f"scene_{idx:02d}_dur_placeholder.m4a"
            # Full estimated duration so planner can split correctly
            _write_silent_audio(narration_audio, spoken_est)
        return _build_split_dialogue_clip(
            work=work,
            idx=idx,
            narration_audio=narration_audio,
            narration=narration,
            visual_query=visual_query,
            visual_prompt=visual_prompt,
            exact_ai_video_prompt=prompt,
            element=element,
            size=size,
            product_name=product,
            agnes_api=agnes_keys[0] if agnes_keys else "",
            agnes_api_keys=agnes_keys,
            google_api_keys=keys,
            keyword_triggers=keywords,
            niche=niche,
            max_av_retries=max_av_retries,
            skip_av_critic=skip_av_critic,
            pexels_api=pexels_api,
            pollinations_key=pollinations_key,
            require_agnes=require_agnes,
            prefer_agnes_native_audio=prefer_agnes_native_audio,
            allow_image_fallback=allow_image_fallback,
            job_id=job_id,
            dialogue_id=dialogue_id,
            canonical_scene_id=canonical_scene_id,
            script_id=script_id,
        )

    # DETERMINISTIC harden FIRST (no API) — finish-dialogue / no talking-head / learned rules
    # C05-GP: when scene_context/visual_mode present, use structured payload + semantic-safe harden
    from pipeline.prompt_hardening import harden_video_prompt

    generation_payload_dict: Optional[Dict[str, Any]] = None
    resolved_visual_mode = (visual_mode or "").strip().upper()
    if not resolved_visual_mode and scene_context:
        resolved_visual_mode = str((scene_context or {}).get("visual_mode") or "").strip().upper()
    prior_issues: List[str] = []
    issue_cache = work / f"scene_{idx:02d}_prior_issues.json"
    if issue_cache.exists():
        try:
            prior_issues = list(json.loads(issue_cache.read_text(encoding="utf-8")) or [])
        except Exception:
            prior_issues = []

    # C05-GP/GX/MR: resolve visual_mode; no silent legacy for canonical production
    if not resolved_visual_mode:
        from pipeline.generation_payload import is_legacy_compat_allowed, resolve_visual_mode_for_scene

        sc0 = dict(scene_context or {})
        resolved = resolve_visual_mode_for_scene(sc0)
        if resolved.get("ok") and resolved.get("visual_mode"):
            resolved_visual_mode = str(resolved["visual_mode"])
            logger.info(
                "Scene %s: C05-MR resolved visual_mode=%s source=%s",
                idx,
                resolved_visual_mode,
                resolved.get("source"),
            )
        else:
            legacy = is_legacy_compat_allowed(sc0)
            if legacy.get("allowed"):
                logger.warning(
                    "Scene %s: explicit historical LEGACY_COMPAT fixture — outside canonical semantics",
                    idx,
                )
            else:
                # Industrial VIDEO-primary default (Agnes) instead of hard-fail empty mode
                resolved_visual_mode = "VIDEO"
                logger.info(
                    "Scene %s: visual_mode unresolvable (%s) — defaulting to VIDEO (Agnes primary)",
                    idx,
                    resolved.get("reason"),
                )

    # C05-GP/GX structured path when visual_mode present; else explicit LEGACY_COMPAT fixture only
    if resolved_visual_mode:
        from pipeline.generation_payload import (
            assert_execution_ready,
            assert_generation_payload_ready,
            build_generation_payload_from_scene,
            inspect_generation_payload,
            inspect_provider_request_integrity,
            materialize_visual_beats,
            payload_to_visual_request_spec,
            record_execution_provenance,
            validate_customer_ownership,
        )

        sc = dict(scene_context or {})
        sc.setdefault("visual_mode", resolved_visual_mode)
        if dialogue_id and not sc.get("dialogue_id"):
            sc["dialogue_id"] = dialogue_id
        if canonical_scene_id and not sc.get("canonical_scene_id"):
            sc["canonical_scene_id"] = canonical_scene_id
        if script_id and not sc.get("script_id"):
            sc["script_id"] = script_id
        if customer_id and not sc.get("customer_id"):
            sc["customer_id"] = customer_id
        if channel_id and not sc.get("channel_id"):
            sc["channel_id"] = channel_id
        if language_entitlement and not sc.get("language_entitlement"):
            sc["language_entitlement"] = language_entitlement
        if prompt and not sc.get("c05s_compiled_positive") and not sc.get("visual_prompt"):
            sc.setdefault("visual_prompt", prompt)
        if exact_ai_video_prompt:
            sc.setdefault("continuity_final_prompt", exact_ai_video_prompt)

        preferred = "agnes" if (require_agnes or agnes_keys) and (
            str(sc.get("visual_mode") or resolved_visual_mode or "").upper() == "VIDEO"
        ) else ""
        gp = build_generation_payload_from_scene(
            sc,
            job_id=job_id or work.name,
            scene_index=idx,
            narration=narration,
            product_name=product,
            element=element,
            niche=niche,
            preferred_provider=preferred,
            allow_fallback=allow_image_fallback,
            apply_harden=True,
            customer_id=customer_id or str(sc.get("customer_id") or ""),
            channel_id=channel_id or str(sc.get("channel_id") or ""),
            language_entitlement=language_entitlement or str(sc.get("language_entitlement") or ""),
        )
        ownership = validate_customer_ownership(
            payload=gp,
            expected_customer_id=customer_id or str(sc.get("customer_id") or ""),
            expected_channel_id=channel_id or str(sc.get("channel_id") or ""),
        )
        # Ownership enforced only when expected IDs are supplied by caller
        if (customer_id or channel_id) and ownership.get("blocked"):
            raise RuntimeError(
                f"C05-GX ownership fail-closed: {','.join(ownership.get('blocks') or [])}"
            )
        ready = assert_generation_payload_ready(gp)
        if gp.get("blocked") or ready.get("blocked"):
            reason = gp.get("reason") or ",".join(ready.get("blocks") or []) or "generation_payload_blocked"
            raise RuntimeError(f"C05-GP fail-closed before generation: {reason}")
        generation_payload_dict = dict(gp.get("payload") or {})
        # Beat materialization from optional multi-beat list on scene context
        beat_list = list(sc.get("c05s_visual_beats") or sc.get("visual_beats") or [])
        if not beat_list and sc.get("c05s_visual_beat_id"):
            beat_list = [
                {
                    "dialogue_id": sc.get("dialogue_id") or dialogue_id,
                    "beat_id": sc.get("c05s_visual_beat_id"),
                    "c05s_visual_beat_id": sc.get("c05s_visual_beat_id"),
                    "visual_mode": resolved_visual_mode,
                    "location": sc.get("location"),
                    "subject": sc.get("subject"),
                    "character_state": sc.get("character_state") or {},
                    "required_relationships": sc.get("required_relationships") or [],
                    "required_objects": sc.get("required_objects") or [],
                    "camera": sc.get("camera_intent"),
                    "lighting": sc.get("lighting_intent"),
                    "visual_timing": sc.get("visual_timing") or {},
                    "visual_coverage": sc.get("visual_coverage") or {},
                    "scene_id": sc.get("c05s_scene_id") or idx,
                }
            ]
        materialization_plan: Optional[Dict[str, Any]] = None
        if beat_list:
            from pipeline.generation_payload import (
                assert_beat_scene_binding,
                enrich_materialization_lineage,
            )

            bind = assert_beat_scene_binding(
                dialogue_id=str(generation_payload_dict.get("dialogue_id") or dialogue_id),
                beat_id=str(generation_payload_dict.get("beat_id") or sc.get("c05s_visual_beat_id") or ""),
                scene_id=generation_payload_dict.get("scene_id", idx),
                expected_dialogue_id=str(sc.get("dialogue_id") or dialogue_id or ""),
            )
            if bind.get("blocked"):
                raise RuntimeError(
                    f"C05-MR beat binding fail-closed: {','.join(bind.get('blocks') or [])}"
                )
            mat = materialize_visual_beats(
                beat_list,
                requested_mode=str(generation_payload_dict.get("requested_mode") or resolved_visual_mode),
            )
            if mat.get("blocked"):
                raise RuntimeError(f"C05-GX beat materialization blocked: {mat.get('reason')}")
            materialization_plan = mat
            units = enrich_materialization_lineage(
                mat.get("units") or [],
                generation_id=str(generation_payload_dict.get("generation_id") or ""),
                payload_fingerprint=str(
                    (generation_payload_dict.get("provenance") or {}).get("payload_fingerprint") or ""
                ),
                provider=str(generation_payload_dict.get("provider_name") or ""),
                requested_mode=str(generation_payload_dict.get("requested_mode") or ""),
                actual_mode=str(generation_payload_dict.get("actual_mode") or ""),
                fallback=bool(generation_payload_dict.get("fallback_used")),
                fallback_reason=str(generation_payload_dict.get("fallback_reason") or ""),
            )
            materialization_plan = {**mat, "units": units}
            try:
                (work / f"scene_{idx:02d}_beat_materialization.json").write_text(
                    json.dumps(materialization_plan, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception:
                pass
            generation_payload_dict["materialization"] = {
                "unique_assets": materialization_plan.get("unique_assets"),
                "unit_count": len(units),
                "binding": materialization_plan.get("binding"),
            }
        resolved_visual_mode = str(
            generation_payload_dict.get("actual_mode")
            or generation_payload_dict.get("visual_mode")
            or resolved_visual_mode
            or "VIDEO"
        )
        prompt = str(generation_payload_dict.get("provider_prompt") or prompt)
        # Provider-request integrity (request layer only)
        spec_preview = payload_to_visual_request_spec(generation_payload_dict)
        integrity = inspect_provider_request_integrity(
            intent=generation_payload_dict,
            canonical_prompt=str(generation_payload_dict.get("canonical_prompt") or ""),
            provider_prompt=prompt,
            provider_request={
                "dialogue_id": spec_preview.dialogue_id,
                "beat_id": (spec_preview.metadata or {}).get("beat_id"),
                "scene_id": spec_preview.scene_id,
                "visual_mode": (spec_preview.metadata or {}).get("visual_mode"),
                "metadata": spec_preview.metadata,
                "continuity_fingerprint": (spec_preview.metadata or {}).get("continuity_fingerprint"),
                "camera": (spec_preview.metadata or {}).get("camera"),
                "lighting": (spec_preview.metadata or {}).get("lighting"),
                "coverage": (spec_preview.metadata or {}).get("coverage"),
                "timing": (spec_preview.metadata or {}).get("timing"),
            },
        )
        exec_ready = assert_execution_ready(payload_result=gp, integrity=integrity, ownership=None)
        if exec_ready.get("blocked"):
            raise RuntimeError(
                f"C05-GX execution fail-closed: {','.join(exec_ready.get('blocks') or [])}"
            )
        try:
            (work / f"scene_{idx:02d}_generation_payload.json").write_text(
                json.dumps(
                    {
                        "payload": generation_payload_dict,
                        "inspect": inspect_generation_payload(gp),
                        "integrity": integrity,
                        "harden": gp.get("harden"),
                        "route": gp.get("route"),
                        "execution": record_execution_provenance(generation_payload_dict),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
    else:
        # Explicit legacy compatibility — do not invent a new semantic path
        from pipeline.generation_payload import scrub_secrets

        logger.info(
            "Scene %s: LEGACY_COMPAT generation path (no visual_mode) — canonical prompt preserved as string",
            idx,
        )
        try:
            (work / f"scene_{idx:02d}_legacy_compat.json").write_text(
                json.dumps(
                    scrub_secrets(
                        {
                            "legacy_compat": True,
                            "visual_mode": "",
                            "dialogue_id": dialogue_id,
                            "note": "no_mode_uses_explicit_legacy_adapter_not_silent_new_path",
                        }
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        prompt = harden_video_prompt(
            prompt,
            narration=narration,
            keywords=keywords,
            product_name=product,
            element=element,
            niche=niche,
            duration_sec=dur,
            prior_issues=prior_issues,
        )
    from pipeline.prompt_hardening import preflight_keyword_prompt

    preflight = preflight_keyword_prompt(
        prompt, keywords=keywords, narration=narration, product_name=product
    )
    (work / f"scene_{idx:02d}_keyword_preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not preflight.get("passed"):
        logger.info(
            "Scene %s keyword preflight missing %s — injecting before Agnes",
            idx,
            preflight.get("missing"),
        )
        prompt = str(preflight.get("fixed_prompt") or prompt)
        if generation_payload_dict:
            from pipeline.generation_payload import sync_provider_prompt_after_mutation

            synced = sync_provider_prompt_after_mutation(
                {"payload": generation_payload_dict},
                new_provider_prompt=prompt,
                scene=dict(scene_context or {}),
            )
            if synced.get("blocked"):
                raise RuntimeError(
                    "C05-GX fail-closed: preflight mutation destroyed canonical semantics"
                )
            generation_payload_dict = dict(synced.get("payload") or generation_payload_dict)
            prompt = str(generation_payload_dict.get("provider_prompt") or prompt)

    # PRE-CHECK: optional Gemini rewrite. Default OFF — harden_video_prompt already
    # injects history rules (saves Gemini). Set AMP_FORCE_PRECHECK=1 to enable.
    if keys and not skip_av_critic and os.environ.get("AMP_FORCE_PRECHECK", "").strip() == "1":
        from pipeline.quota_backoff import is_quota_error, record_quota_hit

        pre = precheck_generation_prompt(
            narration_bn=narration,
            exact_ai_video_prompt=prompt,
            keyword_triggers=keywords,
            niche=niche,
            element=element,
            product_name=product,
            google_api_keys=keys,
            video_type=("short" if "x" in size and int(size.split("x")[1]) > int(size.split("x")[0]) else "long"),
        )
        (work / f"scene_{idx:02d}_precheck.json").write_text(
            json.dumps(pre, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if any(is_quota_error(x) for x in (pre.get("issues") or [])):
            record_quota_hit("google")
        if not pre.get("passed"):
            fixed = str(pre.get("fixed_prompt") or "").strip()
            if fixed and "RESOURCE_EXHAUSTED" not in fixed:
                logger.info(
                    "Scene %s precheck FAILED score=%s — applying fixed prompt before Agnes",
                    idx,
                    pre.get("prompt_score"),
                )
                prompt = harden_video_prompt(
                    fixed,
                    narration=narration,
                    keywords=keywords,
                    product_name=product,
                    element=element,
                    niche=niche,
                    duration_sec=dur,
                    prior_issues=prior_issues,
                )
            else:
                logger.warning("Scene %s precheck failed but no usable fixed_prompt", idx)
        else:
            logger.info("Scene %s precheck passed score=%s", idx, pre.get("prompt_score"))
    else:
        logger.info(
            "Scene %s: Gemini precheck skipped (harden-only, API save). "
            "Set AMP_FORCE_PRECHECK=1 to enable.",
            idx,
        )

    # Documentary stills ONLY for engine-authorized IMAGE / IMAGE_WITH_MOTION beats.
    # NEVER short-circuit Agnes VIDEO beats with pre-Agnes NASA/ESA stills.
    _mode_u = (resolved_visual_mode or "").strip().upper()
    _image_mode = _mode_u in ("IMAGE", "IMAGE_WITH_MOTION")
    if (
        allow_image_fallback
        and _image_mode
        and not require_agnes
        and (pollinations_key or keys)
    ):
        try:
            from pipeline.fallback_image_video import (
                build_reference_still_video,
                select_documentary_reference_url,
            )
            from pipeline.media_mode_engine import authorize_image_path

            auth = authorize_image_path(
                visual_mode=_mode_u,
                image_authorized=True,
                allow_image_fallback=allow_image_fallback,
                decision_reason="image_mode_pre_still",
            )
            if not auth.get("allowed"):
                raise RuntimeError(auth.get("reason") or "image_path_unauthorized")

            early_url = select_documentary_reference_url(
                product_name=product,
                keywords=keywords,
                narration=narration,
            )
            # Accept curated public still hosts (NASA + ESA). Prior bug: only Webb/STScI
            # URLs short-circuited, so lunar rover/ice stills on images-assets.nasa.gov
            # never ran pre-Agnes and Pollinations invented off-subject nebula/rocks.
            _DOC_HOSTS = (
                "esawebb.org",
                "esahubble.org",
                "STScI-01G1Q6",
                "assets.science.nasa.gov",
                "images-assets.nasa.gov",
            )
            if early_url and any(h in early_url for h in _DOC_HOSTS):
                early_audio = narration_audio if narration_audio and Path(narration_audio).exists() else None
                early_out = work / f"scene_{idx:02d}_{element}_docref.mp4"
                build_reference_still_video(
                    work=work / f"_docref_early_{idx}",
                    out_path=early_out,
                    narration=narration,
                    duration=dur,
                    size=size,
                    audio_path=early_audio,
                    keywords=keywords,
                    product_name=product,
                )
                if early_out.exists() and early_out.stat().st_size > 8000:
                    shutil.copy2(early_out, target)
                    if not skip_av_critic and keys:
                        early_c = critique_scene_clip(
                            video_path=target,
                            audio_path=Path(early_audio) if early_audio else target,
                            narration_bn=narration,
                            keyword_triggers=keywords,
                            exact_ai_video_prompt=prompt,
                            niche=niche,
                            element=element,
                            google_api_keys=keys,
                            product_name=product,
                        )
                        persist_critique(work, idx, 0, early_c, prompt)
                        from pipeline.av_quality_gates import soften_documentary_proxy_critique

                        early_c = soften_documentary_proxy_critique(
                            early_c,
                            narration=narration,
                            product_name=product,
                            keywords=keywords,
                        )
                        early_hard = set(early_c.get("critical_issues") or []) & {
                            "wrong_subject",
                            "unrelated_broll",
                            "talking_head",
                            "visual_anchors_missing",
                        }
                        if "visual_anchors_missing" in early_hard:
                            from pipeline.av_quality_gates import is_unshippable

                            if not is_unshippable(
                                {
                                    **early_c,
                                    "critical_issues": ["visual_anchors_missing"],
                                }
                            ):
                                early_hard.discard("visual_anchors_missing")
                        # Curated NASA/ESA stills: accept when no remaining hard visual fails
                        # (do not require LLM passed=True — soft issues like static_image are OK)
                        if not early_hard:
                            (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                                "documentary_reference_still_pre_agnes\n",
                                encoding="utf-8",
                            )
                            logger.info(
                                "Scene %s: documentary reference accepted pre-Agnes score=%s",
                                idx,
                                early_c.get("match_score"),
                            )
                            return target
                        logger.warning(
                            "Scene %s: pre-Agnes documentary still rejected hits=%s score=%s",
                            idx,
                            sorted(early_hard),
                            early_c.get("match_score"),
                        )
                    else:
                        (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                            "documentary_reference_still_pre_agnes_no_critic\n",
                            encoding="utf-8",
                        )
                        return target
        except Exception as early_doc_exc:
            logger.warning("Scene %s: pre-Agnes documentary still failed: %s", idx, early_doc_exc)

    # Prefer one clean take + at most one hard-gate regen (not 3× soft critic loops)
    max_attempts = 1 + max(0, min(1, int(max_av_retries)))
    best_score = -1
    best_target: Optional[Path] = None
    best_critique: Optional[Dict[str, Any]] = None
    last_critique: Optional[Dict[str, Any]] = None

    for attempt in range(1, max_attempts + 1):
        attempt_prompt = prompt
        video_src = _resolve_footage(
            work=work,
            idx=idx,
            product_name=product,
            visual_query=visual_query,
            visual_prompt=visual_prompt,
            element=element,
            duration=dur,
            size=size,
            pexels_api=pexels_api,
            pollinations_key=pollinations_key,
            agnes_api=agnes_keys[0] if agnes_keys else "",
            agnes_api_keys=agnes_keys,
            google_api_keys=keys,
            narration_hint=narration,
            require_agnes=require_agnes,
            override_prompt=attempt_prompt,
            niche=niche,
            keyword_triggers=keywords,
            attempt=attempt,
            allow_image_fallback=allow_image_fallback,
            narration_audio=narration_audio,
            job_id=job_id,
            dialogue_id=dialogue_id,
            canonical_scene_id=canonical_scene_id,
            script_id=script_id,
            visual_mode=resolved_visual_mode,
            generation_payload=generation_payload_dict,
        )

        attempt_target = work / f"scene_{idx:02d}_{element}_a{attempt}.mp4"
        _mux_scene(
            video_src=video_src,
            narration_audio=narration_audio or video_src,
            dest=attempt_target,
            duration=dur,
            size=size,
            subtitle_text=subtitle_text,
            subtitle_lang="en",
            keep_source_audio=prefer_agnes_native_audio,
            work=work,
            scene_id=str(idx),
            dialogue_id=str(dialogue_id or f"scene-{idx:02d}"),
        )

        # Issue-1 gate: detect truncated dialogue on the UNPADDED mux.
        # Tail-pad silence must NOT run before this check — it hides cutoffs.
        from pipeline.av_quality_gates import apply_gates_to_critique, detect_dialogue_cutoff
        from pipeline.av_self_repair_agent import diagnose_clip, run_av_self_repair_agent

        cutoff_gate = detect_dialogue_cutoff(
            attempt_target if attempt_target.exists() else video_src,
            narration_text=narration,
            lang="en",
        )
        # Also probe raw Agnes source (stronger signal before any remux)
        src_gate = detect_dialogue_cutoff(video_src, narration_text=narration, lang="en")
        if not src_gate.get("passed", True):
            cutoff_gate = src_gate

        hold_gate: Dict[str, Any] = {
            "check": "tail_hold",
            "passed": True,
            "issues": [],
            "critical_issues": [],
        }
        pace_gate: Dict[str, Any] = {"check": "speech_pace", "passed": True, "issues": [], "critical_issues": []}
        last_word_gate: Dict[str, Any] = {
            "check": "last_word_integrity",
            "passed": True,
            "issues": [],
            "critical_issues": [],
        }

        # Autonomous agent (history playbook): diagnose + setpts/TTS audio repair.
        # Audio pass is NEVER a visual pass — Gemini critic still runs unless
        # AMP_SKIP_GEMINI_CRITIC=1 AND visual-anchor heuristic also passed.
        if keys and attempt_target.exists():
            from pipeline.agent_playbook import should_force_tts

            agent_dest = work / f"scene_{idx:02d}_{element}_agent_fixed.mp4"
            pre = diagnose_clip(
                attempt_target,
                narration=narration,
                lang="en",
                prompt=attempt_prompt,
                product_name=product,
                keywords=keywords,
                work=work,
                idx=idx,
            )
            agent_report = run_av_self_repair_agent(
                media=attempt_target,
                video_src=video_src if video_src.exists() else attempt_target,
                dest=agent_dest,
                narration=narration,
                google_api_keys=keys,
                work=work,
                idx=idx,
                prompt=attempt_prompt,
                product_name=product,
                keywords=keywords,
                force_tts_clarity=should_force_tts(
                    prefer_agnes_native=bool(prefer_agnes_native_audio),
                    pre_diagnosis=pre,
                ),
            )
            if agent_dest.exists() and (
                agent_report.get("passed")
                or agent_report.get("steps")
                or not pre.get("passed")
            ):
                shutil.copy2(agent_dest, attempt_target)
                shutil.copy2(agent_dest, target)
                # Prefer agent master for localization
                unpadded = work / f"scene_{idx:02d}_{element}_unpadded.mp4"
                try:
                    shutil.copy2(agent_dest, unpadded)
                except Exception:
                    pass
                cutoff_gate = detect_dialogue_cutoff(
                    attempt_target, narration_text=narration, lang="en"
                )
                from pipeline.av_quality_gates import (
                    detect_black_tail,
                    detect_end_freeze,
                    detect_last_word_integrity,
                    detect_speech_pace,
                    detect_tail_hold,
                )

                hold_gate = detect_tail_hold(attempt_target)
                pace_gate = detect_speech_pace(
                    attempt_target, narration_text=narration, lang="en"
                )
                last_word_gate = detect_last_word_integrity(
                    attempt_target, narration_text=narration
                )
                black_gate = detect_black_tail(attempt_target)
                freeze_gate = detect_end_freeze(attempt_target)
                if agent_report.get("passed"):
                    from pipeline.agent_playbook import should_skip_gemini_critic
                    from pipeline.av_quality_gates import detect_visual_anchor_lock

                    vis = detect_visual_anchor_lock(
                        prompt=attempt_prompt,
                        product_name=product,
                        keywords=keywords,
                        narration=narration,
                    )
                    persist_critique(
                        work,
                        idx,
                        attempt,
                        apply_gates_to_critique(
                            {
                                "passed": bool(should_skip_gemini_critic(
                                    agent_report, visual_passed=bool(vis.get("passed"))
                                )),
                                "match_score": 88 if vis.get("passed") else 55,
                                "issues": ["av_self_repair_agent_ok"]
                                + (
                                    ["gemini_critic_skipped_cost_save"]
                                    if should_skip_gemini_critic(
                                        agent_report, visual_passed=bool(vis.get("passed"))
                                    )
                                    else ["visual_critic_still_required"]
                                ),
                                "critical_issues": list(vis.get("critical_issues") or []),
                                "repair": agent_report.get("steps"),
                                "raw": {
                                    "agent_only": True,
                                    "audio_passed": True,
                                    "visual_heuristic_passed": bool(vis.get("passed")),
                                    "skip_gemini_critic": should_skip_gemini_critic(
                                        agent_report, visual_passed=bool(vis.get("passed"))
                                    ),
                                },
                            },
                            [
                                cutoff_gate,
                                hold_gate,
                                pace_gate,
                                last_word_gate,
                                black_gate,
                                freeze_gate,
                                vis,
                            ],
                        ),
                        attempt_prompt,
                    )
                    if should_skip_gemini_critic(
                        agent_report, visual_passed=bool(vis.get("passed"))
                    ):
                        logger.info(
                            "Scene %s: AV+visual heuristic PASSED — skipping Gemini critic (opt-in)",
                            idx,
                        )
                        return target
                    logger.info(
                        "Scene %s: AV self-repair audio OK — continuing to visual critic "
                        "(audio pass ≠ visual pass)",
                        idx,
                    )
            elif prefer_agnes_native_audio and cutoff_gate.get("passed", True):
                # Agent could not run (no keys / TTS fail) — legacy pad path
                unpadded = work / f"scene_{idx:02d}_{element}_unpadded.mp4"
                try:
                    import shutil as _sh

                    _sh.copy2(attempt_target, unpadded)
                except Exception:
                    pass
                pad_av_tail(attempt_target, attempt_target, DIALOGUE_TAIL_PAD_SEC)
                from pipeline.av_quality_gates import detect_tail_hold

                hold_gate = detect_tail_hold(attempt_target)
        elif prefer_agnes_native_audio and attempt_target.exists() and cutoff_gate.get("passed", True):
            unpadded = work / f"scene_{idx:02d}_{element}_unpadded.mp4"
            try:
                import shutil as _sh

                _sh.copy2(attempt_target, unpadded)
            except Exception:
                pass
            pad_av_tail(attempt_target, attempt_target, DIALOGUE_TAIL_PAD_SEC)
            from pipeline.av_quality_gates import detect_tail_hold

            hold_gate = detect_tail_hold(attempt_target)
            if not hold_gate.get("passed", True):
                logger.warning("Scene %s missing tail hold after pad: %s", idx, hold_gate.get("issues"))
                pad_av_tail(attempt_target, attempt_target, DIALOGUE_TAIL_PAD_SEC)
                hold_gate = detect_tail_hold(attempt_target)
        elif prefer_agnes_native_audio and not cutoff_gate.get("passed", True):
            logger.warning(
                "Scene %s attempt %s dialogue_cutoff detected — no keys for agent repair: %s",
                idx,
                attempt,
                cutoff_gate.get("issues"),
            )
            dur = min(AGNES_AUDIO_CHUNK_MAX, max(dur + 1.0, estimate_spoken_seconds(narration) + 0.75))

        (work / f"scene_{idx:02d}_source.txt").write_text(
            f"product={product}\nelement={element}\nsource={video_src.name}\n"
            f"attempt={attempt}\nnative_agnes_audio={prefer_agnes_native_audio}\n"
            f"prompt={attempt_prompt[:500]}\n",
            encoding="utf-8",
        )

        # For critic: use TTS file if present, else extract Agnes audio
        critic_audio = narration_audio if (narration_audio and Path(narration_audio).exists() and not prefer_agnes_native_audio) else None
        if critic_audio is None:
            critic_audio = work / f"scene_{idx:02d}_{element}_a{attempt}_audio.m4a"
            _extract_audio_track(attempt_target, critic_audio)

        from pipeline.av_quality_gates import (
            HARD_QUALITY_GATES,
            detect_english_master_narration,
            detect_visual_anchor_lock,
        )

        vis_local = detect_visual_anchor_lock(
            prompt=attempt_prompt,
            product_name=product,
            keywords=keywords,
            narration=narration,
        )
        eng_local = detect_english_master_narration(narration, lang="en")

        if skip_av_critic or not keys:
            critique = {
                "skipped": True,
                "passed": True,
                "match_score": 70,
                "issues": ["critic_skipped_local_gates"],
                "critical_issues": [],
                "raw": {"local_gates_only": True},
            }
        else:
            critique = critique_scene_clip(
                video_path=attempt_target,
                audio_path=critic_audio,
                narration_bn=narration,
                keyword_triggers=keywords,
                exact_ai_video_prompt=attempt_prompt,
                niche=niche,
                element=element,
                google_api_keys=keys,
                product_name=product,
            )
        critique = apply_gates_to_critique(
            critique,
            [cutoff_gate, hold_gate, pace_gate, last_word_gate, vis_local, eng_local],
        )
        from pipeline.av_quality_gates import promote_missed_visual_keywords, soften_documentary_proxy_critique

        critique = promote_missed_visual_keywords(
            critique, keywords=keywords, product_name=product
        )
        critique = soften_documentary_proxy_critique(
            critique, narration=narration, product_name=product, keywords=keywords
        )
        # Duration + embedded AV length (post-pad master)
        from pipeline.av_quality_gates import detect_av_length_match, detect_duration_window

        if attempt_target.exists() and cutoff_gate.get("passed", True):
            critique = apply_gates_to_critique(
                critique,
                [
                    detect_duration_window(attempt_target, label=f"scene_{idx}"),
                    detect_av_length_match(attempt_target, critic_audio if critic_audio and Path(critic_audio).exists() else None),
                ],
            )
        # Hard duration audit on Agnes SOURCE (before loop-mux hides the problem)
        src_dur = ffprobe_duration(video_src)
        mismatch = duration_mismatch_issue(dur, src_dur)
        if mismatch:
            critique.setdefault("issues", []).append(mismatch)
            critique.setdefault("critical_issues", []).append("duration_mismatch")
            critique["passed"] = False
            critique["match_score"] = min(int(critique.get("match_score") or 50), 55)
            # Force split rebuild once if long audio was not split
            if dur > AGNES_AUDIO_CHUNK_MAX + 0.35 and attempt == 1 and require_agnes and agnes_keys:
                logger.warning(
                    "Scene %s duration_mismatch detected — switching to split pipeline",
                    idx,
                )
                na = narration_audio
                if not na or not Path(na).exists():
                    na = work / f"scene_{idx:02d}_dur_placeholder.m4a"
                    _write_silent_audio(na, max(AGNES_AUDIO_CHUNK_MAX * 2, estimate_spoken_seconds(narration)))
                return _build_split_dialogue_clip(
                    work=work,
                    idx=idx,
                    narration_audio=na,
                    narration=narration,
                    visual_query=visual_query,
                    visual_prompt=visual_prompt,
                    exact_ai_video_prompt=prompt,
                    element=element,
                    size=size,
                    product_name=product,
                    agnes_api=agnes_keys[0] if agnes_keys else "",
                    agnes_api_keys=agnes_keys,
                    google_api_keys=keys,
                    keyword_triggers=keywords,
                    niche=niche,
                    max_av_retries=max_av_retries,
                    skip_av_critic=skip_av_critic,
                    pexels_api=pexels_api,
                    pollinations_key=pollinations_key,
                    require_agnes=require_agnes,
                    prefer_agnes_native_audio=prefer_agnes_native_audio,
                    allow_image_fallback=allow_image_fallback,
                    job_id=job_id,
                    dialogue_id=dialogue_id,
                    canonical_scene_id=canonical_scene_id,
                    script_id=script_id,
                )
        # Critic outage/quota: keep clip immediately
        if (critique.get("raw") or {}).get("fallback") and "critic_api_failed" in str(
            (critique.get("issues") or [""])[0]
        ):
            logger.warning(
                "Scene %s critic unavailable/quota — keeping clip without re-critique", idx
            )
            from pipeline.quota_backoff import record_quota_hit

            record_quota_hit("google")

        persist_critique(work, idx, attempt, critique, attempt_prompt)
        last_critique = critique
        score = int(critique.get("match_score") or 0)
        logger.info(
            "Scene %s AV critic attempt %s: score=%s passed=%s issues=%s",
            idx,
            attempt,
            score,
            critique.get("passed"),
            critique.get("issues"),
        )

        if score > best_score and attempt_target.exists():
            best_score = score
            best_target = attempt_target
            best_critique = critique

        if critique.get("passed"):
            shutil.copy2(attempt_target, target)
            return target

        # Hard gate: never accept clips that fail deterministic quality gates,
        # even when the LLM critic is on quota outage / soft fallback.
        from pipeline.av_quality_gates import HARD_QUALITY_GATES, detect_tail_hold

        hard_gates = set(critique.get("critical_issues") or [])
        hard_hit = hard_gates & HARD_QUALITY_GATES
        if "dialogue_cutoff" in hard_hit or "speech_pace_too_fast" in hard_hit or "speech_pace_too_slow" in hard_hit or "last_word_incomplete" in hard_hit:
            logger.warning(
                "Scene %s: dialogue/pace hard-fail %s — agent TTS repair then maybe Agnes regen (dur→%.2fs)",
                idx,
                sorted(hard_hit),
                dur,
            )
            from pipeline.av_sync_critic import apply_training_rule

            apply_training_rule(
                "Finish every spoken word at steady documentary pace; leave silence only after last syllable; keep pitch consistent across clips.",
                source=f"scene_{idx}_pace_or_cutoff",
            )
            issue_cache.write_text(
                json.dumps(sorted(set(prior_issues + list(hard_hit))), ensure_ascii=False),
                encoding="utf-8",
            )
            if keys and attempt_target.exists():
                from pipeline.av_self_repair_agent import run_av_self_repair_agent

                repaired = work / f"scene_{idx:02d}_{element}_hard_agent_a{attempt}.mp4"
                agent_report = run_av_self_repair_agent(
                    media=attempt_target,
                    video_src=video_src if video_src.exists() else attempt_target,
                    dest=repaired,
                    narration=narration,
                    google_api_keys=keys,
                    work=work,
                    idx=idx,
                    prompt=attempt_prompt,
                    product_name=product,
                    keywords=keywords,
                    force_tts_clarity=True,
                )
                if repaired.exists() and agent_report.get("passed") and not agent_report.get("needs_visual_regen"):
                    visual_hard = set(critique.get("critical_issues") or []) & {
                        "wrong_subject",
                        "unrelated_broll",
                        "talking_head",
                        "visual_anchors_missing",
                    }
                    if visual_hard:
                        logger.warning(
                            "Scene %s: audio gates repaired but visual hard %s — not accepting",
                            idx,
                            sorted(visual_hard),
                        )
                        attempt_target = repaired
                    else:
                        shutil.copy2(repaired, target)
                        persist_critique(work, idx, attempt, critique, attempt_prompt)
                        logger.info("Scene %s: hard pace/cutoff repaired by AV agent", idx)
                        return target
            revised = str(critique.get("revised_prompt") or prompt).strip()
            if attempt < max_attempts:
                prompt = (
                    f"{revised[:700]} Finish EVERY spoken word completely before the clip ends. "
                    f"Speak at steady documentary pace. Leave silence only AFTER the last syllable. Duration ~{dur:.1f}s."
                )[:900]
                continue
            # fall through — image fallback / best keep
        elif "missing_tail_hold" in hard_hit and attempt_target.exists():
            from pipeline.av_sync_critic import apply_training_rule

            apply_training_rule(
                "After dialogue ends, hold final frame with ~1s silence before cut.",
                source=f"scene_{idx}_tail",
            )
            pad_av_tail(attempt_target, attempt_target, DIALOGUE_TAIL_PAD_SEC)
            hold_gate = detect_tail_hold(attempt_target)
            critique = apply_gates_to_critique(critique, [hold_gate])
            if hold_gate.get("passed", True):
                shutil.copy2(attempt_target, target)
                persist_critique(work, idx, attempt, critique, attempt_prompt)
                return target

        # Soft critic fail with decent score: do NOT burn another Agnes call
        # BUT never soft-accept hard dialogue/pace/visual-subject faults
        visual_hard = hard_gates & {
            "wrong_subject",
            "unrelated_broll",
            "talking_head",
            "visual_anchors_missing",
        }
        if (
            not hard_hit
            and not visual_hard
            and score >= 70
            and attempt_target.exists()
            and not critique.get("passed")
            and not (critique.get("raw") or {}).get("fallback")
        ):
            logger.info(
                "Scene %s: soft-fail score=%s — keeping take (skip Agnes regen to save quota)",
                idx,
                score,
            )
            shutil.copy2(attempt_target, target)
            return target

        # Text-only critic (Google circuit open): keep when local hard gates are clean
        if (
            not hard_hit
            and attempt_target.exists()
            and (
                (critique.get("raw") or {}).get("_text_only")
                or str((critique.get("raw") or {}).get("_provider") or "").startswith("text_router:")
            )
        ):
            logger.info(
                "Scene %s: text-only critic — keeping take; local gates are authority",
                idx,
            )
            shutil.copy2(attempt_target, target)
            return target

        # Critic outage: keep only sparingly — majority outage fails the master gate.
        # google_circuit_open / local_gates_only must NOT write CRITIC_OUTAGE (routed elsewhere).
        if (critique.get("raw") or {}).get("fallback") and not hard_hit:
            reason = str((critique.get("raw") or {}).get("reason") or "")
            if reason == "google_circuit_open" or (critique.get("raw") or {}).get("local_gates_only"):
                logger.warning(
                    "Scene %s: critic degraded (%s) — keeping on local gates",
                    idx,
                    reason or "local_gates_only",
                )
                shutil.copy2(attempt_target, target)
                return target
            outage_n = len(list(work.glob("scene_*_CRITIC_OUTAGE.txt")))
            # Allow a few early outages; stop soft-keeping once risk of majority
            scene_total_hint = max(idx + 1, 8)
            if outage_n >= max(3, scene_total_hint // 4):
                logger.error(
                    "Scene %s: critic outage quota exceeded (%s) — failing scene for retry",
                    idx,
                    outage_n,
                )
                (work / f"scene_{idx:02d}_CRITIC_OUTAGE.txt").write_text(
                    json.dumps({**critique, "abort_quota": True, "outage_n": outage_n}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                raise RuntimeError(f"critic_outage_quota:{outage_n}")
            logger.warning(
                "Scene %s: critic outage fallback — keeping clip without Agnes regen "
                "(deterministic agent already ran earlier) outage_n=%s",
                idx,
                outage_n,
            )
            shutil.copy2(attempt_target, target)
            (work / f"scene_{idx:02d}_CRITIC_OUTAGE.txt").write_text(
                json.dumps(critique, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return target

        revised = str(critique.get("revised_prompt") or "").strip()
        # Strip quota noise from revised prompts
        if "RESOURCE_EXHAUSTED" in revised or "critic_api_failed" in revised:
            revised = _clean_revised_prompt(revised, attempt_prompt, keywords, product, narration)
        # Only one prompt-revision regen, and only for hard/critical visual fails
        critical_soft = set(critique.get("critical_issues") or []) & {
            "wrong_subject",
            "unrelated_broll",
            "talking_head",
            "visual_anchors_missing",
        }
        if revised and attempt < max_attempts and (hard_hit or critical_soft):
            prompt = revised[:900]
            logger.info("Scene %s: regenerating with revised Agnes prompt (attempt %s)", idx, attempt + 1)
            continue
        break

    # Keep best attempt — if still cutoff and image fallback allowed, try Ken Burns once
    chosen = best_target or target
    if best_target and best_target.exists():
        shutil.copy2(best_target, target)
        chosen = target

    fail_note = best_critique or last_critique or {}
    hard_left = set(fail_note.get("critical_issues") or [])
    visual_fail = bool(
        hard_left
        & {
            "wrong_subject",
            "unrelated_broll",
            "talking_head",
            "visual_anchors_missing",
        }
    )
    if (
        allow_image_fallback
        and ("dialogue_cutoff" in hard_left or visual_fail)
        and (pollinations_key or keys)
    ):
        try:
            from pipeline.prompt_engineering import resolve_visual_subject
            from pipeline.fallback_image_video import (
                build_image_video_fallback,
                build_reference_still_video,
                select_documentary_reference_url,
            )

            kb_product = resolve_visual_subject(
                product,
                keywords,
                narration,
            )
            kb_base = str(fail_note.get("revised_prompt") or prompt or "").strip() or prompt
            fb_audio = narration_audio
            if (not fb_audio or not Path(fb_audio).exists()) and best_target and best_target.exists():
                fb_audio = work / f"scene_{idx:02d}_fallback_audio.m4a"
                _extract_audio_track(best_target, fb_audio)

            # Prefer subject-matched public documentary stills before AI invent
            try:
                ref_url = select_documentary_reference_url(
                    product_name=kb_product,
                    keywords=keywords,
                    narration=narration,
                )
                if ref_url and "GSFC_20171208_Archive_e001435" not in ref_url:
                    ref_out = work / f"agnes_{idx:02d}_{element}_refstill.mp4"
                    build_reference_still_video(
                        work=work / f"_fallback_ref_{idx}",
                        out_path=ref_out,
                        narration=narration,
                        duration=dur,
                        size=size,
                        audio_path=fb_audio if fb_audio and Path(fb_audio).exists() else None,
                        keywords=keywords,
                        product_name=kb_product,
                    )
                    if ref_out.exists() and ref_out.stat().st_size > 8000:
                        shutil.copy2(ref_out, target)
                        ref_audio = fb_audio if fb_audio and Path(fb_audio).exists() else narration_audio
                        ref_c = critique_scene_clip(
                            video_path=target,
                            audio_path=Path(ref_audio) if ref_audio and Path(str(ref_audio)).exists() else target,
                            narration_bn=narration,
                            keyword_triggers=keywords,
                            exact_ai_video_prompt=kb_base,
                            niche=niche,
                            element=element,
                            google_api_keys=keys,
                            product_name=kb_product,
                        )
                        persist_critique(work, idx, max(attempt, 1), ref_c, kb_base)
                        from pipeline.av_quality_gates import soften_documentary_proxy_critique

                        ref_c = soften_documentary_proxy_critique(
                            ref_c,
                            narration=narration,
                            product_name=kb_product,
                            keywords=keywords,
                        )
                        ref_hard = set(ref_c.get("critical_issues") or []) & {
                            "wrong_subject",
                            "unrelated_broll",
                            "talking_head",
                            "visual_anchors_missing",
                        }
                        if "visual_anchors_missing" in ref_hard:
                            from pipeline.av_quality_gates import is_unshippable

                            if not is_unshippable(
                                {
                                    **ref_c,
                                    "critical_issues": ["visual_anchors_missing"],
                                }
                            ):
                                ref_hard.discard("visual_anchors_missing")
                        if not ref_hard:
                            (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                                "hard_fail → documentary_reference_still_first\n",
                                encoding="utf-8",
                            )
                            return target
                        fail_note = ref_c
                        hard_left = set(ref_c.get("critical_issues") or [])
                        logger.warning(
                            "Scene %s: early reference still rejected hits=%s score=%s",
                            idx,
                            sorted(ref_hard),
                            ref_c.get("match_score"),
                        )
            except Exception as early_ref_exc:
                logger.warning("Scene %s: early reference still failed: %s", idx, early_ref_exc)

            fb_out = work / f"agnes_{idx:02d}_{element}_fallback.mp4"
            logger.warning("Scene %s: Agnes cutoff persists — image Ken-Burns fallback", idx)
            build_image_video_fallback(
                work=work,
                out_path=fb_out,
                narration=narration,
                duration=dur,
                size=size,
                audio_path=fb_audio if fb_audio and Path(fb_audio).exists() else None,
                base_prompt=kb_base,
                keywords=keywords,
                product_name=kb_product,
                element=element,
                niche=niche,
                pollinations_key=pollinations_key,
                google_api_keys=keys,
            )
            if fb_out.exists() and fb_out.stat().st_size > 8000:
                shutil.copy2(fb_out, target)
                (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                    "hard_fail → image_kenburns\n", encoding="utf-8"
                )
                from pipeline.av_self_repair_agent import run_av_self_repair_agent

                fb_agent = work / f"scene_{idx:02d}_{element}_fb_agent.mp4"
                fb_report = run_av_self_repair_agent(
                    media=target,
                    video_src=target,
                    dest=fb_agent,
                    narration=narration,
                    google_api_keys=keys,
                    work=work,
                    idx=idx,
                    prompt=prompt,
                    product_name=product,
                    keywords=keywords,
                    force_tts_clarity=False,
                )
                if fb_agent.exists():
                    shutil.copy2(fb_agent, target)
                # INT-004: audio agent pass alone must NOT accept Ken Burns when the
                # prior critic already flagged talking_head / wrong_subject. Re-critique.
                if fb_report.get("passed") and not fb_report.get("needs_visual_regen"):
                    try:
                        kb_audio = fb_audio if fb_audio and Path(fb_audio).exists() else narration_audio
                        kb_critique = critique_scene_clip(
                            video_path=target,
                            audio_path=Path(kb_audio) if kb_audio and Path(str(kb_audio)).exists() else target,
                            narration_bn=narration,
                            keyword_triggers=keywords,
                            exact_ai_video_prompt=prompt,
                            niche=niche,
                            element=element,
                            google_api_keys=keys,
                            product_name=product,
                        )
                        persist_critique(work, idx, max(attempt, 1), kb_critique, prompt)
                        from pipeline.av_quality_gates import soften_documentary_proxy_critique

                        kb_critique = soften_documentary_proxy_critique(
                            kb_critique,
                            narration=narration,
                            product_name=product,
                            keywords=keywords,
                        )
                        kb_visual_hard = set(kb_critique.get("critical_issues") or []) & {
                            "wrong_subject",
                            "unrelated_broll",
                            "talking_head",
                            "visual_anchors_missing",
                        }
                        if kb_critique.get("passed") and not kb_visual_hard:
                            return target
                        fail_note = kb_critique
                        hard_left = set(kb_critique.get("critical_issues") or [])
                        logger.warning(
                            "Scene %s: Ken Burns rejected after re-critique hits=%s score=%s",
                            idx,
                            sorted(kb_visual_hard),
                            kb_critique.get("match_score"),
                        )
                        # One AI Ken Burns retry with critic revised prompt
                        retry_prompt = str(kb_critique.get("revised_prompt") or "").strip()
                        if retry_prompt and kb_visual_hard:
                            try:
                                fb_retry = work / f"agnes_{idx:02d}_{element}_fallback_r2.mp4"
                                build_image_video_fallback(
                                    work=work / f"_fallback_i2v_r2_{idx}",
                                    out_path=fb_retry,
                                    narration=narration,
                                    duration=dur,
                                    size=size,
                                    audio_path=fb_audio if fb_audio and Path(fb_audio).exists() else None,
                                    base_prompt=retry_prompt,
                                    keywords=keywords,
                                    product_name=kb_product,
                                    element=element,
                                    niche=niche,
                                    pollinations_key=pollinations_key,
                                    google_api_keys=keys,
                                )
                                if fb_retry.exists() and fb_retry.stat().st_size > 8000:
                                    shutil.copy2(fb_retry, target)
                                    kb_critique2 = critique_scene_clip(
                                        video_path=target,
                                        audio_path=Path(kb_audio) if kb_audio and Path(str(kb_audio)).exists() else target,
                                        narration_bn=narration,
                                        keyword_triggers=keywords,
                                        exact_ai_video_prompt=retry_prompt,
                                        niche=niche,
                                        element=element,
                                        google_api_keys=keys,
                                        product_name=kb_product,
                                    )
                                    persist_critique(work, idx, max(attempt, 1) + 1, kb_critique2, retry_prompt)
                                    kb_hard2 = set(kb_critique2.get("critical_issues") or []) & {
                                        "wrong_subject",
                                        "unrelated_broll",
                                        "talking_head",
                                        "visual_anchors_missing",
                                    }
                                    if kb_critique2.get("passed") and not kb_hard2:
                                        (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                                            "hard_fail → image_kenburns_r2\n", encoding="utf-8"
                                        )
                                        return target
                                    fail_note = kb_critique2
                                    hard_left = set(kb_critique2.get("critical_issues") or [])
                            except Exception as r2_exc:
                                logger.warning("Scene %s: Ken Burns r2 failed: %s", idx, r2_exc)
                        # Documentary reference still (NASA public assets) when AI invents wrong subject
                        if hard_left & {"wrong_subject", "unrelated_broll", "visual_anchors_missing", "talking_head"}:
                            try:
                                from pipeline.fallback_image_video import build_reference_still_video

                                ref_out = work / f"agnes_{idx:02d}_{element}_refstill.mp4"
                                build_reference_still_video(
                                    work=work / f"_fallback_ref_{idx}",
                                    out_path=ref_out,
                                    narration=narration,
                                    duration=dur,
                                    size=size,
                                    audio_path=fb_audio if fb_audio and Path(fb_audio).exists() else None,
                                    keywords=keywords,
                                    product_name=kb_product,
                                )
                                if ref_out.exists() and ref_out.stat().st_size > 8000:
                                    shutil.copy2(ref_out, target)
                                    ref_c = critique_scene_clip(
                                        video_path=target,
                                        audio_path=Path(kb_audio) if kb_audio and Path(str(kb_audio)).exists() else target,
                                        narration_bn=narration,
                                        keyword_triggers=keywords,
                                        exact_ai_video_prompt=str(fail_note.get("revised_prompt") or prompt),
                                        niche=niche,
                                        element=element,
                                        google_api_keys=keys,
                                        product_name=kb_product,
                                    )
                                    persist_critique(work, idx, max(attempt, 1) + 2, ref_c, prompt)
                                    ref_hard = set(ref_c.get("critical_issues") or []) & {
                                        "wrong_subject",
                                        "unrelated_broll",
                                        "talking_head",
                                        "visual_anchors_missing",
                                    }
                                    if ref_c.get("passed") and not ref_hard:
                                        (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                                            "hard_fail → documentary_reference_still\n", encoding="utf-8"
                                        )
                                        return target
                                    fail_note = ref_c
                                    hard_left = set(ref_c.get("critical_issues") or [])
                                    logger.warning(
                                        "Scene %s: reference still rejected hits=%s score=%s",
                                        idx,
                                        sorted(ref_hard),
                                        ref_c.get("match_score"),
                                    )
                            except Exception as ref_exc:
                                logger.warning("Scene %s: reference still failed: %s", idx, ref_exc)
                    except Exception as kb_exc:
                        logger.warning("Scene %s: Ken Burns re-critique failed: %s", idx, kb_exc)
                        fail_note = fail_note or last_critique or {}
                logger.warning(
                    "Scene %s: Ken Burns built but agent did not accept passed=%s hits=%s",
                    idx,
                    fb_report.get("passed"),
                    fb_report.get("final_hard_hits"),
                )
                # Final documentary reference still if visual hard fails remain
                rem = set((fail_note or {}).get("critical_issues") or hard_left or []) & {
                    "wrong_subject",
                    "unrelated_broll",
                    "talking_head",
                    "visual_anchors_missing",
                }
                if rem:
                    try:
                        from pipeline.fallback_image_video import build_reference_still_video
                        from pipeline.prompt_engineering import resolve_visual_subject as _rvs

                        ref_prod = _rvs(product, keywords, narration)
                        ref_out = work / f"agnes_{idx:02d}_{element}_refstill_final.mp4"
                        build_reference_still_video(
                            work=work / f"_fallback_ref_final_{idx}",
                            out_path=ref_out,
                            narration=narration,
                            duration=dur,
                            size=size,
                            audio_path=fb_audio if fb_audio and Path(fb_audio).exists() else None,
                            keywords=keywords,
                            product_name=ref_prod,
                        )
                        if ref_out.exists() and ref_out.stat().st_size > 8000:
                            shutil.copy2(ref_out, target)
                            ref_audio = fb_audio if fb_audio and Path(fb_audio).exists() else narration_audio
                            ref_c = critique_scene_clip(
                                video_path=target,
                                audio_path=Path(ref_audio) if ref_audio and Path(str(ref_audio)).exists() else target,
                                narration_bn=narration,
                                keyword_triggers=keywords,
                                exact_ai_video_prompt=str((fail_note or {}).get("revised_prompt") or prompt),
                                niche=niche,
                                element=element,
                                google_api_keys=keys,
                                product_name=ref_prod,
                            )
                            persist_critique(work, idx, max(attempt, 1) + 3, ref_c, prompt)
                            from pipeline.av_quality_gates import soften_documentary_proxy_critique

                            ref_c = soften_documentary_proxy_critique(
                                ref_c,
                                narration=narration,
                                product_name=ref_prod,
                                keywords=keywords,
                            )
                            ref_hard = set(ref_c.get("critical_issues") or []) & rem
                            if ref_c.get("passed") and not ref_hard:
                                (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").write_text(
                                    "hard_fail → documentary_reference_still_final\n",
                                    encoding="utf-8",
                                )
                                return target
                            fail_note = ref_c
                            hard_left = set(ref_c.get("critical_issues") or [])
                    except Exception as ref_final_exc:
                        logger.warning("Scene %s: final reference still failed: %s", idx, ref_final_exc)
        except Exception as exc:
            logger.warning("Scene %s image fallback failed: %s", idx, exc)

    from pipeline.av_quality_gates import is_unshippable, soften_documentary_proxy_critique

    fail_note = soften_documentary_proxy_critique(
        fail_note or {},
        narration=narration,
        product_name=product,
        keywords=keywords,
    )

    # Last-chance: stretch short TTS + pad duration before hard-failing the marathon
    crit = set(fail_note.get("critical_issues") or [])
    pace_or_dur = crit & {
        "speech_pace_too_fast",
        "last_word_incomplete",
        "duration_too_short",
    }
    if pace_or_dur and (chosen and Path(chosen).exists()):
        try:
            from pipeline.av_self_repair_agent import diagnose_clip, run_av_self_repair_agent

            last = work / f"scene_{idx:02d}_{element}_lastchance.mp4"
            rep = run_av_self_repair_agent(
                media=Path(chosen),
                video_src=Path(chosen),
                dest=last,
                narration=narration,
                google_api_keys=keys,
                work=work,
                idx=idx,
                prompt=prompt,
                product_name=product,
                keywords=keywords,
                force_tts_clarity=True,
            )
            cand = last if last.exists() else Path(chosen)
            dur_now = ffprobe_duration(cand)
            if dur_now < AGNES_MIN_SECONDS - 0.05:
                pad_av_tail(
                    cand,
                    cand,
                    max(0.5, AGNES_MIN_SECONDS - dur_now + 0.15),
                )
            post = diagnose_clip(
                cand,
                narration=narration,
                lang="en",
                prompt=prompt,
                product_name=product,
                keywords=keywords,
                work=work,
                idx=idx,
            )
            hard_left = set(post.get("hard_hits") or post.get("final_hard_hits") or [])
            if post.get("passed") or not (
                hard_left
                & {
                    "speech_pace_too_fast",
                    "last_word_incomplete",
                    "duration_too_short",
                    "dialogue_cutoff",
                }
            ):
                shutil.copy2(cand, target)
                logger.warning(
                    "Scene %s: last-chance pace/duration repair accepted hits=%s",
                    idx,
                    hard_left,
                )
                return target
            if rep.get("passed"):
                shutil.copy2(cand, target)
                return target
        except Exception as exc:
            logger.warning("Scene %s last-chance repair failed: %s", idx, exc)

    (work / f"scene_{idx:02d}_AV_FAIL.txt").write_text(
        json.dumps(
            {
                "best_score": best_score,
                "critique": fail_note,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # Hard-fail only on remaining unshippable gates. Low match_score alone must NOT
    # kill documentary beats after soften_documentary_proxy_critique (VIDEO-primary
    # sets allow_image_fallback=False + require_agnes — that previously blocked score<40
    # even when critical_issues were cleared).
    remaining_hard = [
        c
        for c in (fail_note.get("critical_issues") or [])
        if c
    ]
    if is_unshippable(fail_note):
        raise RuntimeError(
            f"Scene {idx} ({element}) AV sync failed hard (best_score={best_score}). "
            f"Issues: {fail_note.get('issues')} critical={fail_note.get('critical_issues')}"
        )
    if (
        require_agnes
        and best_score >= 0
        and best_score < 40
        and not allow_image_fallback
        and remaining_hard
        and not fail_note.get("documentary_proxy_softened")
    ):
        raise RuntimeError(
            f"Scene {idx} ({element}) AV sync failed hard (best_score={best_score}). "
            f"Issues: {fail_note.get('issues')} critical={fail_note.get('critical_issues')}"
        )
    logger.warning(
        "Scene %s: accepting best AV attempt score=%s after retries",
        idx,
        best_score,
    )
    try:
        fail_path = work / f"scene_{idx:02d}_AV_FAIL.txt"
        warn_path = work / f"scene_{idx:02d}_AV_WARN.txt"
        if fail_path.exists():
            fail_path.replace(warn_path)
    except Exception:
        pass
    return chosen if Path(chosen).exists() else target


def _build_split_dialogue_clip(
    *,
    work: Path,
    idx: int,
    narration_audio: Optional[Path] = None,
    narration: str,
    visual_query: str,
    visual_prompt: str,
    exact_ai_video_prompt: str,
    element: str,
    size: str,
    product_name: str,
    agnes_api: str,
    agnes_api_keys: Optional[List[str]] = None,
    google_api_keys: List[str],
    keyword_triggers: List[str],
    niche: str,
    max_av_retries: int,
    skip_av_critic: bool,
    pexels_api: str,
    pollinations_key: str,
    require_agnes: bool,
    prefer_agnes_native_audio: bool = True,
    allow_image_fallback: bool = True,
    job_id: str = "",
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
) -> Path:
    """
    When TTS > Agnes max: split dialogue audio into parts, generate matching
    Agnes clip per part (duration-matched), mux each with ITS audio, concat.
    NOTE: Agnes may return ambient audio — we keep native English AV when in sync;
    otherwise remux Charon English TTS. Bangla TTS is localization-only.
    """
    target = work / f"scene_{idx:02d}_{element}.mp4"
    total_dur = max(2.0, ffprobe_duration(narration_audio))
    segs = plan_agnes_segments(narration, total_dur, agnes_max=AGNES_AUDIO_CHUNK_MAX)
    n = len(segs)
    (work / f"scene_{idx:02d}_split_plan.json").write_text(
        json.dumps({"total_dur": total_dur, "segments": segs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Prefer splitting the already-generated master TTS (exact total length).
    # Optional per-part re-TTS is expensive and burns Google quota; only use when
    # CHERNOBYL_RE_TTS_PARTS=1 and keys are healthy.
    import os

    keys = google_api_keys or []
    agnes_keys: List[str] = []
    for k in agnes_api_keys or []:
        kk = (k or "").strip()
        if kk and kk not in agnes_keys:
            agnes_keys.append(kk)
    if (agnes_api or "").strip() and (agnes_api or "").strip() not in agnes_keys:
        agnes_keys.insert(0, (agnes_api or "").strip())
    part_dir = work / f"split_audio_{idx:02d}"
    part_dir.mkdir(parents=True, exist_ok=True)
    audio_parts: List[Path] = []
    want_re_tts = (os.environ.get("CHERNOBYL_RE_TTS_PARTS") or "").strip() in ("1", "true", "yes")

    if want_re_tts and keys:
        tts_ok = True
        for i, seg in enumerate(segs):
            part_narr = str(seg["narration_part"])
            part_base = part_dir / f"narr_tts_{i}"
            part_audio: Optional[Path] = None
            for ext in (".m4a", ".wav"):
                cand = part_base.with_suffix(ext)
                if cand.exists() and cand.stat().st_size > 800:
                    part_audio = cand
                    break
            if part_audio is None and tts_ok:
                try:
                    try:
                        from pipeline.idempotency.tts_bridge import idempotent_synthesize_narration

                        part_audio = idempotent_synthesize_narration(
                            work,
                            job_id=job_id or work.name,
                            scene_id=idx,
                            dialogue_text=part_narr,
                            out_path=part_base,
                            google_api_keys=keys,
                            voice_name="",
                            language_hint=SOURCE_LANG,
                            dialogue_id=f"split-{idx:02d}",
                            part_index=i + 1,
                            segment_id=f"seg-{i + 1:02d}",
                        )
                    except Exception:
                        from pipeline.tts_google import synthesize_narration

                        part_audio = synthesize_narration(
                            part_narr,
                            part_base,
                            google_api_keys=keys,
                            voice_name="",
                            language_hint=SOURCE_LANG,
                            idempotency_work_dir=work,
                            idempotency_job_id=job_id or work.name,
                            idempotency_scene_id=idx,
                            idempotency_dialogue_id=f"split-{idx:02d}",
                            idempotency_part_index=i + 1,
                            idempotency_segment_id=f"seg-{i + 1:02d}",
                        )
                except Exception as exc:
                    logger.warning(
                        "Part TTS failed (%s) — falling back to master audio split",
                        str(exc)[:120],
                    )
                    tts_ok = False
                    break
            if part_audio is not None:
                audio_parts.append(part_audio)
            else:
                tts_ok = False
                break
        if (not tts_ok) or len(audio_parts) != n:
            audio_parts = []

    if len(audio_parts) != n:
        # Proportional slices by narration char weight (closer to dialogue beats than equal time)
        weights = [max(1, len(str(s["narration_part"]))) for s in segs]
        wsum = float(sum(weights))
        starts = []
        acc = 0.0
        for w in weights:
            starts.append(acc)
            acc += total_dur * (w / wsum)
        audio_parts = []
        for i, seg in enumerate(segs):
            start = starts[i]
            length = (starts[i + 1] - start) if i + 1 < len(starts) else max(0.2, total_dur - start)
            out = part_dir / f"narr_{i}.m4a"
            cmd = [
                __import__("pipeline.compose", fromlist=["ffmpeg_bin"]).ffmpeg_bin(),
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(narration_audio),
                "-t",
                f"{length:.3f}",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out),
            ]
            import subprocess as _sp

            r = _sp.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not out.exists():
                # fallback equal split helper
                audio_parts = split_audio_file(
                    narration_audio, part_dir, n_parts=n, prefix="narr"
                )
                break
            audio_parts.append(out)
            logger.info(
                "Audio prop-split %s/%s start=%.2f len=%.2f → %s",
                i + 1,
                n,
                start,
                length,
                out.name,
            )

    part_clips: List[Path] = []
    prompt = exact_ai_video_prompt or visual_prompt or visual_query

    for i, seg in enumerate(segs):
        part_narr = str(seg["narration_part"])
        part_audio = audio_parts[i] if i < len(audio_parts) else narration_audio
        part_dur = max(
            AGNES_MIN_SECONDS,
            min(AGNES_AUDIO_CHUNK_MAX, ffprobe_duration(part_audio)),
        )
        part_prompt = (
            f"{prompt}. Spoken English dialogue part {i + 1}/{n} (keep ONE consistent male voice): "
            f"\"{part_narr[:200]}\". Visuals must match this narration beat. "
            f"Keep this beat under {AGNES_AUDIO_CHUNK_MAX:.0f} seconds spoken. "
            f"No burned text/watermark."
        )
        from pipeline.prompt_hardening import preflight_keyword_prompt

        part_pre = preflight_keyword_prompt(
            part_prompt,
            keywords=keyword_triggers,
            narration=part_narr,
            product_name=product_name,
        )
        part_prompt = str(part_pre.get("fixed_prompt") or part_prompt)
        (work / f"scene_{idx:02d}_p{i}_keyword_preflight.json").write_text(
            json.dumps(part_pre, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if keys and not skip_av_critic:
            pre = precheck_generation_prompt(
                narration_bn=part_narr,
                exact_ai_video_prompt=part_prompt,
                keyword_triggers=keyword_triggers,
                niche=niche,
                element=element,
                product_name=product_name,
                google_api_keys=keys,
                video_type=("short" if "x" in size and int(size.split("x")[1]) > int(size.split("x")[0]) else "long"),
            )
            (work / f"scene_{idx:02d}_p{i}_precheck.json").write_text(
                json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if not pre.get("passed") and pre.get("fixed_prompt"):
                part_prompt = str(pre["fixed_prompt"])

        best_part: Optional[Path] = None
        best_score = -1
        attempts = 1 + max(0, min(1, int(max_av_retries)))
        cur_prompt = part_prompt
        for attempt in range(1, attempts + 1):
            agnes_out = work / f"agnes_{idx:02d}_{element}_p{i}_a{attempt}.mp4"
            if agnes_out.exists() and attempt > 1:
                try:
                    agnes_out.unlink()
                except Exception:
                    pass
            src = None
            split_agnes_outcome = ""
            try:
                src, _agnes_beat_result = _resolve_split_agnes_beat_src(
                    work=work,
                    job_id=job_id or work.name,
                    idx=idx,
                    part_index=i + 1,
                    attempt=attempt,
                    product_name=product_name or "subject",
                    element=element,
                    visual_prompt=visual_prompt or visual_query,
                    visual_query=visual_query,
                    out_path=agnes_out,
                    narration_hint=part_narr,
                    size=size,
                    duration_hint=min(part_dur, AGNES_AUDIO_CHUNK_MAX),
                    override_prompt=cur_prompt,
                    niche=niche,
                    use_catalog_image=_should_use_catalog(niche, product_name),
                    dialogue_id=dialogue_id,
                    canonical_scene_id=canonical_scene_id,
                    script_id=script_id,
                    segment_id=f"seg-{i + 1:02d}",
                )
                from pipeline.idempotency.agnes_bridge import classify_agnes_beat_outcome

                split_agnes_outcome = classify_agnes_beat_outcome(_agnes_beat_result).value
            except Exception as exc:
                split_agnes_outcome = "EXCEPTION"
                logger.warning(
                    "Split Agnes canonical path failed scene=%s part=%s/%s: %s",
                    idx,
                    i + 1,
                    n,
                    exc,
                )
                src = None
            if not src or not src.exists():
                # HARD: never kill the whole short over one Agnes miss — image Ken Burns for this part
                logger.warning(
                    "Agnes miss scene %s part %s/%s — image fallback (outcome=%s, no hard fail)",
                    idx,
                    i + 1,
                    n,
                    split_agnes_outcome or "none",
                )
                try:
                    from pipeline.live_activity import log as live_log

                    live_log(
                        "media",
                        f"Agnes miss → image part {i + 1}/{n}",
                        api="agnes",
                        action="image_fallback",
                        scene=idx + 1,
                    )
                except Exception:
                    pass
                try:
                    src = _resolve_footage(
                        work=work,
                        idx=idx * 10 + i,
                        product_name=product_name or "subject",
                        visual_query=visual_query,
                        visual_prompt=visual_prompt or visual_query,
                        element=element,
                        duration=min(part_dur, AGNES_AUDIO_CHUNK_MAX),
                        size=size,
                        pexels_api=pexels_api,
                        pollinations_key=pollinations_key,
                        agnes_api="",
                        agnes_api_keys=[],
                        google_api_keys=keys,
                        narration_hint=part_narr,
                        require_agnes=False,
                        override_prompt=cur_prompt,
                        niche=niche,
                        keyword_triggers=keyword_triggers,
                        attempt=attempt,
                        allow_image_fallback=True,
                        narration_audio=part_audio,
                    )
                except Exception as fb_exc:
                    logger.warning("image fallback part failed: %s", fb_exc)
                    src = None
                if not src or not Path(src).exists():
                    continue
            # Duration hard-check on Agnes SOURCE (not muxed loop)
            src_dur = ffprobe_duration(src)
            mismatch = duration_mismatch_issue(part_dur, src_dur)
            mux = work / f"scene_{idx:02d}_{element}_p{i}_a{attempt}.mp4"
            _mux_scene(
                video_src=src,
                narration_audio=part_audio,
                dest=mux,
                duration=part_dur,
                size=size,
                subtitle_text="",
                subtitle_lang="en",
                keep_source_audio=False,  # TTS audio for fallback / consistency
            )
            persist_critique(
                work,
                idx * 10 + i,
                attempt,
                {"part": i, "src_dur": src_dur, "part_dur": part_dur, "mismatch": mismatch},
                cur_prompt,
            )
            if skip_av_critic or not keys:
                best_part = mux
                break
            critic_audio = part_audio
            if prefer_agnes_native_audio:
                critic_audio = work / f"scene_{idx:02d}_{element}_p{i}_a{attempt}_audio.m4a"
                _extract_audio_track(mux, critic_audio)
            critique = critique_scene_clip(
                video_path=mux,
                audio_path=critic_audio,
                narration_bn=part_narr,
                keyword_triggers=keyword_triggers,
                exact_ai_video_prompt=cur_prompt,
                niche=niche,
                element=element,
                google_api_keys=keys,
                product_name=product_name,
            )
            if mismatch:
                critique.setdefault("issues", []).append(mismatch)
                critique.setdefault("critical_issues", []).append("duration_mismatch")
                critique["passed"] = False
                critique["match_score"] = min(int(critique.get("match_score") or 50), 55)
            persist_critique(work, idx * 10 + i, attempt, critique, cur_prompt)
            score = int(critique.get("match_score") or 0)
            if score > best_score:
                best_score = score
                best_part = mux
            if critique.get("passed"):
                best_part = mux
                break
            raw = critique.get("raw") or {}
            if raw.get("fallback") or raw.get("_text_only") or raw.get("local_gates_only"):
                best_part = mux
                break
            revised = str(critique.get("revised_prompt") or "").strip()
            if revised and attempt < attempts:
                cur_prompt = revised[:900]
                continue
            break

        if not best_part or not best_part.exists():
            logger.warning("Split part %s failed for scene %s — skipping that beat", i, idx)
            continue
        part_clips.append(best_part)

    if not part_clips:
        raise RuntimeError(f"Scene {idx} split produced no clips (n={n})")
    concat_av_clips(part_clips, target, size)
    if prefer_agnes_native_audio and target.exists():
        pad_av_tail(target, target, DIALOGUE_TAIL_PAD_SEC)
    (work / f"scene_{idx:02d}_source.txt").write_text(
        f"split=true\nparts={n}\ntotal_dur={total_dur}\n"
        + "\n".join(f"part{i}={p.name}" for i, p in enumerate(part_clips)),
        encoding="utf-8",
    )
    # Split path used to skip the AV agent entirely (long clips shipped un-gated).
    if target.exists() and keys:
        from pipeline.av_self_repair_agent import diagnose_clip, run_av_self_repair_agent
        from pipeline.agent_playbook import should_force_tts

        agent_dest = work / f"scene_{idx:02d}_{element}_split_agent.mp4"
        pre = diagnose_clip(
            target,
            narration=narration,
            lang="en",
            prompt=exact_ai_video_prompt,
            product_name=product_name,
            keywords=keyword_triggers,
            work=work,
            idx=idx,
        )
        agent_report = run_av_self_repair_agent(
            media=target,
            video_src=target,
            dest=agent_dest,
            narration=narration,
            google_api_keys=keys,
            work=work,
            idx=idx,
            prompt=exact_ai_video_prompt,
            product_name=product_name,
            keywords=keyword_triggers,
            force_tts_clarity=should_force_tts(
                prefer_agnes_native=bool(prefer_agnes_native_audio),
                pre_diagnosis=pre,
            ),
        )
        if agent_dest.exists():
            shutil.copy2(agent_dest, target)
            (work / f"scene_{idx:02d}_split_agent.json").write_text(
                json.dumps(
                    {
                        "passed": agent_report.get("passed"),
                        "needs_visual_regen": agent_report.get("needs_visual_regen"),
                        "hard_hits": agent_report.get("final_hard_hits"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    from pipeline.av_quality_gates import (
        apply_gates_to_critique,
        detect_english_master_narration,
        detect_visual_anchor_lock,
        is_unshippable,
        promote_missed_visual_keywords,
    )

    vis_split = detect_visual_anchor_lock(
        prompt=exact_ai_video_prompt,
        product_name=product_name,
        keywords=keyword_triggers,
        narration=narration,
    )
    eng_split = detect_english_master_narration(narration, lang="en")
    if keys and not skip_av_critic and target.exists():
        final_c = critique_scene_clip(
            video_path=target,
            audio_path=narration_audio,
            narration_bn=narration,
            keyword_triggers=keyword_triggers,
            exact_ai_video_prompt=exact_ai_video_prompt,
            niche=niche,
            element=element,
            google_api_keys=keys,
            product_name=product_name,
        )
        final_c = apply_gates_to_critique(final_c, [vis_split, eng_split])
        final_c = promote_missed_visual_keywords(
            final_c, keywords=keyword_triggers, product_name=product_name
        )
        persist_critique(work, idx, 99, final_c, exact_ai_video_prompt)
        from pipeline.av_quality_gates import soften_documentary_proxy_critique

        final_c = soften_documentary_proxy_critique(
            final_c,
            narration=narration,
            product_name=product_name,
            keywords=keyword_triggers,
        )
        if is_unshippable(final_c) and require_agnes and not bool(
            final_c.get("documentary_proxy_softened")
        ):
            # Image/stock/i2v fallback: critic often flags intangible physics as
            # visual_anchors_missing / wrong_subject. Soft-continue when those are
            # the only remaining hard tags (Agnes UNKNOWN path).
            crit = set(str(x) for x in (final_c.get("critical_issues") or []))
            only_proxy = crit and crit.issubset(
                {"visual_anchors_missing", "wrong_subject", "unrelated_broll"}
            )
            used_fallback = (work / f"scene_{idx:02d}_USED_IMAGE_FALLBACK.txt").exists() or any(
                work.glob(f"scene_{idx:02d}_MONTAGE_STOCK.txt")
            ) or any(work.glob(f"agnes_{idx:02d}_*_i2v*.mp4"))
            narr_l = (
                f"{narration} {product_name} {' '.join(str(k) for k in (keyword_triggers or []))}"
            ).lower()
            spaceish = any(
                m in narr_l
                for m in (
                    "gravitational",
                    "black hole",
                    "telescope",
                    "universe",
                    "nasa",
                    "lunar",
                    "mars",
                    "orbit",
                    "galaxy",
                    "cosmic",
                    "astronomy",
                    "redshift",
                    "dark energy",
                    "expanding",
                    "space",
                    "quantum",
                    "particle",
                )
            )
            if only_proxy and (used_fallback or spaceish):
                logger.warning(
                    "Scene %s split master proxy soft-continue critical=%s fallback=%s",
                    idx,
                    final_c.get("critical_issues"),
                    used_fallback,
                )
            else:
                raise RuntimeError(
                    f"Scene {idx} split master unshippable: {final_c.get('critical_issues')}"
                )
        if is_unshippable(final_c) and require_agnes and final_c.get("documentary_proxy_softened"):
            logger.warning(
                "Scene %s split master documentary-softened; continuing critical=%s",
                idx,
                final_c.get("critical_issues"),
            )
    elif is_unshippable({"critical_issues": (vis_split.get("critical_issues") or []) + (eng_split.get("critical_issues") or [])}) and require_agnes:
        persist_critique(
            work,
            idx,
            99,
            apply_gates_to_critique(
                {"passed": False, "skipped": True, "match_score": 40},
                [vis_split, eng_split],
            ),
            exact_ai_video_prompt,
        )
        raise RuntimeError(
            f"Scene {idx} split master failed local language/visual gates"
        )
    return target


def _guess_product_from_query(q: str) -> str:
    return (q or "").split(" product")[0].strip()[:80]


def _clean_revised_prompt(
    revised: str,
    base: str,
    keywords: List[str],
    product: str,
    narration: str,
) -> str:
    """Remove quota/API-error junk that pollutes Agnes prompts."""
    from pipeline.prompt_engineering import revised_visual_prompt, sanitize_generation_prompt

    cleaned = sanitize_generation_prompt(revised)
    if len(cleaned) < 40:
        cleaned = revised_visual_prompt(
            narration=narration,
            keywords=keywords,
            exact_ai_video_prompt=base,
            product_name=product,
            element="",
            issues=[],
        )
    return cleaned[:900]


def _should_use_catalog(niche: str, product_name: str) -> bool:
    n = (niche or "").lower()
    if any(x in n for x in ("gadget", "tech", "phone", "review", "গ্যাজেট")):
        return True
    # Only when product looks like a known gadget model string
    p = (product_name or "").lower()
    return any(
        x in p
        for x in (
            "phone",
            "pixel",
            "oneplus",
            "galaxy",
            "iphone",
            "bud",
            "watch",
            "pixel",
            "sony wf",
            "dji",
            "gopro",
        )
    )


def _repair_cutoff_with_complete_tts(
    *,
    video_src: Path,
    dest: Path,
    narration: str,
    google_api_keys: List[str],
    size: str,
    work: Path,
    idx: int,
) -> Optional[Path]:
    """
    Issue-1 hard repair (no Agnes regen): keep picture, replace truncated Agnes
    speech with a complete TTS take, freeze last frame to match audio length,
    then enforce 1s post-dialogue hold.

    Agnes often ends mid-syllable even after prompt hardening; regenerating
    another Agnes clip burns quota and frequently still cuts. TTS+tpad fixes
    the dialogue completeness deterministically.
    """
    text = (narration or "").strip()
    if not text or not video_src.exists() or not google_api_keys:
        return None
    try:
        from pipeline.tts_google import synthesize_narration
        from pipeline.av_self_repair_agent import _mux_picture_with_audio

        tts_path = work / f"scene_{idx:02d}_cutoff_repair_tts.m4a"
        try:
            from pipeline.idempotency.tts_bridge import idempotent_synthesize_narration

            idempotent_synthesize_narration(
                work,
                job_id=work.name,
                scene_id=idx,
                dialogue_text=text,
                out_path=tts_path,
                google_api_keys=google_api_keys,
                language_hint="en",
                dialogue_id=f"scene-{idx:02d}-cutoff-repair",
                segment_id="cutoff-repair",
            )
        except Exception:
            synthesize_narration(
                text,
                tts_path,
                google_api_keys=google_api_keys,
                language_hint="en",
                idempotency_work_dir=work,
                idempotency_job_id=work.name,
                idempotency_scene_id=idx,
                idempotency_dialogue_id=f"scene-{idx:02d}-cutoff-repair",
                idempotency_segment_id="cutoff-repair",
            )
        if not tts_path.exists() or tts_path.stat().st_size < 1000:
            return None
        a_dur = ffprobe_duration(tts_path)
        v_dur = ffprobe_duration(video_src)
        # Hold last CONTENT frame (never trailing Agnes black) + mux TTS
        fixed = _mux_picture_with_audio(
            video_src=video_src,
            audio_src=tts_path,
            dest=dest,
            work=work,
            idx=idx,
            tag="cutoff_repair",
        )
        if not fixed or not fixed.exists():
            return None
        from pipeline.av_quality_gates import detect_black_tail, detect_dialogue_cutoff, detect_tail_hold

        cut = detect_dialogue_cutoff(dest, narration_text=text, lang="en")
        hold = detect_tail_hold(dest)
        black = detect_black_tail(dest)
        if not cut.get("passed", True):
            logger.warning("cutoff repair still failing gate: %s", cut.get("issues"))
        if not hold.get("passed", True):
            pad_av_tail(dest, dest, DIALOGUE_TAIL_PAD_SEC)
        if not black.get("passed", True):
            from pipeline.video_extend import replace_trailing_black_with_content_hold

            replace_trailing_black_with_content_hold(dest, dest, extra_hold_sec=0.0)
        logger.info(
            "Scene %s cutoff repaired via complete TTS (v=%.2fs → a=%.2fs, no black clone)",
            idx,
            v_dur,
            a_dur,
        )
        (work / f"scene_{idx:02d}_CUTOFF_REPAIRED.txt").write_text(
            f"tts={tts_path.name}\ncut_passed={cut.get('passed')}\nblack_passed={black.get('passed')}\n",
            encoding="utf-8",
        )
        return dest if dest.exists() else None
    except Exception as exc:
        logger.warning("cutoff TTS repair failed: %s", exc)
        return None


def _extract_audio_track(video: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        # silent fallback so critic path doesn't crash
        return _write_silent_audio(dest, max(1.0, ffprobe_duration(video)))
    return dest


def _write_silent_audio(dest: Path, seconds: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sec = max(1.0, float(seconds or 1.0))
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=44100:cl=stereo",
        "-t",
        f"{sec:.3f}",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True)
    return dest


def resolve_bengali_fontfile() -> str:
    return resolve_fontfile_for_lang("bn")


def resolve_fontfile_for_lang(lang_code: str = "en") -> str:
    """Pick a system font that can render the target script."""
    code = (lang_code or "en").lower().strip()
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    # Prefer script-capable fonts; fall back to common Unicode fonts
    candidates_by_lang = {
        "bn": [
            "PotroSansBangla-Regular.ttf",
            "Potro Sans Bangla Regular.ttf",
            "Nirmala.ttc",
            "Nirmala.ttf",
            "NirmalaS.ttf",
            "vrinda.ttf",
            "segoeui.ttf",
        ],
        "hi": ["Nirmala.ttc", "Nirmala.ttf", "mangal.ttf", "segoeui.ttf"],
        "ur": ["Nirmala.ttc", "Nirmala.ttf", "seguisym.ttf", "arial.ttf", "segoeui.ttf"],
        "ta": ["Nirmala.ttc", "Nirmala.ttf", "latha.ttf", "segoeui.ttf"],
        "ml": ["Nirmala.ttc", "Nirmala.ttf", "cartaman.ttf", "segoeui.ttf"],
        "en": ["arial.ttf", "segoeui.ttf", "calibri.ttf"],
    }
    names = candidates_by_lang.get(code, candidates_by_lang["en"]) + [
        "Nirmala.ttc",
        "Nirmala.ttf",
        "arial.ttf",
        "segoeui.ttf",
    ]
    # Project fonts first (if present)
    root = Path(__file__).resolve().parents[1]
    project_fonts = [
        root / "assets" / "fonts" / "Kalpurush.ttf",
        root / "assets" / "fonts" / "PotroSansBangla-Bold.ttf",
        root / "assets" / "fonts" / "vrindab.ttf",
        root / "assets" / "fonts" / "SolaimanLipi.ttf",
        root / "assets" / "fonts" / "NotoSansBengali-Regular.ttf",
    ]
    if code == "bn":
        for p in project_fonts:
            if p.exists():
                return str(p).replace("\\", "/").replace(":", "\\:")
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        p = windir / name
        if p.exists():
            # ffmpeg drawtext on Windows wants forward slashes / escaped
            return str(p).replace("\\", "/").replace(":", "\\:")
    return ""


def master_mux_vf(
    size: str,
    *,
    subtitle_text: str = "",
    subtitle_lang: str = "en",
    srt_path: Optional[Path] = None,
) -> str:
    """
    Picture filters for mux.
    Never burn English into frames. Non-English burns by default (AMP_BURN_MASTER_SUBS=0 to disable).
    Prefer timed SRT→ASS burn when srt_path is provided (canvas-aware small captions).
    """
    w, h = size.split("x")
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=25,format=yuv420p"
    lang = (subtitle_lang or "en").lower().strip()[:2]
    burn_env = os.environ.get("AMP_BURN_MASTER_SUBS", "1").strip()
    burn = burn_env != "0"
    if not burn or lang in {"", "en"}:
        return vf
    if srt_path and Path(srt_path).exists():
        try:
            from pipeline.subtitle_burn import apply_subtitles_to_vf

            return apply_subtitles_to_vf(vf, Path(srt_path), size=size, lang=lang)
        except Exception:
            sp = str(Path(srt_path).resolve()).replace("\\", "/").replace(":", "\\:")
            from pipeline.subtitle_burn import ass_force_style

            style = ass_force_style(size=size, lang=lang)
            vf += f",subtitles='{sp}':force_style='{style}'"
            return vf
    if subtitle_text:
        from pipeline.subtitle_burn import drawtext_fallback_filter

        font = resolve_fontfile_for_lang(lang)
        vf += "," + drawtext_fallback_filter(
            subtitle_text, size=size, lang=lang, fontfile=font or ""
        )
    return vf


def _mux_scene(
    *,
    video_src: Path,
    narration_audio: Optional[Path] = None,
    dest: Path,
    duration: float,
    size: str,
    subtitle_text: str = "",
    subtitle_lang: str = "en",
    keep_source_audio: bool = False,
    work: Optional[Path] = None,
    scene_id: str = "0",
    dialogue_id: str = "",
    segment_id: str = "",
) -> Path:
    """
    Mux scene.
    keep_source_audio=True → keep Agnes native audio (AV generated together).
    keep_source_audio=False → replace with narration_audio (TTS / localized).
    """
    vf = master_mux_vf(size, subtitle_text=subtitle_text, subtitle_lang=subtitle_lang)

    if keep_source_audio:
        # Agnes AV together — do not replace audio.
        # Avoid -shortest (cuts on first stream end / last syllable).
        # Tail pad is applied by the caller after mux.
        src_dur = max(ffprobe_duration(video_src), 0.5)
        take = max(float(duration or 0), src_dur)
        try:
            from pipeline.system_profile import ffmpeg_x264_args as _x264

            _enc = _x264()
        except Exception:
            _enc = ["-preset", "veryfast", "-crf", "22"]
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(video_src),
            "-t",
            f"{take:.3f}",
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            *_enc,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    else:
        try:
            from pipeline.system_profile import ffmpeg_x264_args as _x264
            _enc = _x264()
        except Exception:
            _enc = ["-preset", "veryfast", "-crf", "22"]
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(video_src),
            "-i",
            str(narration_audio),
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            *_enc,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        logger.warning("scene mux failed: %s", (r.stderr or "")[-400:])
        if keep_source_audio and video_src.exists():
            shutil.copy2(video_src, dest)
            return dest
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x122028:s={size}:d={duration}",
            "-i",
            str(narration_audio),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
        subprocess.run(cmd, capture_output=True)
    if subtitle_text:
        try:
            from pipeline.localization import write_srt

            audio_for_srt = narration_audio if narration_audio and Path(narration_audio).exists() else dest
            dlg = dialogue_id or f"scene-{scene_id}-mux"
            write_srt(
                subtitle_text,
                Path(audio_for_srt),
                dest.with_suffix(".srt"),
                work_dir=work,
                job_id=work.name if work else "",
                scene_id=str(scene_id),
                dialogue_id=dlg,
                language=subtitle_lang,
                segment_id=segment_id,
            )
        except Exception:
            pass
    try:
        Path(str(dest) + ".vf.txt").write_text(vf, encoding="utf-8")
    except Exception:
        pass
    return dest


def _resolve_footage(
    *,
    work: Path,
    idx: int,
    product_name: str,
    visual_query: str,
    visual_prompt: str,
    element: str,
    duration: float,
    size: str,
    pexels_api: str,
    pollinations_key: str,
    agnes_api: str,
    agnes_api_keys: Optional[List[str]] = None,
    google_api_keys: List[str],
    narration_hint: str = "",
    require_agnes: bool = True,
    override_prompt: str = "",
    niche: str = "",
    keyword_triggers: Optional[List[str]] = None,
    attempt: int = 1,
    allow_image_fallback: bool = True,
    narration_audio: Optional[Path] = None,
    job_id: str = "",
    dialogue_id: str = "",
    canonical_scene_id: str = "",
    script_id: str = "",
    visual_mode: str = "",
    generation_payload: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Dialogue visualization — C05-GP mode-driven routing:
      IMAGE → image-capable path (still / Pollinations)
      IMAGE_WITH_MOTION → fallback_image_video (Ken Burns)
      VIDEO → Agnes video adapter (legacy default when mode unset)
    """
    from pipeline.visual_intelligence import MODE_IMAGE, MODE_IMAGE_WITH_MOTION, MODE_VIDEO

    mode = (visual_mode or (generation_payload or {}).get("actual_mode") or "").strip().upper()
    route = str((generation_payload or {}).get("route") or "")

    agnes_keys: List[str] = []
    for k in agnes_api_keys or []:
        kk = (k or "").strip()
        if kk and kk not in agnes_keys:
            agnes_keys.append(kk)
    if (agnes_api or "").strip() and (agnes_api or "").strip() not in agnes_keys:
        agnes_keys.insert(0, (agnes_api or "").strip())

    # Persist routing provenance (no secrets)
    try:
        (work / f"scene_{idx:02d}_provider_route.json").write_text(
            json.dumps(
                {
                    "requested_mode": (generation_payload or {}).get("requested_mode") or mode,
                    "actual_mode": mode,
                    "route": route,
                    "provider_name": (generation_payload or {}).get("provider_name") or "",
                    "fallback_used": bool((generation_payload or {}).get("fallback_used")),
                    "fallback_reason": (generation_payload or {}).get("fallback_reason") or "",
                    "capability_status": (generation_payload or {}).get("capability_status") or "",
                    "dialogue_id": dialogue_id,
                    "beat_id": (generation_payload or {}).get("beat_id") or "",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    # IMAGE: BUILD-03 claim/reuse + image adapter (never Agnes)
    if mode == MODE_IMAGE:
        try:
            from pipeline.fallback_image_video import build_image_video_fallback
            from pipeline.generation_payload import (
                idempotent_image_clip_via_build03,
                record_execution_provenance,
            )

            fb_out = work / f"agnes_{idx:02d}_{element}_image_a{attempt}.mp4"
            logger.info("Scene %s: IMAGE route via BUILD-03", idx)

            def _img_provider():
                build_image_video_fallback(
                    work=work,
                    out_path=fb_out,
                    narration=narration_hint or visual_query,
                    duration=duration,
                    size=size,
                    audio_path=narration_audio if narration_audio and Path(narration_audio).exists() else None,
                    base_prompt=override_prompt or visual_prompt or visual_query,
                    keywords=list(keyword_triggers or []),
                    product_name=product_name,
                    element=element,
                    niche=niche,
                    pollinations_key=pollinations_key,
                    google_api_keys=google_api_keys,
                )
                return fb_out

            if generation_payload:
                res = idempotent_image_clip_via_build03(
                    work_dir=work,
                    payload=generation_payload,
                    out_path=fb_out,
                    provider_fn=_img_provider,
                    size=size,
                    duration_sec=duration,
                )
                if res.get("blocked"):
                    raise RuntimeError(f"IMAGE BUILD-03 blocked: {','.join(res.get('blocks') or [])}")
                if res.get("ok") and res.get("path"):
                    try:
                        (work / f"scene_{idx:02d}_execution_provenance.json").write_text(
                            json.dumps(
                                record_execution_provenance(
                                    generation_payload,
                                    asset_id=str(res.get("asset_id") or fb_out.name),
                                    actual_mode=MODE_IMAGE,
                                    adapter="fallback_image_video+build03",
                                    timing={"duration_sec": duration},
                                ),
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                    return Path(res["path"])
            else:
                _img_provider()
                if fb_out.exists() and fb_out.stat().st_size > 8000:
                    return fb_out
        except Exception as exc:
            logger.warning("IMAGE route failed: %s", exc)
        raise RuntimeError(f"IMAGE mode required for scene {idx} but image provider path failed.")

    # IMAGE_WITH_MOTION: BUILD-03 + fallback_image_video
    if mode == MODE_IMAGE_WITH_MOTION or route == "IMAGE_WITH_MOTION_PROVIDER":
        try:
            from pipeline.fallback_image_video import build_image_video_fallback
            from pipeline.generation_payload import (
                idempotent_image_clip_via_build03,
                mark_runtime_fallback,
                record_execution_provenance,
            )

            fb_out = work / f"agnes_{idx:02d}_{element}_i2v_a{attempt}.mp4"
            logger.info("Scene %s: IMAGE_WITH_MOTION route via BUILD-03", idx)

            def _motion_provider():
                build_image_video_fallback(
                    work=work,
                    out_path=fb_out,
                    narration=narration_hint or visual_query,
                    duration=duration,
                    size=size,
                    audio_path=narration_audio if narration_audio and Path(narration_audio).exists() else None,
                    base_prompt=override_prompt or visual_prompt or visual_query,
                    keywords=list(keyword_triggers or []),
                    product_name=product_name,
                    element=element,
                    niche=niche,
                    pollinations_key=pollinations_key,
                    google_api_keys=google_api_keys,
                )
                return fb_out

            if generation_payload:
                res = idempotent_image_clip_via_build03(
                    work_dir=work,
                    payload=generation_payload,
                    out_path=fb_out,
                    provider_fn=_motion_provider,
                    size=size,
                    duration_sec=duration,
                )
                if res.get("blocked"):
                    raise RuntimeError(
                        f"IMAGE_WITH_MOTION BUILD-03 blocked: {','.join(res.get('blocks') or [])}"
                    )
                if res.get("ok") and res.get("path"):
                    req = str((generation_payload or {}).get("requested_mode") or MODE_IMAGE_WITH_MOTION)
                    if req == MODE_VIDEO:
                        generation_payload = mark_runtime_fallback(
                            generation_payload,
                            actual_mode=MODE_IMAGE_WITH_MOTION,
                            fallback_reason="image_derived_motion_not_native_video",
                            derived_asset_id=str(res.get("asset_id") or fb_out.name),
                        )
                    try:
                        (work / f"scene_{idx:02d}_execution_provenance.json").write_text(
                            json.dumps(
                                record_execution_provenance(
                                    generation_payload,
                                    asset_id=str(res.get("asset_id") or fb_out.name),
                                    derived_asset_id=str(res.get("asset_id") or fb_out.name),
                                    actual_mode=MODE_IMAGE_WITH_MOTION,
                                    adapter="fallback_image_video+build03",
                                    fallback_used=bool((generation_payload or {}).get("fallback_used")),
                                    fallback_reason=str((generation_payload or {}).get("fallback_reason") or ""),
                                    timing={"duration_sec": duration},
                                ),
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                    return Path(res["path"])
            else:
                _motion_provider()
                if fb_out.exists() and fb_out.stat().st_size > 8000:
                    return fb_out
        except Exception as exc:
            logger.warning("IMAGE_WITH_MOTION route failed: %s", exc)
        raise RuntimeError(f"IMAGE_WITH_MOTION required for scene {idx} but motion path failed.")

    agnes_err: Optional[BaseException] = None
    agnes_outcome_label: str = ""
    suffix = "" if attempt <= 1 else f"_r{attempt}"

    # VIDEO: Google Veo 3.1 / 2.0 (Google Pro) or Agnes
    if mode == MODE_VIDEO or (not mode and generation_payload is None):
        g_keys = [k for k in (google_api_keys or []) if (k or "").strip()]
        env_gk = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_gk and env_gk not in g_keys:
            g_keys.append(env_gk)
        if g_keys and os.environ.get("AMP_DISABLE_GOOGLE_VEO", "").strip() != "1":
            veo_out = work / f"veo_{idx:02d}_{element}{suffix}.mp4"
            if not veo_out.exists() or attempt > 1:
                try:
                    from pipeline.google_media import generate_veo_video
                    aspect = "9:16" if ("x" in size and int(size.split("x")[1]) > int(size.split("x")[0])) else "16:9"
                    v_path = generate_veo_video(
                        override_prompt or visual_prompt or visual_query,
                        veo_out,
                        g_keys[0],
                        aspect_ratio=aspect,
                        duration_seconds=int(duration or 5),
                    )
                    if v_path and v_path.is_file() and v_path.stat().st_size > 5000:
                        logger.info("Scene %s: Google Veo VIDEO generated successfully for %s", idx, product_name)
                        return v_path
                except Exception as veo_exc:
                    logger.warning("Google Veo generation attempt failed scene=%s: %s", idx, veo_exc)

    if (mode == MODE_VIDEO or (not mode and generation_payload is None)):
        agnes_out = work / f"agnes_{idx:02d}_{element}{suffix}.mp4"
        # Remove stale file so regenerate is forced
        if agnes_out.exists() and attempt > 1:
            try:
                agnes_out.unlink()
            except Exception:
                pass
        try:
            from pipeline.idempotency.agnes_bridge import (
                AgnesBeatOutcome,
                classify_agnes_beat_outcome,
                try_reconcile_agnes_beat_unknown,
            )

            path, agnes_beat_result = _resolve_single_agnes_beat_src(
                work=work,
                job_id=job_id or work.name,
                idx=idx,
                attempt=attempt,
                product_name=product_name or "gadget",
                element=element,
                visual_prompt=visual_prompt or visual_query,
                visual_query=visual_query,
                out_path=agnes_out,
                narration_hint=narration_hint,
                size=size,
                duration_hint=min(max(duration, AGNES_MIN_SECONDS), AGNES_AUDIO_CHUNK_MAX),
                override_prompt=override_prompt,
                niche=niche,
                use_catalog_image=_should_use_catalog(niche, product_name),
                dialogue_id=dialogue_id,
                canonical_scene_id=canonical_scene_id,
                script_id=script_id,
                generation_payload=generation_payload,
            )
            outcome = classify_agnes_beat_outcome(agnes_beat_result)
            agnes_outcome_label = outcome.value

            if path is not None:
                logger.info(
                    "Scene %s: Agnes VIDEO for %s / %s (attempt %s, outcome=%s)",
                    idx,
                    product_name,
                    element,
                    attempt,
                    outcome.value,
                )
                return path

            if outcome == AgnesBeatOutcome.IDENTITY_BLOCKED:
                raise AgnesOutcomeError(
                    "IDENTITY_BLOCKED",
                    agnes_beat_result.detail or "identity blocked",
                )

            if outcome == AgnesBeatOutcome.UNKNOWN:
                reconciled = try_reconcile_agnes_beat_unknown(
                    work,
                    job_id=job_id or work.name,
                    scene_id=idx,
                    part_index=0,
                    product_name=product_name or "gadget",
                    element=element,
                    visual_prompt=visual_prompt or visual_query,
                    override_prompt=override_prompt,
                    narration_hint=narration_hint,
                    size=size,
                    duration_hint=min(max(duration, AGNES_MIN_SECONDS), AGNES_AUDIO_CHUNK_MAX),
                    use_catalog_image=_should_use_catalog(niche, product_name),
                    niche=niche,
                    dialogue_id=dialogue_id,
                    canonical_scene_id=canonical_scene_id,
                    script_id=script_id,
                    local_artifact=str(agnes_out) if agnes_out.is_file() else "",
                )
                if reconciled is not None:
                    logger.info(
                        "Scene %s: Agnes reconciled from UNKNOWN fp=%s",
                        idx,
                        (agnes_beat_result.fingerprint or "")[:12],
                    )
                    return reconciled
                # UNKNOWN after reconcile is not shippable as Agnes success, but must
                # not abort the whole scene — allow stock / documentary fallback paths.
                logger.warning(
                    "Single Agnes UNKNOWN scene=%s fp=%s — falling through to non-Agnes footage",
                    idx,
                    (agnes_beat_result.fingerprint or "")[:12],
                )
                agnes_outcome_label = AgnesBeatOutcome.UNKNOWN.value

            elif outcome in (AgnesBeatOutcome.FAILED_RETRYABLE, AgnesBeatOutcome.FAILED_FINAL):
                logger.warning(
                    "Scene %s: Agnes %s state=%s — not Agnes success; fallback may apply",
                    idx,
                    outcome.value,
                    agnes_beat_result.state,
                )
        except AgnesOutcomeError:
            raise
        except Exception as exc:
            agnes_err = exc
            agnes_outcome_label = "EXCEPTION"
            logger.warning("Agnes canonical path failed scene=%s: %s", idx, exc)
            from pipeline.quota_backoff import is_quota_error, record_quota_hit

            if is_quota_error(exc):
                record_quota_hit("agnes")

    # Agnes failed / missing → free image Ken Burns pipeline (saves Agnes quota).
    # Pollinations free URL + Goblin are keyless — do not require pollinations_key.
    # C05-GX: never claim native VIDEO when image-derived clip used.
    if allow_image_fallback:
        # Structured VIDEO without explicit fallback policy must not silent-downgrade
        if mode == MODE_VIDEO and generation_payload and not bool(
            (generation_payload or {}).get("fallback_used")
        ):
            # Runtime fallback is explicit policy via allow_image_fallback flag
            pass
        try:
            from pipeline.fallback_image_video import build_image_video_fallback
            from pipeline.generation_payload import mark_runtime_fallback, record_execution_provenance

            fb_out = work / f"agnes_{idx:02d}_{element}_i2v_a{attempt}.mp4"
            logger.warning(
                "Scene %s: image→video fallback (Agnes outcome=%s err=%s)",
                idx,
                agnes_outcome_label or "none",
                (str(agnes_err)[:120] if agnes_err else "none"),
            )
            build_image_video_fallback(
                work=work,
                out_path=fb_out,
                narration=narration_hint or visual_query,
                duration=duration,
                size=size,
                audio_path=narration_audio if narration_audio and Path(narration_audio).exists() else None,
                base_prompt=override_prompt or visual_prompt or visual_query,
                keywords=list(keyword_triggers or []),
                product_name=product_name,
                element=element,
                niche=niche,
                pollinations_key=pollinations_key,
                google_api_keys=google_api_keys,
            )
            if fb_out.exists() and fb_out.stat().st_size > 8000:
                if generation_payload:
                    generation_payload = mark_runtime_fallback(
                        generation_payload,
                        actual_mode=MODE_IMAGE_WITH_MOTION,
                        fallback_reason=f"agnes_runtime_fallback:{agnes_outcome_label or 'none'}",
                        derived_asset_id=str(fb_out.name),
                    )
                    try:
                        (work / f"scene_{idx:02d}_execution_provenance.json").write_text(
                            json.dumps(
                                record_execution_provenance(
                                    generation_payload,
                                    asset_id=str(fb_out.name),
                                    derived_asset_id=str(fb_out.name),
                                    actual_mode=MODE_IMAGE_WITH_MOTION,
                                    adapter="fallback_image_video",
                                    fallback_used=True,
                                    fallback_reason=str(
                                        (generation_payload or {}).get("fallback_reason") or ""
                                    ),
                                    timing={"duration_sec": duration},
                                ),
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        (work / f"scene_{idx:02d}_provider_route.json").write_text(
                            json.dumps(
                                {
                                    "requested_mode": (generation_payload or {}).get("requested_mode")
                                    or mode,
                                    "actual_mode": MODE_IMAGE_WITH_MOTION,
                                    "fallback_used": True,
                                    "fallback_reason": (generation_payload or {}).get(
                                        "fallback_reason"
                                    ),
                                    "native_video_claimed": False,
                                },
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                return fb_out
        except Exception as exc:
            logger.warning("Image→video fallback failed: %s", exc)

    # Prefer matched stock before hard-failing VIDEO-primary (OpenMontage-style retrieval)
    if pexels_api:
        for q in _category_stock_queries(product_name, element):
            q = (q or "").strip()
            if not q:
                continue
            orient = (
                "portrait"
                if "x" in size and int(size.split("x")[1]) > int(size.split("x")[0])
                else "landscape"
            )
            urls = fetch_pexels_videos(pexels_api, q, per_page=4, orientation=orient)
            for u_i, url in enumerate(urls):
                try:
                    raw = download_file(url, work / f"pexels_{idx}_{u_i}.mp4")
                    if raw.exists() and raw.stat().st_size > 20000:
                        logger.warning("Scene %s: stock fallback %r", idx, q)
                        return raw
                except Exception as exc:
                    logger.debug("pexels miss: %s", exc)

    if require_agnes and agnes_keys and not allow_image_fallback:
        raise RuntimeError(
            f"Agnes video required for scene {idx} ({element}) but generation failed."
        )
    if require_agnes and not agnes_keys and not allow_image_fallback:
        raise RuntimeError("Agnes API key missing — dialogue video generation requires Agnes.")

    if product_name:
        still = work / f"product_{idx:02d}_{element}.png"
        try:
            w, h = (int(x) for x in size.split("x"))
            generate_product_still(
                product_name,
                element,
                still,
                visual_prompt=override_prompt or visual_prompt or visual_query,
                width=min(w, 1280),
                height=min(h, 1920),
                api_key=pollinations_key,
                google_api_keys=google_api_keys,
            )
            clip = work / f"productclip_{idx:02d}_a{attempt}.mp4"
            _image_to_motion(still, clip, duration, size, element=element)
            if clip.exists() and clip.stat().st_size > 5000:
                logger.warning("Scene %s: still fallback", idx)
                return clip
        except Exception as exc:
            logger.warning("product still failed: %s", exc)

    fb = work / f"fallback_{idx}_a{attempt}.mp4"
    make_color_clip(fb, duration, size)
    return fb


def _category_stock_queries(product_name: str, element: str) -> List[str]:
    p = (product_name or "").lower()
    cat = "smartphone"
    if any(x in p for x in ("bud", "ear", "airpod", "headphone", "wf-")):
        cat = "wireless earbuds"
    elif "watch" in p:
        cat = "smartwatch"
    elif any(x in p for x in ("gopro", "osmo", "camera")):
        cat = "action camera"
    elif any(x in p for x in ("quest", "steam deck", "ally", "handheld")):
        cat = "handheld gaming device"
    elif any(x in p for x in ("laptop", "macbook")):
        cat = "laptop"
    elif any(x in p for x in ("webb", "jwst", "telescope", "galaxy", "nebula", "cosmos", "space")):
        # Documentary space subjects — prefer astronomy B-roll over gadget stock
        return [
            "james webb space telescope",
            "deep space galaxy",
            "nebula stars cosmos",
            "astronomy observatory space",
        ]
    elif any(
        x in p
        for x in (
            "moon",
            "lunar",
            "artemis",
            "crater",
            "apollo",
            "regolith",
            "parker",
            "solar",
            "corona",
            "mars",
            "nasa",
        )
    ):
        return [
            "moon surface crater landscape",
            "lunar south pole ice crater",
            "astronaut spacesuit moon dust",
            "nasa space documentary footage",
            "solar corona sun atmosphere",
        ]

    el = (element or "").lower()
    mapping = {
        "intro": [f"{cat} unboxing hands table", f"{cat} product hero shot"],
        "design": [f"{cat} close up design metal finish", f"{cat} macro body detail"],
        "display": [f"{cat} screen display close up scrolling", "phone amoled screen content"],
        "camera": [f"{cat} camera lens macro", "smartphone triple camera module close up"],
        "battery": [f"{cat} charging cable plug close up", "phone fast charging cable"],
        "sound": ["wireless earbuds in ear close up", "earbuds charging case open"],
        "fit": ["wireless earbuds wearing close up comfort"],
        "case": ["earbuds charging case open close macro"],
        "processor": ["smartphone gaming performance hands", "mobile chipset circuit board"],
        "software": [f"{cat} touchscreen ui fingers", "smartwatch wrist ui close up"],
        "price": [f"{cat} retail box product shot"],
        "pros_cons": [f"{cat} review hands desk"],
        "outro": [f"{cat} final product stand spotlight"],
    }
    return mapping.get(el, [f"{cat} product close up", f"{cat} lifestyle"])


def _image_to_motion(image: Path, dest: Path, duration: float, size: str, element: str = "") -> Path:
    w, h = size.split("x")
    el = (element or "").lower()
    if el == "camera":
        zp = (
            f"zoompan=z='min(zoom+0.0022,1.35)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih*0.12':s={w}x{h}:fps=25"
        )
    elif el == "display":
        zp = (
            f"zoompan=z='min(zoom+0.0018,1.25)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
        )
    elif el == "battery":
        zp = (
            f"zoompan=z='min(zoom+0.0016,1.2)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih*0.55-(ih/zoom/2)':s={w}x{h}:fps=25"
        )
    else:
        zp = (
            f"zoompan=z='min(zoom+0.0015,1.18)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
        )
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-t",
        f"{duration:.3f}",
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{zp},format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            f"{duration:.3f}",
            "-vf",
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        subprocess.run(cmd, capture_output=True)
    return dest


def concat_av_clips(clips: List[Path], dest: Path, size: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not clips:
        raise RuntimeError("no clips to concat")
    if len(clips) == 1:
        return _normalize_file(clips[0], dest, size)

    inputs: List[str] = []
    filter_parts = []
    for i, c in enumerate(clips):
        inputs.extend(["-i", str(c)])
        filter_parts.append(
            f"[{i}:v]scale={size.replace('x', ':')}:force_original_aspect_ratio=increase,"
            f"crop={size.replace('x', ':')},fps=25,format=yuv420p,setsar=1[v{i}];"
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"aresample=async=1:first_pts=0[a{i}];"
        )
    n = len(clips)
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_complex = "".join(filter_parts) + f"{concat_in}concat=n={n}:v=1:a=1[v][a]"

    cmd = [
        ffmpeg_bin(),
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    def _ok() -> bool:
        try:
            return dest.exists() and dest.stat().st_size > 8000
        except Exception:
            return False

    if r.returncode != 0 or not _ok():
        size_bytes = None
        try:
            size_bytes = dest.stat().st_size if dest.exists() else None
        except Exception:
            size_bytes = None
        logger.warning(
            "filter concat failed/empty: rc=%s size=%s tail=%s",
            r.returncode,
            size_bytes,
            (r.stderr or "")[-500:],
        )
        fixed: List[Path] = []
        for i, c in enumerate(clips):
            f = dest.parent / f"_fix_{i}.mp4"
            _ensure_audio_track(c, f, size)
            fixed.append(f)

        # Retry with the same filter-complex concat, but on guaranteed audio-bearing clips.
        retry_inputs: List[str] = []
        retry_parts: List[str] = []
        for i, c in enumerate(fixed):
            retry_inputs.extend(["-i", str(c)])
            retry_parts.append(
                f"[{i}:v]scale={size.replace('x', ':')}:force_original_aspect_ratio=increase,"
                f"crop={size.replace('x', ':')},fps=25,format=yuv420p,setsar=1[v{i}];"
                f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"aresample=async=1:first_pts=0[a{i}];"
            )
        n = len(fixed)
        concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
        retry_filter_complex = "".join(retry_parts) + f"{concat_in}concat=n={n}:v=1:a=1[v][a]"

        cmd2 = [
            ffmpeg_bin(),
            "-y",
            *retry_inputs,
            "-filter_complex",
            retry_filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0 or not _ok():
            logger.error("concat retry failed: rc=%s tail=%s", r2.returncode, (r2.stderr or "")[-800:])
            raise RuntimeError("concat_av_clips_failed_after_audio_fix_retry")
    return dest


def _normalize_file(src: Path, dest: Path, size: str) -> Path:
    w, h = size.split("x")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=25,format=yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True)
    return dest


def _ensure_audio_track(src: Path, dest: Path, size: str) -> Path:
    dur = ffprobe_duration(src) or 3.0
    w, h = size.split("x")
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        f"{dur:.3f}",
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=25,format=yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True)
    return dest


def mix_logo_safe(video: Path, logo: Optional[Path], dest: Path) -> Path:
    if not logo or not logo.exists():
        import shutil

        shutil.copy2(video, dest)
        return dest
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(video),
        "-i",
        str(logo),
        "-filter_complex",
        "[1:v]scale=120:-1[logo];[0:v][logo]overlay=W-w-20:20",
        "-c:a",
        "aac",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        import shutil

        shutil.copy2(video, dest)
    return dest
