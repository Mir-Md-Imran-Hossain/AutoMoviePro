"""Lightweight quality / publishability gate for custom pipeline packages."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.custom_pipeline.package_layout import lang_code_for, open_package
from pipeline.output_layout import write_json

logger = logging.getLogger(__name__)


def run_custom_quality_gate(
    package_root: Path | str,
    *,
    languages: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Check finals exist, basic duration, and optional legacy AV gates."""
    pkg = Path(package_root)
    paths = open_package(pkg)
    issues: List[str] = []
    checks: Dict[str, Any] = {}

    # Shared masters
    masters = list(paths.video_clips.glob("S*.mp4")) if paths.video_clips.is_dir() else []
    masters = [p for p in masters if p.parent == paths.video_clips]
    checks["master_clips"] = len(masters)
    if not masters:
        issues.append("no_shared_master_clips")

    lang_names = list(languages or [])
    finals_ok: List[str] = []
    for lang in lang_names:
        code = lang_code_for(lang)
        final = paths.final_video_lang(code) / f"final_{code}.mp4"
        ok = final.is_file() and final.stat().st_size > 10000
        checks[f"final_{code}"] = {"ok": ok, "path": str(final) if ok else None}
        if ok:
            finals_ok.append(lang)
            try:
                from pipeline.compose import ffprobe_duration

                dur = float(ffprobe_duration(final) or 0)
                checks[f"final_{code}"]["duration_sec"] = dur
                if dur < 1.0:
                    issues.append(f"final_{code}_too_short")
            except Exception:
                pass
        else:
            issues.append(f"missing_final_{code}")

    # Optional legacy publishability soft probe (first final only)
    legacy: Dict[str, Any] = {"skipped": True}
    if finals_ok:
        try:
            code = lang_code_for(finals_ok[0])
            final = paths.final_video_lang(code) / f"final_{code}.mp4"
            from pipeline.av_quality_gates import evaluate_master_shippable

            legacy = evaluate_master_shippable(media=final)  # type: ignore[misc]
            if isinstance(legacy, dict) and legacy.get("ok") is False:
                # Soft: record but do not hard-fail custom shorts by default
                issues.append("legacy_gate_soft_fail")
        except Exception as exc:
            legacy = {"skipped": True, "error": str(exc)[:200]}

    # Degraded providers from media state
    degraded = []
    try:
        st = paths.file_dir / "media_generation_state.json"
        if st.is_file():
            data = json.loads(st.read_text(encoding="utf-8"))
            for k, v in (data.get("shots") or {}).items():
                if v.get("fallback") or "stock" in str(v.get("provider") or "").lower() or "kenburns" in str(
                    v.get("provider") or ""
                ).lower():
                    degraded.append({"shot": k, "provider": v.get("provider")})
    except Exception:
        pass
    checks["degraded_shots"] = degraded

    hard_fail = any(
        i.startswith("no_shared") or i.startswith("missing_final") for i in issues
    )
    report = {
        "ok": not hard_fail,
        "ship_blockers": [i for i in issues if i.startswith("no_shared") or i.startswith("missing_final")],
        "warnings": [i for i in issues if i not in (
            [x for x in issues if x.startswith("no_shared") or x.startswith("missing_final")]
        )],
        "checks": checks,
        "legacy": legacy,
        "finals_ok": finals_ok,
        "degraded_count": len(degraded),
    }
    write_json(paths.file_dir / "quality_gate_manifest.json", report)
    logger.info(
        "Quality gate ok=%s finals=%s degraded=%s issues=%s",
        report["ok"],
        finals_ok,
        len(degraded),
        issues,
    )
    return report
