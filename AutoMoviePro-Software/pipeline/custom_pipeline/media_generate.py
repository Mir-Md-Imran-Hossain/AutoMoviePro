"""Stage 5a — Generate shared Image/ + Video/Video Clips/ from visual_render_plan."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.custom_pipeline.media_prompts import (
    build_detailed_media_prompt,
    prompt_audit,
    stock_search_query,
)
from pipeline.custom_pipeline.media_providers import (
    canvas_for_aspect,
    generate_image_with_fallback,
    generate_video_with_fallback,
    ken_burns_from_image,
)
from pipeline.custom_pipeline.multi_still_clip import build_multi_still_master, upscale_still_to_canvas
from pipeline.custom_pipeline.package_layout import open_package
from pipeline.custom_pipeline.visual_continuity import (
    apply_visual_mode_to_render_type,
    av_matched_stock_query,
    beat_visual_prompt,
    frames_for_duration,
    package_seed,
    resolve_media_visual_mode,
    seed_lock_prompt_suffix,
    shot_seed,
    split_narration_beats,
)
from pipeline.output_layout import write_json

logger = logging.getLogger(__name__)

STATE_NAME = "media_generation_state.json"


def _load_plan(pkg: Path) -> Dict[str, Any]:
    paths = open_package(pkg)
    candidates = [
        paths.file_dir / "visual_render_plan.json",
        *sorted(paths.file_dir.glob("Visual_*.json")),
    ]
    for p in candidates:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"visual_render_plan.json missing under {paths.file_dir}")


def _package_topic_meta(pkg: Path) -> Dict[str, str]:
    """Niche/topic from topic_script for subject inference."""
    out = {"niche": "", "topic": ""}
    try:
        paths = open_package(pkg)
        for name in ("topic_script.json", "package_meta.json"):
            p = paths.file_dir / name
            if not p.is_file():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            seo = data.get("seo_metadata") or {}
            out["topic"] = str(seo.get("selected_topic") or data.get("selected_topic") or out["topic"] or "")
            out["niche"] = str(data.get("niche") or seo.get("niche") or out["niche"] or "")
            if out["topic"] or out["niche"]:
                break
        # Folder name often embeds topic
        if not out["topic"] and pkg.name:
            out["topic"] = pkg.name
    except Exception:
        pass
    return out


def _enrich_scene_from_script(pkg: Path, scene: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill camera/light/character/voiceover from topic_script if plan is thin."""
    out = dict(scene)
    meta = _package_topic_meta(pkg)
    if meta.get("niche"):
        out.setdefault("package_niche", meta["niche"])
        out.setdefault("niche", meta["niche"])
    if meta.get("topic"):
        out.setdefault("package_topic", meta["topic"])
        out.setdefault("selected_topic", meta["topic"])
        out.setdefault("topic", meta["topic"])
    try:
        paths = open_package(pkg)
        script_path = paths.file_dir / "topic_script.json"
        if not script_path.is_file():
            return out
        data = json.loads(script_path.read_text(encoding="utf-8"))
        scenes = data.get("script_scenes") or data.get("voice_scenes") or []
        out.setdefault("package_total_shots", len(scenes) or 0)
        out.setdefault("total_shots", len(scenes) or 0)
        n = int(out.get("shot_number") or 0)
        src = None
        for sc in scenes:
            try:
                if int(sc.get("shot_number") or 0) == n:
                    src = sc
                    break
            except (TypeError, ValueError):
                continue
        if not isinstance(src, dict):
            return out
        mapping = {
            "source_camera_angle": "camera_angle",
            "source_lighting": "lighting",
            "source_character_details": "character_details",
            "source_voiceover_script": "voiceover_script",
            "source_emotion_tag": "emotion_tag",
            "source_background": "background",
            "source_visual_subject": "visual_subject",
            "visual_subject": "visual_subject",
        }
        for dst, src_key in mapping.items():
            if not out.get(dst) and src.get(src_key):
                out[dst] = src.get(src_key)
        if not out.get("visual_prompt") and src.get("visual_prompt"):
            out["visual_prompt"] = src.get("visual_prompt")
    except Exception:
        return out
    return out


def _load_state(paths) -> Dict[str, Any]:
    p = paths.file_dir / STATE_NAME
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"shots": {}}


def _save_state(paths, state: Dict[str, Any]) -> None:
    write_json(paths.file_dir / STATE_NAME, state)


