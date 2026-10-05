"""Structured telemetry events for custom pipeline (file + log)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def emit(
    package_root: Path | str,
    kind: str,
    message: str = "",
    **fields: Any,
) -> None:
    pkg = Path(package_root)
    event = {
        "ts": time.time(),
        "kind": kind,
        "message": message,
        **{k: v for k, v in fields.items() if v is not None},
    }
    logger.info("telemetry %s %s", kind, message or fields)
    try:
        from pipeline.custom_pipeline.package_layout import open_package

        path = open_package(pkg).file_dir / "telemetry.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("telemetry write soft-fail: %s", exc)

    try:
        from pipeline.custom_pipeline.job_state import append_event, load_job_state, save_job_state

        state = load_job_state(pkg)
        if state:
            append_event(state, kind, message, **fields)
            save_job_state(pkg, state)
    except Exception:
        pass
