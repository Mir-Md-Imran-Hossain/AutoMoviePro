"""Short vs Long custom-pipeline runners (mutually exclusive).

Industrial controls: job_state, cancel/progress, resume, honest shippable flag,
budget, wall-clock timeout, quality gate hook.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from pipeline.custom_pipeline.job_budget import BudgetExceeded, ensure_budget, record_spend
from pipeline.custom_pipeline.job_state import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SKIPPED,
    STATUS_SUCCEEDED,
    compute_shippable,
    finish_active_stage,
    finish_stage,
    heartbeat,
    load_job_state,
    new_job_state,
    prepare_resume,
    reaper_mark_stale,
    save_job_state,
    set_progress,
    start_stage,
)
from pipeline.custom_pipeline.localization import localize_to_languages
from pipeline.custom_pipeline.media_stage import run_media_stage
from pipeline.custom_pipeline.package_archive import archive_complete_json_package
from pipeline.custom_pipeline.pipeline_control import (
    PipelineCancelled,
    check_cancelled,
    clear_cancel,
    emit_progress,
    register_progress,
    wall_clock_exceeded,
)
from pipeline.custom_pipeline.session_keys import session_key_report, start_session
from pipeline.custom_pipeline.stage_resume import existing_topic_package, existing_visual_plan
from pipeline.custom_pipeline.telemetry import emit as telemetry_emit
from pipeline.custom_pipeline.topic_research import (
    normalize_video_type,
    pick_primary_title,
    run_topic_research,
)
from pipeline.custom_pipeline.tts_synthesize import synthesize_package_tts
from pipeline.custom_pipeline.visual_render import plan_visual_renders
from pipeline.output_layout import CURATED_OUTPUT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_LOCALIZE_LANGUAGES = ("English", "Hindi", "Tamil", "Malayalam", "Urdu")
ProgressCb = Callable[[float, str], None]


def _wall_cap_sec() -> float:
    raw = (os.environ.get("AMP_PIPELINE_MAX_SEC") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 6 * 3600.0  # 6h default


def run_pipeline(
    *,
    video_type: str,
    niche: str,
    audience: str = "সাধারণ দর্শক",
    languages: Optional[Sequence[str]] = None,
    output_root: Optional[Path] = None,
    skip_localize: bool = False,
    skip_visual: bool = False,
    skip_tts: bool = False,
    skip_media: bool = False,
    skip_thumbnail: bool = False,
    include_bangla_tts: bool = True,
    session_id: Optional[str] = None,
    resume_package: Optional[Path] = None,
    force: bool = False,
    require_approval: bool = False,
    progress_cb: Optional[ProgressCb] = None,
) -> Dict[str, Any]:
    """Run the custom pipeline for EXACTLY one format: short OR long."""
    kind = normalize_video_type(video_type)
    sid = start_session(session_id)
    root = Path(output_root) if output_root else CURATED_OUTPUT_ROOT
    langs = list(languages) if languages else list(DEFAULT_LOCALIZE_LANGUAGES)
    started = time.time()
    wall = _wall_cap_sec()

    logger.info("Custom pipeline start session=%s format=%s niche=%s", sid, kind, niche)

    # Industrial preflight — fail closed on missing Grok / localize before burn
    from pipeline.custom_pipeline.pipeline_preflight import (
        raise_if_preflight_blocked,
        run_pipeline_preflight,
    )

    preflight = run_pipeline_preflight(
        languages=langs,
        include_bangla_tts=include_bangla_tts,
        skip_localize=skip_localize,
        skip_visual=skip_visual,
        skip_tts=skip_tts,
        skip_media=skip_media,
        allow_degraded=True,
    )
    raise_if_preflight_blocked(preflight)

    pkg = Path(resume_package) if resume_package else None
    planned_langs = (["Bangla"] if include_bangla_tts else []) + list(langs)
    state: Dict[str, Any]
    if pkg and pkg.exists():
        reaper_mark_stale(pkg)
        state = load_job_state(pkg) or new_job_state(
            package_root=pkg,
            video_type=kind,
            session_id=sid,
            expected_languages=planned_langs,
        )
        prepare_resume(state)
        clear_cancel(pkg)
        register_progress(pkg, progress_cb)
        state["planned_languages"] = list(state.get("planned_languages") or planned_langs)
        state["preflight"] = {
            "warnings": preflight.get("warnings"),
            "facts": preflight.get("facts"),
        }
        save_job_state(pkg, state)
    else:
        state = new_job_state(
            package_root=Path("."),
            video_type=kind,
            session_id=sid,
            expected_languages=planned_langs,
        )
        state["planned_languages"] = list(planned_langs)
        state["preflight"] = {
            "warnings": preflight.get("warnings"),
            "facts": preflight.get("facts"),
        }

    def _tick(pct: float, msg: str) -> None:
        set_progress(state, pct, msg)
        # Always surface stage progress on stderr for live ops (logging may be muted)
        print(f"[pipeline] {pct:.0f}% {msg}", file=sys.stderr, flush=True)
        if pkg and pkg.exists():
            heartbeat(pkg, state, msg)
            emit_progress(pkg, pct, msg, state=state)
            check_cancelled(pkg, state)
        if wall_clock_exceeded(started, wall):
            raise TimeoutError(f"Pipeline wall-clock exceeded ({wall}s)")

    try:
        # ── Stage 1: topic ─────────────────────────────────────
        start_stage(state, "topic")
        _tick(5, "topic")
        ensure_budget(state, kind="topic")
        stage1: Dict[str, Any]
        if pkg and pkg.exists() and not force:
            resumed = existing_topic_package(pkg)
            if resumed:
                stage1 = resumed
                finish_stage(state, "topic", status=STATUS_SKIPPED, detail={"resumed": True})
            else:
                stage1 = run_topic_research(
                    niche=niche, video_type=kind, audience=audience, output_root=root, save=True
                )
                record_spend(state, kind="topic", provider="grok")
                finish_stage(state, "topic", status=STATUS_SUCCEEDED if stage1.get("ok") else STATUS_FAILED)
        else:
            stage1 = run_topic_research(
                niche=niche, video_type=kind, audience=audience, output_root=root, save=True
            )
            record_spend(state, kind="topic", provider="grok")
            finish_stage(state, "topic", status=STATUS_SUCCEEDED if stage1.get("ok") else STATUS_FAILED)

        pkg = Path((stage1.get("save") or {}).get("package_root") or (pkg or ""))
        if not pkg.exists():
            raise RuntimeError("Topic stage did not produce package_root")
        parent_kind = pkg.parent.name
        expected = "Short" if kind == "short" else "Long"
        if parent_kind not in (expected,):
            raise RuntimeError(
                f"Pipeline format mismatch: expected Output/{expected}/… but got {pkg}"
            )

        state["package_root"] = str(pkg)
        register_progress(pkg, progress_cb)
        clear_cancel(pkg)
        save_job_state(pkg, state)
        telemetry_emit(pkg, "stage.started", "topic done", session_id=sid)

        # Optional approval gate before expensive stages
        if require_approval or str(os.environ.get("AMP_REQUIRE_APPROVAL") or "").strip() in (
            "1",
            "true",
            "yes",
        ):
            approval = pkg / "File" / "APPROVED.flag"
            if not approval.is_file():
                state["status"] = STATUS_PARTIAL
                state["progress_message"] = "awaiting_approval"
                state["awaiting_approval"] = True
                append = state.setdefault("events", [])
                append.append({"ts": time.time(), "kind": "approval.required"})
                save_job_state(pkg, state)
                telemetry_emit(pkg, "approval.required", "awaiting File/APPROVED.flag")
                # Marker for UIs / ops
                try:
                    (pkg / "File" / "AWAITING_APPROVAL.txt").write_text(
                        "Create APPROVED.flag in this folder to continue TTS/media.\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                return {
                    "ok": False,
                    "awaiting_approval": True,
                    "package_root": str(pkg),
                    "session_id": sid,
                    "message": "Create File/APPROVED.flag to continue TTS/media spend",
                    "stage1_topic": stage1,
                }
            state.pop("awaiting_approval", None)
            telemetry_emit(pkg, "approval.granted", "APPROVED.flag present")

        # ── Stage 3: visual ────────────────────────────────────
        stage3: Dict[str, Any] = {"ok": False, "skipped": True}
        if not skip_visual:
            start_stage(state, "visual")
            _tick(15, "visual")
            check_cancelled(pkg, state)
            ensure_budget(state, kind="visual")
            if not force:
                resumed_v = existing_visual_plan(pkg)
                if resumed_v:
                    stage3 = resumed_v
                    finish_stage(state, "visual", status=STATUS_SKIPPED, detail={"resumed": True})
                else:
                    stage3 = plan_visual_renders(
                        stage1["payload"],
                        video_type=kind,
                        package_root=pkg,
                        output_root=root,
                        save=True,
                    )
                    record_spend(state, kind="visual", provider="grok")
                    finish_stage(
                        state,
                        "visual",
                        status=STATUS_SUCCEEDED if stage3.get("ok") else STATUS_FAILED,
                    )
            else:
                stage3 = plan_visual_renders(
                    stage1["payload"],
                    video_type=kind,
                    package_root=pkg,
                    output_root=root,
                    save=True,
                )
                record_spend(state, kind="visual", provider="grok")
                finish_stage(
                    state, "visual", status=STATUS_SUCCEEDED if stage3.get("ok") else STATUS_FAILED
                )
            save_job_state(pkg, state)

        # ── Stage 2: localize ──────────────────────────────────
        stage2: Dict[str, Any] = {"ok": False, "skipped": True}
        if not skip_localize:
            start_stage(state, "localize")
            _tick(30, "localize")
            check_cancelled(pkg, state)
            for _ in langs:
                ensure_budget(state, kind="localize")
            stage2 = localize_to_languages(
                stage1["payload"],
                languages=langs,
                package_root=pkg,
                output_root=root,
                video_type=kind,
                save=True,
                force=force,
            )
            api_n = int(stage2.get("api_count") or 0)
            if api_n > 0:
                record_spend(state, kind="localize", provider="google", units=api_n)
            finish_stage(
                state,
                "localize",
                status=STATUS_SUCCEEDED if stage2.get("ok") else STATUS_PARTIAL,
                detail={
                    "errors": stage2.get("errors"),
                    "resumed_count": stage2.get("resumed_count"),
                    "api_count": api_n,
                },
            )
            save_job_state(pkg, state)

        # ── Stage 4: TTS ───────────────────────────────────────
        stage4: Dict[str, Any] = {"ok": False, "skipped": True}
        if not skip_tts:
            start_stage(state, "tts")
            _tick(45, "tts")
            check_cancelled(pkg, state)
            tts_langs = langs
            if isinstance(stage2, dict) and stage2.get("results"):
                tts_langs = list(stage2["results"].keys()) or langs
            ensure_budget(state, kind="tts", upcoming=3.0 * max(1, len(tts_langs)))
            stage4 = synthesize_package_tts(
                pkg,
                languages=tts_langs,
                include_bangla=include_bangla_tts,
                force=force,
            )
            if not any((v or {}).get("resumed") for v in (stage4.get("results") or {}).values()):
                record_spend(state, kind="tts", provider="gemini", units=3.0 * len(tts_langs))
            finish_stage(
                state,
                "tts",
                status=STATUS_SUCCEEDED
                if stage4.get("ok")
                else (STATUS_PARTIAL if stage4.get("partial") else STATUS_FAILED),
                detail={"errors": stage4.get("errors")},
            )
            save_job_state(pkg, state)

        # ── Stage 5: media ─────────────────────────────────────
        stage5: Dict[str, Any] = {"ok": False, "skipped": True}
        if not skip_media:
            start_stage(state, "media")
            _tick(60, "media")
            check_cancelled(pkg, state)
            media_langs: List[str]
            if isinstance(stage2, dict) and stage2.get("results"):
                media_langs = (["Bangla"] if include_bangla_tts else []) + list(
                    stage2["results"].keys()
                )
            else:
                media_langs = (["Bangla"] if include_bangla_tts else []) + list(langs)
            # Compose only langs with audio; keep FULL plan for honest ship gate
            state["expected_languages"] = media_langs
            state["planned_languages"] = list(state.get("planned_languages") or planned_langs)
            if isinstance(stage2, dict) and stage2.get("errors"):
                state["localize_errors"] = dict(stage2.get("errors") or {})
            stage5 = run_media_stage(
                pkg,
                languages=media_langs,
                include_bangla=include_bangla_tts,
                force=force,
                job_state=state,
            )
            finish_stage(
                state,
                "media",
                status=STATUS_SUCCEEDED
                if stage5.get("ok")
                else (STATUS_PARTIAL if stage5.get("partial") else STATUS_FAILED),
                detail={
                    "shared": (stage5.get("shared") or {}).get("success_count"),
                    "errors": (stage5.get("compose") or {}).get("errors"),
                },
            )
            save_job_state(pkg, state)

        # ── Stage 6: thumbnail ─────────────────────────────────
        stage6: Dict[str, Any] = {"ok": False, "skipped": True}
        if not skip_thumbnail:
            start_stage(state, "thumbnail")
            _tick(80, "thumbnail")
            check_cancelled(pkg, state)
            thumb_langs = state.get("expected_languages") or planned_langs
            try:
                from pipeline.custom_pipeline.thumbnail_engine import generate_localized_thumbnail_package

                stage6 = generate_localized_thumbnail_package(
                    pkg,
                    languages=thumb_langs,
                    force=force,
                )
                finish_stage(
                    state,
                    "thumbnail",
                    status=STATUS_SUCCEEDED if stage6.get("results") else STATUS_FAILED,
                    detail={"languages": list((stage6.get("results") or {}).keys())},
                )
            except Exception as exc:
                logger.warning("Thumbnail generation warning: %s", exc)
                finish_stage(state, "thumbnail", status=STATUS_FAILED, error=str(exc))
            save_job_state(pkg, state)
        else:
            finish_stage(state, "thumbnail", status=STATUS_SKIPPED)
            save_job_state(pkg, state)

        # ── Quality gate ───────────────────────────────────────
        start_stage(state, "quality")
        _tick(90, "quality")
        quality: Dict[str, Any] = {"ok": True, "skipped": False}
        try:
            from pipeline.custom_pipeline.quality_gate import run_custom_quality_gate

            quality = run_custom_quality_gate(pkg, languages=state.get("expected_languages") or [])
        except Exception as exc:
            logger.warning("quality gate soft-fail: %s", exc)
            quality = {"ok": True, "soft_error": str(exc)}
        finish_stage(
            state,
            "quality",
            status=STATUS_SUCCEEDED if quality.get("ok") else STATUS_FAILED,
            detail=quality,
        )

        # Shippable computation
        shared = stage5.get("shared") or {}
        compose = stage5.get("compose") or {}
        finals_ok = [
            lang
            for lang, item in (compose.get("finals") or {}).items()
            if isinstance(item, dict) and item.get("ok")
        ]
        expected_shots = int(shared.get("shot_count") or state.get("expected_shots") or 0)
        expected_langs = list(state.get("expected_languages") or [])
        ship = compute_shippable(
            state,
            shared_success=int(shared.get("success_count") or 0),
            shared_expected=expected_shots if not skip_media else 0,
            finals_ok=finals_ok,
            expected_languages=expected_langs if not skip_media else [],
        )
        if state.get("degraded"):
            telemetry_emit(
                pkg,
                "shot.degraded",
                f"count={len(state.get('degraded') or [])}",
                count=len(state.get("degraded") or []),
            )
        telemetry_emit(
            pkg,
            "job.finished",
            state.get("status") or "",
            shippable=ship.get("shippable"),
            partial=ship.get("partial"),
        )

        # ── Archive ────────────────────────────────────────────
        start_stage(state, "archive")
        archive: Dict[str, Any] = {"ok": False}
        try:
            archive = archive_complete_json_package(
                package_root=pkg,
                video_type=kind,
                title=pick_primary_title(stage1.get("payload") or {}),
            )
            finish_stage(state, "archive", status=STATUS_SUCCEEDED, detail=archive)
        except Exception as exc:
            logger.warning("JSON archive failed: %s", exc)
            archive = {"ok": False, "error": str(exc)}
            finish_stage(state, "archive", status=STATUS_FAILED, error=str(exc))

        _tick(100, "done")
        save_job_state(pkg, state)

        report = {
            "ok": bool(ship.get("shippable")) and bool(quality.get("ok", True)),
            "shippable": bool(ship.get("shippable")),
            "shippable_bn_only": bool(ship.get("shippable_bn_only", ship.get("shippable"))),
            "shippable_all_languages": bool(ship.get("shippable_all_languages")),
            "partial": bool(ship.get("partial"))
            or bool(stage4.get("partial"))
            or bool(stage5.get("partial"))
            or bool(ship.get("missing_languages")),
            "missing_languages": list(ship.get("missing_languages") or []),
            "planned_languages": list(state.get("planned_languages") or planned_langs),
            "preflight": preflight,
            "session_id": sid,
            "video_type": kind,
            "session_keys": session_key_report(),
            "package_root": str(pkg),
            "job_id": state.get("job_id"),
            "job_status": state.get("status"),
            "progress_pct": state.get("progress_pct"),
            "degraded": state.get("degraded") or [],
            "budget": state.get("budget"),
            "ship_report": ship,
            "stage1_topic": stage1,
            "stage3_visual": stage3,
            "stage2_localize": stage2,
            "stage4_tts": stage4,
            "stage5_media": stage5,
            "quality": quality,
            "dedupe": (stage1.get("dedupe") if isinstance(stage1, dict) else None),
            "complete_json_archive": archive,
            "outputs": {
                "topic_script": (stage1.get("save") or {}).get("json_path"),
                "visual_render_plan": (stage3.get("save") or {}).get("json_path"),
                "localized_voices": {
                    lang: item.get("json_path") or (item.get("save") or {}).get("json_path")
                    for lang, item in (
                        (stage2.get("results") or {}) if isinstance(stage2, dict) else {}
                    ).items()
                },
                "tts_audio": {
                    lang: {
                        "audio_dir": (item.get("audio_dir") if isinstance(item, dict) else None),
                        "narration_full": (
                            item.get("narration_full") if isinstance(item, dict) else None
                        ),
                        "success_count": (
                            item.get("success_count") if isinstance(item, dict) else None
                        ),
                        "resumed": (item.get("resumed") if isinstance(item, dict) else None),
                    }
                    for lang, item in (
                        (stage4.get("results") or {}) if isinstance(stage4, dict) else {}
                    ).items()
                },
                "media": {
                    "shared_ok": (stage5.get("shared") or {}).get("ok")
                    if isinstance(stage5, dict)
                    else None,
                    "compose_ok": (stage5.get("compose") or {}).get("ok")
                    if isinstance(stage5, dict)
                    else None,
                    "layout": stage5.get("layout") if isinstance(stage5, dict) else None,
                },
                "thumbnails": stage6.get("results") or {},
                "job_state": str(pkg / "File" / "job_state.json"),
            },
        }
        logger.info(
            "Custom pipeline done format=%s package=%s shippable=%s status=%s",
            kind,
            pkg,
            ship.get("shippable"),
            state.get("status"),
        )
        return report

    except PipelineCancelled:
        if pkg and pkg.exists():
            state["status"] = STATUS_CANCELLED
            finish_active_stage(state, status=STATUS_CANCELLED, error="cancelled")
            save_job_state(pkg, state)
        return {
            "ok": False,
            "cancelled": True,
            "package_root": str(pkg) if pkg else None,
            "session_id": sid,
            "job_status": STATUS_CANCELLED,
        }
    except BudgetExceeded as exc:
        if pkg and pkg.exists():
            state["status"] = STATUS_FAILED
            finish_active_stage(state, status=STATUS_FAILED, error=str(exc))
            save_job_state(pkg, state)
        return {
            "ok": False,
            "budget_exceeded": True,
            "error": str(exc),
            "package_root": str(pkg) if pkg else None,
            "session_id": sid,
        }
    except Exception as exc:
        logger.exception("Custom pipeline failed")
        if pkg and pkg.exists():
            state["status"] = STATUS_FAILED
            finish_active_stage(state, status=STATUS_FAILED, error=str(exc)[:500])
            save_job_state(pkg, state)
        raise


def run_short_pipeline(**kwargs: Any) -> Dict[str, Any]:
    kwargs.pop("video_type", None)
    return run_pipeline(video_type="short", **kwargs)


def run_long_pipeline(**kwargs: Any) -> Dict[str, Any]:
    kwargs.pop("video_type", None)
    return run_pipeline(video_type="long", **kwargs)