def _narration_for_shot(pkg: Path, shot_number: int, scene: Dict[str, Any]) -> str:
    """Prefer English beat for image/video APIs; fall back to Bangla source voiceover."""
    # 1) already on render scene
    spoken = str(
        scene.get("source_voiceover_script")
        or scene.get("voiceover_script")
        or ""
    ).strip()
    # 2) English localized voice (better for most image/video models)
    try:
        from pipeline.custom_pipeline.package_layout import open_package

        paths = open_package(pkg)
        en = paths.file_dir / "localized_voice_EN.json"
        if en.is_file():
            data = json.loads(en.read_text(encoding="utf-8"))
            for sc in data.get("voice_scenes") or []:
                try:
                    n = int(sc.get("shot_number") or 0)
                except (TypeError, ValueError):
                    continue
                if n == shot_number:
                    eng = str(sc.get("voiceover_script") or sc.get("subtitle_text") or "").strip()
                    if eng:
                        return eng
    except Exception:
        pass
    return spoken


def _ensure_character_reference(
    pkg: Path,
    paths,
    scenes: List[Dict[str, Any]],
    *,
    aspect: str,
    art: str,
) -> Optional[Path]:
    """Generate one master character still used as continuity anchor for presenter shots.

    Skip entirely for product/UI-heavy packages where no presenter face is needed.
    """
    from pipeline.custom_pipeline.media_prompts import resolve_scene_subject
    from pipeline.custom_pipeline.visual_subject_policy import character_allowed, is_non_presenter_topic

    topic = str(pkg.name)
    niche = ""
    if scenes and isinstance(scenes[0], dict):
        topic = str(scenes[0].get("topic") or scenes[0].get("package_topic") or pkg.name)
        niche = str(scenes[0].get("niche") or scenes[0].get("package_niche") or "")

    if is_non_presenter_topic(niche, topic):
        logger.info("Topic is non-presenter/documentary (%s) — skip character_reference", topic)
        return None

    ref = paths.image / "character_reference.png"
    if ref.is_file() and ref.stat().st_size > 2000:
        return ref

    presenter_scenes = []
    for sc in scenes:
        subj = resolve_scene_subject(sc)
        char = str(sc.get("source_character_details") or sc.get("character_details") or "").strip().lower()
        has_char = bool(char and char not in ("none", "n/a", "na", "no character", "-", "null"))
        if character_allowed(subj) and has_char:
            presenter_scenes.append(sc)
    if not presenter_scenes:
        logger.info("No presenter/hands shots — skip character_reference (faceless/documentary package)")
        return None
    # Build from first presenter scene with character details
    seed = None
    for sc in presenter_scenes:
        if sc.get("source_character_details") or sc.get("character_details"):
            seed = sc
            break
    if seed is None:
        seed = presenter_scenes[0]
    char = str(seed.get("source_character_details") or seed.get("character_details") or "").strip()
    if char.lower() in ("none", "n/a", "na", "no character", "-", "null"):
        char = ""
    if not char:
        logger.info("Presenter shots lack character_details — skip character_reference")
        return None
    light = str(seed.get("source_lighting") or seed.get("lighting") or "").strip()
    bg = str(seed.get("source_background") or "").strip()
    prompt = (
        f"CHARACTER REFERENCE SHEET, front-facing portrait, neutral pose, "
        f"CHARACTER LOCK: {char}. "
        f"LIGHTING: {light or 'clean studio key light'}. "
        f"BACKGROUND: {bg or 'simple neutral backdrop'}. "
        f"Art style: {art}. Identical face, hair, wardrobe for later shot matching. "
        f"Aspect {aspect}. No text, no watermark."
    )
    try:
        res = generate_image_with_fallback(prompt, ref, aspect=aspect, stock_query="portrait young man studio")
        if res.get("ok") and Path(res["path"]).is_file():
            logger.info("Character reference ready → %s", ref.name)
            return Path(res["path"])
    except Exception as exc:
        logger.warning("character reference failed: %s", exc)
    return None


def _quality_tier(provider: str, fallback: bool = False) -> str:
    p = (provider or "").lower()
    if fallback or "stock" in p or "kenburns" in p or "pexels" in p or "pixabay" in p:
        return "degraded"
    if p in ("agnes", "kling", "google", "pollinations", "openrouter", "luma", "seedance"):
        return "ai_primary"
    return "ai_fallback"


