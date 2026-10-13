"""Render assembly manifest builder (BUILD-04D)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.fingerprint import hash_artifact

MANIFEST_VERSION = "1.0.0"
RENDER_TEMPLATE_VERSION = "compose-v1"


@dataclass
class RenderSceneInput:
    scene_index: int
    visual_asset_hash: str
    audio_asset_hash: str = ""
    subtitle_asset_hash: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0

    def normalized(self) -> dict[str, Any]:
        return {
            "scene_index": int(self.scene_index),
            "visual_asset_hash": self.visual_asset_hash.strip(),
            "audio_asset_hash": self.audio_asset_hash.strip(),
            "subtitle_asset_hash": self.subtitle_asset_hash.strip(),
            "start_sec": round(float(self.start_sec), 4),
            "end_sec": round(float(self.end_sec), 4),
            "duration_sec": round(float(self.duration_sec), 4),
        }


@dataclass
class RenderAssemblyManifest:
    job_id: str
    script_fingerprint: str = ""
    scenes: list[RenderSceneInput] = field(default_factory=list)
    logo_hash: str = ""
    intro_hash: str = ""
    subtitle_hash: str = ""
    video_type: str = "short"
    size: str = "1080x1920"
    max_seconds: int = 120
    fps: int = 25
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_sample_rate: int = 44100
    manifest_version: str = MANIFEST_VERSION
    render_template_version: str = RENDER_TEMPLATE_VERSION

    def normalized(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version.strip(),
            "render_template_version": self.render_template_version.strip(),
            "job_id": self.job_id.strip(),
            "script_fingerprint": self.script_fingerprint.strip(),
            "scenes": [s.normalized() for s in self.scenes],
            "logo_hash": self.logo_hash.strip(),
            "intro_hash": self.intro_hash.strip(),
            "subtitle_hash": self.subtitle_hash.strip(),
            "output_config": {
                "video_type": self.video_type.strip().lower(),
                "size": self.size.strip().lower(),
                "max_seconds": int(self.max_seconds),
                "fps": int(self.fps),
                "video_codec": self.video_codec.strip().lower(),
                "audio_codec": self.audio_codec.strip().lower(),
                "audio_sample_rate": int(self.audio_sample_rate),
            },
        }


def asset_hash(path: Optional[Path]) -> str:
    if path is None:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    return hash_artifact(str(p))


def build_manifest_from_clips(
    *,
    job_id: str,
    clips: list[Path],
    script_fingerprint: str = "",
    logo_path: Optional[Path] = None,
    intro_path: Optional[Path] = None,
    subtitle_path: Optional[Path] = None,
    video_type: str = "short",
    size: str = "1080x1920",
    max_seconds: int = 120,
) -> RenderAssemblyManifest:
    scenes: list[RenderSceneInput] = []
    for i, clip in enumerate(clips):
        dur = 0.0
        try:
            from pipeline.compose import ffprobe_duration

            dur = float(ffprobe_duration(clip) or 0.0)
        except Exception:
            dur = 0.0
        scenes.append(
            RenderSceneInput(
                scene_index=i,
                visual_asset_hash=asset_hash(clip),
                duration_sec=dur,
            )
        )
    return RenderAssemblyManifest(
        job_id=job_id,
        script_fingerprint=script_fingerprint,
        scenes=scenes,
        logo_hash=asset_hash(logo_path),
        intro_hash=asset_hash(intro_path),
        subtitle_hash=asset_hash(subtitle_path),
        video_type=video_type,
        size=size,
        max_seconds=max_seconds,
    )


def load_script_fingerprint(work_dir: Path) -> str:
    work = Path(work_dir)
    prov_dir = work / "script_provenance"
    if prov_dir.is_dir():
        files = sorted(prov_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            try:
                import json

                data = json.loads(files[0].read_text(encoding="utf-8"))
                return str(data.get("fingerprint") or "")[:64]
            except Exception:
                pass
    plan = work / "director_plan.json"
    if plan.is_file():
        return hash_artifact(str(plan))[:32]
    return ""


# Backward-compatible alias
RenderManifest = RenderAssemblyManifest
