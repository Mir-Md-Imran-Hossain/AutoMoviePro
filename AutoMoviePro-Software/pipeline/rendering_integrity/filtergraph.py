"""Filtergraph + stream mapping + geometry validation (AMP-004 Phase-08)."""
from __future__ import annotations

from typing import Any

from pipeline.rendering_integrity.contract import FiltergraphContract, GeometrySpec


def validate_filtergraph(fg: FiltergraphContract | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fg, FiltergraphContract):
        data = fg
    else:
        from pipeline.rendering_integrity.contract import FilterNode, StreamMap

        data = FiltergraphContract(
            nodes=[
                FilterNode(**n) if isinstance(n, dict) else n
                for n in (fg.get("nodes") or [])
            ],
            stream_maps=[
                StreamMap(**s) if isinstance(s, dict) else s
                for s in (fg.get("stream_maps") or [])
            ],
            ordering=list(fg.get("ordering") or []),
        )
    issues: list[str] = []
    if not data.nodes:
        issues.append("empty_filtergraph")
    node_ids = {n.node_id for n in data.nodes}
    if len(node_ids) != len(data.nodes):
        issues.append("duplicate_filter_node_id")
    for n in data.nodes:
        if not (n.filter_name or "").strip():
            issues.append(f"missing_filter_name:{n.node_id}")
        if not n.outputs:
            issues.append(f"filter_missing_outputs:{n.node_id}")
        for inp in n.inputs:
            # inputs may be raw stream labels (v0) or prior node outputs
            pass
    if not data.stream_maps:
        issues.append("missing_stream_maps")
    mapped_types = {s.media_type for s in data.stream_maps if s.mapped}
    if "video" not in mapped_types:
        issues.append("video_stream_unmapped")
    if "audio" not in mapped_types:
        issues.append("audio_stream_unmapped")
    for s in data.stream_maps:
        if s.mapped and not (s.source or "").strip():
            issues.append(f"mapped_stream_missing_source:{s.stream_id}")
    # Ordering must reference existing nodes when provided
    for oid in data.ordering:
        if oid and oid not in node_ids:
            issues.append(f"invalid_filter_order_ref:{oid}")
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC"}


def validate_geometry(geo: GeometrySpec | dict[str, Any]) -> dict[str, Any]:
    if isinstance(geo, dict):
        geo = GeometrySpec(**{k: geo[k] for k in GeometrySpec().__dict__.keys() if k in geo})
    issues: list[str] = []
    if int(geo.width) <= 0 or int(geo.height) <= 0:
        issues.append("invalid_dimensions")
    if int(geo.width) % 2 != 0 or int(geo.height) % 2 != 0:
        issues.append("odd_frame_dimension")
    if float(geo.fps) <= 0:
        issues.append("invalid_fps")
    if int(geo.rotation) not in (0, 90, 180, 270):
        issues.append("unexpected_rotation_metadata")
    if (geo.pixel_format or "").lower() not in ("yuv420p", "yuv422p", "yuv444p", "nv12", ""):
        issues.append(f"unusual_pixel_format:{geo.pixel_format}")
    # Aspect sanity: reject extreme stretch markers
    if geo.width and geo.height:
        ratio = geo.width / geo.height
        if ratio < 0.2 or ratio > 5.0:
            issues.append("extreme_aspect_ratio")
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "geometry": geo.to_dict(), "method": "DETERMINISTIC"}


def build_explicit_ffmpeg_args(
    *,
    inputs: list[str],
    filter_complex: str,
    output: str,
    map_video: str = "[vout]",
    map_audio: str = "[aout]",
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    pixel_format: str = "yuv420p",
    audio_rate: int = 44100,
) -> list[str]:
    """Structured argv list — never uncontrolled shell concatenation."""
    args: list[str] = ["-y"]
    for inp in inputs:
        args.extend(["-i", str(inp)])
    if filter_complex:
        args.extend(["-filter_complex", filter_complex])
        args.extend(["-map", map_video, "-map", map_audio])
    else:
        # Explicit first video + first audio
        args.extend(["-map", "0:v:0", "-map", "0:a:0?"])
    args.extend(
        [
            "-c:v",
            video_codec,
            "-pix_fmt",
            pixel_format,
            "-c:a",
            audio_codec,
            "-ar",
            str(int(audio_rate)),
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return args


def build_cinematic_motion_filter(
    *,
    w: int = 1080,
    h: int = 1920,
    width: Optional[int] = None,
    height: Optional[int] = None,
    duration: float = 5.0,
    preset: str = "dynamic_zoom_in",
    fps: int = 25,
) -> str:
    """Builds a cinematic FFmpeg filtergraph for still images ensuring zero static frames.

    Presets:
      - 'dynamic_zoom_in': Smooth continuous zoom from 1.0 to 1.18 centered on subject.
      - 'slow_pan': Gentle horizontal pan across working buffer with steady motion.
      - 'subtle_parallax': Compound dynamic zoom + sinusoidal ease pan for 2.5D depth illusion.
    """
    if width is not None:
        w = width
    if height is not None:
        h = height
    frames = max(int(fps * 2), int(round(max(1.0, float(duration or 5.0)) * fps)))
    work = max(w, h) * 4
    pid = (preset or "dynamic_zoom_in").strip().lower()

    if pid in ("slow_pan", "pan_right", "pan_left"):
        # Gentle pan
        z_expr = "1.12"
        x_expr = f"(iw-iw/zoom)*(on/{max(1, frames - 1)})" if "left" not in pid else f"(iw-iw/zoom)*(1-on/{max(1, frames - 1)})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pid in ("subtle_parallax", "parallax", "organic_motion"):
        # Compound subtle zoom + sinusoidal micro-parallax curve
        z_expr = "min(zoom+0.00035,1.15)"
        prog = f"(on/{max(1, frames - 1)})"
        x_expr = f"(iw-iw/zoom)*(0.5+0.35*sin(2*3.14159*{prog}))"
        y_expr = f"(ih-ih/zoom)*(0.5+0.25*cos(2*3.14159*{prog}))"
    else:  # 'dynamic_zoom_in' / default
        z_expr = "min(zoom+0.00045,1.18)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    return (
        f"scale={work}:-1:flags=lanczos,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps={fps},"
        f"fps={fps},format=yuv420p"
    )


def is_still_image(path: str) -> bool:
    """Returns True if the path represents a still image file."""
    ext = str(path).lower().split(".")[-1]
    return ext in ("png", "jpg", "jpeg", "webp", "bmp", "tiff")

