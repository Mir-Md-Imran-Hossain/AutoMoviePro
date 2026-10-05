"""Custom pipeline Stage 5 — shared media generate → per-lang compose → finals."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.custom_pipeline.honest_status import honest_shippable
from pipeline.custom_pipeline.media_compose import compose_and_assemble_all
from pipeline.custom_pipeline.media_generate import generate_shared_media
from pipeline.custom_pipeline.package_layout import open_package
from pipeline.output_layout import write_json

logger = logging.getLogger(__name__)


def run_media_stage(
    package_root: Path | str,
    *,
    languages: Optional[Sequence[str]] = None,
    include_bangla: bool = True,
    max_shots: Optional[int] = None,
    force: bool = False,
    skip_compose: bool = False,
    job_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Industrial media stage:
      1) Shared Image/ + Video/Video Clips/ from visual_render_plan
      2) Per-language setpts fit + subtitle burn
      3) Final Video/{BN,EN,...}/final_*.mp4
    Honest shippable: all expected shots + all expected language finals.
    """
    pkg = Path(package_root)
    paths = open_package(pkg)
    logger.info("Media stage start package=%s", pkg)

    shared = generate_shared_media(pkg, max_shots=max_shots, force=force, job_state=job_state)
    compose: Dict[str, Any] = {"ok": False, "skipped": True}
    if not skip_compose and shared.get("success_count", 0) > 0:
        compose = compose_and_assemble_all(
            pkg,
            languages=list(languages) if languages else None,
            include_bangla=include_bangla,
        )

    expected_shots = int(shared.get("shot_count") or 0)
    success_shots = int(shared.get("success_count") or 0)
    expected_langs = list(languages or [])
    finals = compose.get("finals") or {}
    finals_ok = [
        lang for lang, item in finals.items() if isinstance(item, dict) and item.get("ok")
    ]
    cancel = bool(job_state and job_state.get("cancel_requested"))
    ship = honest_shippable(
        shared_success=success_shots,
        shared_expected=expected_shots,
        finals_ok=finals_ok,
        expected_languages=expected_langs,
        shared_errors=shared.get("errors") or {},
        cancel_requested=cancel,
        skip_compose=skip_compose,
    )

    report = {
        "ok": ship["shippable"],
        "shippable": ship["shippable"],
        "partial": ship["partial"],
        "failed": ship["failed"],
        "package_root": str(pkg),
        "shared": shared,
        "compose": compose,
        "missing_languages": ship["missing_languages"],
        "layout": {
            "image": str(paths.image),
            "video_clips": str(paths.video_clips),
            "final_video": str(paths.final_video),
        },
        "degraded": shared.get("degraded") or [],
        "ship_report": ship,
    }
    write_json(paths.file_dir / "media_stage_manifest.json", report)
    logger.info(
        "Media stage done shared=%s/%s shippable=%s partial=%s",
        success_shots,
        expected_shots,
        ship["shippable"],
        ship["partial"],
    )
    return report
