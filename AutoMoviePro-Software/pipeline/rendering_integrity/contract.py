"""Canonical rendering integrity contracts (AMP-004 Phase-08).

Extends BUILD-04D RenderAssemblyManifest — does not replace it.
Renderer must not invent business meaning.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from pipeline.idempotency.fingerprint import hash_text

VFX_PURPOSES = frozenset(
    {
        "emphasis",
        "transition",
        "visual_hierarchy",
        "information_clarity",
        "atmosphere",
        "temporal_continuity",
        "storytelling_support",
        "none",
    }
)

ALLOWED_TRANSITION_TYPES = frozenset({"cut", "dissolve", "fade", "none"})
NOISE_TRANSITIONS = frozenset({"zoom", "flash", "spin", "glitch", "wipe", "shake"})


@dataclass
class TimelineSegment:
    scene_id: str
    start_sec: float
    end_sec: float
    intentional_overlap: bool = False
    intentional_gap: bool = False
    overlap_reason: str = ""
    gap_reason: str = ""
    asset_path: str = ""
    asset_fingerprint: str = ""

    @property
    def duration_sec(self) -> float:
        return float(self.end_sec) - float(self.start_sec)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_sec"] = round(self.duration_sec, 4)
        return d


@dataclass
class VfxDirective:
    vfx_id: str
    scene_id: str
    purpose: str
    start_time: float
    end_time: float
    target: str = "full_frame"
    intensity: float = 0.5
    blend_mode: str = "normal"
    provenance: str = ""
    approval_status: str = "approved"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TransitionDirective:
    source_scene: str
    destination_scene: str
    type: str = "cut"
    duration: float = 0.0
    reason: str = "default_cut"
    timing: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilterNode:
    node_id: str
    filter_name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StreamMap:
    stream_id: str
    media_type: str  # video | audio | subtitle
    source: str
    mapped: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FiltergraphContract:
    nodes: list[FilterNode] = field(default_factory=list)
    stream_maps: list[StreamMap] = field(default_factory=list)
    ordering: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "stream_maps": [s.to_dict() for s in self.stream_maps],
            "ordering": list(self.ordering),
        }


@dataclass
class GeometrySpec:
    width: int = 1080
    height: int = 1920
    fps: float = 25.0
    pixel_format: str = "yuv420p"
    sar: str = "1:1"
    dar: str = ""
    rotation: int = 0
    color_metadata: str = ""

    def size_str(self) -> str:
        return f"{int(self.width)}x{int(self.height)}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EncodeSpec:
    container: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_sample_rate: int = 44100
    audio_channels: int = 2
    quality_mode: str = "crf"
    bitrate: str = ""
    deterministic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RenderIntegrityContract:
    """Industrial render contract — composition/render only; no semantic invention."""

    project_id: str
    render_id: str
    scene_ids: list[str] = field(default_factory=list)
    timeline_version: str = "1.0.0"
    timeline: list[TimelineSegment] = field(default_factory=list)
    geometry: GeometrySpec = field(default_factory=GeometrySpec)
    encode: EncodeSpec = field(default_factory=EncodeSpec)
    filtergraph: FiltergraphContract = field(default_factory=FiltergraphContract)
    vfx: list[VfxDirective] = field(default_factory=list)
    transitions: list[TransitionDirective] = field(default_factory=list)
    subtitle_config: dict[str, Any] = field(default_factory=dict)
    text_overlays: list[dict[str, Any]] = field(default_factory=list)
    approved_visual_assets: list[str] = field(default_factory=list)
    approved_audio_assets: list[str] = field(default_factory=list)
    source_fingerprints: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    contract_fingerprint: str = ""
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "render_id": self.render_id,
            "scene_ids": list(self.scene_ids),
            "timeline_version": self.timeline_version,
            "timeline": [t.to_dict() for t in self.timeline],
            "geometry": self.geometry.to_dict(),
            "encode": self.encode.to_dict(),
            "filtergraph": self.filtergraph.to_dict(),
            "vfx": [v.to_dict() for v in self.vfx],
            "transitions": [t.to_dict() for t in self.transitions],
            "subtitle_config": dict(self.subtitle_config),
            "text_overlays": list(self.text_overlays),
            "approved_visual_assets": list(self.approved_visual_assets),
            "approved_audio_assets": list(self.approved_audio_assets),
            "source_fingerprints": dict(self.source_fingerprints),
            "provenance": dict(self.provenance),
            "contract_fingerprint": self.contract_fingerprint,
            "schema_version": self.schema_version,
        }


def render_contract_fingerprint(contract: RenderIntegrityContract | dict[str, Any]) -> str:
    data = contract.to_dict() if isinstance(contract, RenderIntegrityContract) else dict(contract)
    data.pop("contract_fingerprint", None)
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hash_text(payload)[:24]


def build_render_integrity_contract(
    *,
    project_id: str,
    render_id: str,
    clips: Optional[list[Any]] = None,
    scene_ids: Optional[list[str]] = None,
    width: int = 1080,
    height: int = 1920,
    fps: float = 25.0,
    durations: Optional[list[float]] = None,
    vfx: Optional[list[VfxDirective]] = None,
    transitions: Optional[list[TransitionDirective]] = None,
    source_fingerprints: Optional[dict[str, str]] = None,
) -> RenderIntegrityContract:
    clips = list(clips or [])
    durs = list(durations or [])
    ids = list(scene_ids or [f"scene-{i}" for i in range(len(clips) or len(durs) or 0)])
    if not ids and clips:
        ids = [f"scene-{i}" for i in range(len(clips))]
    timeline: list[TimelineSegment] = []
    t = 0.0
    n = max(len(ids), len(durs), len(clips))
    for i in range(n):
        sid = ids[i] if i < len(ids) else f"scene-{i}"
        dur = float(durs[i]) if i < len(durs) else 0.0
        path = str(clips[i]) if i < len(clips) else ""
        if dur <= 0 and path:
            try:
                from pipeline.compose import ffprobe_duration

                dur = float(ffprobe_duration(path) or 0.0)
            except Exception:
                dur = 0.0
        end = t + max(0.0, dur)
        timeline.append(
            TimelineSegment(
                scene_id=str(sid),
                start_sec=round(t, 4),
                end_sec=round(end, 4),
                asset_path=path,
            )
        )
        t = end
    # Default concat filtergraph with explicit maps
    nodes = [
        FilterNode(
            node_id="concat0",
            filter_name="concat",
            inputs=[f"v{i}" for i in range(len(timeline))] + [f"a{i}" for i in range(len(timeline))],
            outputs=["vout", "aout"],
            params={"n": len(timeline), "v": 1, "a": 1},
        )
    ]
    maps = [
        StreamMap(stream_id="vout", media_type="video", source="concat0", mapped=True),
        StreamMap(stream_id="aout", media_type="audio", source="concat0", mapped=True),
    ]
    fg = FiltergraphContract(nodes=nodes, stream_maps=maps, ordering=["concat0"])
    # Default cut transitions between scenes
    trans: list[TransitionDirective] = list(transitions or [])
    if not trans and len(timeline) >= 2:
        for i in range(len(timeline) - 1):
            trans.append(
                TransitionDirective(
                    source_scene=timeline[i].scene_id,
                    destination_scene=timeline[i + 1].scene_id,
                    type="cut",
                    duration=0.0,
                    reason="default_conservative_cut",
                    timing=timeline[i].end_sec,
                )
            )
    contract = RenderIntegrityContract(
        project_id=project_id,
        render_id=render_id,
        scene_ids=[seg.scene_id for seg in timeline],
        timeline=timeline,
        geometry=GeometrySpec(width=width, height=height, fps=fps),
        filtergraph=fg,
        vfx=list(vfx or []),
        transitions=trans,
        approved_visual_assets=[str(c) for c in clips],
        source_fingerprints=dict(source_fingerprints or {}),
        provenance={"builder": "rendering_integrity", "authority": "BUILD-04D+Phase08"},
    )
    contract.contract_fingerprint = render_contract_fingerprint(contract)
    return contract