def generate_shared_media(
    package_root: Path | str,
    *,
    max_shots: Optional[int] = None,
    force: bool = False,
    job_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create shared stills + master clips. Resume-safe via media_generation_state.json."""
    pkg = Path(package_root)
    paths = open_package(pkg)
    plan = _load_plan(pkg)
    meta = plan.get("production_metadata") or {}
    aspect = str(meta.get("aspect_ratio") or "9:16")
    art = str(meta.get("art_style") or "Cinematic Hyper-realistic")
    scenes = [s for s in (plan.get("render_scenes") or []) if isinstance(s, dict)]
    scenes = [_enrich_scene_from_script(pkg, s) for s in scenes]
    if max_shots is None:
        raw = (os.environ.get("AMP_MEDIA_MAX_SHOTS") or "").strip()
        if raw.isdigit():
            max_shots = int(raw)
    if max_shots:
        scenes = scenes[: int(max_shots)]

    state = _load_state(paths)
    shot_state: Dict[str, Any] = dict(state.get("shots") or {})
    results: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    degraded: List[Dict[str, Any]] = []

    pkg_seed = package_seed(pkg)
    w, h = canvas_for_aspect(aspect)
    paths.image.mkdir(parents=True, exist_ok=True)
    paths.video_clips.mkdir(parents=True, exist_ok=True)

    char_ref = _ensure_character_reference(pkg, paths, scenes, aspect=aspect, art=art)
    if job_state is not None and char_ref:
        job_state.setdefault("character_reference", str(char_ref))

    visual_mode = resolve_media_visual_mode()
    state["package_seed"] = pkg_seed
    state["visual_mode"] = visual_mode
    logger.info(
        "Media continuity seed=%s mode=%s char_ref=%s",
        pkg_seed,
        visual_mode,
        char_ref.name if char_ref else None,
    )

    try:
        from pipeline.custom_pipeline.media_gap import set_media_gap_package

        set_media_gap_package(str(pkg), job_state)
    except Exception:
        pass

    for sc in scenes:
        try:
            n = int(sc.get("shot_number") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        key = f"S{n:02d}"
        prev = shot_state.get(key) or {}
        img_out = paths.image / f"{key}.png"
        vid_out = paths.video_clips / f"{key}.mp4"
        rtype_raw = str(sc.get("render_type") or "IMAGE").upper().strip()
        rtype = apply_visual_mode_to_render_type(rtype_raw, visual_mode)
        dur = float(sc.get("shot_duration_seconds") or 6)
        motion = sc.get("motion_directives") if isinstance(sc.get("motion_directives"), dict) else {}
        s_seed = shot_seed(pkg_seed, n)

        if (
            not force
            and prev.get("ok")
            and Path(prev.get("video_path") or "").is_file()
            and Path(prev.get("video_path") or "").stat().st_size > 5000
        ):
            logger.info("Media shot %s already done — skip (resume)", key)
            results.append(prev)
            if prev.get("quality") == "degraded" or prev.get("fallback"):
                degraded.append({"shot": key, "provider": prev.get("provider")})
            continue

        entry: Dict[str, Any] = {
            "shot_number": n,
            "render_type": rtype,
            "render_type_planned": rtype_raw,
            "ok": False,
            "character_reference": str(char_ref) if char_ref else None,
            "package_seed": pkg_seed,
            "shot_seed": s_seed,
        }
        try:
            if job_state is not None:
                from pipeline.custom_pipeline.job_budget import ensure_budget, record_spend
                from pipeline.custom_pipeline.job_state import heartbeat, set_progress
                from pipeline.custom_pipeline.pipeline_control import check_cancelled

                check_cancelled(pkg, job_state)
                ensure_budget(
                    job_state,
                    kind="video" if rtype in ("VIDEO", "STOCK_VIDEO") else "image",
                )
                set_progress(
                    job_state,
                    60 + 25 * (len(results) / max(1, len(scenes))),
                    f"media {key} {rtype}",
                )
                heartbeat(pkg, job_state, f"media {key} {rtype}")
                logger.info("Media shot start %s type=%s seed=%s", key, rtype, s_seed)

            narr = _narration_for_shot(pkg, n, sc)
            from pipeline.custom_pipeline.av_match_gate import (
                brand_ui_stock_query,
                ensure_prompt_av_ready,
                evaluate_generated_asset,
                extract_must_show,
                max_local_regen,
                merge_gate_with_vision,
                stock_forbidden_for_shot,
            )
            from pipeline.custom_pipeline.media_prompts import resolve_scene_subject
            from pipeline.custom_pipeline.pipeline_learning import (
                LESSON_BRAND_UI_NO_STOCK,
                record_lesson,
                seed_known_lessons_from_live004,
            )
            from pipeline.custom_pipeline.visual_subject_policy import character_allowed

            niche = str(sc.get("niche") or sc.get("package_niche") or "")
            topic = str(sc.get("topic") or sc.get("package_topic") or pkg.name)
            sc["niche"] = niche
            sc["topic"] = topic

            subject = resolve_scene_subject(sc, narration_text=narr)
            sc["visual_subject"] = subject
            entry["visual_subject"] = subject
            must_show = extract_must_show(
                narr, visual_subject=subject, niche=niche, topic=topic
            )
            entry["must_show"] = must_show
            forbid_stock = stock_forbidden_for_shot(
                visual_subject=subject, narration=narr, niche=niche, topic=topic
            )
            if forbid_stock and rtype == "STOCK_VIDEO":
                if visual_mode == "video_only":
                    logger.info("%s STOCK_VIDEO preserved as VIDEO for AI chain (Google Pro/video_only active)", key)
                    rtype = "VIDEO"
                    entry["render_type"] = rtype
                else:
                    logger.warning(
                        "%s STOCK_VIDEO rewritten → IMAGE (brand UI cannot use stock)", key
                    )
                    rtype = "IMAGE"
                    entry["render_type"] = rtype
                    entry["render_type_rewritten_from"] = "STOCK_VIDEO"
                    record_lesson(
                        kind=LESSON_BRAND_UI_NO_STOCK,
                        title="STOCK_VIDEO rewritten to IMAGE for brand UI",
                        detail=f"{key} wanted ChatGPT/settings UI; stock forbidden.",
                        fix="Force AI IMAGE + Ken Burns for product_ui/hands_ui.",
                        package_root=pkg,
                        meta={"shot": key, "subject": subject},
                    )

            stock_q = (
                brand_ui_stock_query(narr)
                if forbid_stock
                else (av_matched_stock_query(narr, sc) or stock_search_query(sc))
            )
            use_char_ref = bool(char_ref) and character_allowed(subject)
            if use_char_ref:
                ref_note = (
                    f" Match character_reference identity exactly ({char_ref.name}). "
                    f"{seed_lock_prompt_suffix(s_seed, character_ref_name=char_ref.name)}."
                )
            else:
                ref_note = (
                    f" {seed_lock_prompt_suffix(s_seed, character_ref_name='')}."
                    if character_allowed(subject) and subject == "presenter"
                    else f" SEED LOCK {s_seed}: consistent scene environment, color grade, and lighting — strictly NO human face, NO portrait."
                )
            regen_budget = max_local_regen()
            pkg_id = pkg.name

            def _run_vision_if_needed(gate: Dict[str, Any], image_path: Path) -> Dict[str, Any]:
                """Thrifty AI critic — only when local gate / auto policy says so."""
                try:
                    from pipeline.custom_pipeline.av_vision_critic import (
                        critique_frame_vs_dialogue,
                        should_run_vision,
                    )

                    if not should_run_vision(
                        heuristic_ok=bool(gate.get("ok")),
                        visual_subject=subject,
                        provider=str(gate.get("provider") or ""),
                        fallback=bool(gate.get("fallback")),
                        package_id=pkg_id,
                        shot_key=key,
                    ):
                        return gate
                    if not image_path.is_file():
                        return gate
                    vision = critique_frame_vs_dialogue(
                        image_path,
                        narration=narr,
                        must_show=must_show,
                        visual_subject=subject,
                        package_id=pkg_id,
                        shot_key=key,
                    )
                    return merge_gate_with_vision(gate, vision)
                except Exception as exc:
                    logger.debug("vision critic skipped: %s", exc)
                    return gate

            if rtype in ("VIDEO", "STOCK_VIDEO"):
                raw_prompt = (
                    build_detailed_media_prompt(
                        sc,
                        aspect_ratio=aspect,
                        art_style=art,
                        for_video=True,
                        narration_text=narr,
                    )
                    + ref_note
                )
                pre = ensure_prompt_av_ready(
                    raw_prompt,
                    narr,
                    visual_subject=subject,
                    niche=niche,
                    topic=topic,
                )
                prompt = pre["prompt"]

                # ── Stage B: Pre-Generation Dual Prompt Clearance Gate ──
                from pipeline.custom_pipeline.visual_intelligence import verify_prompt_dual_clearance
                clearance = verify_prompt_dual_clearance(
                    sc, prompt, narr, for_video=True, aspect_ratio=aspect, art_style=art
                )
                prompt = clearance["verified_prompt"]
                entry["prompt_clearance"] = clearance
                logger.info(
                    "Shot %s Stage B Dual Prompt Clearance: %s (Domain: %s, Score: %.2f, Words: %d)",
                    key,
                    clearance["clearance"],
                    clearance["thematic_domain"],
                    clearance.get("alignment_score", 1.0),
                    clearance.get("word_count", 0),
                )

                entry["av_preflight"] = {
                    "ok": pre.get("ok"),
                    "alignment": pre.get("alignment"),
                }
                img_fb_pre = ensure_prompt_av_ready(
                    build_detailed_media_prompt(
                        sc,
                        aspect_ratio=aspect,
                        art_style=art,
                        for_video=False,
                        narration_text=narr,
                    )
                    + ref_note,
                    narr,
                    visual_subject=subject,
                    niche=niche,
                    topic=topic,
                )
                img_fb_clearance = verify_prompt_dual_clearance(
                    sc, img_fb_pre["prompt"], narr, for_video=False, aspect_ratio=aspect, art_style=art
                )
                vres = generate_video_with_fallback(
                    prompt,
                    vid_out,
                    aspect=aspect,
                    duration=dur,
                    stock_query=stock_q,
                    image_fallback_prompt=img_fb_clearance["verified_prompt"],
                    kenburns_filter=str(motion.get("ffmpeg_filter") or ""),
                    shot_key=key,
                    seed=s_seed,
                    prefer_stock_video=(
                        (rtype == "STOCK_VIDEO" or visual_mode == "prefer_stock_video")
                        and not forbid_stock
                    ),
                    allow_stock=not forbid_stock,
                )
                gate = evaluate_generated_asset(
                    provider=str(vres.get("provider") or ""),
                    fallback=bool(vres.get("fallback")),
                    prompt=prompt,
                    stock_query=stock_q,
                    narration=narr,
                    visual_subject=subject,
                    niche=niche,
                    topic=topic,
                )
                gate["provider"] = vres.get("provider")
                gate["fallback"] = vres.get("fallback")
                # Poster for vision (if video ok)
                poster_for_vision = img_out
                if vres.get("ok") and Path(vres.get("path") or "").is_file():
                    try:
                        _extract_poster(Path(vres["path"]), img_out)
                    except Exception:
                        pass
                gate = _run_vision_if_needed(gate, poster_for_vision)
                entry["av_gate"] = gate
                is_stock_clip = vres.get("provider") in ("pexels_stock", "pixabay_stock") or bool(vres.get("fallback"))
                if vres.get("ok") and not gate.get("ok") and regen_budget > 0:
                    if visual_mode == "video_only" and not is_stock_clip:
                        logger.info(
                            "%s AV gate note (%s), but visual_mode is video_only — keeping AI video clip",
                            key,
                            gate.get("reasons"),
                        )
                    else:
                        logger.warning(
                            "%s AV gate FAIL %s — AI regen (budget=%s)",
                            key,
                            gate.get("reasons"),
                            regen_budget,
                        )
                        record_lesson(
                            kind=LESSON_BRAND_UI_NO_STOCK,
                            title="AV gate rejected weak/stock brand UI clip",
                            detail="; ".join(gate.get("reasons") or []),
                            fix="Regenerate AI IMAGE + kenburns, allow_stock=False (max 1)",
                            package_root=pkg,
                            meta={"shot": key, "gate": gate},
                        )
                        raw_regen_p = (
                            build_detailed_media_prompt(
                                sc,
                                aspect_ratio=aspect,
                                art_style=art,
                                for_video=False,
                                narration_text=narr,
                            )
                            + ref_note
                        )
                        regen_pre = ensure_prompt_av_ready(
                            raw_regen_p,
                            narr,
                            visual_subject=subject,
                            niche=niche,
                            topic=topic,
                        )
                        regen_clearance = verify_prompt_dual_clearance(
                            sc, regen_pre["prompt"], narr, for_video=False, aspect_ratio=aspect, art_style=art
                        )
                        img_prompt = regen_clearance["verified_prompt"]
                        ires = generate_image_with_fallback(
                            img_prompt,
                            img_out,
                            aspect=aspect,
                            stock_query=stock_q,
                            seed=s_seed,
                            allow_stock=False,
                        )
                        if ires.get("ok") and Path(ires["path"]).is_file():
                            kb = ken_burns_from_image(
                                Path(ires["path"]),
                                vid_out,
                                duration=dur,
                                w=w,
                                h=h,
                                ffmpeg_filter=str(motion.get("ffmpeg_filter") or ""),
                                shot_number=n,
                            )
                            if kb and Path(kb).is_file():
                                vres = {
                                    "ok": True,
                                    "path": str(kb),
                                    "provider": f"avgate_regen:{ires.get('provider')}+kenburns",
                                    "fallback": False,
                                    "seed": s_seed,
                                }
                                gate2 = evaluate_generated_asset(
                                    provider=str(vres.get("provider") or ""),
                                    fallback=False,
                                    prompt=img_prompt,
                                    stock_query=stock_q,
                                    narration=narr,
                                    visual_subject=subject,
                                    niche=niche,
                                    topic=topic,
                                )
                                entry["av_gate_after_regen"] = gate2
                entry.update(vres)
                entry["video_path"] = vres.get("path")
                entry["prompt_chars"] = len(prompt)
                entry["prompt_words"] = len(prompt.split())
                entry["prompt_preview"] = prompt[:500]
                entry["prompt_audit"] = prompt_audit(sc, prompt)
                entry["narration_beat"] = narr
                entry["stock_query"] = stock_q
                if vres.get("ok") and Path(vres["path"]).is_file():
                    _extract_poster(Path(vres["path"]), img_out)
                    entry["image_path"] = str(img_out) if img_out.exists() else None
                if job_state is not None:
                    from pipeline.custom_pipeline.job_budget import record_spend

                    record_spend(
                        job_state,
                        kind="stock" if vres.get("fallback") else "video",
                        provider=str(vres.get("provider") or ""),
                    )
            else:
                # IMAGE: multi-still (2–3) seed-locked beats → Ken Burns → concat
                n_frames = frames_for_duration(dur)
                # Allow plan override
                try:
                    planned = int(sc.get("image_frame_count") or 0)
                    if planned:
                        n_frames = max(1, min(3, planned))
                except (TypeError, ValueError):
                    pass
                beats = split_narration_beats(narr, n_frames)
                still_paths: List[Path] = []
                frame_meta: List[Dict[str, Any]] = []
                prev_beat = ""
                providers_used: List[str] = []
                for fi, beat in enumerate(beats):
                    f_seed = shot_seed(pkg_seed, n, frame_index=fi)
                    raw_f = (
                        beat_visual_prompt(
                            base_scene={**sc, "aspect_ratio": aspect},
                            beat_text=beat,
                            frame_index=fi,
                            total_frames=n_frames,
                            package_seed_val=pkg_seed,
                            prev_beat=prev_beat,
                            art_style=art,
                        )
                        + ref_note
                    )
                    pre_f = ensure_prompt_av_ready(
                        raw_f,
                        beat,
                        visual_subject=subject,
                        niche=niche,
                        topic=topic,
                    )
                    from pipeline.custom_pipeline.visual_intelligence import verify_prompt_dual_clearance
                    f_clearance = verify_prompt_dual_clearance(
                        sc, pre_f["prompt"], beat, for_video=False, aspect_ratio=aspect, art_style=art
                    )
                    f_prompt = f_clearance["verified_prompt"]
                    frame_out = paths.image / f"{key}_f{fi + 1:02d}.png"
                    ires = generate_image_with_fallback(
                        f_prompt,
                        frame_out,
                        aspect=aspect,
                        stock_query=av_matched_stock_query(beat, sc) or stock_q,
                        seed=f_seed,
                        allow_stock=not forbid_stock,
                    )
                    fgate = evaluate_generated_asset(
                        provider=str(ires.get("provider") or ""),
                        fallback=bool(ires.get("fallback")),
                        prompt=f_prompt,
                        stock_query=stock_q,
                        narration=beat,
                        visual_subject=subject,
                        niche=niche,
                        topic=topic,
                    )
                    fgate["provider"] = ires.get("provider")
                    fgate["fallback"] = ires.get("fallback")
                    if ires.get("ok") and Path(ires.get("path") or "").is_file():
                        fgate = _run_vision_if_needed(fgate, Path(ires["path"]))
                    # At most ONE local regen per frame (API thrift)
                    if (
                        ires.get("ok")
                        and not fgate.get("ok")
                        and regen_budget > 0
                    ):
                        f_pre2 = ensure_prompt_av_ready(
                            f_prompt,
                            beat,
                            visual_subject=subject,
                            niche=niche,
                            topic=topic,
                        )
                        f_clearance2 = verify_prompt_dual_clearance(
                            sc, f_pre2["prompt"], beat, for_video=False, aspect_ratio=aspect, art_style=art
                        )
                        f_prompt2 = f_clearance2["verified_prompt"]
                        ires = generate_image_with_fallback(
                            f_prompt2,
                            frame_out,
                            aspect=aspect,
                            stock_query=stock_q,
                            seed=f_seed,
                            allow_stock=False,
                        )
                        f_prompt = f_prompt2
                        record_lesson(
                            kind=LESSON_BRAND_UI_NO_STOCK,
                            title="Frame AV gate forced AI retry",
                            detail=str(fgate.get("reasons")),
                            fix="allow_stock=False + strengthen must_show (max 1 regen)",
                            package_root=pkg,
                            meta={"shot": key, "frame": fi, "gate": fgate},
                        )
                        fgate2 = evaluate_generated_asset(
                            provider=str(ires.get("provider") or ""),
                            fallback=bool(ires.get("fallback")),
                            prompt=f_prompt,
                            stock_query=stock_q,
                            narration=beat,
                            visual_subject=subject,
                            niche=niche,
                            topic=topic,
                        )
                        fgate = fgate2
                    if not ires.get("ok"):
                        # Fall back to primary single image once
                        if fi == 0:
                            raise RuntimeError(f"image failed: {ires.get('errors')}")
                        break
                    # Upscale to canvas for quality parity with Agnes
                    hq = paths.image / f"{key}_f{fi + 1:02d}_hq.png"
                    up = upscale_still_to_canvas(Path(ires["path"]), hq, w=w, h=h)
                    still_paths.append(up or Path(ires["path"]))
                    providers_used.append(str(ires.get("provider") or ""))
                    frame_meta.append(
                        {
                            "index": fi,
                            "beat": beat[:160],
                            "seed": f_seed,
                            "path": str(still_paths[-1]),
                            "provider": ires.get("provider"),
                            "av_gate": fgate,
                            "av_preflight": pre_f.get("alignment"),
                        }
                    )
                    prev_beat = beat
                    if job_state is not None:
                        from pipeline.custom_pipeline.job_budget import record_spend

                        record_spend(
                            job_state,
                            kind="stock" if ires.get("fallback") else "image",
                            provider=str(ires.get("provider") or ""),
                        )

                if not still_paths:
                    raise RuntimeError("no stills generated")

                # Primary poster = first frame
                import shutil

                shutil.copy2(still_paths[0], img_out)

                if len(still_paths) == 1:
                    kb = ken_burns_from_image(
                        still_paths[0],
                        vid_out,
                        duration=dur,
                        w=w,
                        h=h,
                        ffmpeg_filter=str(motion.get("ffmpeg_filter") or ""),
                        motion_preset=str(motion.get("motion_preset") or ""),
                        shot_number=n,
                    )
                    if not kb:
                        raise RuntimeError("kenburns failed for IMAGE shot")
                    entry["video_path"] = str(kb)
                    entry["provider"] = f"image:{providers_used[0]}+kenburns"
                else:
                    multi = build_multi_still_master(
                        still_paths,
                        vid_out,
                        total_duration=dur,
                        w=w,
                        h=h,
                        shot_number=n,
                        motion_preset=str(motion.get("motion_preset") or ""),
                    )
                    if not multi.get("ok"):
                        raise RuntimeError(f"multi-still failed: {multi.get('error')}")
                    entry["video_path"] = multi["path"]
                    entry["provider"] = (
                        f"image:multi{len(still_paths)}:"
                        f"{'+'.join(dict.fromkeys(providers_used))}+kenburns"
                    )
                    entry["multi_still"] = multi

                entry["ok"] = True
                entry["image"] = {"frames": frame_meta, "primary": str(img_out)}
                entry["image_path"] = str(img_out)
                entry["image_frame_count"] = len(still_paths)
                entry["prompt_chars"] = sum(len(str(f.get("beat") or "")) for f in frame_meta)
                entry["prompt_words"] = len(narr.split())
                entry["prompt_preview"] = (beats[0] if beats else narr)[:500]
                entry["prompt_audit"] = prompt_audit(
                    sc,
                    beat_visual_prompt(
                        base_scene={**sc, "aspect_ratio": aspect},
                        beat_text=beats[0] if beats else narr,
                        frame_index=0,
                        total_frames=n_frames,
                        package_seed_val=pkg_seed,
                        art_style=art,
                    ),
                )
                entry["narration_beat"] = narr
                entry["fallback"] = any("stock" in (p or "") for p in providers_used)

            prov = str(entry.get("provider") or "")
            entry["quality"] = _quality_tier(prov, bool(entry.get("fallback")))
            if entry["quality"] == "degraded":
                degraded.append({"shot": key, "provider": prov})
                if job_state is not None:
                    from pipeline.custom_pipeline.job_state import mark_degraded

                    mark_degraded(job_state, key, prov, reason="fallback_or_stock")

            if entry.get("video_path") and Path(entry["video_path"]).is_file():
                entry["ok"] = True
                # Agnes/talking models: extract EN audio + silence master (prevent BN bleed)
                try:
                    from pipeline.custom_pipeline.master_audio import sanitize_master_clip

                    san = sanitize_master_clip(
                        Path(entry["video_path"]),
                        shot_key=key,
                        video_clips_dir=paths.video_clips,
                        provider=str(entry.get("provider") or ""),
                    )
                    entry["native_audio"] = san
                    if san.get("native_audio_path"):
                        shot_state[key] = entry  # keep path for EN TTS skip
                except Exception as san_exc:
                    logger.warning("master audio sanitize %s: %s", key, san_exc)
            else:
                entry["ok"] = False
                errors[key] = str(entry.get("errors") or "no video")
        except Exception as exc:
            logger.exception("Shared media failed %s", key)
            entry["ok"] = False
            entry["error"] = str(exc)
            errors[key] = str(exc)

        shot_state[key] = entry
        state["shots"] = shot_state
        state["character_reference"] = str(char_ref) if char_ref else None
        _save_state(paths, state)
        results.append(entry)
        logger.info(
            "Shared media %s type=%s ok=%s provider=%s quality=%s words=%s",
            key,
            rtype,
            entry.get("ok"),
            entry.get("provider"),
            entry.get("quality"),
            entry.get("prompt_words"),
        )

        # Post-generation randomized cooldown between clips/stills to protect API limits
        if entry.get("ok"):
            try:
                from pipeline.custom_pipeline.google_pacing_guard import post_generation_cooldown

                post_modality = "video" if rtype in ("VIDEO", "STOCK_VIDEO") else "image"
                post_generation_cooldown(
                    modality=post_modality,
                    provider=str(entry.get("provider") or "media"),
                    package_root=str(pkg),
                    state=job_state,
                )
            except Exception as post_exc:
                logger.debug("Post-generation cooldown error: %s", post_exc)

    summary = {
        "ok": not errors and len(results) == len(scenes) and all(r.get("ok") for r in results),
        "partial": bool(results) and (bool(errors) or any(not r.get("ok") for r in results)),
        "package_root": str(pkg),
        "aspect_ratio": aspect,
        "shot_count": len(scenes),
        "success_count": sum(1 for r in results if r.get("ok")),
        "errors": errors,
        "shots": results,
        "degraded": degraded,
        "character_reference": str(char_ref) if char_ref else None,
        "image_dir": str(paths.image),
        "video_clips_dir": str(paths.video_clips),
    }
    write_json(paths.file_dir / "media_shared_manifest.json", summary)
    return summary


def _extract_poster(video: Path, image_out: Path) -> None:
    try:
        from pipeline.compose import ffmpeg_bin

        ff = ffmpeg_bin()
    except Exception:
        ff = "ffmpeg"
    image_out.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    cmd = [ff, "-y", "-i", str(video), "-ss", "0.3", "-frames:v", "1", str(image_out)]
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
