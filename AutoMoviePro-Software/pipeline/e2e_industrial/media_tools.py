"""Media tool capability + final-file observation helpers (Phase-09)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.compose import probe_media_tool_capability


def discover_media_tools() -> dict[str, Any]:
    """Separate FFMPEG_AVAILABLE vs FFPROBE_AVAILABLE — never fabricate."""
    return probe_media_tool_capability()


def observe_final_media(path: Path | str) -> dict[str, Any]:
    """Inspect actual output; mark ENVIRONMENT_CAPABILITY_MISSING when ffprobe absent."""
    from pipeline.rendering_integrity.observe import observe_rendered_output

    cap = discover_media_tools()
    p = Path(path)
    obs = observe_rendered_output(p)
    obs["FFMPEG_AVAILABLE"] = bool(cap.get("FFMPEG_AVAILABLE"))
    obs["FFPROBE_AVAILABLE"] = bool(cap.get("FFPROBE_AVAILABLE"))
    if not cap.get("FFPROBE_AVAILABLE"):
        obs["environment_limitation"] = "ENVIRONMENT_CAPABILITY_MISSING"
        obs["environment_limitation_detail"] = "ffprobe"
        # Honesty: without ffprobe, stream/duration claims cannot be PROVIDER_VERIFIED
        if obs.get("status") == "PASS":
            # Container-only may still PASS under validate_render_output — annotate
            obs["verification_depth"] = "CONTAINER_OR_LIMITED"
        else:
            obs["verification_depth"] = "FAILED_OR_UNKNOWN"
    else:
        obs["verification_depth"] = "FFPROBE_OBSERVED"
        obs["environment_limitation"] = None
    return obs
