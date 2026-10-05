"""CLI for custom pipeline stages.

  python -m pipeline.custom_pipeline short --niche "AI Tech"
  python -m pipeline.custom_pipeline long --niche "AI Tech"
  python -m pipeline.custom_pipeline topic --niche "AI Tech" --type short
  python -m pipeline.custom_pipeline localize --source path/to/topic_script.json --lang English
  python -m pipeline.custom_pipeline visual --source path/to/topic_script.json
  python -m pipeline.custom_pipeline status --package-root …
  python -m pipeline.custom_pipeline cancel --package-root …
  python -m pipeline.custom_pipeline retry-shot --package-root … --shot 3
  python -m pipeline.custom_pipeline retry-lang --package-root … --lang Hindi
"""

from __future__ import annotations

import argparse
import json
import sys


def _cmd_topic(args: argparse.Namespace) -> int:
    from pipeline.custom_pipeline.session_keys import start_session
    from pipeline.custom_pipeline.topic_research import run_topic_research

    start_session()
    try:
        result = run_topic_research(
            niche=args.niche,
            video_type=args.video_type,
            audience=args.audience,
            save=not args.no_save,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.get("save"):
        print(f"Saved: {result['save'].get('json_path')}")
        print(f"Folder: {result['save'].get('package_root')}")
    print(json.dumps(result.get("payload") or {}, ensure_ascii=False, indent=2))
    return 0


def _cmd_localize(args: argparse.Namespace) -> int:
    from pipeline.custom_pipeline.localization import (
        SUPPORTED_LANGUAGES,
        localize_script,
        localize_to_languages,
    )
    from pipeline.custom_pipeline.session_keys import session_key_report, start_session

    start_session()
    source = args.source
    cultures = {}
    if args.culture:
        cultures[args.lang or "English"] = args.culture

    try:
        if args.all:
            result = localize_to_languages(
                source,
                languages=list(SUPPORTED_LANGUAGES),
                audience_cultures=cultures or None,
                package_root=args.package_root,
                save=not args.no_save,
                force=getattr(args, "force", False),
            )
            print("session_keys:", session_key_report())
            if result.get("errors"):
                print(f"ERRORS: {result['errors']}", file=sys.stderr)
            for lang, item in (result.get("results") or {}).items():
                save = item.get("save") or {}
                print(f"{lang}: {save.get('json_path') or 'ok'}")
            return 0 if result.get("ok") else 1

        result = localize_script(
            source,
            target_language=args.lang or "English",
            audience_culture=args.culture,
            package_root=args.package_root,
            save=not args.no_save,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("session_keys:", session_key_report())
    if result.get("save"):
        print(f"Saved: {result['save'].get('json_path')}")
    print(json.dumps(result.get("payload") or {}, ensure_ascii=False, indent=2))
    return 0


def _cmd_visual(args: argparse.Namespace) -> int:
    from pipeline.custom_pipeline.session_keys import start_session
    from pipeline.custom_pipeline.visual_render import plan_visual_renders

    start_session()
    try:
        result = plan_visual_renders(
            args.source,
            video_type=args.video_type or None,
            aspect_ratio=args.aspect or None,
            package_root=args.package_root,
            save=not args.no_save,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.get("save"):
        print(f"Saved: {result['save'].get('json_path')}")
        print(
            f"IMAGE={result['save'].get('image_shots')} "
            f"VIDEO={result['save'].get('video_shots')}"
        )
    print(json.dumps(result.get("payload") or {}, ensure_ascii=False, indent=2))
    return 0


def _cmd_tts(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.session_keys import session_key_report, start_session
    from pipeline.custom_pipeline.tts_synthesize import (
        synthesize_language_tts,
        synthesize_package_tts,
    )

    start_session()
    pkg = Path(args.package_root)
    force = bool(getattr(args, "force", False))
    try:
        if args.all:
            result = synthesize_package_tts(
                pkg,
                languages=None if not args.langs else args.langs.split(","),
                include_bangla=args.include_bangla,
                force=force,
            )
        else:
            result = synthesize_language_tts(pkg, args.lang or "English", force=force)
            result = {
                "ok": result.get("ok"),
                "results": {result.get("language") or args.lang: result},
                "errors": result.get("errors") or {},
            }
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("session_keys:", session_key_report())
    for lang, item in (result.get("results") or {}).items():
        print(
            f"{lang}: shots={item.get('success_count')}/{item.get('shot_count')} "
            f"full={item.get('narration_full')} resumed={item.get('resumed')}"
        )
    if result.get("errors"):
        print(f"ERRORS: {result['errors']}", file=sys.stderr)
    return 0 if result.get("ok") else 1


def _cmd_media(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.media_stage import run_media_stage
    from pipeline.custom_pipeline.session_keys import session_key_report, start_session

    start_session()
    pkg = Path(args.package_root)
    langs = [x.strip() for x in (args.langs or "").split(",") if x.strip()] or None
    try:
        result = run_media_stage(
            pkg,
            languages=langs,
            include_bangla=not args.no_bangla,
            max_shots=args.max_shots,
            force=args.force,
            skip_compose=args.skip_compose,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("session_keys:", session_key_report())
    shared = result.get("shared") or {}
    compose = result.get("compose") or {}
    print(
        f"shared: {shared.get('success_count')}/{shared.get('shot_count')} "
        f"ok={shared.get('ok')} shippable={result.get('shippable')} "
        f"partial={result.get('partial')}"
    )
    if shared.get("errors"):
        print(f"shared_errors: {shared['errors']}", file=sys.stderr)
    if not args.skip_compose:
        finals = (compose.get("finals") or {})
        for lang, item in finals.items():
            print(f"compose_errors: {compose['errors']}", file=sys.stderr)
    return 0 if result.get("ok") else 1


def _cmd_thumbnail(args: argparse.Namespace) -> int:
    from pathlib import Path
    from pipeline.custom_pipeline.thumbnail_engine import generate_localized_thumbnail_package

    pkg = Path(args.package_root)
    langs = [x.strip() for x in (args.langs or "").split(",") if x.strip()] or None
    try:
        res = generate_localized_thumbnail_package(
            pkg,
            languages=langs,
            channel_name=args.channel_name or None,
            logo_path=Path(args.logo) if args.logo else None,
            force=args.force,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _cmd_format_pipeline(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.runner import run_long_pipeline, run_short_pipeline

    runner = run_short_pipeline if args.command == "short" else run_long_pipeline
    try:
        result = runner(
            niche=args.niche,
            audience=args.audience,
            languages=args.langs.split(",") if args.langs else None,
            skip_localize=args.skip_localize,
            skip_visual=args.skip_visual,
            skip_tts=args.skip_tts,
            skip_media=getattr(args, "skip_media", False),
            include_bangla_tts=args.include_bangla_tts,
            resume_package=Path(args.resume) if getattr(args, "resume", None) else None,
            force=bool(getattr(args, "force", False)),
            require_approval=bool(getattr(args, "require_approval", False)),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": result.get("ok"),
                "shippable": result.get("shippable"),
                "partial": result.get("partial"),
                "video_type": result.get("video_type"),
                "session_id": result.get("session_id"),
                "session_keys": result.get("session_keys"),
                "package_root": result.get("package_root"),
                "outputs": result.get("outputs"),
                "degraded": result.get("degraded"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.get("ok") else 1


def _cmd_status(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.job_state import load_job_state

    pkg = Path(args.package_root)
    state = load_job_state(pkg)
    if not state:
        print(json.dumps({"ok": False, "error": "no job_state.json"}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "status": state.get("status"),
                "shippable": state.get("shippable"),
                "partial": state.get("partial"),
                "progress_pct": state.get("progress_pct"),
                "progress_message": state.get("progress_message"),
                "cancel_requested": state.get("cancel_requested"),
                "heartbeat_at": state.get("heartbeat_at"),
                "stages": state.get("stages"),
                "budget": state.get("budget"),
                "degraded": state.get("degraded"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_cancel(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.pipeline_control import request_cancel

    pkg = Path(args.package_root)
    request_cancel(pkg)
    print(json.dumps({"ok": True, "cancelled": True, "package_root": str(pkg)}, indent=2))
    return 0


def _cmd_retry_shot(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.retry_ops import retry_media_shot

    langs = [x.strip() for x in (args.langs or "").split(",") if x.strip()] or None
    result = retry_media_shot(Path(args.package_root), int(args.shot), languages=langs)
    print(json.dumps({"ok": result.get("ok"), "shot": result.get("shot")}, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_retry_lang(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pipeline.custom_pipeline.retry_ops import retry_language

    result = retry_language(
        Path(args.package_root),
        args.lang,
        force_tts=not getattr(args, "keep_tts", False),
    )
    print(json.dumps({"ok": result.get("ok"), "language": args.lang}, indent=2))
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    # Keep httpx/httpcore quieter unless debugging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="Custom AutoMovie pipeline")
    sub = parser.add_subparsers(dest="command")
    raw = list(argv) if argv is not None else None

    for name, help_txt in (("short", "Run SHORT-only pipeline"), ("long", "Run LONG-only pipeline")):
        p = sub.add_parser(name, help=help_txt)
        p.add_argument("--niche", required=True)
        p.add_argument("--audience", default="সাধারণ দর্শক")
        p.add_argument("--langs", default="", help="Comma list, e.g. English,Hindi")
        p.add_argument("--skip-localize", action="store_true")
        p.add_argument("--skip-visual", action="store_true")
        p.add_argument("--skip-tts", action="store_true")
        p.add_argument("--skip-media", action="store_true")
        p.add_argument("--include-bangla-tts", action="store_true")
        p.add_argument("--resume", default=None, help="Resume existing package root")
        p.add_argument("--force", action="store_true", help="Ignore skip-if-exists artifacts")
        p.add_argument("--require-approval", action="store_true", help="Pause after topic/script")
        p.set_defaults(func=_cmd_format_pipeline)

    p_topic = sub.add_parser("topic", help="Stage 1 — Grok topic + script")
    p_topic.add_argument("--niche", required=True)
    p_topic.add_argument("--type", dest="video_type", choices=("short", "long"), default="short")
    p_topic.add_argument("--audience", default="সাধারণ দর্শক")
    p_topic.add_argument("--no-save", action="store_true")
    p_topic.set_defaults(func=_cmd_topic)

    p_loc = sub.add_parser("localize", help="Stage 2 — voice/subtitle localization only")
    p_loc.add_argument("--source", required=True, help="Path to Shared/topic_script.json")
    p_loc.add_argument("--lang", default="English")
    p_loc.add_argument("--culture", default="")
    p_loc.add_argument("--all", action="store_true")
    p_loc.add_argument("--package-root", default=None)
    p_loc.add_argument("--no-save", action="store_true")
    p_loc.add_argument("--force", action="store_true")
    p_loc.set_defaults(func=_cmd_localize)

    p_vis = sub.add_parser("visual", help="Stage 3 — IMAGE vs VIDEO render plan (once)")
    p_vis.add_argument("--source", required=True)
    p_vis.add_argument("--type", dest="video_type", choices=("short", "long"), default=None)
    p_vis.add_argument("--aspect", default=None)
    p_vis.add_argument("--package-root", default=None)
    p_vis.add_argument("--no-save", action="store_true")
    p_vis.set_defaults(func=_cmd_visual)

    p_tts = sub.add_parser("tts", help="Stage 4 — Gemini TTS (emotion + language settings)")
    p_tts.add_argument("--package-root", required=True)
    p_tts.add_argument("--lang", default="English")
    p_tts.add_argument("--all", action="store_true", help="All 5 localized languages")
    p_tts.add_argument("--langs", default="", help="Comma list override")
    p_tts.add_argument("--include-bangla", action="store_true")
    p_tts.add_argument("--force", action="store_true")
    p_tts.set_defaults(func=_cmd_tts)

    p_media = sub.add_parser(
        "media",
        help="Stage 5 — shared image/video generate + per-lang stretch/subtitle + finals",
    )
    p_media.add_argument("--package-root", required=True)
    p_media.add_argument("--langs", default="", help="Comma list, e.g. Bangla,English")
    p_media.add_argument("--max-shots", type=int, default=None)
    p_media.add_argument("--force", action="store_true", help="Regenerate even if resume state exists")
    p_media.add_argument("--skip-compose", action="store_true", help="Only shared Image/Video Clips")
    p_media.add_argument("--no-bangla", action="store_true")
    p_media.set_defaults(func=_cmd_media)

    p_status = sub.add_parser("status", help="Show job_state progress / shippable")
    p_status.add_argument("--package-root", required=True)
    p_status.set_defaults(func=_cmd_status)

    p_cancel = sub.add_parser("cancel", help="Request cancel for a running package")
    p_cancel.add_argument("--package-root", required=True)
    p_cancel.set_defaults(func=_cmd_cancel)

    p_rs = sub.add_parser("retry-shot", help="Retry one shared media shot + recompose")
    p_rs.add_argument("--package-root", required=True)
    p_rs.add_argument("--shot", type=int, required=True)
    p_rs.add_argument("--langs", default="")
    p_rs.set_defaults(func=_cmd_retry_shot)

    p_rl = sub.add_parser("retry-lang", help="Retry TTS+compose+final for one language")
    p_rl.add_argument("--package-root", required=True)
    p_rl.add_argument("--lang", required=True)
    p_rl.add_argument("--keep-tts", action="store_true", help="Do not regenerate TTS")
    p_rl.set_defaults(func=_cmd_retry_lang)

    p_thumb = sub.add_parser("thumbnail", help="Stage 6 — Localized High-CTR thumbnails and metadata JSON")
    p_thumb.add_argument("--package-root", required=True)
    p_thumb.add_argument("--langs", default="", help="Comma list, e.g. Bangla,English,Hindi")
    p_thumb.add_argument("--channel-name", default="")
    p_thumb.add_argument("--logo", default="", help="Path to channel logo")
    p_thumb.add_argument("--force", action="store_true")
    p_thumb.set_defaults(func=_cmd_thumbnail)

    known = (
        "topic",
        "localize",
        "visual",
        "tts",
        "media",
        "thumbnail",
        "short",
        "long",
        "status",
        "cancel",
        "retry-shot",
        "retry-lang",
        "-h",
        "--help",
    )
    if raw is None:
        raw = sys.argv[1:]
    if raw and raw[0] not in known and raw[0].startswith("-"):
        raw = ["topic", *raw]

    args = parser.parse_args(raw)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
